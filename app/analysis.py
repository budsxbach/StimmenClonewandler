"""Audio-Analyse: Pegel, Übersteuerung, Hintergrundgeräusche.

Läuft komplett lokal und ohne zusätzliche Pakete. Damit die Analyse auch bei
langen Dateien auf einem älteren Laptop schnell bleibt, wird blockweise
gelesen und für die Statistik eine Stichprobe je Block verwendet.
Die exakten Spitzenwerte und die Anzahl übersteuerter Samples werden dabei
weiterhin vollständig erfasst (bei 16-Bit-PCM exakt gezählt).
"""

from __future__ import annotations

import array
import math
import sys
import wave
from pathlib import Path
from typing import List

from .wav_io import WavError, amp_to_db, read_wav

MAX_ANALYSIS_SECONDS = 180.0  # längere Dateien werden nur im ersten Teil analysiert
BLOCK_SECONDS = 0.1          # Analysefenster
SAMPLES_PER_BLOCK = 512      # Stichproben pro Fenster (Statistik)
CLIP_FRACTION_WARN = 0.0005  # 0,05 % übersteuerte Samples = Warnung
CLIP_FRACTION_ERR = 0.01     # 1 % = deutlicher Fehler


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * pct / 100.0))
    return ordered[max(0, min(len(ordered) - 1, idx))]


def _decode_block(raw: bytes, width: int, channels: int) -> List[List[int]] | None:
    """Rohbytes eines Blocks → Liste je Kanal mit Ganzzahlwerten."""
    if width == 2:
        arr = array.array("h")
        arr.frombytes(raw)
        if sys.byteorder == "big":
            arr.byteswap()
    elif width == 4:
        arr = array.array("i")
        arr.frombytes(raw)
        if sys.byteorder == "big":
            arr.byteswap()
    elif width == 1:
        arr = array.array("B")
        arr.frombytes(raw)
        return [[(v - 128) for v in arr[ch::channels]] for ch in range(channels)]
    else:
        return None  # 24 Bit: wird über den generischen Weg gelesen
    return [arr[ch::channels] for ch in range(channels)]


def analyze(path: Path | str) -> dict:
    """Analysiert eine WAV-Datei und liefert ein Ergebnis-Dictionary."""
    path = Path(path)
    try:
        with wave.open(str(path), "rb") as w:
            channels = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            total_frames = w.getnframes()
            if width not in (1, 2, 3, 4) or channels < 1 or rate <= 0:
                raise WavError("Nicht unterstütztes WAV-Format.")
            return _analyze_pcm_stream(w, path, channels, width, rate, total_frames)
    except wave.Error:
        # z. B. Float-WAV: über den generischen Leser analysieren
        return _analyze_generic(path)
    except EOFError:
        raise WavError("Die WAV-Datei ist unvollständig oder beschädigt.")


