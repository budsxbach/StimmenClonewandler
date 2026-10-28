"""Tests für den Stimmen-Helfer (ohne Internet: Netzwerk wird ersetzt)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import voice_setup

SAMPLE_VOICES = {
    "de_DE-thorsten-medium": {
        "quality": "medium",
        "num_speakers": 1,
        "files": {
            "de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx": {"size_bytes": 63_200_000},
            "de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json": {"size_bytes": 3_000},
        },
    },
    "de_DE-eva_k-x_low": {
        "quality": "x_low",
        "files": {"x.onnx": {"size_bytes": 20_000_000}},
    },
    "de_DE-kerstin-low": {
        "quality": "low",
        "files": {"y.onnx": {"size_bytes": 30_000_000}},
    },
    "en_US-lessac-medium": {
        "quality": "medium",
        "files": {"z.onnx": {"size_bytes": 61_000_000}},
    },
}


def test_only_german_voices_are_listed():
    voices = voice_setup._german_voices(SAMPLE_VOICES)
    names = [voice["name"] for voice in voices]
    assert "en_US-lessac-medium" not in names
    assert len(names) == 3


def test_recommended_voice_comes_first():
    voices = voice_setup._german_voices(SAMPLE_VOICES)
    assert voices[0]["name"] == voice_setup.RECOMMENDED
    assert voices[0]["recommended"] is True


def test_size_is_summed_and_rounded():
    voices = {voice["name"]: voice for voice in voice_setup._german_voices(SAMPLE_VOICES)}
    assert voices["de_DE-thorsten-medium"]["size_mb"] == pytest.approx(60.3, abs=0.2)


def test_list_voices_uses_injected_source():
    voices = voice_setup.list_voices(lambda: SAMPLE_VOICES)
    assert len(voices) == 3


def test_network_error_is_reported_in_german():
    def broken():
        raise ConnectionError("Die Stimmenliste konnte nicht geladen werden. Bitte die Internetverbindung prüfen.")

    with pytest.raises(ConnectionError) as info:
        voice_setup.list_voices(broken)
    assert "Internetverbindung" in str(info.value)


def test_download_writes_into_model_dir(monkeypatch, tmp_path: Path):
    model_dir = tmp_path / "piper"
    monkeypatch.setattr(voice_setup, "PIPER_DIR", model_dir)

    def fake_downloader(name, target_dir, force_redownload=False):
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{name}.onnx").write_bytes(b"x" * 2048)
        (target / f"{name}.onnx.json").write_text("{}", encoding="utf-8")

    result = voice_setup.download_voice("de_DE-thorsten-medium", downloader=fake_downloader)
    assert result["model"] == "de_DE-thorsten-medium.onnx"
    assert (model_dir / "de_DE-thorsten-medium.onnx").exists()
    assert (model_dir / "de_DE-thorsten-medium.onnx.json").exists()


def test_invalid_voice_name_is_explained(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(voice_setup, "PIPER_DIR", tmp_path)

    def raising(name, target_dir, force_redownload=False):
        raise ValueError("bad pattern")

    with pytest.raises(ValueError) as info:
        voice_setup.download_voice("kaputter name", downloader=raising)
    assert "de_DE-" in str(info.value)


def test_incomplete_download_is_detected(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(voice_setup, "PIPER_DIR", tmp_path)

    def half(name, target_dir, force_redownload=False):
        (Path(target_dir) / f"{name}.onnx").write_bytes(b"x" * 100)

    with pytest.raises(RuntimeError) as info:
        voice_setup.download_voice("de_DE-test-medium", downloader=half)
    assert "unvollständig" in str(info.value)


def test_empty_name_is_rejected():
    with pytest.raises(ValueError):
        voice_setup.download_voice("  ")


def test_cli_installed_shows_hint(capsys):
    code = voice_setup.main(["--installed"])
    output = capsys.readouterr().out
    assert code == 0
    assert "Stimme" in output or "Stimmen" in output


def test_cli_lists_voices_without_network(monkeypatch, capsys):
    monkeypatch.setattr(voice_setup, "_fetch_voices", lambda: SAMPLE_VOICES)
    code = voice_setup.main(["--list"])
    output = capsys.readouterr().out
    assert code == 0
    assert "de_DE-thorsten-medium" in output
    assert "empfohlen" in output
