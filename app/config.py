"""Zentrale Pfade und Einstellungen.

Wichtig: Alle Pfade zeigen ausschließlich auf Ordner innerhalb dieses Projekts
(lokal auf dem Laptop). Es gibt in dieser Datei keinerlei Netzwerk-, Cloud- oder
API-Konfiguration – die App spricht mit keinem Server im Internet.
"""

from __future__ import annotations

import os
from pathlib import Path

# Projektwurzel (ein Verzeichnis über app/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Lokaler Datenordner. Kann über die Umgebungsvariable SCW_DATA_DIR verschoben werden.
DATA_DIR = Path(os.environ.get("SCW_DATA_DIR", BASE_DIR / "data")).resolve()

# Lokale Arbeitsverzeichnisse
RECORDINGS_DIR = DATA_DIR / "aufnahmen"        # importierte und aufgenommene Originale
RESULTS_DIR = DATA_DIR / "ergebnisse"          # erzeugte Sprachdateien
MASTERS_DIR = DATA_DIR / "master"              # Referenz-/Master-Aufbereitung für das Modell
TMP_DIR = DATA_DIR / "tmp"                     # temporäre Dateien
MODELS_DIR = DATA_DIR / "modelle"              # lokale Sprachmodelle
PIPER_DIR = MODELS_DIR / "piper"               # Piper-Stimmen (*.onnx + *.onnx.json)
XTTS_DIR = MODELS_DIR / "xtts"                 # optionales XTTS-v2-Modell

STATIC_DIR = BASE_DIR / "app" / "static"

# Diese Datei enthält den tatsächlich benutzten Port (falls 8765 belegt war),
# damit das Startskript den Browser auf die richtige Adresse schicken kann.
PORT_FILE = DATA_DIR / ".port"

# Server: standardmäßig NUR localhost (kein Zugriff aus dem Netzwerk).
HOST = os.environ.get("SCW_HOST", "127.0.0.1")
PORT = int(os.environ.get("SCW_PORT", "8765"))

# Grenzen
MAX_UPLOAD_MB = 200
MAX_TEXT_CHARS = 4000
MAX_REFERENCE_SECONDS = 30.0   # Länge der Referenzdatei für das Modell
PREVIEW_BITS = 16

APP_NAME = "StimmenClonewandler"
APP_VERSION = "1.0.0"

PRIVACY_NOTICE = (
    "Alle Audiodateien und Sprachmodelle werden ausschließlich auf diesem Laptop "
    "verarbeitet. Es erfolgt kein Upload ins Internet."
)

# Ordner, die beim Start existieren müssen
DATA_SUBDIRS = (
    RECORDINGS_DIR,
    RESULTS_DIR,
    MASTERS_DIR,
    TMP_DIR,
    MODELS_DIR,
    PIPER_DIR,
    XTTS_DIR,
)


def ensure_dirs() -> None:
    """Legt alle lokalen Arbeitsverzeichnisse an (idempotent)."""
    for directory in DATA_SUBDIRS:
        directory.mkdir(parents=True, exist_ok=True)


def relative_to_data(path: Path) -> str:
    """Gibt einen Pfad relativ zum Datenordner zurück (für Anzeige/Logs)."""
    try:
        return str(Path(path).resolve().relative_to(DATA_DIR))
    except Exception:
        return str(path)
