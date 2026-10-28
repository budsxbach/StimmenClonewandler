"""Tests für WAV-Verarbeitung und Audio-Analyse (ohne Sprachmodell)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from app import analysis
from app.wav_io import (
    WavError,
    amp_to_db,
    change_tempo,
    low_shelf,
    peak_normalize,
    read_wav,
    resample,
    soft_saturation,
    to_mono,
    trim_silence,
    wav_info,
    write_wav,
)

from conftest import make_speechlike_wav


def test_wav_roundtrip(tmp_path: Path) -> None:
    samples = [math.sin(2 * math.pi * 440 * i / 8000) * 0.5 for i in range(8000)]
    target = tmp_path / "ton.wav"
    write_wav(target, 8000, [samples])

    info = wav_info(target)
    assert info["sample_rate"] == 8000
    assert info["channels"] == 1
    assert info["bits"] == 16
    assert info["duration_s"] == pytest.approx(1.0, abs=0.01)

    rate, data = read_wav(target)
    assert rate == 8000
    assert len(data) == 1
    assert len(data[0]) == 8000
    # Amplitude bleibt (bis auf 16-Bit-Rundung) erhalten
    assert max(abs(value) for value in data[0]) == pytest.approx(0.5, abs=0.01)


def test_stereo_and_mono_mix(stereo_wav: Path) -> None:
    rate, data = read_wav(stereo_wav)
    assert rate == 48000
    assert len(data) == 2
    mono = to_mono(data)
    assert len(mono) == len(data[0])


def test_invalid_file_is_rejected(tmp_path: Path) -> None:
    broken = tmp_path / "kaputt.wav"
    broken.write_bytes(b"kein wav")
    with pytest.raises(WavError):
        read_wav(broken)
    with pytest.raises(WavError):
        wav_info(broken)


def test_trim_silence_removes_padding() -> None:
    rate = 16000
    samples = [0.0] * 8000 + [0.4] * 8000 + [0.0] * 8000
    trimmed = trim_silence(samples, rate)
    assert 0 < len(trimmed) < len(samples)
    assert len(trimmed) >= 8000


def test_normalize_and_tempo() -> None:
    samples = [0.1, -0.2, 0.3, -0.05] * 100
    normalized = peak_normalize(samples, -1.0)
    assert max(abs(value) for value in normalized) == pytest.approx(0.891, abs=0.01)

    slower = change_tempo(samples, 0.8)
    assert len(slower) > len(samples)
    faster = change_tempo(samples, 1.2)
    assert len(faster) < len(samples)


def test_resample_changes_length() -> None:
    samples = [math.sin(i / 10) for i in range(1000)]
    out = resample(samples, 44100, 24000)
    assert len(out) == pytest.approx(1000 * 24000 / 44100, abs=2)


def test_filters_and_saturation_stay_stable() -> None:
    samples = [0.3 * math.sin(i / 20) for i in range(4000)]
    filtered = low_shelf(samples, 16000, 200.0, 3.0)
    assert len(filtered) == len(samples)
    assert all(abs(value) < 5.0 for value in filtered)
    saturated = soft_saturation(samples, 1.5)
    assert max(abs(value) for value in saturated) <= 1.0


def test_amp_to_db() -> None:
    assert amp_to_db(1.0) == pytest.approx(0.0)
    assert amp_to_db(0.5) == pytest.approx(-6.02, abs=0.01)
    assert amp_to_db(0.0) <= -100


def test_analysis_detects_speech(speech_wav: Path) -> None:
    result = analysis.analyze(speech_wav)
    assert result["sample_rate"] == 44100
    assert result["channels"] == 1
    assert result["duration_s"] == pytest.approx(8.0, abs=0.1)
    assert result["peak_dbfs"] < 0
    assert result["snr_db"] > 10
    assert result["clipping"] is False
    assert result["loudness_label"] in {"sehr leise", "leise", "gut ausgesteuert", "sehr laut"}


def test_analysis_detects_clipping(clipped_wav: Path) -> None:
    result = analysis.analyze(clipped_wav)
    assert result["clipping"] is True
    assert result["clipped_samples"] > 0
    assert any("Übersteuerung" in warning["text"] for warning in result["warnings"])
    assert result["ok_for_model"] is False


def test_analysis_detects_noise(tmp_path: Path) -> None:
    noisy = make_speechlike_wav(tmp_path / "rausch.wav", noise_level=0.12)
    result = analysis.analyze(noisy)
    assert result["snr_db"] < 20
    assert any(
        "Hintergrundgeräusch" in warning["text"] for warning in result["warnings"]
    )


def test_analysis_of_silence(tmp_path: Path) -> None:
    silent = tmp_path / "still.wav"
    write_wav(silent, 16000, [[0.0] * 16000])
    result = analysis.analyze(silent)
    assert result["peak_dbfs"] <= -100
    assert result["loudness_label"] == "sehr leise"


def test_voice_profile_on_pure_tone() -> None:
    from app import voice_profile

    rate = 24000
    samples = [0.4 * math.sin(2 * math.pi * 200 * t / rate) for t in range(rate * 3)]
    profile = voice_profile.analyze_reference(samples, rate)
    assert profile["median_f0_hz"] == pytest.approx(200, abs=12)
    assert profile["pitch_class"] in {"mittelhoch", "hoch", "mittel"}
    assert profile["honest_note"]


def test_voice_profile_handles_silence() -> None:
    from app import voice_profile

    profile = voice_profile.analyze_reference([0.0] * 8000, 8000)
    assert profile["median_f0_hz"] is None
    assert profile["suggested_preset"] == "weise"
