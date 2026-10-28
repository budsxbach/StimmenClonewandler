"""Kleines WAV-Werkzeug – nur Python-Standardbibliothek.

Damit läuft die App auch auf einem älteren Laptop ohne zusätzliche Audio-Pakete.
Unterstützt werden PCM-WAV-Dateien mit 8/16/24/32 Bit sowie Float-WAV (32/64 Bit).
"""

from __future__ import annotations

import array
import math
import struct
import sys
import wave
from pathlib import Path
from typing import List, Sequence, Tuple

# ---------------------------------------------------------------------------
# Typen
# ---------------------------------------------------------------------------

ChannelData = List[List[float]]  # [Kanal][Sample], Werte in [-1.0, 1.0]


class WavError(Exception):
    """Fehler beim Lesen/Schreiben einer WAV-Datei (deutsche Meldung)."""


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------

def wav_info(path: Path | str) -> dict:
    """Liest die Kopfdaten einer WAV-Datei (ohne die Samples zu dekodieren)."""
    path = Path(path)
    try:
        with wave.open(str(path), "rb") as w:
            channels = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            frames = w.getnframes()
    except wave.Error as exc:
        raise WavError(
            "Diese Datei ist keine gültige PCM-WAV-Datei "
            f"(Details: {exc}). Bitte als WAV (PCM, 16 Bit) exportieren."
        ) from exc
    except FileNotFoundError as exc:
        raise WavError("Die Audiodatei wurde nicht gefunden.") from exc

    return {
        "sample_rate": rate,
        "channels": channels,
        "bits": width * 8,
        "frames": frames,
        "duration_s": round(frames / rate, 3) if rate else 0.0,
    }


def _decode_interleaved(raw: bytes, width: int) -> List[float]:
    """Rohbytes (little endian, PCM) in Float-Samples [-1, 1] umwandeln."""
    if width == 2:
        arr = array.array("h")
        arr.frombytes(raw)
        if sys.byteorder == "big":
            arr.byteswap()
        return [v / 32768.0 for v in arr]
    if width == 1:
        # 8-Bit-WAV ist unsigned
        arr = array.array("B")
        arr.frombytes(raw)
        return [(v - 128) / 128.0 for v in arr]
    if width == 4:
        arr = array.array("i")
        arr.frombytes(raw)
        if sys.byteorder == "big":
            arr.byteswap()
        return [v / 2147483648.0 for v in arr]
    if width == 3:
        out: List[float] = []
        for i in range(0, len(raw) - 2, 3):
            value = int.from_bytes(raw[i:i + 3], "little", signed=True)
            out.append(value / 8388608.0)
        return out
    raise WavError(f"Nicht unterstützte Bittiefe: {width * 8} Bit.")


def _decode_float(raw: bytes, width: int) -> List[float]:
    if width == 4:
        count = len(raw) // 4
        return list(struct.unpack("<%df" % count, raw[: count * 4]))
    if width == 8:
        count = len(raw) // 8
        return list(struct.unpack("<%dd" % count, raw[: count * 8]))
    raise WavError("Nicht unterstütztes Float-WAV-Format.")


def _is_float_wave(path: Path) -> bool:
    """Prüft das Format-Tag im RIFF-Header (3 = IEEE-Float)."""
    try:
        with open(path, "rb") as fh:
            header = fh.read(64)
    except OSError:
        return False
    if len(header) < 24 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        return False
    # Chunk-Schleife über die ersten Bytes
    pos = 12
    while pos + 8 <= len(header):
        chunk_id = header[pos:pos + 4]
        size = int.from_bytes(header[pos + 4:pos + 8], "little")
        if chunk_id == b"fmt ":
            if pos + 8 + 2 > len(header):
                return False
            tag = int.from_bytes(header[pos + 8:pos + 10], "little")
            return tag in (3, 0xFFFE)
        pos += 8 + size + (size % 2)
    return False


