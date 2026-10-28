"""Lokale Ablage für Aufnahmen, Master-Datei und Ergebnisse.

Alles liegt in `data/` auf dem Laptop. Es wird nie etwas hochgeladen.
Originaldateien werden niemals überschrieben: jede Aufnahme bekommt eine
eigene, eindeutige ID.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import analysis as analysis_mod
from .config import MASTERS_DIR, RECORDINGS_DIR, RESULTS_DIR, XTTS_DIR
from .wav_io import WavError, wav_info

MASTER_SELECTION_FILE = MASTERS_DIR / "auswahl.json"
BASE_VOICE_FILE = MASTERS_DIR / "ausgangsstimme.json"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Aufnahmen
# ---------------------------------------------------------------------------

def save_recording(
    source: Path,
    *,
    display_name: str,
    kind: str = "import",
    original_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Übernimmt eine WAV-Datei in die lokale Bibliothek (Kopie, Original bleibt unberührt)."""
    info = wav_info(source)  # wirft WavError bei ungültigen Dateien
    if info["duration_s"] <= 0:
        raise WavError("Die Audiodatei ist leer.")

    rec_id = new_id("auf-")
    target = RECORDINGS_DIR / f"{rec_id}.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

    record: Dict[str, Any] = {
        "id": rec_id,
        "kind": kind,                       # "aufnahme" (Mikrofon) oder "import"
        "name": display_name,
        "original_name": original_name or source.name,
        "filename": target.name,
        "created_at": _now(),
        "size_bytes": target.stat().st_size,
        "info": info,
    }
    try:
        record["analysis"] = analysis_mod.analyze(target)
    except WavError as exc:
        record["analysis"] = {"error": str(exc)}

    _write_json(RECORDINGS_DIR / f"{rec_id}.json", record)
    return record


def update_recording(record: Dict[str, Any]) -> None:
    """Aktualisiert die Metadaten einer Aufnahme (z. B. nach neuer Analyse)."""
    rec_id = record.get("id")
    if not rec_id or not _is_safe_id(str(rec_id)):
        raise WavError("Ungültige Aufnahme-ID.")
    _write_json(RECORDINGS_DIR / f"{rec_id}.json", record)


def list_recordings() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    master = get_master_id()
    if not RECORDINGS_DIR.exists():
        return items
    for meta_path in sorted(RECORDINGS_DIR.glob("*.json")):
        record = _read_json(meta_path)
        if not record:
            continue
        wav_path = RECORDINGS_DIR / record.get("filename", "")
        if not wav_path.exists():
            continue
        record["is_master"] = record.get("id") == master
        record["file_exists"] = True
        items.append(record)
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items


def get_recording(rec_id: str) -> Optional[Dict[str, Any]]:
    if not _is_safe_id(rec_id):
        return None
    record = _read_json(RECORDINGS_DIR / f"{rec_id}.json")
    if not record:
        return None
    record["is_master"] = rec_id == get_master_id()
    return record


def recording_path(rec_id: str) -> Optional[Path]:
    record = get_recording(rec_id)
    if not record:
        return None
    path = RECORDINGS_DIR / record.get("filename", "")
    return path if path.exists() else None


def delete_recording(rec_id: str) -> bool:
    if not _is_safe_id(rec_id):
        return False
    deleted = False
    for suffix in (".wav", ".json"):
        path = RECORDINGS_DIR / f"{rec_id}{suffix}"
        if path.exists():
            path.unlink()
            deleted = True
    reference = MASTERS_DIR / f"{rec_id}_referenz.wav"
    if reference.exists():
        reference.unlink()
    if get_master_id() == rec_id:
        clear_master()
        clear_base_voice_profile()
    return deleted


# ---------------------------------------------------------------------------
# Master-Auswahl
# ---------------------------------------------------------------------------

def get_master_id() -> Optional[str]:
    payload = _read_json(MASTER_SELECTION_FILE) or {}
    master_id = payload.get("recording_id")
    return master_id if isinstance(master_id, str) else None


