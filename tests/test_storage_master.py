"""Tests für lokale Ablage und Master-Aufbereitung (ohne Sprachmodell)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import master, storage
from app.wav_io import read_wav


@pytest.fixture(autouse=True)
def clean_storage():
    # Vor jedem Test die lokale Testablage leeren
    yield
    for record in storage.list_recordings():
        storage.delete_recording(record["id"])
    for result in storage.list_results():
        storage.delete_result(result["id"])
    storage.clear_master()


def test_import_keeps_original_untouched(speech_wav: Path) -> None:
    before = speech_wav.read_bytes()
    record = storage.save_recording(speech_wav, display_name="Test", kind="import")

    assert (speech_wav).read_bytes() == before, "Die Originaldatei darf nicht verändert werden"
    copied = storage.recording_path(record["id"])
    assert copied is not None
    assert copied.read_bytes() == before
    assert record["info"]["sample_rate"] == 44100
    assert record["analysis"]["snr_db"] is not None


def test_list_and_delete(speech_wav: Path) -> None:
    record = storage.save_recording(speech_wav, display_name="Löschtest")
    assert any(item["id"] == record["id"] for item in storage.list_recordings())
    assert storage.delete_recording(record["id"]) is True
    assert storage.recording_path(record["id"]) is None
    assert storage.get_recording(record["id"]) is None


def test_master_reference_is_prepared(speech_wav: Path) -> None:
    record = storage.save_recording(speech_wav, display_name="Referenz")
    result = master.build_reference(record["id"])

    reference = storage.reference_path(record["id"])
    assert reference is not None and reference.exists()
    assert result["usable_as_reference"] is True
    assert result["sample_rate"] == master.XTTS_SAMPLE_RATE
    assert result["duration_s"] <= 30.5

    rate, data = read_wav(reference)
    assert rate == master.XTTS_SAMPLE_RATE
    assert len(data) == 1

    overview = master.master_overview()
    assert overview["present"] is True
    assert overview["recording"]["id"] == record["id"]


def test_short_reference_is_flagged(short_wav: Path) -> None:
    record = storage.save_recording(short_wav, display_name="Kurz")
    result = master.build_reference(record["id"])
    # 2 s sind zu kurz – die App sagt das ehrlich
    assert result["usable_as_reference"] is False
    assert any(note["severity"] == "error" for note in result["notes"])


def test_result_save_and_delete(speech_wav: Path) -> None:
    record = storage.save_result(
        speech_wav,
        name="Sprachausgabe",
        meta={"engine": "piper", "preset": "weise"},
    )
    assert storage.result_path(record["id"]) is not None
    assert storage.list_results()[0]["name"] == "Sprachausgabe"
    assert storage.delete_result(record["id"]) is True
    assert storage.result_path(record["id"]) is None


def test_invalid_ids_are_rejected() -> None:
    assert storage.recording_path("../etc/passwd") is None
    assert storage.delete_recording("../../x") is False
    assert storage.result_path("a/b") is None


def test_voice_profile_and_suggestion(speech_wav: Path) -> None:
    record = storage.save_recording(speech_wav, display_name="Profil")
    result = master.build_reference(record["id"])
    profile = result["voice_profile"]
    assert profile["estimated"] is True
    # Die synthetische Testdatei hat einen Grundton um 110 Hz
    assert profile["median_f0_hz"] is not None
    assert 90 <= profile["median_f0_hz"] <= 130
    assert profile["suggested_preset"] in {"weise", "mystisch", "warm", "ruhig", "neutral"}
    assert 0.5 <= profile["suggested_intensity"] <= 1.2

    overview = master.master_overview()
    assert overview["reference"]["voice_profile"]["median_f0_hz"] is not None


def test_reference_uses_best_window(tmp_path) -> None:
    """Aus einer langen Datei wird eine zusammenhängende, laute Passage gewählt."""
    from conftest import make_speechlike_wav

    long_wav = make_speechlike_wav(tmp_path / "lang.wav", seconds=60.0)
    record = storage.save_recording(long_wav, display_name="Lang")
    result = master.build_reference(record["id"])
    assert result["duration_s"] <= 30.5
    assert result["usable_as_reference"] is True
    assert result["analysis"]["snr_db"] > 10
