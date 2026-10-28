"""Digitale Signalverarbeitung für die Stimm-Anpassung.

Hier liegt die einzige Stelle, an der numpy verwendet wird (numpy ist ohnehin
über Piper installiert). Fällt numpy aus, greift eine einfache, langsamere
Ersatzlösung – die App bleibt in jedem Fall lauffähig.

Kernstück ist eine WSOLA-Zeitdehnung: Sie verändert die Länge eines Signals,
**ohne** die Tonhöhe zu verändern. Zusammen mit einer Abtastratenänderung ergibt
das eine echte Tonhöhenverschiebung (Pitch-Shift) bei gleichbleibender Dauer.
Damit lässt sich die Stimmlage der Modellstimme an die eigene Referenzaufnahme
annähern, ohne dass es „Chipmunk“ klingt.
"""

from __future__ import annotations

import math
from typing import List, Sequence

try:  # numpy kommt über piper-tts, ist aber optional
    import numpy as _np
except Exception:  # pragma: no cover - Umgebung ohne numpy
    _np = None


def numpy_available() -> bool:
    return _np is not None


# ---------------------------------------------------------------------------
# WSOLA
# ---------------------------------------------------------------------------

def _wsola(x: "_np.ndarray", factor: float, frame: int = 1024, tolerance: int = 96) -> "_np.ndarray":
    hop_s = frame // 2
    hop_a = max(1, int(round(hop_s / factor)))
    out_len = int(round(len(x) * factor)) + frame
    out = _np.zeros(out_len, dtype=_np.float64)
    window = 0.5 - 0.5 * _np.cos(2.0 * _np.pi * _np.arange(frame) / frame)

    limit = len(x) - frame
    if limit <= 0:
        return x.copy()

    prev_pos = 0
    out_pos = 0
    k = 0
    while out_pos + frame <= out_len:
        nominal = min(limit, int(round(k * hop_a)))
        position = nominal
        if k > 0:
            # Natürliche Fortsetzung des vorherigen Rahmens im Original
            nat_start = prev_pos + hop_s
            nat_end = nat_start + hop_s
            if nat_end <= len(x):
                reference = x[nat_start:nat_end]
                lo = max(0, nominal - tolerance)
                hi = min(limit, nominal + tolerance)
                if hi > lo:
                    window_view = _np.lib.stride_tricks.sliding_window_view(
                        x[lo:hi + hop_s], hop_s
                    )
                    scores = window_view @ reference
                    position = lo + int(_np.argmax(scores))
        segment = x[position:position + frame]
        out[out_pos:out_pos + frame] += segment * window
        prev_pos = position
        out_pos += hop_s
        k += 1
        if position >= limit:
            break

    # Gewichtung der Überlappung normalisieren (Hann-Fenster, 50 % Überlappung
    # ergibt überall exakt 1.0 – kleine Rundungsreste werden korrigiert)
    total = _np.zeros(out_len, dtype=_np.float64)
    pos = 0
    while pos + frame <= out_len:
        total[pos:pos + frame] += window
        pos += hop_s
    total[total < 1e-6] = 1.0
    out = out / total

    return out[: int(round(len(x) * factor))]


def _wsola_fallback(samples: Sequence[float], factor: float) -> List[float]:
    """Einfache Overlap-Add-Dehnung ohne numpy (nur als Notlösung)."""
    length = len(samples)
    frame = 512
    if length < frame * 2:
        return list(samples)
    hop_in = max(1, int(round(frame / 2 / max(factor, 0.01))))
    hop_out = frame // 2
    out_len = int(round(length * factor)) + frame
    out = [0.0] * out_len
    pos = 0
    out_pos = 0
    while pos + frame <= length and out_pos + frame <= out_len:
        for i in range(frame):
            w = 0.5 - 0.5 * math.cos(2.0 * math.pi * i / frame)
            out[out_pos + i] += samples[pos + i] * w
        pos += hop_in
        out_pos += hop_out
    return out[: int(round(length * factor))]


def time_stretch(samples: Sequence[float], factor: float) -> List[float]:
    """Länge mit dem Faktor `factor` ändern, Tonhöhe bleibt erhalten."""
    if not samples or abs(factor - 1.0) < 1e-3:
        return list(samples)
    factor = max(0.4, min(2.5, float(factor)))
    if _np is None:
        return _wsola_fallback(samples, factor)
    data = _np.asarray(samples, dtype=_np.float64)
    return _wsola(data, factor).tolist()


def _resample_numpy(samples: Sequence[float], src_rate: int, dst_rate: int) -> List[float]:
    if src_rate == dst_rate or not samples:
        return list(samples)
    data = _np.asarray(samples, dtype=_np.float64)
    ratio = dst_rate / float(src_rate)
    if ratio < 1.0:
        # Tiefpass vor dem Heruntertasten (gleitender Mittelwert)
        window = max(2, int(round(1.0 / ratio)))
        if window >= 3:
            kernel = _np.ones(window) / window
            data = _np.convolve(data, kernel, mode="same")
    out_len = max(1, int(round(len(data) * ratio)))
    positions = _np.arange(out_len) / ratio
    left = _np.floor(positions).astype(_np.int64)
    left = _np.clip(left, 0, len(data) - 1)
    right = _np.clip(left + 1, 0, len(data) - 1)
    frac = positions - left
    return (data[left] * (1.0 - frac) + data[right] * frac).tolist()


def resample_fast(samples: Sequence[float], src_rate: int, dst_rate: int) -> List[float]:
    """Abtastrate ändern (numpy, sonst Standard-Python)."""
    if src_rate == dst_rate or not samples:
        return list(samples)
    if _np is None:
        from .wav_io import resample

        return resample(samples, src_rate, dst_rate)
    return _resample_numpy(samples, src_rate, dst_rate)


def pitch_shift(samples: Sequence[float], semitones: float, rate: int) -> List[float]:
    """Tonhöhe um `semitones` Halbtöne verschieben, Dauer bleibt gleich."""
    try:
        shift = float(semitones)
    except (TypeError, ValueError):
        return list(samples)
    if not samples or abs(shift) < 0.05:
        return list(samples)
    shift = max(-6.0, min(6.0, shift))
    ratio = 2.0 ** (shift / 12.0)

    if _np is None:
        # Notlösung ohne numpy: Abtastrate ändern (Tempo ändert sich mit)
        from .wav_io import resample

        return resample(samples, rate, max(1000, int(round(rate / ratio))))

    stretched = time_stretch(samples, ratio)
    shifted = resample_fast(stretched, rate, max(1000, int(round(rate / ratio))))
    # Länge exakt auf das Original bringen
    if len(shifted) > len(samples):
        return shifted[: len(samples)]
    if len(shifted) < len(samples) and shifted:
        return shifted + [shifted[-1]] * (len(samples) - len(shifted))
    return shifted


def semitones_between(source_hz: float, target_hz: float) -> float:
    """Abstand zweier Frequenzen in Halbtönen."""
    if not source_hz or not target_hz or source_hz <= 0 or target_hz <= 0:
        return 0.0
    return 12.0 * math.log2(target_hz / source_hz)