def read_wav(path: Path | str, max_seconds: float | None = None) -> Tuple[int, ChannelData]:
    """Liest eine WAV-Datei und liefert (Samplerate, Kanaldaten als Floats)."""
    path = Path(path)
    if _is_float_wave(path):
        return _read_wav_float(path, max_seconds)

    try:
        with wave.open(str(path), "rb") as w:
            channels = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            frames = w.getnframes()
            if max_seconds is not None:
                limit = int(max_seconds * rate)
                if frames > limit:
                    frames = limit
            raw = w.readframes(frames)
    except wave.Error as exc:
        raise WavError(
            "Diese Datei ist keine gültige PCM-WAV-Datei "
            f"(Details: {exc}). Bitte als WAV (PCM, 16 Bit) exportieren."
        ) from exc
    except FileNotFoundError as exc:
        raise WavError("Die Audiodatei wurde nicht gefunden.") from exc

    if channels < 1:
        raise WavError("Die WAV-Datei enthält keine Kanäle.")

    samples = _decode_interleaved(raw, width)
    data: ChannelData = [samples[ch::channels] for ch in range(channels)]
    return rate, data


def _read_wav_float(path: Path, max_seconds: float | None) -> Tuple[int, ChannelData]:
    """Minimaler Float-WAV-Leser (Format-Tag 3), da `wave` das nicht kann."""
    raw_file = path.read_bytes()
    if len(raw_file) < 12 or raw_file[:4] != b"RIFF":
        raise WavError("Die Datei ist keine gültige WAV-Datei.")
    pos = 12
    fmt: tuple | None = None
    data_bytes = b""
    while pos + 8 <= len(raw_file):
        chunk_id = raw_file[pos:pos + 4]
        size = int.from_bytes(raw_file[pos + 4:pos + 8], "little")
        body = raw_file[pos + 8: pos + 8 + size]
        if chunk_id == b"fmt ":
            tag, channels, rate, _byte_rate, _align, bits = struct.unpack("<HHIIHH", body[:16])
            if tag not in (3, 0xFFFE):
                raise WavError("Nicht unterstütztes WAV-Format.")
            fmt = (channels, rate, bits)
        elif chunk_id == b"data":
            data_bytes = body
            break
        pos += 8 + size + (size % 2)

    if fmt is None or not data_bytes:
        raise WavError("Die WAV-Datei enthält keine lesbaren Audiodaten.")

    channels, rate, bits = fmt
    samples = _decode_float(data_bytes, bits // 8)
    if max_seconds is not None:
        limit = int(max_seconds * rate)
        samples = samples[: limit * channels]
    data: ChannelData = [samples[ch::channels] for ch in range(channels)]
    return rate, data


# ---------------------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------------------

def _encode_float_to_int16(data: ChannelData, peak_limit: float = 0.999) -> bytes:
    """Interleaved Float-Kanäle → 16-Bit-PCM (hart begrenzt, ohne Rundungslast)."""
    if not data:
        return b""
    channels = len(data)
    frames = min(len(channel) for channel in data)
    scale = 32767.0
    limit = peak_limit

    def to_int(value: float) -> int:
        if value > limit:
            value = limit
        elif value < -limit:
            value = -limit
        return int(value * scale)

    if channels == 1:
        samples = data[0]
        out = array.array("h", (to_int(value) for value in samples[:frames]))
    else:
        out = array.array("h")
        for index in range(frames):
            for channel in data:
                out.append(to_int(channel[index]))

    if sys.byteorder == "big":
        out.byteswap()
    return out.tobytes()


def write_wav(path: Path | str, rate: int, data: ChannelData, bits: int = 16) -> Path:
    """Schreibt Kanaldaten (Floats in [-1, 1]) als PCM-WAV."""
    if bits != 16:
        raise WavError("Es werden nur 16-Bit-WAV-Dateien geschrieben.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    channels = len(data)
    if channels not in (1, 2):
        raise WavError("Es werden nur Mono- oder Stereo-Dateien geschrieben.")
    raw = _encode_float_to_int16(data)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(bits // 8)
        w.setframerate(int(rate))
        w.writeframes(raw)
    return path


# ---------------------------------------------------------------------------
# Bearbeitung
# ---------------------------------------------------------------------------

def to_mono(data: ChannelData) -> List[float]:
    """Mehrere Kanäle zu Mono mischen (Mittelwert)."""
    if len(data) == 1:
        return list(data[0])
    frames = min(len(ch) for ch in data)
    count = len(data)
    return [sum(ch[i] for ch in data) / count for i in range(frames)]


def peak_of(samples: Sequence[float]) -> float:
    if not samples:
        return 0.0
    return max(abs(min(samples)), abs(max(samples)))


def rms_of(samples: Sequence[float]) -> float:
    if not samples:
        return 0.0
    total = 0.0
    for value in samples:
        total += value * value
    return math.sqrt(total / len(samples))


def amp_to_db(amplitude: float) -> float:
    if amplitude <= 1e-12:
        return -120.0
    return 20.0 * math.log10(amplitude)


def db_to_amp(db: float) -> float:
    return 10.0 ** (db / 20.0)


def peak_normalize(samples: Sequence[float], target_dbfs: float = -1.0) -> List[float]:
    """Hebt/senkt die Lautstärke so, dass die Spitze bei `target_dbfs` liegt."""
    peak = peak_of(samples)
    if peak <= 1e-9:
        return list(samples)
    gain = db_to_amp(target_dbfs) / peak
    gain = min(gain, 32.0)  # keine absurde Verstärkung von Stille
    return [max(-1.0, min(1.0, value * gain)) for value in samples]


def resample(samples: Sequence[float], src_rate: int, dst_rate: int) -> List[float]:
    """Lineare Interpolation mit einfachem Anti-Aliasing-Tiefpass.

    Ausreichend für Referenzdateien, Tempoänderung und Tonhöhenverschiebung –
    ohne zusätzliche Abhängigkeiten. Beim Heruntertasten wird vorher geglättet,
    damit keine Aliasing-Artefakte entstehen.
    """
    if src_rate == dst_rate or not samples:
        return list(samples)
    ratio = dst_rate / src_rate

    if ratio < 1.0:
        # Tiefpass (gleitender Mittelwert) vor dem Heruntertasten
        window = max(2, int(round(1.0 / ratio)))
        if window > 2:
            half = window // 2
            filtered: List[float] = []
            total = 0.0
            ring: List[float] = []
            for value in samples:
                ring.append(value)
                total += value
                if len(ring) > window:
                    total -= ring.pop(0)
                filtered.append(total / len(ring))
            # Randbereiche mit dem Original auffüllen (keine Pegelabsenkung)
            for index in range(min(half, len(filtered))):
                filtered[index] = samples[index]
                back = len(filtered) - 1 - index
                if back >= 0:
                    filtered[back] = samples[back]
            samples = filtered
    out_len = max(1, int(round(len(samples) * ratio)))
    out: List[float] = []
    last = len(samples) - 1
    for i in range(out_len):
        pos = i / ratio
        idx = int(pos)
        if idx >= last:
            out.append(samples[last])
            continue
        frac = pos - idx
        out.append(samples[idx] * (1.0 - frac) + samples[idx + 1] * frac)
    return out


def trim_silence(
    samples: Sequence[float],
    rate: int,
    threshold_dbfs: float = -45.0,
    pad_ms: int = 120,
) -> List[float]:
    """Schneidet Stille am Anfang und Ende ab (mit etwas Vorlauf/Nachlauf)."""
    if not samples:
        return []
    threshold = db_to_amp(threshold_dbfs)
    step = max(1, rate // 100)  # 10-ms-Fenster
    start = 0
    end = len(samples)

    for i in range(0, len(samples) - step, step):
        if peak_of(samples[i:i + step]) > threshold:
            start = i
            break
    else:
        return []

    for i in range(len(samples) - step, 0, -step):
        if peak_of(samples[i:i + step]) > threshold:
            end = min(len(samples), i + step)
            break

    pad = int(pad_ms / 1000.0 * rate)
    start = max(0, start - pad)
    end = min(len(samples), end + pad)
    return list(samples[start:end])


def change_tempo(samples: Sequence[float], speed: float) -> List[float]:
    """Einfache Tempoänderung durch Resampling.

    `speed` < 1.0 = langsamer. Hinweis: Das verändert auch die Tonhöhe
    (langsamer ⇒ etwas tiefer). Genau das ist für den gewünschten ruhigen,
    tiefen Stimmcharakter gewollt und wird in der App auch so benannt.
    """
    if not samples or abs(speed - 1.0) < 1e-3:
        return list(samples)
    speed = max(0.6, min(1.6, speed))
    out_len = max(1, int(round(len(samples) / speed)))
    out: List[float] = []
    last = len(samples) - 1
    for i in range(out_len):
        pos = i * speed
        idx = int(pos)
        if idx >= last:
            out.append(samples[last])
            continue
        frac = pos - idx
        out.append(samples[idx] * (1.0 - frac) + samples[idx + 1] * frac)
    return out


# ---------------------------------------------------------------------------
# Einfache Filter (Biquad) für den warmen Stimmcharakter
# ---------------------------------------------------------------------------

def low_shelf(samples: List[float], rate: int, freq: float, gain_db: float, q: float = 0.7) -> List[float]:
    """Tiefenanhebung/-absenkung (Shelving-Filter)."""
    if not samples or abs(gain_db) < 0.05:
        return list(samples)
    a = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * freq / rate
    cos_w0, sin_w0 = math.cos(w0), math.sin(w0)
    alpha = sin_w0 / (2 * q)
    sq = 2 * math.sqrt(a) * alpha

    b0 = a * ((a + 1) - (a - 1) * cos_w0 + sq)
    b1 = 2 * a * ((a - 1) - (a + 1) * cos_w0)
    b2 = a * ((a + 1) - (a - 1) * cos_w0 - sq)
    a0 = (a + 1) + (a - 1) * cos_w0 + sq
    a1 = -2 * ((a - 1) + (a + 1) * cos_w0)
    a2 = (a + 1) + (a - 1) * cos_w0 - sq

    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
    return _biquad(samples, b0, b1, b2, a1, a2)


def high_shelf(samples: List[float], rate: int, freq: float, gain_db: float, q: float = 0.7) -> List[float]:
    """Höhenabsenkung/-anhebung (Shelving-Filter)."""
    if not samples or abs(gain_db) < 0.05:
        return list(samples)
    a = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * freq / rate
    cos_w0, sin_w0 = math.cos(w0), math.sin(w0)
    alpha = sin_w0 / (2 * q)
    sq = 2 * math.sqrt(a) * alpha

    b0 = a * ((a + 1) + (a - 1) * cos_w0 + sq)
    b1 = -2 * a * ((a - 1) + (a + 1) * cos_w0)
    b2 = a * ((a + 1) + (a - 1) * cos_w0 - sq)
    a0 = (a + 1) - (a - 1) * cos_w0 + sq
    a1 = 2 * ((a - 1) - (a + 1) * cos_w0)
    a2 = (a + 1) - (a - 1) * cos_w0 - sq

    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
    return _biquad(samples, b0, b1, b2, a1, a2)


def _biquad(samples: List[float], b0: float, b1: float, b2: float, a1: float, a2: float) -> List[float]:
    out: List[float] = []
    x1 = x2 = y1 = y2 = 0.0
    for x in samples:
        y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x
        y2, y1 = y1, y
        out.append(y)
    return out


def soft_saturation(samples: List[float], drive: float = 1.25) -> List[float]:
    """Sehr milde Sättigung – gibt der Stimme eine leichte Rauheit, ohne zu verzerren."""
    if not samples:
        return []
    norm = math.tanh(drive)
    return [math.tanh(drive * value) / norm for value in samples]
