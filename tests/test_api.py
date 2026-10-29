"""Tests für die lokale API (ohne Sprachmodell)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from app import tts


def test_status_reports_honestly(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert "Es erfolgt kein Upload ins Internet" in payload["privacy_notice"]
    assert payload["local_only"] is True
    assert "ready" in payload
    assert isinstance(payload["messages"], list)
    # Ohne lokales Modell darf die App nicht behaupten, sie sei bereit
    if payload["german_voice_count"] == 0:
        assert payload["ready"] is False


def test_health(client):
    assert client.get("/api/health").get_json()["ok"] is True


def test_index_and_static(client):
    page = client.get("/")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "StimmenClonewandler" in body
    assert "kein Upload ins Internet" in body
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_upload_and_delete_recording(client, speech_wav: Path):
    with speech_wav.open("rb") as handle:
        data = {"file": (io.BytesIO(handle.read()), "sprache.wav")}
        response = client.post("/api/recordings/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 200, response.get_data(as_text=True)
    record = response.get_json()["recording"]
    assert record["info"]["sample_rate"] == 44100

    listing = client.get("/api/recordings").get_json()
    assert listing["count"] >= 1

    audio = client.get(f"/api/recordings/{record['id']}/audio")
    assert audio.status_code == 200
    assert audio.mimetype == "audio/wav"

    master = client.post(f"/api/recordings/{record['id']}/master", json={"cleanup": True})
    assert master.status_code == 200
    assert master.get_json()["usable_as_reference"] is True

    reference = client.get("/api/master/reference")
    assert reference.status_code == 200

    assert client.delete(f"/api/recordings/{record['id']}").status_code == 200
    assert client.get(f"/api/recordings/{record['id']}/audio").status_code == 404


def test_upload_rejects_non_wav(client):
    data = {"file": (io.BytesIO(b"kein audio"), "notiz.txt")}
    response = client.post("/api/recordings/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "WAV" in response.get_json()["error"]


def test_upload_rejects_broken_wav(client):
    data = {"file": (io.BytesIO(b"RIFFxxxxWAVEkaputt"), "kaputt.wav")}
    response = client.post("/api/recordings/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_tts_without_model_is_refused(client):
    payload = {"text": "Guten Tag.", "engine": "piper", "preset": "weise"}
    response = client.post("/api/tts", json=payload)
    if client.get("/api/voices").get_json()["voices"]:
        pytest.skip("Es liegt ein Testmodell vor – Ablehnung nicht prüfbar.")
    assert response.status_code == 409
    body = response.get_json()
    assert body["ok"] is False
    assert "kein" in body["error"].lower() or "nicht" in body["error"].lower()


def test_tts_rejects_empty_text(client):
    response = client.post("/api/tts", json={"text": "   "})
    assert response.status_code == 400


def test_tts_rejects_long_text(client):
    response = client.post("/api/tts", json={"text": "a" * 5000})
    assert response.status_code == 400
    assert "zu lang" in response.get_json()["error"]


def test_xtts_capability_is_honest(client):
    payload = client.get("/api/capabilities").get_json()
    assert payload["ok"] is True
    assert "missing" in payload["xtts"]
    if not payload["xtts"]["available"]:
        assert payload["clone_possible"] is False
        assert payload["xtts"]["missing"]


def test_xtts_without_requirements_is_refused(client):
    response = client.post("/api/tts", json={"text": "Hallo", "engine": "xtts"})
    capabilities = client.get("/api/capabilities").get_json()
    if capabilities["xtts"]["available"]:
        pytest.skip("XTTS ist vorhanden.")
    assert response.status_code == 409
    assert response.get_json()["missing"]


def test_job_not_found(client):
    assert client.get("/api/jobs/gibtsnicht").status_code == 404


def test_save_result_requires_finished_job(client):
    response = client.post("/api/results", json={"job_id": "unbekannt"})
    assert response.status_code == 400


def test_results_listing(client):
    payload = client.get("/api/results").get_json()
    assert payload["ok"] is True
    assert isinstance(payload["results"], list)


def test_presets_and_preset_content():
    presets = tts.preset_list()
    ids = {preset["id"] for preset in presets}
    assert "weise" in ids
    assert any(preset["default"] for preset in presets)
    weise = tts.PRESET_BY_ID["weise"]
    assert weise.length_scale > 1.0, "Der empfohlene Stil spricht ruhiger als normal"
    assert weise.low_shelf_db > 0, "Der empfohlene Stil hat mehr Tiefe"


def test_split_text():
    chunks = tts.split_text("Erster Satz. Zweiter Satz! Dritter Satz?")
    assert len(chunks) >= 1
    assert all(chunk.strip() for chunk in chunks)


def test_unknown_route_is_json_404(client):
    response = client.get("/api/gibtsnicht")
    assert response.status_code == 404
    assert response.get_json()["ok"] is False


def test_status_reports_whether_xtts_can_really_run(client):
    """Die Oberfläche muss zwischen „Dateien liegen da“ und „läuft“ unterscheiden.

    Vorher lieferte /api/status nur den Dateibefund (hardware.find_xtts), die
    Oberfläche fragte aber `available` ab – und zeigte deshalb immer
    „nicht ausführbar“, selbst wenn PyTorch und Modell vorhanden waren.
    """
    payload = client.get("/api/status").get_json()
    xtts = payload["xtts"]
    assert "available" in xtts
    assert isinstance(xtts["available"], bool)
    assert "present" in xtts
    assert "missing" in xtts
    assert "honest_note" in xtts
    # Ohne PyTorch ist die Stimmkopie ehrlich als nicht verfügbar gemeldet.
    assert xtts["available"] is False
    assert any("coqui-tts[cpu]" in item for item in xtts["missing"])
