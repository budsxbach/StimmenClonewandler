"""Tests für den Stimmen-Helfer (ohne Internet: Netzwerk wird ersetzt)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import hardware, voice_setup

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


# ---------------------------------------------------------------------------
# XTTS-v2: Modell-Download (Netzwerk wird ersetzt)
# ---------------------------------------------------------------------------

SMALL_XTTS_FILES = {
    "model.pth": {"size": 8, "sha256": None},
    "config.json": {"size": 2, "sha256": None},
    "vocab.json": {"size": 3, "sha256": None},
    "speakers_xtts.pth": {"size": 4, "sha256": None},
    "mel_stats.pth": {"size": 2, "sha256": None},
}


@pytest.fixture()
def small_xtts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(voice_setup, "XTTS_FILES", SMALL_XTTS_FILES)
    monkeypatch.setattr(
        voice_setup, "XTTS_REQUIRED_FILES", tuple(SMALL_XTTS_FILES)
    )
    monkeypatch.setattr(voice_setup, "XTTS_MIN_FREE_MB", 0)
    return tmp_path / "xtts"


def _fake_fetcher(contents: dict):
    calls = []

    def fetcher(url, dest, expected_size=None, on_progress=None):
        calls.append(url)
        dest.write_bytes(contents[dest.name])
        if on_progress:
            on_progress(len(contents[dest.name]), len(contents[dest.name]))

    fetcher.calls = calls
    return fetcher


def test_xtts_status_reports_all_missing_files(tmp_path: Path):
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    status = voice_setup.xtts_status(tmp_path)
    assert status["present"] is False
    assert len(status["missing"]) == len(voice_setup.XTTS_FILES)
    assert status["required_mb"] > 1700  # ~1,8 GB laut Modellablage
    assert "Coqui" in status["license"]


def test_xtts_download_writes_all_files(small_xtts, monkeypatch):
    contents = {name: b"x" * info["size"] for name, info in SMALL_XTTS_FILES.items()}
    fetcher = _fake_fetcher(contents)
    result = voice_setup.download_xtts(small_xtts, fetcher=fetcher)

    assert result["present"] is True
    assert sorted(result["downloaded"]) == sorted(SMALL_XTTS_FILES)
    assert len(fetcher.calls) == len(SMALL_XTTS_FILES)
    assert all(url.startswith("https://huggingface.co/tts-hub/XTTS-v2/") for url in fetcher.calls)
    for name, info in SMALL_XTTS_FILES.items():
        assert (small_xtts / name).stat().st_size == info["size"]


def test_xtts_download_reuses_existing_files(small_xtts):
    small_xtts.mkdir(parents=True)
    (small_xtts / "model.pth").write_bytes(b"y" * 8)
    contents = {
        name: b"x" * info["size"]
        for name, info in SMALL_XTTS_FILES.items()
        if name != "model.pth"
    }
    fetcher = _fake_fetcher(contents)
    result = voice_setup.download_xtts(small_xtts, fetcher=fetcher)

    assert result["skipped"] == ["model.pth"]
    assert "model.pth" not in [url.rsplit("/", 1)[-1] for url in fetcher.calls]


def test_xtts_download_needs_free_disk_space(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(voice_setup, "XTTS_MIN_FREE_MB", 10 ** 9)
    with pytest.raises(RuntimeError) as error:
        voice_setup.download_xtts(tmp_path, fetcher=_fake_fetcher({}))
    assert "Platz" in str(error.value)


def test_xtts_download_reports_connection_error(small_xtts):
    from urllib.error import URLError

    def failing(url, dest, expected_size=None, on_progress=None):
        raise URLError("kein Netz")

    with pytest.raises(ConnectionError) as error:
        voice_setup.download_xtts(small_xtts, fetcher=failing)
    assert "Internetverbindung" in str(error.value)


def test_xtts_download_deletes_file_with_wrong_checksum(small_xtts):
    files = dict(SMALL_XTTS_FILES)
    files["model.pth"] = {"size": 8, "sha256": "0" * 64}
    voice_setup.XTTS_FILES = files

    contents = {name: b"x" * info["size"] for name, info in files.items()}
    with pytest.raises(RuntimeError) as error:
        voice_setup.download_xtts(small_xtts, fetcher=_fake_fetcher(contents))
    assert "Prüfsumme" in str(error.value)
    assert not (small_xtts / "model.pth").exists()


def test_cli_xtts_download_prints_next_steps(small_xtts, monkeypatch, capsys):
    contents = {name: b"x" * info["size"] for name, info in SMALL_XTTS_FILES.items()}
    monkeypatch.setattr(
        voice_setup, "download_xtts", lambda **kwargs: {
            "path": str(small_xtts),
            "total_mb": 1.0,
            "downloaded": ["model.pth"],
            "skipped": [],
            "present": True,
            "missing": [],
        }
    )
    code = voice_setup.main(["--xtts", "--yes"])
    out = capsys.readouterr().out
    assert code == 0
    assert "coqui-tts[cpu]" in out
    assert "Coqui Public Model License" in out
    assert "1,9" in out.replace("~1.9", "~1,9") or "MB" in out


def test_cli_xtts_without_confirmation_downloads_nothing(small_xtts, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *_: "nein")
    called = []
    monkeypatch.setattr(voice_setup, "download_xtts", lambda **kwargs: called.append(1))
    code = voice_setup.main(["--xtts"])
    assert code == 1
    assert called == []
    assert "Abgebrochen" in capsys.readouterr().out


def test_hardware_find_xtts_needs_every_model_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(hardware, "XTTS_DIR", tmp_path)
    assert hardware.find_xtts()["present"] is False

    for name in hardware.XTTS_REQUIRED_FILES[:-1]:
        (tmp_path / name).write_bytes(b"x")
    partial = hardware.find_xtts()
    assert partial["present"] is False
    assert partial["missing"] == [hardware.XTTS_REQUIRED_FILES[-1]]
    assert partial["any_files"] is True

    (tmp_path / hardware.XTTS_REQUIRED_FILES[-1]).write_bytes(b"x")
    assert hardware.find_xtts()["present"] is True


def test_status_mentions_installed_xtts_when_complete(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(hardware, "XTTS_DIR", tmp_path)
    monkeypatch.setattr(voice_setup, "XTTS_DIR", tmp_path)
    for name in hardware.XTTS_REQUIRED_FILES:
        (tmp_path / name).write_bytes(b"x" * 10)
    voice_setup._print_xtts_state()
    out = capsys.readouterr().out
    assert "vollständig vorhanden" in out
    assert "coqui-tts[cpu]" in out