def get_master() -> Optional[Dict[str, Any]]:
    master_id = get_master_id()
    if not master_id:
        return None
    record = get_recording(master_id)
    if not record:
        clear_master()
        return None
    record["reference_path"] = reference_path(master_id)
    return record


def set_master(rec_id: str, reference: Optional[Path]) -> Dict[str, Any]:
    payload = {
        "recording_id": rec_id,
        "created_at": _now(),
        "reference": reference.name if reference else None,
    }
    _write_json(MASTER_SELECTION_FILE, payload)
    return payload


def clear_master() -> None:
    if MASTER_SELECTION_FILE.exists():
        MASTER_SELECTION_FILE.unlink()


def save_base_voice_profile(rec_id: str, profile: Dict[str, Any], extra: Dict[str, Any] | None = None) -> None:
    """Speichert das Stimmprofil der Ausgangsstimme lokal (nur auf diesem Laptop)."""
    payload: Dict[str, Any] = {
        "recording_id": rec_id,
        "created_at": _now(),
        "profile": profile,
    }
    if extra:
        payload.update(extra)
    _write_json(BASE_VOICE_FILE, payload)


def get_base_voice_profile() -> Optional[Dict[str, Any]]:
    return _read_json(BASE_VOICE_FILE)


def clear_base_voice_profile() -> None:
    if BASE_VOICE_FILE.exists():
        BASE_VOICE_FILE.unlink()


def reference_path(rec_id: str) -> Optional[Path]:
    path = MASTERS_DIR / f"{rec_id}_referenz.wav"
    return path if path.exists() else None


# ---------------------------------------------------------------------------
# Ergebnisse (erzeugte Sprachdateien)
# ---------------------------------------------------------------------------

def save_result(source: Path, *, name: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    res_id = new_id("erg-")
    target = RESULTS_DIR / f"{res_id}.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    try:
        info = wav_info(target)
    except WavError:
        info = {}
    record = {
        "id": res_id,
        "name": name,
        "filename": target.name,
        "created_at": _now(),
        "size_bytes": target.stat().st_size,
        "info": info,
        **meta,
    }
    _write_json(RESULTS_DIR / f"{res_id}.json", record)
    return record


def list_results() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not RESULTS_DIR.exists():
        return items
    for meta_path in sorted(RESULTS_DIR.glob("*.json")):
        record = _read_json(meta_path)
        if not record:
            continue
        if not (RESULTS_DIR / record.get("filename", "")).exists():
            continue
        items.append(record)
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items


def result_path(res_id: str) -> Optional[Path]:
    if not _is_safe_id(res_id):
        return None
    record = _read_json(RESULTS_DIR / f"{res_id}.json")
    if not record:
        return None
    path = RESULTS_DIR / record.get("filename", "")
    return path if path.exists() else None


def delete_result(res_id: str) -> bool:
    if not _is_safe_id(res_id):
        return False
    deleted = False
    for suffix in (".wav", ".json"):
        path = RESULTS_DIR / f"{res_id}{suffix}"
        if path.exists():
            path.unlink()
            deleted = True
    return deleted


# ---------------------------------------------------------------------------
# Speicherübersicht
# ---------------------------------------------------------------------------

def storage_summary() -> Dict[str, Any]:
    def _dir_size(directory: Path) -> int:
        total = 0
        if directory.exists():
            for path in directory.rglob("*"):
                if path.is_file():
                    try:
                        total += path.stat().st_size
                    except OSError:
                        continue
        return total

    return {
        "aufnahmen_bytes": _dir_size(RECORDINGS_DIR),
        "ergebnisse_bytes": _dir_size(RESULTS_DIR),
        "modelle_bytes": _dir_size(XTTS_DIR.parent),
    }


def _is_safe_id(value: str) -> bool:
    return bool(value) and all(ch.isalnum() or ch in "-_" for ch in value) and len(value) <= 64
