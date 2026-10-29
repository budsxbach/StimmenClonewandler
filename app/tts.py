"""Lokale Sprachausgabe (Text-zu-Sprache).

Zwei Wege stehen zur Verfügung – beide laufen vollständig auf dem Laptop:

1. **Piper** (empfohlen, Standard): neuronale Sprachsynthese auf der CPU.
   Kleine Modelle (~20–60 MB), kein Grafikprozessor nötig, sehr sparsam.
   Die App wendet zusätzlich einen vorsichtigen Stimm-Feinschliff an
   (Tempo, Tiefen, milde Sättigung), damit die gewünschte warme, ruhige und
   leicht raue Klangfarbe entsteht.

2. **XTTS-v2** (optional, experimentell): kann eine eigene Stimmaufnahme
   nachbilden. Benötigt PyTorch, ~2 GB Modell und ist auf einer CPU ohne
   Grafikprozessor meist extrem langsam. Die App sagt das offen und behauptet
   nie, eine Stimmkopie sei fertig, wenn sie es nicht ist.

Es gibt in diesem Modul keinen Netzwerkzugriff. Modelle müssen vorher manuell
(nach ausdrücklicher Zustimmung, siehe README) in `data/modelle` abgelegt werden.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import dsp, hardware, voice_profile
from .config import XTTS_DIR
from .jobs import JobCancelled
from .wav_io import (
    change_tempo,
    high_shelf,
    low_shelf,
    peak_normalize,
    soft_saturation,
    write_wav,
)


class EngineError(Exception):
    """Ehrlicher Fehler mit deutscher Meldung für die Oberfläche."""


# ---------------------------------------------------------------------------
# Stimm-Stile
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StylePreset:
    id: str
    label: str
    description: str
    length_scale: float          # > 1.0 = langsameres Sprechen
    noise_scale: float           # Variation der Stimmfarbe
    noise_w_scale: float         # Variation der Sprechgeschwindigkeit
    tempo: float = 1.0           # < 1.0 = zusätzlich langsamer (auch etwas tiefer)
    low_shelf_hz: float = 200.0
    low_shelf_db: float = 0.0
    high_shelf_hz: float = 3600.0
    high_shelf_db: float = 0.0
    saturation: float = 0.0
    room: float = 0.0            # dezenter Raumanteil (kein Hall-Effekt)
    pitch: float = 0.0           # feste Tonhöhen-Absenkung in Halbtönen (Alter/Tiefe)


PRESETS: Tuple[StylePreset, ...] = (
    StylePreset(
        id="weise",
        label="Weise & warm (empfohlen)",
        description=(
            "Ruhig, leicht tief, warmer Grundton, ganz leichte Rauheit. "
            "Entspricht am ehesten der gewünschten älteren, glaubwürdigen Männerstimme."
        ),
        length_scale=1.12,
        noise_scale=0.62,
        noise_w_scale=0.78,
        tempo=0.97,
        low_shelf_hz=190.0,
        low_shelf_db=2.4,
        high_shelf_hz=3500.0,
        high_shelf_db=-2.0,
        saturation=0.07,
        room=0.04,
    ),
    StylePreset(
        id="alt_weise",
        label="Alt & weise (tief, bedächtig)",
        description=(
            "Deutlich tiefer und langsamer: kräftige Tiefen, gezähmte Höhen, leichte "
            "Rauheit und ein Hauch Raum. Kommt einem älteren, ruhigen Erzähler am nächsten."
        ),
        length_scale=1.22,
        noise_scale=0.72,
        noise_w_scale=0.86,
        tempo=0.95,
        low_shelf_hz=165.0,
        low_shelf_db=4.0,
        high_shelf_hz=3000.0,
        high_shelf_db=-4.0,
        saturation=0.11,
        room=0.09,
        pitch=-1.5,
    ),
    StylePreset(
        id="warm",
        label="Warm & ruhig",
        description="Nur leichte Wärme und ein Hauch Tiefe, sehr natürlicher Klang.",
        length_scale=1.06,
        noise_scale=0.60,
        noise_w_scale=0.76,
        tempo=0.99,
        low_shelf_hz=180.0,
        low_shelf_db=1.6,
        high_shelf_hz=3800.0,
        high_shelf_db=-1.4,
        saturation=0.04,
        room=0.02,
    ),
    StylePreset(
        id="mystisch",
        label="Mystisch & tief",
        description="Dunkler, langsamer, mit einem Hauch Raum. Bewusst zurückhaltend dosiert.",
        length_scale=1.20,
        noise_scale=0.72,
        noise_w_scale=0.88,
        tempo=0.94,
        low_shelf_hz=170.0,
        low_shelf_db=3.0,
        high_shelf_hz=3200.0,
        high_shelf_db=-3.2,
        saturation=0.08,
        room=0.10,
    ),
    StylePreset(
        id="ruhig",
        label="Nur ruhig & langsam",
        description="Keine Klangveränderung, nur langsamer und gleichmäßig gesprochen.",
        length_scale=1.18,
        noise_scale=0.60,
        noise_w_scale=0.74,
        tempo=1.0,
    ),
    StylePreset(
        id="neutral",
        label="Neutral (Modell-Stimme pur)",
        description="Originalausgabe des Modells ohne jeden Feinschliff – zum Vergleich.",
        length_scale=1.0,
        noise_scale=0.667,
        noise_w_scale=0.8,
    ),
)

PRESET_BY_ID = {preset.id: preset for preset in PRESETS}
DEFAULT_PRESET_ID = "weise"


def preset_list() -> List[Dict[str, Any]]:
    return [
        {
            "id": preset.id,
            "label": preset.label,
            "description": preset.description,
            "default": preset.id == DEFAULT_PRESET_ID,
        }
        for preset in PRESETS
    ]


# ---------------------------------------------------------------------------
# Text zerlegen
# ---------------------------------------------------------------------------

def split_text(text: str, max_chars: int = 260) -> List[str]:
    """Text in sprechbare Abschnitte zerlegen (für Fortschritt und Abbruch)."""
    text = " ".join(text.split())
    if not text:
        return []
    pieces: List[str] = []
    current = ""
    for word in text.split(" "):
        if len(current) + len(word) + 1 > max_chars and current:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
        # an Satzzeichen zusätzlich trennen
        while current and current[-1] in ".!?;:" and len(current) > 12:
            pieces.append(current)
            current = ""
    if current:
        pieces.append(current)
    return [piece for piece in pieces if piece.strip()]


# ---------------------------------------------------------------------------
# Piper
# ---------------------------------------------------------------------------

_VOICE_CACHE: Dict[str, Any] = {}
_SESSION_LOCK = threading.Lock()


def _build_session(model_path: Path, threads: int, slow_mode: bool):
    """ONNX-Sitzung mit begrenzter Thread-Zahl bauen (schont alte CPUs)."""
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, min(int(threads), os.cpu_count() or 1))
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = (
        ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        if slow_mode
        else ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    )
    options.enable_cpu_mem_arena = not slow_mode
    return ort.InferenceSession(
        str(model_path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


def load_voice(voice_path: Path, threads: int = 2, slow_mode: bool = False, progress=None):
    """Lädt eine Piper-Stimme (mit Zwischenspeicher, damit nicht jedes Mal neu geladen wird)."""
    from piper import PiperVoice
    from piper.config import PiperConfig

    voice_path = Path(voice_path)
    if not voice_path.exists():
        raise EngineError(
            f"Das Sprachmodell wurde nicht gefunden: {voice_path.name}. "
            "Bitte prüfen, ob die Datei im Ordner data/modelle/piper liegt."
        )
    config_path = Path(str(voice_path) + ".json")
    if not config_path.exists():
        raise EngineError(
            f"Zur Stimme fehlt die Konfigurationsdatei: {config_path.name}."
        )

    cache_key = f"{voice_path}|{threads}|{slow_mode}"
    with _SESSION_LOCK:
        if cache_key in _VOICE_CACHE:
            return _VOICE_CACHE[cache_key]

    if progress:
        progress(3, "Sprachmodell wird geladen …")
    started = time.time()
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            config_dict = json.load(fh)
        config = PiperConfig.from_dict(config_dict)
        session = _build_session(voice_path, threads, slow_mode)
        voice = PiperVoice(session=session, config=config)
    except EngineError:
        raise
    except Exception as exc:
        raise EngineError(
            "Das Sprachmodell konnte auf diesem Laptop nicht geladen werden. "
            f"Technische Ursache: {type(exc).__name__}: {exc}"
        ) from exc

    load_seconds = time.time() - started
    if progress:
        progress(8, f"Sprachmodell geladen ({load_seconds:.1f} s)")

    with _SESSION_LOCK:
        # nur eine Stimme gleichzeitig im Speicher halten (RAM sparen)
        _VOICE_CACHE.clear()
        _VOICE_CACHE[cache_key] = voice
    return voice


def unload_voices() -> None:
    with _SESSION_LOCK:
        _VOICE_CACHE.clear()


# ---------------------------------------------------------------------------
# Nachbearbeitung
# ---------------------------------------------------------------------------

def apply_style(
    samples: Sequence[float],
    rate: int,
    preset: StylePreset,
    *,
    intensity: float = 1.0,
    tempo_user: float = 1.0,
) -> List[float]:
    """Wendet den gewählten Stimm-Stil auf die Rohsynthese an."""
    values = [float(value) for value in samples]
    amount = max(0.0, min(2.0, float(intensity)))
    if not values or preset.id == "neutral":
        tempo_total = tempo_user
        return change_tempo(values, tempo_total) if abs(tempo_total - 1) > 1e-3 else values

    low_gain = preset.low_shelf_db * amount
    high_gain = preset.high_shelf_db * amount
    if abs(low_gain) > 0.05:
        values = low_shelf(values, rate, preset.low_shelf_hz, low_gain)
    if abs(high_gain) > 0.05:
        values = high_shelf(values, rate, preset.high_shelf_hz, high_gain)

    if preset.saturation > 0 and amount > 0:
        drive = 1.0 + preset.saturation * amount * 2.2
        values = soft_saturation(values, drive)

    # Feste Stil-Tonhöhe (z. B. „Alt & weise“): klingt tiefer, ohne das Tempo zu ändern
    if abs(preset.pitch) > 0.05 and amount > 0:
        values = dsp.pitch_shift(values, preset.pitch * min(1.0, amount), rate)

    # Tempo: Stil-Tempo (macht auch etwas tiefer) und Nutzer-Regler kombinieren
    total_tempo = preset.tempo * tempo_user
    if abs(total_tempo - 1.0) > 1e-3:
        values = change_tempo(values, total_tempo)

    if preset.room > 0 and amount > 0:
        values = _add_room(values, rate, preset.room * amount)

    return peak_normalize(values, -1.5)


def _add_room(samples: List[float], rate: int, amount: float) -> List[float]:
    """Dezenter, kurzer Raumeindruck über zwei verzögerte Kopien (kein Hall-Effekt)."""
    if amount <= 0:
        return list(samples)
    dry = 1.0 - 0.45 * amount
    delays = ((int(rate * 0.055), 0.28 * amount), (int(rate * 0.113), 0.16 * amount))
    out = [value * dry for value in samples]
    for delay, gain in delays:
        if delay <= 0 or gain <= 0:
            continue
        for index in range(delay, len(samples)):
            out[index] += samples[index - delay] * gain
    return out


# ---------------------------------------------------------------------------
# Stimmlage an die eigene Ausgangsstimme annähern
# ---------------------------------------------------------------------------

MAX_PITCH_SHIFT = 4.0   # mehr klingt künstlich – die App bleibt hier vorsichtig


def adapt_pitch_to_reference(
    samples: Sequence[float],
    rate: int,
    options: "SynthesisOptions",
) -> Tuple[List[float], Dict[str, Any]]:
    """Verschiebt die Stimmlage der Modellstimme in Richtung der eigenen Stimme.

    Grundlage ist die gemessene mittlere Sprechlage der Referenzaufnahme. Die
    Tonhöhe wird per WSOLA + Neubetastung verschoben (Dauer bleibt gleich).
    Bewusst auf ±4 Halbtöne begrenzt – stärkere Verschiebungen klingen
    künstlich und wären unehrlich gegenüber dem Hörergebnis.
    """
    from . import master as master_mod

    info: Dict[str, Any] = {
        "adapted": False,
        "manual_semitones": options.pitch_semitones,
        "applied_semitones": 0.0,
    }
    values = list(samples)

    # 1) manuelle Korrektur (Regler in der Oberfläche)
    manual = float(options.pitch_semitones or 0.0)
    if abs(manual) >= 0.05:
        values = dsp.pitch_shift(values, manual, rate)
        info["applied_semitones"] = round(manual, 2)
        info["manual_applied"] = True

    # 2) automatische Anpassung an die Ausgangsstimme
    if options.adapt_pitch:
        base = master_mod.base_voice()
        target = ((base.get("profile") or {}).get("median_f0_hz")) if base.get("present") else None
        info["reference_f0_hz"] = target
        info["reference_name"] = (base.get("recording") or {}).get("name")
        if not target:
            info["reason"] = base.get("reason") or "Keine Ausgangsstimme mit messbarer Stimmlage vorhanden."
        else:
            measured = voice_profile.estimate_f0(values, rate).get("median_hz")
            info["model_f0_hz"] = measured
            if not measured:
                info["reason"] = "Die Stimmlage der Modellstimme konnte nicht gemessen werden."
            else:
                shift = dsp.semitones_between(measured, target)
                limited = max(-MAX_PITCH_SHIFT, min(MAX_PITCH_SHIFT, shift))
                info["requested_semitones"] = round(shift, 2)
                if abs(limited) >= 0.1:
                    values = dsp.pitch_shift(values, limited, rate)
                    info["adapted"] = True
                    info["applied_semitones"] = round(info["applied_semitones"] + limited, 2)
                info["reference_target_hz"] = target
    return values, info


# ---------------------------------------------------------------------------
# Synthese
# ---------------------------------------------------------------------------

@dataclass
class SynthesisOptions:
    voice: Optional[str] = None
    preset: str = DEFAULT_PRESET_ID
    intensity: float = 1.0
    tempo: float = 1.0
    slow_mode: bool = False
    threads: int = 2
    speaker_id: Optional[int] = None
    engine: str = "piper"
    adapt_pitch: bool = False        # Stimmlage an die eigene Referenz anpassen
    pitch_semitones: float = 0.0     # manuelle Tonhöhen-Korrektur (Halbtöne)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "SynthesisOptions":
        preset = str(payload.get("preset") or DEFAULT_PRESET_ID)
        if preset not in PRESET_BY_ID:
            preset = DEFAULT_PRESET_ID
        try:
            intensity = float(payload.get("intensity", 1.0))
        except (TypeError, ValueError):
            intensity = 1.0
        try:
            tempo = float(payload.get("tempo", 1.0))
        except (TypeError, ValueError):
            tempo = 1.0
        speaker = payload.get("speaker_id")
        try:
            speaker_id = int(speaker) if speaker is not None and str(speaker) != "" else None
        except (TypeError, ValueError):
            speaker_id = None
        try:
            pitch = float(payload.get("pitch_semitones", 0.0) or 0.0)
        except (TypeError, ValueError):
            pitch = 0.0
        return cls(
            adapt_pitch=bool(payload.get("adapt_pitch", False)),
            pitch_semitones=max(-5.0, min(5.0, pitch)),
            voice=payload.get("voice") or None,
            preset=preset,
            intensity=max(0.0, min(2.0, intensity)),
            tempo=max(0.7, min(1.3, tempo)),
            slow_mode=bool(payload.get("slow_mode", False)),
            threads=max(1, min(int(payload.get("threads") or 2), 8)),
            speaker_id=speaker_id,
            engine=str(payload.get("engine") or "piper"),
        )


def _find_voice(voice_name: Optional[str]) -> Dict[str, Any]:
    voices = [voice for voice in hardware.find_piper_voices() if voice.get("usable")]
    if not voices:
        raise EngineError(
            "Es ist kein nutzbares Sprachmodell vorhanden. Bitte eine Piper-Stimme nach "
            "data/modelle/piper legen (Anleitung: README, Abschnitt „Sprachmodell“). "
            "Es wurde kein Modell erzeugt."
        )
    if voice_name:
        for voice in voices:
            if voice["name"] == voice_name or voice["filename"] == voice_name:
                return voice
        raise EngineError(f"Die gewählte Stimme „{voice_name}“ wurde nicht gefunden.")
    german = [voice for voice in voices if voice.get("is_german")]
    return (german or voices)[0]


def synthesize_to_wav(
    text: str,
    out_path: Path,
    options: SynthesisOptions,
    progress=None,
) -> Dict[str, Any]:
    """Erzeugt eine WAV-Datei mit lokaler Sprachsynthese. Gibt Metadaten zurück."""
    text = (text or "").strip()
    if not text:
        raise EngineError("Bitte einen Text eingeben, der vorgelesen werden soll.")
    if len(text) > 4000:
        raise EngineError("Der Text ist zu lang (höchstens 4000 Zeichen).")

    if options.engine == "xtts":
        return _synthesize_xtts(text, out_path, options, progress)

    if not hardware.piper_status()["available"]:
        raise EngineError(
            "Die lokale Sprach-Engine (Piper) ist nicht installiert. Es wurde kein Audio erzeugt. "
            "Bitte die Installation aus der README ausführen."
        )

    voice_meta = _find_voice(options.voice)
    preset = PRESET_BY_ID.get(options.preset, PRESET_BY_ID[DEFAULT_PRESET_ID])
    chunks = split_text(text)
    if not chunks:
        raise EngineError("Der Text enthält keine sprechbaren Wörter.")

    def report(percent: float, stage: str) -> None:
        if progress:
            progress(int(max(0, min(100, percent))), stage)

    report(1, "Vorbereitung …")
    voice = load_voice(
        Path(voice_meta["path"]),
        threads=options.threads,
        slow_mode=options.slow_mode,
        progress=report,
    )

    from piper.config import SynthesisConfig

    sample_rate = int(voice.config.sample_rate)
    # Piper-Tempo und späterer Feinschliff teilen sich die Langsamkeit:
    # der Stil selbst wird nicht doppelt verlangsamt.
    style_scale = 1.0 + (preset.length_scale - 1.0) * min(1.0, options.intensity)
    syn_config = SynthesisConfig(
        speaker_id=options.speaker_id if voice.config.num_speakers > 1 else None,
        length_scale=max(0.5, style_scale),
        noise_scale=preset.noise_scale,
        noise_w_scale=preset.noise_w_scale,
        normalize_audio=True,
        volume=1.0,
    )

    collected: List[float] = []
    total_chars = sum(len(chunk) for chunk in chunks) or 1
    done_chars = 0
    started = time.time()
    audio_seconds = 0.0

    for index, chunk in enumerate(chunks, start=1):
        if progress:
            report(10 + 72 * (done_chars / total_chars), f"Spreche Abschnitt {index} von {len(chunks)} …")
        try:
            for audio_chunk in voice.synthesize(chunk, syn_config=syn_config):
                array = audio_chunk.audio_float_array
                if getattr(array, "ndim", 1) > 1:
                    array = array.reshape(-1)
                collected.extend(float(value) for value in array.tolist())
                audio_seconds += len(array) / sample_rate
                if progress:
                    # Fortschritt auch innerhalb langer Abschnitte aktualisieren
                    share = min(1.0, len(array) / max(1, len(chunk) * sample_rate * 0.06))
                    report(
                        10 + 72 * ((done_chars + len(chunk) * share) / total_chars),
                        f"Spreche Abschnitt {index} von {len(chunks)} …",
                    )
        except (EngineError, JobCancelled):
            raise
        except Exception as exc:
            raise EngineError(
                "Die Sprachausgabe ist während der Berechnung fehlgeschlagen. "
                f"Technische Ursache: {type(exc).__name__}: {exc}"
            ) from exc
        done_chars += len(chunk)

    if not collected:
        raise EngineError(
            "Die Sprach-Engine hat kein Audio erzeugt. Bitte einen anderen Text testen "
            "oder ein anders Sprachmodell verwenden."
        )

    report(80, "Klang wird verfeinert …")
    styled = apply_style(
        collected,
        sample_rate,
        preset,
        intensity=options.intensity,
        tempo_user=options.tempo,
    )

    pitch_info: Dict[str, Any] = {}
    if options.adapt_pitch or abs(options.pitch_semitones) >= 0.05:
        report(85, "Stimmlage wird an die eigene Stimme angepasst …")
        styled, pitch_info = adapt_pitch_to_reference(styled, sample_rate, options)
        styled = peak_normalize(styled, -1.5)

    report(93, "WAV-Datei wird geschrieben …")
    write_wav(out_path, sample_rate, [styled])

    duration = len(styled) / sample_rate
    elapsed = time.time() - started
    report(98, "Fertig")

    return {
        "engine": "piper",
        "voice": voice_meta["name"],
        "voice_dataset": voice_meta.get("dataset"),
        "preset": preset.id,
        "preset_label": preset.label,
        "intensity": options.intensity,
        "tempo": options.tempo,
        "slow_mode": options.slow_mode,
        "threads": options.threads,
        "sample_rate": sample_rate,
        "duration_s": round(duration, 2),
        "compute_seconds": round(elapsed, 1),
        "realtime_factor": round(duration / elapsed, 2) if elapsed > 0 else None,
        "characters": len(text),
        "pitch": pitch_info,
        "is_clone": False,
        "note": (
            "Lokal mit dem Piper-Sprachmodell erzeugt und klanglich angepasst. "
            "Das ist keine Kopie einer echten Stimme, sondern die Stimme des lokalen Modells."
        ),
    }


# ---------------------------------------------------------------------------
# XTTS (optional)
# ---------------------------------------------------------------------------

def xtts_requirements() -> Dict[str, Any]:
    torch = hardware.torch_status()
    model = hardware.find_xtts()
    try:
        import TTS  # noqa: F401
        coqui = True
        coqui_error = None
    except Exception as exc:
        coqui = False
        coqui_error = f"{type(exc).__name__}: {exc}"
    system = hardware.system_report()
    available_mb = system.get("ram_available_mb")
    missing = []
    memory_note = None
    if available_mb is not None and available_mb < 4500:
        memory_note = (
            f"Nur {available_mb} MB Arbeitsspeicher frei. XTTS-v2 benötigt beim Laden "
            "etwa 4–5 GB – bitte alle anderen Programme schließen, sonst bricht der "
            "Vorgang mit einer Fehlermeldung ab (es wird dann nichts gespeichert)."
        )
    if not torch["available"]:
        missing.append("PyTorch (pip install torch --index-url https://download.pytorch.org/whl/cpu)")
    if not coqui:
        missing.append("Coqui TTS (pip install coqui-tts)")
    if not model.get("present"):
        missing.append("XTTS-v2-Modell in data/modelle/xtts")
    return {
        "available": not missing,
        "missing": missing,
        "memory_note": memory_note,
        "ram_available_mb": available_mb,
        "model": model,
        "torch": torch,
        "coqui": coqui,
        "coqui_error": coqui_error,
        "honest_note": (
            "XTTS-v2 ist ~2 GB groß und benötigt auf einer reinen CPU meist ein Vielfaches "
            "der Sprechdauer (oft 5–30×). Auf einem älteren Laptop ist das praktisch oft "
            "nicht nutzbar. Die App meldet dann einen Fehler – sie behauptet nie, eine "
            "Stimmkopie sei fertig."
        ),
    }


def _synthesize_xtts(
    text: str,
    out_path: Path,
    options: SynthesisOptions,
    progress=None,
) -> Dict[str, Any]:
    from . import storage

    requirements = xtts_requirements()
    if not requirements["available"]:
        raise EngineError(
            "Die eigene Stimmkopie (XTTS-v2) kann auf diesem Laptop nicht ausgeführt werden. "
            "Es fehlt: " + ", ".join(requirements["missing"]) + ". Es wurde kein Audio erzeugt."
        )

    master = storage.get_master()
    if not master:
        raise EngineError(
            "Für die Stimmkopie muss zuerst eine Master-Aufnahme festgelegt werden "
            "(Aufnahme auswählen → „Als Master festlegen“)."
        )
    reference = storage.reference_path(master["id"])
    if not reference:
        raise EngineError(
            "Die Referenzdatei der Master-Aufnahme fehlt. Bitte die Aufnahme erneut als Master festlegen."
        )

    def report(percent: float, stage: str) -> None:
        if progress:
            progress(int(max(0, min(100, percent))), stage)

    report(2, "XTTS-Modell wird geladen (kann dauern) …")
    try:
        import torch
        from TTS.api import TTS  # noqa: F401  (nur Verfügbarkeitsprüfung)

        torch.set_num_threads(max(1, options.threads))
        model_dir = XTTS_DIR
        if not any(model_dir.glob("*.pth")):
            candidates = list(model_dir.glob("**/*.pth"))
            model_path = candidates[0] if candidates else None
        else:
            model_path = next(model_dir.glob("*.pth"))
        if model_path is None:
            raise EngineError("Im Ordner data/modelle/xtts wurde keine model.pth gefunden.")
        config_path = model_path.parent / "config.json"

        report(8, "Modell wird initialisiert …")
        api = TTS(model_path=str(model_path), config_path=str(config_path))
        report(20, "Text wird gesprochen …")

        preset = PRESET_BY_ID.get(options.preset, PRESET_BY_ID[DEFAULT_PRESET_ID])
        speed = 1.0 / max(0.5, preset.length_scale * options.tempo)
        raw_path = out_path.with_suffix(".raw.wav")
        api.tts_to_file(
            text=text,
            speaker_wav=str(reference),
            language="de",
            file_path=str(raw_path),
            speed=speed,
            split_sentences=True,
        )
        report(88, "Klang wird verfeinert …")

        from .wav_io import read_wav, to_mono

        rate, data = read_wav(raw_path)
        mono = to_mono(data)
        styled = apply_style(
            mono, rate, preset, intensity=options.intensity, tempo_user=1.0
        )
        write_wav(out_path, rate, [styled])
        try:
            raw_path.unlink()
        except OSError:
            pass
        duration = len(styled) / rate
        return {
            "engine": "xtts",
            "voice": "XTTS-v2 (eigene Referenzstimme)",
            "preset": preset.id,
            "preset_label": preset.label,
            "sample_rate": rate,
            "duration_s": round(duration, 2),
            "characters": len(text),
            "is_clone": True,
            "reference": master.get("name"),
            "note": (
                "Mit dem lokalen XTTS-v2-Modell aus der Referenzaufnahme erzeugt. "
                "Bitte nur die eigene Stimme oder ausdrücklich erlaubte Aufnahmen verwenden."
            ),
        }
    except EngineError:
        raise
    except Exception as exc:
        raise EngineError(
            "Die Stimmkopie ist fehlgeschlagen. Es wurde keine Ergebnisdatei gespeichert. "
            f"Technische Ursache: {type(exc).__name__}: {exc}"
        ) from exc
