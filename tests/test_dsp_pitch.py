"""Tests für die Tonhöhen-Anpassung (WSOLA + Neubetastung)."""

from __future__ import annotations

import math
import time

import pytest

from app import dsp, voice_profile


def _sine(freq: float, rate: int, seconds: float) -> list:
    return [0.45 * math.sin(2 * math.pi * freq * t / rate) for t in range(int(rate * seconds))]


def _peak_freq(samples, rate: int) -> float:
    numpy = pytest.importorskip("numpy")
    data = numpy.asarray(samples[rate // 4: rate // 4 + rate * 2], dtype=float)
    window = numpy.hanning(len(data))
    spectrum = numpy.abs(numpy.fft.rfft(data * window))
    freqs = numpy.fft.rfftfreq(len(data), 1.0 / rate)
    return float(freqs[int(numpy.argmax(spectrum))])


@pytest.mark.parametrize("factor", [0.7, 0.85, 1.2, 1.4])
def test_time_stretch_keeps_pitch(factor: float):
    rate = 22050
    samples = _sine(110.0, rate, 3.0)
    stretched = dsp.time_stretch(samples, factor)
    assert len(stretched) == pytest.approx(len(samples) * factor, rel=0.01)
    assert _peak_freq(stretched, rate) == pytest.approx(110.0, abs=3.0)


@pytest.mark.parametrize("semitones", [-5, -3, -1.5, 0, 1.5, 3, 5])
def test_pitch_shift_matches_target(semitones: float):
    rate = 22050
    base = 110.0
    samples = _sine(base, rate, 3.0)
    shifted = dsp.pitch_shift(samples, semitones, rate)
    assert len(shifted) == len(samples)
    expected = base * 2 ** (semitones / 12)
    assert _peak_freq(shifted, rate) == pytest.approx(expected, rel=0.02)


def test_pitch_shift_is_clamped():
    rate = 16000
    samples = _sine(120.0, rate, 1.0)
    extreme = dsp.pitch_shift(samples, 24, rate)
    assert len(extreme) == len(samples)
    clamped = dsp.pitch_shift(samples, 6, rate)
    assert extreme == clamped


def test_semitones_between():
    assert dsp.semitones_between(110.0, 220.0) == pytest.approx(12.0, abs=0.01)
    assert dsp.semitones_between(0, 120) == 0.0
    assert dsp.semitones_between(123.0, 123.0) == pytest.approx(0.0, abs=1e-6)


def test_pitch_shift_is_fast_enough():
    rate = 22050
    samples = _sine(120.0, rate, 20.0)
    started = time.time()
    dsp.pitch_shift(samples, 2, rate)
    # 20 s Audio müssen in deutlich weniger als der Sprechdauer verschoben werden
    assert time.time() - started < 8.0


def test_profile_matches_shifted_voice():
    """Nach der Anpassung liegt die gemessene Sprechlage beim Ziel."""
    rate = 22050
    samples = _sine(95.0, rate, 4.0)
    target = 123.0
    shift = dsp.semitones_between(95.0, target)
    shifted = dsp.pitch_shift(samples, shift, rate)
    profile = voice_profile.analyze_reference(shifted, rate)
    assert profile["median_f0_hz"] == pytest.approx(target, rel=0.05)
