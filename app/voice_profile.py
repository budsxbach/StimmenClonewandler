"""Grobe Stimmanalyse der Master-Aufnahme.

Diese Auswertung ist bewusst als **Schätzung** gekennzeichnet. Sie misst die
mittlere Sprech-Tonhöhe (Grundfrequenz), die Tonhöhen-Schwankung und einen
groben Helligkeitswert der Referenzaufnahme. Daraus entsteht ein Vorschlag für
den Stimm-Stil (Tempo, Tiefe, Intensität).

Das ersetzt **keine** Stimmkopie: Die Klangfarbe kommt weiterhin aus dem
lokalen Sprachmodell. Die App behauptet nie, hier werde die eigene Stimme
nachgebaut.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence

MIN_F0_HZ = 55.0
MAX_F0_HZ = 320.0
ANALYSIS_RATE = 8000          # Abtastrate für die Analyse (schnell, reicht für Tonhöhe)
FRAME_SECONDS = 0.045
HOP_SECONDS = 0.0225
MAX_FRAMES = 260
VOICING_THRESHOLD = 0.34


def _decimate(samples: Sequence[float], rate: int, target: int) -> tuple:
    """Einfache Tiefpass-Vorfilterung + Dezimierung (für die Analyse)."""
    if rate <= target:
        return list(samples), rate
    factor = max(1, int(round(rate / target)))
    # gleitender Mittelwert als Anti-Aliasing-Filter
    window = factor
    if window > 1:
        total = 0.0
        buffer: List[float] = []
        filtered: List[float] = []
        for value in samples:
            buffer.append(value)
            total += value
            if len(buffer) > window:
                total -= buffer.pop(0)
            filtered.append(total / len(buffer))
    else:
        filtered = list(samples)
    decimated = filtered[::factor]
    return decimated, rate / factor


def _frames(samples: Sequence[float], size: int, hop: int) -> List[Sequence[float]]:
    total = len(samples)
    frames: List[Sequence[float]] = []
    for start in range(0, max(1, total - size), hop):
        frames.append(samples[start:start + size])
        if len(frames) >= MAX_FRAMES:
            break
    return frames


def estimate_f0(samples: Sequence[float], rate: int) -> Dict[str, Any]:
    """Schätzt die Grundfrequenz über normalisierte Autokorrelation."""
    analysis_rate = int(ANALYSIS_RATE)
    work, work_rate = _decimate(samples, rate, analysis_rate)
    size = int(FRAME_SECONDS * work_rate)
    hop = int(HOP_SECONDS * work_rate)
    min_lag = max(2, int(work_rate / MAX_F0_HZ))
    max_lag = min(size - 2, int(work_rate / MIN_F0_HZ))
    if size <= min_lag * 3 or max_lag <= min_lag:
        return {"median_hz": None, "voiced_ratio": 0.0, "jitter": None, "analysis_rate": work_rate}

    values: List[float] = []
    voiced = 0
    analyzed = 0
    prev_lag = 0
    for frame in _frames(work, size, hop):
        analyzed += 1
        mean = sum(frame) / len(frame)
        centered = [value - mean for value in frame]
        energy0 = sum(value * value for value in centered)
        if energy0 <= 1e-6:
            continue
        scores: List[float] = [0.0] * (max_lag + 1)
        for lag in range(min_lag, max_lag + 1):
            limit = size - lag
            accum = 0.0
            for index in range(limit):
                accum += centered[index] * centered[index + lag]
            scores[lag] = accum / (energy0 * (limit / size))

        best_lag = max(range(min_lag, max_lag + 1), key=lambda lag: scores[lag])
        best_score = scores[best_lag]
        if best_score < VOICING_THRESHOLD:
            continue

        # Gegen Oktavfehler: den *kleinsten* deutlichen Peak nehmen
        chosen = best_lag
        for lag in range(min_lag + 1, max_lag):
            if (
                scores[lag] >= 0.88 * best_score
                and scores[lag] >= scores[lag - 1]
                and scores[lag] >= scores[lag + 1]
            ):
                chosen = lag
                break

        # Sprech-Kontinuität: Sprünge über eine Oktave gelten meist als Fehler
        if prev_lag:
            low = int(prev_lag * 0.8)
            high = int(prev_lag * 1.25)
            around = [
                lag for lag in range(max(min_lag, low), min(max_lag, high) + 1)
                if scores[lag] >= 0.75 * best_score
            ]
            if around:
                chosen = max(around, key=lambda lag: scores[lag])

        prev_lag = chosen
        values.append(work_rate / chosen)
        voiced += 1

    if not values:
        return {"median_hz": None, "voiced_ratio": 0.0, "jitter": None, "analysis_rate": work_rate}

    ordered = sorted(values)
    median = ordered[len(ordered) // 2]
    low = ordered[max(0, int(len(ordered) * 0.1))]
    high = ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))]
    # direkte Nachbar-Vergleiche: robuster als die Streuung über alle Abschnitte
    steps = [
        abs(12.0 * math.log2(values[index] / values[index - 1]))
        for index in range(1, len(values))
        if values[index] > 0 and values[index - 1] > 0
    ]
    local_jitter = None
    if steps:
        ordered_steps = sorted(steps)
        local_jitter = ordered_steps[len(ordered_steps) // 2]  # Median in Halbtönen
    return {
        "median_hz": round(median, 1),
        "low_hz": round(low, 1),
        "high_hz": round(high, 1),
        "voiced_ratio": round(voiced / max(1, analyzed), 2),
        "jitter": round(local_jitter, 2) if local_jitter is not None else None,
        "range_semitones": round(12.0 * math.log2(high / low), 1) if low > 0 else None,
        "analysis_rate": work_rate,
    }


def brightness(samples: Sequence[float], rate: int) -> float:
    """Grober Helligkeitswert über die mittlere Nulldurchgangsrate (in Hz)."""
    work, work_rate = _decimate(samples, rate, int(ANALYSIS_RATE))
    size = int(FRAME_SECONDS * work_rate)
    hop = int(HOP_SECONDS * work_rate)
    rates: List[float] = []
    for frame in _frames(work, size, hop):
        energy = sum(value * value for value in frame) / len(frame)
        if energy <= 1e-6:
            continue
        crossings = 0
        for index in range(1, len(frame)):
            if (frame[index - 1] < 0) != (frame[index] < 0):
                crossings += 1
        rates.append(crossings / (2 * len(frame) / work_rate))
    if not rates:
        return 0.0
    rates.sort()
    return round(rates[len(rates) // 2], 1)


def _pitch_class(median: float | None) -> str:
    if median is None:
        return "unbekannt"
    if median < 95:
        return "sehr tief"
    if median < 120:
        return "tief"
    if median < 155:
        return "mittel"
    if median < 190:
        return "mittelhoch"
    return "hoch"


def analyze_reference(samples: Sequence[float], rate: int) -> Dict[str, Any]:
    """Erstellt ein grobes Stimmprofil mit Stil-Empfehlung."""
    f0 = estimate_f0(samples, rate)
    bright = brightness(samples, rate)
    median = f0.get("median_hz")
    low = f0.get("low_hz")
    high = f0.get("high_hz")
    pitch_class = _pitch_class(median)
    jitter = f0.get("jitter")
    pitch_range = f0.get("range_semitones")

    roughness = "gleichmäßig"
    if pitch_range is not None:
        if pitch_range > 14:
            roughness = "sehr ausdrucksstark (großer Tonumfang)"
        elif pitch_range > 9:
            roughness = "lebendig (mittlerer Tonumfang)"
        else:
            roughness = "ruhig (kleiner Tonumfang)"

    if median is None:
        preset, intensity, tempo = "weise", 1.0, 1.0
        summary = (
            "Die Tonhöhe konnte nicht zuverlässig bestimmt werden (zu leise, zu "
            "verrauscht oder keine Sprache). Es gilt der empfohlene Standardstil."
        )
    else:
        if median < 105:
            preset, intensity, tempo = "mystisch", 0.9, 0.97
        elif median < 125:
            preset, intensity, tempo = "weise", 1.0, 0.98
        elif median < 155:
            preset, intensity, tempo = "weise", 0.95, 1.0
        else:
            preset, intensity, tempo = "warm", 0.85, 1.02
        if pitch_range is not None and pitch_range > 12:
            intensity = min(1.0, intensity + 0.05)
        summary = (
            f"Geschätzte Sprechlage: {pitch_class} (etwa {median:.0f} Hz). "
            f"Tonumfang: {roughness}"
            + (f" (etwa {low:.0f}–{high:.0f} Hz)" if low and high else "")
            + f". Rauer Helligkeitswert: {bright:.0f} Hz (nur zur Information)."
        )

    return {
        "estimated": True,
        "median_f0_hz": median,
        "f0_low_hz": f0.get("low_hz"),
        "f0_high_hz": f0.get("high_hz"),
        "voiced_ratio": f0.get("voiced_ratio"),
        "jitter": jitter,
        "range_semitones": pitch_range,
        "pitch_class": pitch_class,
        "roughness": roughness,
        "brightness_hz": bright,
        "suggested_preset": preset,
        "suggested_intensity": round(intensity, 2),
        "suggested_tempo": round(tempo, 2),
        "summary": summary,
        "honest_note": (
            "Das ist eine grobe Schätzung aus der Referenzaufnahme, keine Stimmkopie. "
            "Der Vorschlag stellt nur Tempo und Klangfarbe der Modellstimme näher an "
            "deine Sprechlage."
        ),
    }
