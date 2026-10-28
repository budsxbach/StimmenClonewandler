"""Master-Aufnahme vorbereiten.

Die Master-Datei ist die aufbereitete Referenz-Aufnahme: Mono, beschnitten,
normalisiert, auf höchstens 30 Sekunden begrenzt. Für XTTS-v2 wird sie zusätzlich
auf 24 kHz gebracht (das Modell arbeitet mit dieser Rate).

Wichtig: Die Originaldatei bleibt unverändert erhalten. Die Master-Datei ist
immer eine neue Datei in `data/master/`.
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import analysis as analysis_mod
from . import storage, voice_profile
from .config import MASTERS_DIR, MAX_REFERENCE_SECONDS
from .wav_io import (
    WavError,
    rms_of,
    high_shelf,
    low_shelf,
    peak_normalize,
    read_wav,
    resample,
    to_mono,
    trim_silence,
    write_wav,
)

XTTS_SAMPLE_RATE = 24000
MIN_REFERENCE_SECONDS = 6.0
IDEAL_REFERENCE_SECONDS = 12.0


def _best_window(samples, rate: int, max_seconds: float):
    """Wählt die aussagekräftigste Passage (gleichmäßig laut, keine Stille).

    Statt einfach die ersten Sekunden zu nehmen, wird das Fenster mit dem
    höchsten durchschnittlichen Pegel gewählt – dort ist am ehesten
    durchgehende Sprache zu hören.
    """
    window = int(max_seconds * rate)
    if len(samples) <= window:
        return list(samples)

    block = max(1, rate // 2)          # 0,5-s-Blöcke
    levels = []
    for start in range(0, len(samples) - block, block):
        chunk = samples[start:start + block]
        levels.append(rms_of(chunk))

    per_window = max(1, window // block)
    best_start_block = 0
    best_score = -1.0
    running = sum(levels[:per_window])
    for index in range(0, max(1, len(levels) - per_window)):
        if index > 0:
            running += levels[index + per_window - 1] - levels[index - 1]
        if running > best_score:
            best_score = running
            best_start_block = index

    start = best_start_block * block
    # etwas Vorlauf, damit der erste Ton nicht abgeschnitten wird
    start = max(0, min(start - block, len(samples) - window))
    return list(samples[start:start + window])


def build_reference(
    rec_id: str,
    *,
    target_rate: int = XTTS_SAMPLE_RATE,
    max_seconds: float = MAX_REFERENCE_SECONDS,
    cleanup: bool = True,
) -> Dict[str, Any]:
    """Erstellt aus einer Aufnahme die aufbereitete Master-Referenzdatei."""
    record = storage.get_recording(rec_id)
    if not record:
        raise WavError("Die Aufnahme wurde nicht gefunden.")
    source = storage.recording_path(rec_id)
    if not source:
        raise WavError("Die Audiodatei der Aufnahme fehlt.")

    rate, data = read_wav(source)
    mono = to_mono(data)
    if not mono:
        raise WavError("Die Aufnahme enthält kein Audio.")

    original_duration = len(mono) / rate

    trimmed = trim_silence(mono, rate, threshold_dbfs=-45.0, pad_ms=120)
    if not trimmed:
        raise WavError(
            "In der Aufnahme wurde keine Sprache gefunden (nur Stille). "
            "Bitte erneut aufnehmen."
        )

    if len(trimmed) > max_seconds * rate:
        trimmed = _best_window(trimmed, rate, max_seconds)

    if cleanup:
        # Gleichstromanteil und tiefes Dröhnen entfernen, Höhen leicht zähmen
        trimmed = low_shelf(trimmed, rate, 90.0, -3.0, q=0.7)
        trimmed = high_shelf(trimmed, rate, 7000.0, -1.5, q=0.7)

    normalized = peak_normalize(trimmed, -2.0)
    if target_rate and rate != target_rate:
        normalized = resample(normalized, rate, target_rate)
        rate = target_rate

    reference = MASTERS_DIR / f"{rec_id}_referenz.wav"
    write_wav(reference, rate, [normalized])

    info = analysis_mod.analyze(reference)
    duration = len(normalized) / rate
    profile = voice_profile.analyze_reference(normalized, rate)

    notes: List[Dict[str, str]] = []
    if duration < MIN_REFERENCE_SECONDS:
        notes.append({
            "severity": "error",
            "text": (
                f"Die Master-Aufnahme ist nur {duration:.1f} s lang. Für eine nutzbare "
                f"Stimmreferenz werden mindestens {MIN_REFERENCE_SECONDS:.0f} s empfohlen – "
                "die eigene Stimmkopie wird damit nicht zuverlässig funktionieren."
            ),
        })
    elif duration < IDEAL_REFERENCE_SECONDS:
        notes.append({
            "severity": "warn",
            "text": (
                f"Die Master-Aufnahme ist {duration:.1f} s lang. Besser wären "
                f"{IDEAL_REFERENCE_SECONDS:.0f}–{MAX_REFERENCE_SECONDS:.0f} s ruhiger, "
                "gleichmäßiger Sprache."
            ),
        })
    else:
        notes.append({
            "severity": "ok",
            "text": f"Die Master-Aufnahme ist {duration:.1f} s lang – gute Länge für eine Referenz.",
        })

    if info.get("snr_db", 0) < 15:
        notes.append({
            "severity": "warn",
            "text": "Die Referenz enthält hörbare Hintergrundgeräusche. Das verschlechtert das Ergebnis deutlich.",
        })
    if info.get("clipping"):
        notes.append({
            "severity": "warn",
            "text": "Die Referenz war übersteuert – Verzerrungen lassen sich nicht mehr rückgängig machen.",
        })
    if info.get("sample_rate", 0) < 16000:
        notes.append({
            "severity": "info",
            "text": "Die Aufnahme hat eine niedrige Samplerate (unter 16 kHz). Für ein gutes Modell besser mit 44,1/48 kHz aufnehmen.",
        })

    storage.set_master(rec_id, reference)
    storage.save_base_voice_profile(
        rec_id,
        profile,
        {"name": record.get("name"), "reference": reference.name, "duration_s": round(duration, 2)},
    )

    return {
        "recording_id": rec_id,
        "recording_name": record.get("name"),
        "reference_file": reference.name,
        "reference_path": str(reference),
        "sample_rate": rate,
        "duration_s": round(duration, 2),
        "original_duration_s": round(original_duration, 2),
        "analysis": info,
        "notes": notes,
        "voice_profile": profile,
        "usable_as_reference": bool(duration >= MIN_REFERENCE_SECONDS and info.get("snr_db", 0) >= 12),
        "honest_note": (
            "Die Master-Aufnahme ist eine aufbereitete Kopie deiner Referenzaufnahme. "
            "Es wurde noch keine Sprachausgabe und keine Stimmkopie erzeugt."
        ),
    }


def base_voice() -> Dict[str, Any]:
    """Ausgangsstimme (Referenzprofil) für die Stimm-Anpassung."""
    master = storage.get_master()
    profile_payload = storage.get_base_voice_profile()
    if not master:
        return {"present": False, "profile": None, "reason": "Es ist keine Master-Aufnahme festgelegt."}
    reference = storage.reference_path(master["id"])
    if not reference:
        return {"present": False, "profile": None, "reason": "Die Referenzdatei der Master-Aufnahme fehlt."}
    profile = (profile_payload or {}).get("profile")
    if not profile:
        try:
            rate, data = read_wav(reference)
            profile = voice_profile.analyze_reference(to_mono(data), rate)
            storage.save_base_voice_profile(master["id"], profile, {"name": master.get("name")})
        except WavError:
            profile = None
    return {
        "present": bool(profile and profile.get("median_f0_hz")),
        "profile": profile,
        "recording": {"id": master.get("id"), "name": master.get("name")},
        "reference": reference.name,
        "reason": None if profile and profile.get("median_f0_hz") else "Die Stimmlage der Referenz konnte nicht bestimmt werden.",
    }


def master_overview() -> Dict[str, Any]:
    master = storage.get_master()
    if not master:
        return {"present": False}
    reference = storage.reference_path(master["id"])
    info: Dict[str, Any] = {}
    profile: Dict[str, Any] = {}
    if reference:
        try:
            info = analysis_mod.analyze(reference)
            rate, data = read_wav(reference)
            profile = voice_profile.analyze_reference(to_mono(data), rate)
        except WavError:
            info = {}
    return {
        "present": True,
        "recording": {
            "id": master.get("id"),
            "name": master.get("name"),
            "created_at": master.get("created_at"),
        },
        "reference": {
            "file": reference.name if reference else None,
            "sample_rate": info.get("sample_rate"),
            "duration_s": info.get("duration_s"),
            "analysis": info,
            "voice_profile": profile,
        },
    }
