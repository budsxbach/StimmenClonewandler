"""End-to-End-Test der Sprachausgabe-Kette mit einer *Teststimme*.

Die Teststimme (siehe test_voice_factory.py) ist kein echtes Sprachmodell,
sondern ein kleiner ONNX-Graph, der einen Ton erzeugt. Damit lässt sich die
komplette technische Kette prüfen: Phonemisierung über espeak, ONNX-Sitzung,
Zusammensetzen der Abschnitte, Klangformung, Fortschrittsmeldungen,
WAV-Ausgabe und Speichern der Ergebnisse.

Ist das optionale Paket `onnx` nicht installiert, werden diese Tests
übersprungen.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

onnx = pytest.importorskip("onnx", reason="onnx wird nur für die Teststimme benötigt")

from app import hardware, server, tts  # noqa: E402

from test_voice_factory import build_test_voice  # noqa: E402


@pytest.fixture(scope="module")
def test_voice() -> Path:
    path = build_test_voice(hardware.PIPER_DIR)
    server.STATUS_CACHE["value"] = None
    hardware._IMPORT_CACHE.clear()
    yield path
    tts.unload_voices()
    for suffix in ("", ".json"):
        target = Path(str(path) + suffix)
        if target.exists():
            target.unlink()
    server.STATUS_CACHE["value"] = None


def _wait_for_job(client, job_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/jobs/{job_id}").get_json()
        job = payload["job"]
        if job["status"] in ("fertig", "fehler", "abgebrochen"):
            return job
        time.sleep(0.1)
    raise AssertionError("Der Auftrag wurde nicht rechtzeitig fertig.")


def test_status_ready_with_voice(client, test_voice: Path):
    payload = client.get("/api/status").get_json()
    assert payload["german_voice_count"] >= 1
    assert payload["ready"] is True
    names = [voice["name"] for voice in payload["voices"]]
    assert test_voice.stem in names


def test_synthesis_end_to_end(client, test_voice: Path):
    response = client.post("/api/tts", json={
        "text": "Guten Tag. Dies ist ein Test der lokalen Sprachausgabe.",
        "engine": "piper",
        "preset": "weise",
        "intensity": 1.0,
        "tempo": 1.0,
        "slow_mode": True,
        "threads": 1,
    })
    assert response.status_code == 200, response.get_data(as_text=True)
    job = _wait_for_job(client, response.get_json()["job"]["id"])
    assert job["status"] == "fertig", job.get("error")
    assert job["progress"] == 100
    assert job["result"]["engine"] == "piper"
    assert job["result"]["duration_s"] > 0.5
    assert job["result"]["is_clone"] is False

    audio = client.get(f"/api/jobs/{job['id']}/audio")
    assert audio.status_code == 200
    assert audio.data[:4] == b"RIFF"

    saved = client.post("/api/results", json={"job_id": job["id"], "name": "Testausgabe"})
    assert saved.status_code == 200, saved.get_data(as_text=True)
    record = saved.get_json()["result"]
    assert record["name"] == "Testausgabe"

    listing = client.get("/api/results").get_json()
    assert any(item["id"] == record["id"] for item in listing["results"])

    result_audio = client.get(f"/api/results/{record['id']}/audio")
    assert result_audio.status_code == 200

    download = client.get(f"/api/results/{record['id']}/download")
    assert download.status_code == 200
    assert "attachment" in download.headers.get("Content-Disposition", "")

    assert client.delete(f"/api/results/{record['id']}").status_code == 200
    assert client.get(f"/api/results/{record['id']}/audio").status_code == 404


def test_slow_mode_still_produces_audio(client, test_voice: Path):
    response = client.post("/api/tts", json={
        "text": "Ein kurzer Satz.",
        "preset": "ruhig",
        "slow_mode": True,
        "threads": 1,
        "tempo": 0.9,
    })
    job = _wait_for_job(client, response.get_json()["job"]["id"])
    assert job["status"] == "fertig", job.get("error")
    assert job["result"]["slow_mode"] is True


def test_unknown_voice_reports_error(client, test_voice: Path):
    response = client.post("/api/tts", json={
        "text": "Hallo.",
        "voice": "gibt-es-nicht",
        "preset": "weise",
    })
    job = _wait_for_job(client, response.get_json()["job"]["id"])
    assert job["status"] == "fehler"
    assert "nicht gefunden" in job["error"]
    # Es darf keine Ergebnisdatei entstanden sein
    assert client.get(f"/api/jobs/{job['id']}/audio").status_code == 404


def test_benchmark_returns_realtime_factor(client, test_voice: Path):
    response = client.post("/api/benchmark", json={"slow_mode": True, "threads": 1})
    assert response.status_code == 200
    job = _wait_for_job(client, response.get_json()["job"]["id"])
    assert job["status"] == "fertig", job.get("error")
    assert job["result"]["realtime_factor"] is not None


def test_presets_change_output_length(client, test_voice: Path):
    """Der Stil „weise“ spricht langsamer und erzeugt mehr Audio als „neutral“."""
    lengths = {}
    for preset in ("neutral", "weise"):
        response = client.post("/api/tts", json={
            "text": "Dieser Satz hat eine feste Länge.",
            "preset": preset,
            "slow_mode": True,
            "threads": 1,
        })
        job = _wait_for_job(client, response.get_json()["job"]["id"])
        assert job["status"] == "fertig", job.get("error")
        lengths[preset] = job["result"]["duration_s"]
    assert lengths["weise"] > lengths["neutral"]


def _prepare_reference(tmp_path, seconds: float = 12.0) -> str:
    """Legt eine synthetische Referenzaufnahme als Master an."""
    from conftest import make_speechlike_wav
    from app import storage

    wav = make_speechlike_wav(tmp_path / "referenz.wav", seconds=seconds)
    record = storage.save_recording(wav, display_name="Test-Ausgangsstimme")
    return record["id"]


def test_base_voice_endpoint(client, test_voice: Path, tmp_path):
    from app import master, storage

    rec_id = _prepare_reference(tmp_path)
    master.build_reference(rec_id)
    payload = client.get("/api/master").get_json()
    assert payload["present"] is True
    base = payload["base_voice"]
    assert base["present"] is True
    assert base["profile"]["median_f0_hz"] is not None
    storage.delete_recording(rec_id)


def test_pitch_adaptation_to_base_voice(client, test_voice: Path, tmp_path):
    from app import master, storage

    rec_id = _prepare_reference(tmp_path)
    master.build_reference(rec_id)
    base = master.base_voice()
    target = base["profile"]["median_f0_hz"]

    response = client.post("/api/tts", json={
        "text": "Die Stimmlage wird angepasst.",
        "preset": "neutral",
        "adapt_pitch": True,
        "slow_mode": True,
        "threads": 1,
    })
    job = _wait_for_job(client, response.get_json()["job"]["id"])
    assert job["status"] == "fertig", job.get("error")
    pitch = job["result"]["pitch"]
    assert pitch["reference_f0_hz"] == pytest.approx(target, rel=0.01)
    assert pitch["model_f0_hz"] is not None
    assert abs(pitch["applied_semitones"]) <= 4.01
    # Die Anpassung wird ehrlich benannt
    assert job["result"]["is_clone"] is False
    storage.delete_recording(rec_id)


def test_adapt_pitch_without_base_voice_is_reported(client, test_voice: Path):
    from app import master, storage

    # Master entfernen, damit keine Ausgangsstimme vorliegt
    current = storage.get_master()
    if current:
        storage.delete_recording(current["id"])
    master_id = storage.get_master_id()
    assert master_id is None

    response = client.post("/api/tts", json={
        "text": "Ohne Ausgangsstimme.",
        "preset": "neutral",
        "adapt_pitch": True,
        "slow_mode": True,
        "threads": 1,
    })
    job = _wait_for_job(client, response.get_json()["job"]["id"])
    assert job["status"] == "fertig", job.get("error")
    pitch = job["result"]["pitch"]
    assert pitch["adapted"] is False
    assert pitch["reason"]
