"""Hardware-Prüfung, Modell-Erkennung und Status der lokalen Sprachausgabe.

Die App prüft beim Start ehrlich, was auf dem Laptop möglich ist:
  * Wie viel Arbeitsspeicher ist frei?
  * Wie viele CPU-Kerne gibt es?
  * Ist genug Speicherplatz für ein Modell frei?
  * Liegt ein lokales Sprachmodell im Ordner `data/modelle`?
  * Ist die Piper-Engine (lokale CPU-Synthese) installiert?

Es wird nichts heruntergeladen und nichts geprüft, was einen Internetzugang
bräuchte.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import voice_licenses
from .config import (
    DATA_DIR,
    PIPER_DIR,
    XTTS_DIR,
    ensure_dirs,
)

_IMPORT_CACHE: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Systemwerte
# ---------------------------------------------------------------------------

def _total_ram_bytes() -> Optional[int]:
    try:
        import psutil  # optional
        return int(psutil.virtual_memory().total)
    except Exception:
        pass
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) * 1024
    except OSError:
        pass
    if os.name == "nt":
        try:
            import ctypes

            class MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemStatus()
            status.dwLength = ctypes.sizeof(MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys)
        except Exception:
            pass
    return None


def _available_ram_bytes() -> Optional[int]:
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except Exception:
        pass
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                values = {}
                for line in fh:
                    key, _, rest = line.partition(":")
                    values[key] = int(rest.split()[0]) * 1024
                return values.get("MemAvailable") or values.get("MemFree")
    except OSError:
        pass
    return None


def cpu_flags() -> Dict[str, Any]:
    flags = ""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/cpuinfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.lower().startswith("flags"):
                        flags = line.split(":", 1)[1]
                        break
    except OSError:
        pass
    lowered = flags.lower()
    return {
        "known": bool(flags),
        "avx": "avx" in lowered if flags else None,
        "avx2": "avx2" in lowered if flags else None,
        "sse4_1": "sse4_1" in lowered if flags else None,
    }


def system_report() -> Dict[str, Any]:
    ensure_dirs()
    cores = os.cpu_count() or 1
    total_ram = _total_ram_bytes()
    available_ram = _available_ram_bytes()
    try:
        usage = shutil.disk_usage(str(DATA_DIR))
        free_disk = usage.free
    except OSError:
        free_disk = 0

    warnings: List[Dict[str, str]] = []
    errors: List[Dict[str, str]] = []

    if cores <= 1:
        warnings.append({
            "severity": "warn",
            "text": "Nur ein CPU-Kern erkannt. Die Sprachausgabe wird sehr langsam sein – bitte den langsamen CPU-Modus verwenden.",
        })
    elif cores == 2:
        warnings.append({
            "severity": "info",
            "text": "Zwei CPU-Kerne erkannt. Der langsame CPU-Modus wird empfohlen.",
        })

    if available_ram is not None:
        available_mb = available_ram / (1024 * 1024)
        if available_mb < 512:
            errors.append({
                "severity": "error",
                "text": f"Nur {available_mb:.0f} MB Arbeitsspeicher frei. Ein Sprachmodell kann so nicht geladen werden.",
            })
        elif available_mb < 1024:
            warnings.append({
                "severity": "warn",
                "text": f"Nur {available_mb:.0f} MB Arbeitsspeicher frei. Bitte alle anderen Programme schließen, bevor die Sprachausgabe startet.",
            })

    if free_disk and free_disk < 300 * 1024 * 1024:
        errors.append({
            "severity": "error",
            "text": "Weniger als 300 MB freier Speicherplatz. Bitte Speicher freigeben, bevor ein Modell abgelegt wird.",
        })

    flags = cpu_flags()
    if flags.get("known") and flags.get("sse4_1") is False:
        warnings.append({
            "severity": "warn",
            "text": "Dieser Prozessor unterstützt SSE4.1 nicht. Die lokale Sprachausgabe benötigt meist SSE4.1 oder neuer.",
        })

    return {
        "os": f"{sys.platform}",
        "python": sys.version.split()[0],
        "cpu_cores": cores,
        "cpu_flags": flags,
        "ram_total_mb": round(total_ram / (1024 * 1024)) if total_ram else None,
        "ram_available_mb": round(available_ram / (1024 * 1024)) if available_ram else None,
        "disk_free_mb": round(free_disk / (1024 * 1024)),
        "data_dir": str(DATA_DIR),
        "warnings": warnings,
        "errors": errors,
        "sufficient": not errors,
    }


# ---------------------------------------------------------------------------
# Engine-Erkennung
# ---------------------------------------------------------------------------

def piper_status() -> Dict[str, Any]:
    """Prüft, ob die Piper-Engine (lokale CPU-Synthese) importierbar ist."""
    if "piper" in _IMPORT_CACHE:
        return _IMPORT_CACHE["piper"]
    info: Dict[str, Any] = {"available": False, "version": None, "error": None, "numpy": None}
    try:
        import importlib.metadata as md

        info["version"] = md.version("piper-tts")
    except Exception:
        pass
    try:
        from piper import PiperVoice  # noqa: F401  (Verfügbarkeitsprüfung)
        import numpy  # noqa: F401  (Verfügbarkeitsprüfung)

        info["available"] = True
        info["numpy"] = getattr(__import__("numpy"), "__version__", None)
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
    _IMPORT_CACHE["piper"] = info
    return info


def onnxruntime_status() -> Dict[str, Any]:
    try:
        import onnxruntime as ort

        return {
            "available": True,
            "version": ort.__version__,
            "providers": ort.get_available_providers(),
        }
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def torch_status() -> Dict[str, Any]:
    try:
        import torch

        return {"available": True, "version": torch.__version__, "cuda": torch.cuda.is_available()}
    except Exception:
        return {"available": False, "version": None, "cuda": False}


# ---------------------------------------------------------------------------
# Lokale Modelle finden
# ---------------------------------------------------------------------------

def _voice_meta(model_path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    audio = config.get("audio") or {}
    espeak = config.get("espeak") or {}
    dataset = config.get("dataset") or (config.get("language") or {}).get("name")
    language = (
        (config.get("language") or {}).get("code")
        or espeak.get("voice")
        or "unbekannt"
    )
    name = model_path.stem
    parts = name.split("-")
    quality = parts[-1] if len(parts) >= 3 else "unbekannt"
    license_info = voice_licenses.voice_license(name) or {}
    return {
        "name": name,
        "license": license_info.get("license"),
        "commercial_use": license_info.get("commercial"),
        "attribution": license_info.get("attribution"),
        "filename": model_path.name,
        "path": str(model_path),
        "language": language,
        "dataset": dataset,
        "quality": quality,
        "sample_rate": audio.get("sample_rate"),
        "num_speakers": config.get("num_speakers", 1),
        "speaker_id_map": config.get("speaker_id_map") or {},
        "size_mb": round(model_path.stat().st_size / (1024 * 1024), 1) if model_path.exists() else None,
        "is_german": str(language).lower().startswith("de"),
    }


def find_piper_voices() -> List[Dict[str, Any]]:
    """Sucht lokale Piper-Stimmen (*.onnx + passende *.onnx.json)."""
    voices: List[Dict[str, Any]] = []
    if not PIPER_DIR.exists():
        return voices
    for model_path in sorted(PIPER_DIR.glob("**/*.onnx")):
        config_path = Path(str(model_path) + ".json")
        if not config_path.exists():
            voices.append({
                "name": model_path.stem,
                "filename": model_path.name,
                "path": str(model_path),
                "error": "Die Konfigurationsdatei fehlt (…onnx.json).",
                "is_german": False,
                "usable": False,
            })
            continue
        try:
            with config_path.open("r", encoding="utf-8") as fh:
                config = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            voices.append({
                "name": model_path.stem,
                "filename": model_path.name,
                "path": str(model_path),
                "error": f"Konfiguration nicht lesbar: {exc}",
                "is_german": False,
                "usable": False,
            })
            continue
        meta = _voice_meta(model_path, config)
        meta["usable"] = True
        meta["error"] = None
        voices.append(meta)
    voices.sort(key=lambda item: (not item.get("is_german"), item.get("name", "")))
    return voices


# Ein lauffähiges XTTS-v2-Modell besteht aus allen fünf Dateien. Fehlt eine,
# bricht das Laden später mit einer schwer verständlichen Fehlermeldung ab –
# deshalb gilt das Modell erst dann als vorhanden, wenn alles da ist.
XTTS_REQUIRED_FILES = ("model.pth", "config.json", "vocab.json", "speakers_xtts.pth", "mel_stats.pth")


def find_xtts() -> Dict[str, Any]:
    """Prüft, ob das XTTS-v2-Modell vollständig lokal liegt (eigene Stimmkopie)."""
    if not XTTS_DIR.exists():
        return {
            "present": False,
            "size_mb": 0,
            "missing": list(XTTS_REQUIRED_FILES),
            "found_files": [],
            "any_files": False,
            "path": str(XTTS_DIR),
        }
    files = [p for p in XTTS_DIR.glob("**/*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    names = {p.name for p in files}
    found = sorted(names & set(XTTS_REQUIRED_FILES))
    missing = [name for name in XTTS_REQUIRED_FILES if name not in names]
    return {
        "present": not missing,
        "size_mb": round(total / (1024 * 1024), 1),
        "missing": missing,
        "found_files": found,
        # Nur relevante Modelldateien zählen – ein leeres Verzeichnis (oder nur
        # eine .gitkeep-Datei) ist kein "unvollständiges Modell".
        "any_files": bool(found),
        "path": str(XTTS_DIR),
    }


def status() -> Dict[str, Any]:
    """Gesamtstatus für die Oberfläche und die Startprüfung."""
    ensure_dirs()
    system = system_report()
    piper = piper_status()
    ort = onnxruntime_status()
    voices = find_piper_voices()
    german_voices = [voice for voice in voices if voice.get("is_german") and voice.get("usable")]
    xtts = find_xtts()
    torch = torch_status()

    ready = bool(system["sufficient"] and piper["available"] and german_voices)

    messages: List[Dict[str, str]] = []
    messages.extend(system["errors"])
    messages.extend(system["warnings"])

    if not piper["available"]:
        messages.append({
            "severity": "error",
            "text": (
                "Die lokale Sprach-Engine (Piper) ist nicht installiert. "
                "Bitte die Installation aus der README ausführen – ohne Internet "
                "kann die Sprachausgabe nicht starten."
                + (f" Details: {piper['error']}" if piper.get("error") else "")
            ),
        })
    if not onnxruntime_status()["available"]:
        messages.append({
            "severity": "error",
            "text": "onnxruntime fehlt. Ohne diese Rechen-Engine kann kein Sprachmodell ausgeführt werden.",
        })
    if not german_voices:
        messages.append({
            "severity": "warn",
            "text": (
                "Es liegt noch kein deutsches Sprachmodell lokal vor. Bitte eine passende "
                "Stimme in den Ordner data/modelle/piper legen (Anleitung in der README)."
            ),
        })
    if xtts.get("present") and not torch.get("available"):
        messages.append({
            "severity": "warn",
            "text": (
                "Das XTTS-v2-Modell ist vorhanden, aber PyTorch fehlt – die eigene "
                'Stimmkopie ist damit nicht nutzbar. Installieren mit: pip install "coqui-tts[cpu]"'
            ),
        })
    elif not xtts.get("present") and xtts.get("any_files"):
        messages.append({
            "severity": "warn",
            "text": (
                "Das XTTS-v2-Modell in data/modelle/xtts ist unvollständig – es fehlt: "
                + ", ".join(xtts.get("missing") or [])
                + ". Vervollständigen mit: python -m app.voice_setup --xtts"
            ),
        })

    if not ready:
        messages.append({
            "severity": "info",
            "text": (
                "Ehrlicher Hinweis: Solange die oben genannten Punkte nicht erfüllt sind, "
                "kann die App keine Stimme erzeugen. Es wird dann auch kein Modell als "
                "„erstellt“ gemeldet."
            ),
        })

    return {
        "ready": ready,
        "system": system,
        "piper": piper,
        "onnxruntime": ort,
        "torch": torch,
        "voices": voices,
        "german_voice_count": len(german_voices),
        "xtts": xtts,
        "messages": messages,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def recommended_mode() -> Dict[str, Any]:
    """Empfehlung für den Rechenmodus anhand der Hardware."""
    cores = os.cpu_count() or 1
    available = _available_ram_bytes()
    available_mb = available / (1024 * 1024) if available else None
    slow = cores <= 2 or (available_mb is not None and available_mb < 1500)
    return {
        "slow_mode": slow,
        "reason": (
            "Wenige CPU-Kerne oder wenig freier Arbeitsspeicher erkannt – der langsame CPU-Modus "
            "ist die sichere Wahl."
            if slow
            else "Die Hardware reicht für den normalen CPU-Modus; der langsame Modus bleibt als Option verfügbar."
        ),
        # Bei vielen Kernen bringt mehr als 4 Threads kaum Tempo, kostet aber Strom/Wärme
        "threads": max(1, min(cores, 4)),
        "max_threads": max(1, min(cores, 8)),
    }
