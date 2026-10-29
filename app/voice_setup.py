"""Stimmen-Helfer: lädt deutsche Piper-Stimmen oder das XTTS-v2-Modell auf Wunsch.

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
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import hardware
from .config import PIPER_DIR, XTTS_DIR, ensure_dirs

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
# Optional: XTTS-v2 (echte Stimmnachbildung aus der eigenen Aufnahme)
# ---------------------------------------------------------------------------

XTTS_REPO = "tts-hub/XTTS-v2"
XTTS_URL = f"https://huggingface.co/{XTTS_REPO}/resolve/main"
XTTS_LICENSE_NAME = "Coqui Public Model License (CPML)"
XTTS_LICENSE_URL = "https://coqui.ai/cpml"
# Beim Laden braucht das Modell rund 4 GB – plus Platz für die Dateien selbst.
XTTS_MIN_FREE_MB = 2600

# Dateien, die zusammen das XTTS-v2-Modell ergeben (Stand: tts-hub/XTTS-v2).
# "size" dient der Fortschrittsanzeige, "sha256" der Prüfung nach dem Download.
# Für die kleinen Dateien gibt die Modellablage keine Prüfsumme heraus – dort
# wird nur geprüft, dass die Datei nicht leer ist.
XTTS_FILES = {
    "model.pth": {
        "size": 1_867_929_383,
        "sha256": "d5822cb1d4bf97c418855e326562a934caa20cef01ebf4c90bf792df0fd5b99e",
    },
    "config.json": {"size": 4_031, "sha256": None},
    "vocab.json": {"size": 361_219, "sha256": None},
    "speakers_xtts.pth": {
        "size": 7_754_818,
        "sha256": "f0f6137c19a4eab0cbbe4c99b5babacf68b1746e50da90807708c10e645b943b",
    },
    "mel_stats.pth": {
        "size": 1_067,
        "sha256": "1f69422a8a8f344c4fca2f0c6b8d41d2151d6615b7321e48e6bb15ae949b119c",
    },
}

XTTS_REQUIRED_FILES = tuple(XTTS_FILES)


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def _download_file(
    url: str,
    dest: Path,
    expected_size: Optional[int] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Lädt eine Datei nach ``dest`` (erst ``.part``, dann umbenennen)."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    part = dest.with_name(dest.name + ".part")
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        total = int(response.headers.get("Content-Length") or expected_size or 0)
        done = 0
        with open(part, "wb") as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if on_progress:
                    on_progress(done, total)
    part.replace(dest)


def xtts_status(target_dir: Optional[Path] = None) -> dict:
    """Prüft, ob das XTTS-v2-Modell vollständig lokal liegt."""
    target = Path(target_dir or XTTS_DIR)
    paths = {name: target / name for name in XTTS_REQUIRED_FILES}
    missing = [
        name for name, path in paths.items()
        if not path.is_file() or path.stat().st_size == 0
    ]
    present_sizes = [path.stat().st_size for path in paths.values() if path.is_file()]
    required_mb = sum(info["size"] for info in XTTS_FILES.values()) / (1024 * 1024)
    return {
        "path": str(target),
        "present": not missing,
        "complete": not missing,
        "missing": missing,
        "size_mb": round(sum(present_sizes) / (1024 * 1024), 1),
        "required_mb": round(required_mb, 1),
        "license": XTTS_LICENSE_NAME,
    }


def _verify_xtts_file(path: Path, info: dict) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(
            f"Die Datei {path.name} wurde nicht geschrieben. Bitte den Befehl erneut starten."
        )
    expected_hash = info.get("sha256")
    if expected_hash and _sha256(path) != expected_hash:
        try:
            path.unlink()
        except OSError:
            pass
        raise RuntimeError(
            f"Die Datei {path.name} stimmt nicht mit der offiziellen Prüfsumme überein "
            "und wurde gelöscht. Bitte den Download erneut starten."
        )


def download_xtts(
    target_dir: Optional[Path] = None,
    *,
    force: bool = False,
    fetcher: Optional[Callable[..., None]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Lädt das XTTS-v2-Modell (~1,9 GB) nach ``data/modelle/xtts``.

    Nur diese Funktion holt etwas aus dem Internet, und nur wenn du sie selbst
    startest. Vorher wird geprüft, ob genug freier Speicher vorhanden ist.
    """
    ensure_dirs()
    target = Path(target_dir or XTTS_DIR)
    target.mkdir(parents=True, exist_ok=True)

    free_mb = shutil.disk_usage(target).free // (1024 * 1024)
    if free_mb < XTTS_MIN_FREE_MB:
        raise RuntimeError(
            f"Auf diesem Laptop sind nur {free_mb} MB frei. Das XTTS-v2-Modell braucht "
            f"rund 1,9 GB Platz (empfohlen: {XTTS_MIN_FREE_MB} MB frei). Bitte erst "
            "Platz schaffen – es wurde nichts heruntergeladen."
        )

    if fetcher is None:
        fetcher = _download_file

    downloaded: List[str] = []
    skipped: List[str] = []
    for name, info in XTTS_FILES.items():
        dest = target / name
        if dest.is_file() and dest.stat().st_size > 0 and not force:
            skipped.append(name)
            continue
        url = f"{XTTS_URL}/{name}"
        try:
            fetcher(url, dest, info["size"], on_progress)
        except (URLError, HTTPError, TimeoutError, OSError) as exc:
            raise ConnectionError(
                "Der Download des XTTS-v2-Modells ist fehlgeschlagen. Bitte die "
                "Internetverbindung prüfen und den Befehl erneut starten – bereits "
                f"geladene Dateien werden wiederverwendet. Technische Ursache: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        _verify_xtts_file(dest, info)
        downloaded.append(name)

    status = xtts_status(target)
    if not status["present"]:
        raise RuntimeError(
            "Der Download war unvollständig – es fehlt: "
            + ", ".join(status["missing"])
            + ". Bitte den Befehl erneut starten."
        )
    return {
        **status,
        "downloaded": downloaded,
        "skipped": skipped,
        "total_mb": status["size_mb"],
    }


def _print_xtts_plan(status: dict) -> None:
    print("\nXTTS-v2 – echte Stimmnachbildung aus deiner Aufnahme (optional)\n")
    print("  Modell:   tts-hub/XTTS-v2 (Spiegel der Coqui-Modellablage)")
    print("  Inhalt:   " + ", ".join(XTTS_REQUIRED_FILES))
    print(f"  Größe:    ~{status['required_mb']:.0f} MB Download")
    print(f"  Ordner:   {status['path']}")
    print(f"  Lizenz:   {XTTS_LICENSE_NAME} – nicht-kommerzielle Nutzung")
    print(f"            {XTTS_LICENSE_URL}")
    print("\n  Ehrlicher Hinweis: Auf einer reinen CPU (kein Grafikprozessor) braucht")
    print("  XTTS-v2 meist ein Vielfaches der Sprechdauer, auf diesem Laptop oft")
    print("  5–30×. Ein einzelner Satz kann Minuten dauern. Piper bleibt die schnelle")
    print("  Wahl; XTTS-v2 ist nur etwas für Geduld und einzelne Sätze.\n")


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


def _print_xtts_state() -> None:
    status = xtts_status()
    if status["present"]:
        print(f"XTTS-v2-Modell: vollständig vorhanden ({status['size_mb']} MB) in {status['path']}")
        print("                Nutzung setzt PyTorch + Coqui TTS voraus "
              '(pip install "coqui-tts[cpu]").')
    elif status["size_mb"]:
        print(f"XTTS-v2-Modell: unvollständig ({status['size_mb']} MB von "
              f"~{status['required_mb']:.0f} MB) – es fehlt: {', '.join(status['missing'])}")
        print("                Vervollständigen mit: .venv/bin/python -m app.voice_setup --xtts")
    else:
        print("XTTS-v2-Modell: nicht vorhanden (optional).")
        print("                Laden mit: .venv/bin/python -m app.voice_setup --xtts")


def _run_xtts_download(*, force: bool, assume_yes: bool) -> int:
    status = xtts_status()
    _print_xtts_plan(status)

    if status["present"] and not force:
        print("[ok] Das Modell liegt bereits vollständig vor. Nichts zu tun (--force erzwingt neu).")
        return 0

    if not assume_yes:
        try:
            answer = input("Lizenz akzeptieren und herunterladen? [ja/nein] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("ja", "j", "yes", "y"):
            print("Abgebrochen – es wurde nichts heruntergeladen.")
            return 1

    def progress(done: int, total: int) -> None:
        if total:
            percent = int(done * 100 / total)
            print(f"\r  … {percent:3d} %  ({done / (1024 * 1024):6.1f} MB)", end="", flush=True)

    print("[i] Lade das Modell – das dauert je nach Verbindung einige Minuten …")
    try:
        result = download_xtts(force=force, on_progress=progress)
    except (ConnectionError, RuntimeError) as exc:
        print(f"\n[!] {exc}")
        return 1
    print()

    print(f"[ok] XTTS-v2-Modell gespeichert in {result['path']} ({result['total_mb']} MB)")
    if result["downloaded"]:
        print(f"     Neu geladen: {', '.join(result['downloaded'])}")
    if result["skipped"]:
        print(f"     Wiederverwendet: {', '.join(result['skipped'])}")
    print()
    print("Nächste Schritte (nur wenn du es wirklich willst):")
    print('  1. PyTorch + Coqui TTS installieren:  .venv/bin/python -m pip install "coqui-tts[cpu]"')
    print("  2. In der App eine Master-Aufnahme festlegen (12–30 s, nur deine Stimme).")
    print("  3. Sprachausgabe → Verfahren „Eigene Stimmkopie (XTTS-v2)“ wählen.")
    print()
    print("Ohne Schritt 1 meldet die App ehrlich, dass die Stimmkopie nicht lauffähig ist.")
    print("Alle Dateien bleiben ausschließlich auf diesem Laptop.\n")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.voice_setup",
        description="Lädt eine deutsche Piper-Stimme nach data/modelle/piper (nur auf Wunsch).",
    )
    parser.add_argument("voice", nargs="?", help="Stimmenname, z. B. de_DE-thorsten-medium")
    parser.add_argument("--list", action="store_true", help="Verfügbare deutsche Stimmen anzeigen")
    parser.add_argument("--installed", action="store_true", help="Nur lokale Stimmen anzeigen (ohne Internet)")
    parser.add_argument("--force", action="store_true", help="Vorhandene Dateien erneut herunterladen")
    parser.add_argument(
        "--xtts",
        action="store_true",
        help="Optionales XTTS-v2-Modell (~1,9 GB) nach data/modelle/xtts laden",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Lizenz bestätigen und ohne Rückfrage herunterladen (für --xtts)",
    )
    args = parser.parse_args(argv)

    if args.installed:
        _print_installed()
        _print_xtts_state()
        return 0

    if args.xtts:
        return _run_xtts_download(force=args.force, assume_yes=args.yes)

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
