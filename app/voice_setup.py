"""Stimmen-Helfer: lädt eine deutsche Piper-Stimme ausdrücklich auf Wunsch.

Diese Datei ist die **einzige** Stelle im Projekt, die etwas aus dem Internet
holt – und sie tut das nur, wenn du sie selbst startest. Die Web-App selbst
bleibt vollständig offline und lädt niemals Modelle nach.

Benutzung (im Projektordner, einmalig mit Internet):

    .venv/bin/python -m app.voice_setup                  # deutsche Stimmen anzeigen
    .venv/bin/python -m app.voice_setup de_DE-thorsten-medium
    .venv/bin/python -m app.voice_setup --installed      # nur lokale Stimmen (ohne Internet)

Die Dateien landen in ``data/modelle/piper`` und bleiben ausschließlich auf
diesem Laptop. Sie gehören nicht zu GitHub (siehe .gitignore).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import hardware
from .config import PIPER_DIR, ensure_dirs

TIMEOUT_SECONDS = 60
USER_AGENT = "StimmenClonewandler/1.0 (lokale Stimmen-Installation)"

# Empfehlung für einen älteren Laptop mit 2-Kern-Klasse-CPU
RECOMMENDED = "de_DE-thorsten-medium"


def _voices_json_url() -> str:
    """Adresse der offiziellen Piper-Stimmenliste (nur bei Bedarf geladen)."""
    from piper.download_voices import VOICES_JSON

    return VOICES_JSON


def _fetch_voices() -> Dict[str, dict]:
    """Lädt die Stimmenliste (JSON) von der offiziellen Piper-Quelle."""
    url = _voices_json_url()
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (URLError, HTTPError, TimeoutError) as exc:
        raise ConnectionError(
            "Die Stimmenliste konnte nicht geladen werden. Bitte die Internetverbindung prüfen. "
            f"Technische Ursache: {type(exc).__name__}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ConnectionError(f"Die Stimmenliste war nicht lesbar: {exc}") from exc


def _total_size_mb(entry: dict) -> float:
    total = 0
    for info in (entry.get("files") or {}).values():
        try:
            total += int(info.get("size_bytes") or 0)
        except (TypeError, ValueError):
            continue
    return round(total / (1024 * 1024), 1)


def _german_voices(data: Dict[str, dict]) -> List[dict]:
    """Filtert die deutschen Stimmen aus der Stimmenliste und sortiert sie."""
    voices = []
    for name, entry in (data or {}).items():
        if not str(name).lower().startswith("de_de-"):
            continue
        voices.append({
            "name": name,
            "quality": (entry or {}).get("quality") or name.rsplit("-", 1)[-1],
            "size_mb": _total_size_mb(entry or {}),
            "num_speakers": (entry or {}).get("num_speakers", 1),
            "recommended": name == RECOMMENDED,
        })
    voices.sort(key=lambda voice: (not voice["recommended"], voice["size_mb"], voice["name"]))
    return voices


def list_voices(fetcher: Optional[Callable[[], Dict[str, dict]]] = None) -> List[dict]:
    """Listet deutsche Stimmen (Standard: offizielle Piper-Quelle)."""
    source = fetcher or _fetch_voices
    return _german_voices(source())


def installed_voices() -> List[dict]:
    """Bereits lokal vorhandene Stimmen (ohne Internet)."""
    return [
        {
            "name": voice.get("name"),
            "size_mb": voice.get("size_mb"),
            "is_german": voice.get("is_german"),
            "usable": voice.get("usable"),
        }
        for voice in hardware.find_piper_voices()
    ]


def download_voice(
    name: str,
    *,
    force: bool = False,
    downloader: Optional[Callable[..., None]] = None,
) -> dict:
    """Lädt eine Stimme in den lokalen Modellordner und prüft das Ergebnis."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Bitte den Namen einer Stimme angeben, z. B. de_DE-thorsten-medium.")

    ensure_dirs()
    if downloader is None:
        from piper.download_voices import download_voice as piper_download

        downloader = piper_download

    target_dir = Path(PIPER_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        downloader(name, target_dir, force_redownload=force)
    except ValueError as exc:
        raise ValueError(
            f"Der Stimmenname „{name}“ ist ungültig. Erwartetes Format: "
            "de_DE-<name>-<qualität>, z. B. de_DE-thorsten-medium."
        ) from exc
    except (URLError, HTTPError, TimeoutError) as exc:
        raise ConnectionError(
            "Der Download ist fehlgeschlagen. Bitte die Internetverbindung prüfen und "
            f"den Befehl erneut starten. Technische Ursache: {type(exc).__name__}: {exc}"
        ) from exc

    model = target_dir / f"{name}.onnx"
    config = target_dir / f"{name}.onnx.json"
    missing = [path.name for path in (model, config) if not path.exists() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(
            "Der Download war unvollständig – es fehlt: " + ", ".join(missing) + ". "
            "Bitte den Befehl erneut ausführen (ggf. mit --force)."
        )

    return {
        "name": name,
        "model": model.name,
        "config": config.name,
        "size_mb": round(model.stat().st_size / (1024 * 1024), 1),
        "path": str(target_dir),
        "usable": any(
            voice.get("name") == name and voice.get("usable")
            for voice in hardware.find_piper_voices()
        ),
    }


# ---------------------------------------------------------------------------
# Kommandozeile
# ---------------------------------------------------------------------------

def _print_list(voices: List[dict]) -> None:
    if not voices:
        print("Es wurden keine deutschen Stimmen gefunden.")
        return
    print("\nDeutsche Piper-Stimmen (Auswahl aus der offiziellen Liste):\n")
    print(f"  {'Name':38} {'Qualität':10} {'Größe':>9}")
    print("  " + "-" * 60)
    for voice in voices:
        marker = "  ← empfohlen" if voice["recommended"] else ""
        print(f"  {voice['name']:38} {voice['quality']:10} {voice['size_mb']:>7} MB{marker}")
    print("\nInstallieren mit:")
    print(f"  .venv/bin/python -m app.voice_setup {RECOMMENDED}")
    print("\nHinweis: Die Stimmen haben eigene Lizenzen – bitte in der jeweiligen")
    print("Modellbeschreibung nachsehen, bevor du sie verwendest.\n")


def _print_installed() -> None:
    voices = installed_voices()
    if not voices:
        print(f"Im Ordner {PIPER_DIR} liegt noch keine Stimme.")
        print(f"Installieren mit: .venv/bin/python -m app.voice_setup {RECOMMENDED}")
        return
    print(f"\nLokal vorhandene Stimmen in {PIPER_DIR}:\n")
    for voice in voices:
        state = "nutzbar" if voice.get("usable") else "unvollständig"
        lang = "Deutsch" if voice.get("is_german") else "andere Sprache"
        print(f"  {voice['name']:38} {voice.get('size_mb') or '?':>7} MB  {lang}, {state}")
    print()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.voice_setup",
        description="Lädt eine deutsche Piper-Stimme nach data/modelle/piper (nur auf Wunsch).",
    )
    parser.add_argument("voice", nargs="?", help="Stimmenname, z. B. de_DE-thorsten-medium")
    parser.add_argument("--list", action="store_true", help="Verfügbare deutsche Stimmen anzeigen")
    parser.add_argument("--installed", action="store_true", help="Nur lokale Stimmen anzeigen (ohne Internet)")
    parser.add_argument("--force", action="store_true", help="Vorhandene Dateien erneut herunterladen")
    args = parser.parse_args(argv)

    if args.installed:
        _print_installed()
        return 0

    if args.list or not args.voice:
        try:
            _print_list(list_voices())
        except ConnectionError as exc:
            print(f"[!] {exc}")
            print("Ohne Internet kannst du nur vorhandene Stimmen prüfen:")
            print("    .venv/bin/python -m app.voice_setup --installed")
            return 1
        return 0

    print(f"[i] Lade „{args.voice}“ nach {PIPER_DIR} …")
    try:
        result = download_voice(args.voice, force=args.force)
    except (ValueError, ConnectionError, RuntimeError) as exc:
        print(f"[!] {exc}")
        return 1

    print(f"[ok] Stimme gespeichert: {result['model']} ({result['size_mb']} MB)")
    print(f"     Konfiguration: {result['config']}")
    print(f"     Ordner: {result['path']}")
    if not result["usable"]:
        print("[i] Die Dateien liegen jetzt vor. In der App auf „Erneut prüfen“ klicken.")
    else:
        print("[i] Die Stimme ist sofort nutzbar – in der App auf „Erneut prüfen“ klicken.")
    print("\nHinweis: Diese Modelldateien bleiben lokal und gehören nicht zu GitHub.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
