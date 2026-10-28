"""Testkonfiguration.

Wichtig: Die Tests arbeiten in einem temporären Datenordner, damit niemals
echte Aufnahmen, Modelle oder Ergebnisse im Projektordner verändert werden.
Die Umgebungsvariable SCW_DATA_DIR wird gesetzt, *bevor* das App-Paket
importiert wird.
"""

from __future__ import annotations

import math
import os
import random
import tempfile
import wave
from pathlib import Path

import pytest

TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="scw-test-"))
os.environ["SCW_DATA_DIR"] = str(TEST_DATA_DIR)


def make_speechlike_wav(
    path: Path,
    *,
    seconds: float = 8.0,
    rate: int = 44100,
    channels: int = 1,
    noise_level: float = 0.002,
    gain: float = 0.45,
    silence_lead: float = 0.4,
    clip: bool = False,
) -> Path:
    """Erzeugt eine synthetische, sprachähnliche WAV-Datei (kein echtes Audio)."""
    random.seed(42)
    frames = int(seconds * rate)
    samples = []
    for i in range(frames):
        t = i / rate
        if t < silence_lead or t > seconds - 0.3:
            value = 0.0
        else:
            # Grundton ~110 Hz mit Obertönen, in Silben unterteilt
            syllable = 0.55 + 0.45 * math.sin(2 * math.pi * 2.2 * t)
            envelope = max(0.0, math.sin(math.pi * ((t * 2.4) % 1.0)) ** 0.5) * syllable
            value = envelope * (
                0.6 * math.sin(2 * math.pi * 110.0 * t)
                + 0.25 * math.sin(2 * math.pi * 220.0 * t)
                + 0.1 * math.sin(2 * math.pi * 330.0 * t)
            )
        value *= gain
        value += random.uniform(-noise_level, noise_level)
        if clip:
            value = 1.0 if value > 0 else -1.0
        samples.append(max(-1.0, min(1.0, value)))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        if channels == 1:
            data = samples
        else:
            data = [value for sample in samples for value in (sample, sample)]
        handle.writeframes(
            b"".join(int(round(value * 32767)).to_bytes(2, "little", signed=True) for value in data)
        )
    return path


@pytest.fixture()
def speech_wav(tmp_path: Path) -> Path:
    return make_speechlike_wav(tmp_path / "sprache.wav")


@pytest.fixture()
def short_wav(tmp_path: Path) -> Path:
    return make_speechlike_wav(tmp_path / "kurz.wav", seconds=2.0)


@pytest.fixture()
def stereo_wav(tmp_path: Path) -> Path:
    return make_speechlike_wav(tmp_path / "stereo.wav", channels=2, rate=48000)


@pytest.fixture()
def clipped_wav(tmp_path: Path) -> Path:
    return make_speechlike_wav(tmp_path / "uebersteuert.wav", gain=1.4, clip=True)


@pytest.fixture()
def client():
    from app.server import app

    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client