def _analyze_pcm_stream(w, path: Path, channels: int, width: int, rate: int, total_frames: int) -> dict:
    block_frames = max(64, int(rate * BLOCK_SECONDS))
    max_value = (1 << (width * 8 - 1)) - 1
    min_value = -(1 << (width * 8 - 1))

    peaks = [0.0] * channels
    clipped = 0
    total_samples = 0
    dc_sums = [0] * channels
    dc_counts = [0] * channels
    block_db: List[float] = []
    total_rss = 0.0
    total_rss_count = 0

    analysis_limit = int(MAX_ANALYSIS_SECONDS * rate)
    frames_seen = 0
    while frames_seen < analysis_limit:
        raw = w.readframes(min(block_frames, analysis_limit - frames_seen))
        if not raw:
            break
        frames_seen += len(raw) // (width * channels)
        frames_read = len(raw) // (width * channels)
        if frames_read <= 0:
            break
        per_channel = _decode_block(raw, width, channels)

        if per_channel is None:
            # 24-Bit: generisch, aber blockweise
            values: List[List[int]] = [[] for _ in range(channels)]
            step = width * channels
            for i in range(0, len(raw) - step + 1, step):
                for ch in range(channels):
                    off = i + ch * width
                    values[ch].append(int.from_bytes(raw[off:off + 3], "little", signed=True))
            per_channel = values

        block_rss = 0.0
        block_count = 0
        for ch in range(channels):
            samples = per_channel[ch]
            if not samples:
                continue
            ch_peak = max(max(samples), -min(samples)) / float(max_value)
            if ch_peak > peaks[ch]:
                peaks[ch] = ch_peak
            # Übersteuerung exakt zählen
            clipped += samples.count(max_value) + samples.count(min_value)
            total_samples += len(samples)
            stride = max(1, len(samples) // SAMPLES_PER_BLOCK)
            sub = samples[::stride]
            dc_sums[ch] += sum(sub)
            dc_counts[ch] += len(sub)
            for value in sub:
                normalized = value / float(max_value)
                block_rss += normalized * normalized
                block_count += 1

        if block_count:
            total_rss += block_rss
            total_rss_count += block_count
            block_rms = math.sqrt(block_rss / block_count)
            block_db.append(amp_to_db(block_rms))

    duration = total_frames / rate if rate else 0.0
    overall_rms = math.sqrt(total_rss / total_rss_count) if total_rss_count else 0.0
    peak_overall = max(peaks) if peaks else 0.0

    noise_db = _percentile(block_db, 10)
    speech_db = _percentile(block_db, 90)
    snr = speech_db - noise_db
    silence_ratio = (
        sum(1 for value in block_db if value < -55.0) / len(block_db) if block_db else 0.0
    )
    dc_offsets = [
        (dc_sums[ch] / dc_counts[ch]) / float(max_value) for ch in range(channels) if dc_counts[ch]
    ]
    dc_offset = max((abs(value) for value in dc_offsets), default=0.0)
    clipped_fraction = (clipped / total_samples) if total_samples else 0.0

    analyzed_seconds = frames_seen / rate if rate else 0.0
    result = _build_result(
        sample_rate=rate,
        channels=channels,
        bits=width * 8,
        duration=duration,
        analyzed_seconds=analyzed_seconds,
        peak=peak_overall,
        rms=overall_rms,
        noise_db=noise_db,
        speech_db=speech_db,
        snr=snr,
        clipped=clipped,
        clipped_fraction=clipped_fraction,
        dc_offset=dc_offset,
        silence_ratio=silence_ratio,
        channels_peak=peaks,
    )
    return result


def _analyze_generic(path: Path) -> dict:
    """Fallback für Float-WAV und andere Sonderfälle (lädt die Datei in den Speicher)."""
    try:
        rate, channel_data = read_wav(path)
    except WavError:
        raise
    frames = min((len(ch) for ch in channel_data), default=0)
    block_frames = max(64, int(rate * BLOCK_SECONDS))
    block_db: List[float] = []
    peaks = [0.0] * len(channel_data)
    clipped = 0
    total = 0
    dc_offsets = []

    for ch, samples in enumerate(channel_data):
        peaks[ch] = max((abs(v) for v in samples), default=0.0)
        clipped += sum(1 for v in samples if abs(v) >= 0.999)
        total += len(samples)
        dc_offsets.append(abs(sum(samples) / len(samples)) if samples else 0.0)

    stride = max(1, frames // 40000)
    for start in range(0, frames, block_frames):
        chunk = channel_data[0][start:start + block_frames:stride]
        if not chunk:
            continue
        rms = math.sqrt(sum(v * v for v in chunk) / len(chunk))
        block_db.append(amp_to_db(rms))

    speech_db = _percentile(block_db, 90)
    noise_db = _percentile(block_db, 10)
    # Blockpegel (dB) zurück in lineare Leistung mitteln
    overall_rms = math.sqrt(
        sum((10 ** (db / 20.0)) ** 2 for db in block_db) / len(block_db)
    ) if block_db else 0.0
    silence_ratio = sum(1 for db in block_db if db < -55.0) / len(block_db) if block_db else 0.0

    return _build_result(
        sample_rate=rate,
        channels=len(channel_data),
        bits=32,
        duration=frames / rate if rate else 0.0,
        analyzed_seconds=frames / rate if rate else 0.0,
        peak=max(peaks) if peaks else 0.0,
        rms=overall_rms,
        noise_db=noise_db,
        speech_db=speech_db,
        snr=speech_db - noise_db,
        clipped=clipped,
        clipped_fraction=(clipped / total) if total else 0.0,
        dc_offset=max(dc_offsets, default=0.0),
        silence_ratio=silence_ratio,
        channels_peak=peaks,
    )


def _build_result(
    *,
    sample_rate: int,
    channels: int,
    bits: int,
    duration: float,
    analyzed_seconds: float,
    peak: float,
    rms: float,
    noise_db: float,
    speech_db: float,
    snr: float,
    clipped: int,
    clipped_fraction: float,
    dc_offset: float,
    silence_ratio: float,
    channels_peak: List[float],
) -> dict:
    peak_db = amp_to_db(peak)
    rms_db = amp_to_db(rms)

    if rms_db < -33:
        loudness = "sehr leise"
    elif rms_db < -26:
        loudness = "leise"
    elif rms_db <= -12:
        loudness = "gut ausgesteuert"
    elif rms_db <= -8:
        loudness = "sehr laut"
    else:
        loudness = "übersteuert"

    if snr >= 30:
        noise_label = "ruhig"
    elif snr >= 20:
        noise_label = "leichtes Grundrauschen"
    elif snr >= 12:
        noise_label = "hörbares Hintergrundgeräusch"
    else:
        noise_label = "starkes Hintergrundgeräusch"

    warnings: List[dict] = []
    if clipped_fraction >= 0.0002 or peak_db >= -0.1:
        severity = "error" if clipped_fraction >= CLIP_FRACTION_ERR else "warn"
        if clipped_fraction > 0:
            text = (
                f"Übersteuerung erkannt: {clipped} Samples am Vollausschlag "
                f"({clipped_fraction * 100:.2f} %). Das führt zu hörbaren Verzerrungen."
            )
        else:
            text = "Der Pegel liegt direkt am Vollausschlag – Übersteuerung möglich."
        warnings.append({"severity": severity, "text": text})

    if snr < 12:
        warnings.append({
            "severity": "warn",
            "text": (
                f"Starkes Hintergrundgeräusch: geschätzter Abstand zwischen Stimme und "
                f"Grundgeräusch nur {snr:.0f} dB. Für eine gute Sprachausgabe bitte in "
                "einem ruhigeren Raum aufnehmen."
            ),
        })
    elif snr < 20:
        warnings.append({
            "severity": "info",
            "text": (
                f"Hörbares Hintergrundgeräusch (ca. {snr:.0f} dB Abstand zur Stimme). "
                "Für ein Sprachmodell noch brauchbar, aber nicht ideal."
            ),
        })

    if rms_db < -33 and duration > 0.5:
        warnings.append({
            "severity": "warn",
            "text": f"Die Aufnahme ist sehr leise ({rms_db:.1f} dBFS). Bitte näher am Mikrofon sprechen.",
        })

    if dc_offset > 0.02:
        warnings.append({
            "severity": "info",
            "text": "Die Aufnahme hat einen Gleichstromanteil (DC-Offset). Das ist meist harmlos.",
        })

    if silence_ratio > 0.75:
        warnings.append({
            "severity": "info",
            "text": "Der größte Teil der Aufnahme ist still. Für das Modell bitte nur gesprochene Passagen verwenden.",
        })

    if analyzed_seconds and duration > analyzed_seconds + 0.5:
        warnings.append({
            "severity": "info",
            "text": (
                f"Die Datei ist {duration / 60:.1f} Minuten lang. Aus Zeitgründen wurden nur die "
                f"ersten {analyzed_seconds / 60:.1f} Minuten ausgewertet."
            ),
        })

    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "bits": bits,
        "duration_s": round(duration, 3),
        "analyzed_seconds": round(analyzed_seconds, 2),
        "peak_dbfs": round(peak_db, 2),
        "rms_dbfs": round(rms_db, 2),
        "loudness_label": loudness,
        "channel_peaks_dbfs": [round(amp_to_db(value), 2) for value in channels_peak],
        "clipped_samples": clipped,
        "clipped_fraction": round(clipped_fraction, 6),
        "clipping": bool(clipped_fraction >= 0.0002 or peak_db >= -0.1),
        "noise_floor_dbfs": round(noise_db, 2),
        "speech_level_dbfs": round(speech_db, 2),
        "snr_db": round(snr, 2),
        "noise_label": noise_label,
        "dc_offset": round(dc_offset, 5),
        "silence_ratio": round(silence_ratio, 3),
        "warnings": warnings,
        "ok_for_model": bool(
            duration >= 3.0
            and clipped_fraction < CLIP_FRACTION_WARN
            and snr >= 15
            and rms_db > -33
        ),
        "estimated": True,
    }
