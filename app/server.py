"""Lokaler Webserver der App „StimmenClonewandler“.

Der Server hört ausschließlich auf 127.0.0.1 (localhost). Er ist nicht aus dem
Netzwerk erreichbar und sendet keine Daten nach außen. Es gibt keine Cloud,
keine API und keinen Schlüssel.
"""

from __future__ import annotations

import socket
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from flask import (
    Flask,
    Response,
    jsonify,
    request,
    send_file,
    send_from_directory,
)

from . import hardware, master, storage, tts
from .config import (
    APP_NAME,
    APP_VERSION,
    DATA_DIR,
    HOST,
    MAX_TEXT_CHARS,
    MAX_UPLOAD_MB,
    PIPER_DIR,
    PORT,
    PORT_FILE,
    PRIVACY_NOTICE,
    RECORDINGS_DIR,
    RESULTS_DIR,
    STATIC_DIR,
    TMP_DIR,
    XTTS_DIR,
    ensure_dirs,
)
from .jobs import jobs
from .wav_io import WavError

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["JSON_AS_ASCII"] = False

STATUS_CACHE: Dict[str, Any] = {"value": None, "time": 0.0}
STATUS_TTL_SECONDS = 20


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _json_error(message: str, status: int = 400, **extra: Any):
    payload = {"ok": False, "error": message}
    payload.update(extra)
    response = jsonify(payload)
    response.status_code = status
    return response


def _safe_name(name: Optional[str], fallback: str = "Aufnahme") -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        return fallback
    cleaned = "".join(ch for ch in cleaned if ch.isprintable())
    return cleaned[:120]


def _temp_path(job_id: str) -> Path:
    return TMP_DIR / f"vorschau-{job_id}.wav"


def cleanup_temp(max_age_hours: float = 24.0) -> int:
    """Alte Vorschaudateien entfernen (nur temporäre Dateien)."""
    removed = 0
    if not TMP_DIR.exists():
        return removed
    now = time.time()
    for path in TMP_DIR.glob("*"):
        try:
            if path.is_file() and (now - path.stat().st_mtime) > max_age_hours * 3600:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def port_is_free(host: str, port: int) -> bool:
    """Prüft, ob ein Port belegt ist (ohne ihn dauerhaft zu belegen)."""
    probe_host = "0.0.0.0" if host in ("", "localhost") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        try:
            probe.bind((probe_host, port))
        except OSError:
            return False
    return True


def find_free_port(host: str, preferred: int, attempts: int = 12) -> tuple:
    """Sucht den ersten freien Port ab `preferred`.

    Rückgabe: (Port, verschoben?) – so startet die App auch dann, wenn der
    Standardport schon belegt ist (z. B. weil sie bereits in einem anderen
    Terminal läuft).
    """
    for offset in range(max(1, attempts)):
        candidate = preferred + offset
        if candidate > 65535:
            break
        if port_is_free(host, candidate):
            return candidate, offset > 0
    raise OSError(
        f"Kein freier Port im Bereich {preferred}–{preferred + attempts - 1} gefunden. "
        "Bitte einen anderen Port wählen, z. B.: SCW_PORT=8900 ./start.sh"
    )


def _status(for_ui: bool = True) -> Dict[str, Any]:
    now = time.time()
    if for_ui and STATUS_CACHE["value"] and (now - STATUS_CACHE["time"]) < STATUS_TTL_SECONDS:
        return STATUS_CACHE["value"]
    payload = hardware.status()
    payload.update({
        "app": {"name": APP_NAME, "version": APP_VERSION},
        "privacy_notice": PRIVACY_NOTICE,
        "presets": tts.preset_list(),
        "default_preset": tts.DEFAULT_PRESET_ID,
        "recommended_mode": hardware.recommended_mode(),
        "storage": storage.storage_summary(),
        "paths": {
            "data": str(DATA_DIR),
            "recordings": str(RECORDINGS_DIR),
            "results": str(RESULTS_DIR),
            "piper": str(PIPER_DIR),
            "xtts": str(XTTS_DIR),
        },
        "limits": {
            "max_upload_mb": MAX_UPLOAD_MB,
            "max_text_chars": MAX_TEXT_CHARS,
        },
        "local_only": True,
    })
    STATUS_CACHE["value"] = payload
    STATUS_CACHE["time"] = now
    return payload


# ---------------------------------------------------------------------------
# Seiten
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/favicon.svg")
def favicon():
    return send_from_directory(str(STATIC_DIR), "favicon.svg", mimetype="image/svg+xml")


# ---------------------------------------------------------------------------
# Status & Hardware
# ---------------------------------------------------------------------------

@app.get("/api/status")
def api_status():
    return jsonify({"ok": True, **_status()})


@app.get("/api/system")
def api_system():
    return jsonify({
        "ok": True,
        "system": hardware.system_report(),
        "onnxruntime": hardware.onnxruntime_status(),
        "piper": hardware.piper_status(),
        "torch": hardware.torch_status(),
        "recommended_mode": hardware.recommended_mode(),
    })


@app.get("/api/health")
def api_health():
    return jsonify({"ok": True, "time": time.strftime("%Y-%m-%dT%H:%M:%S")})


@app.post("/api/status/refresh")
def api_status_refresh():
    STATUS_CACHE["value"] = None
    hardware._IMPORT_CACHE.clear()
    return jsonify({"ok": True, **_status()})


# ---------------------------------------------------------------------------
# Stimmen & Stile
# ---------------------------------------------------------------------------

@app.get("/api/voices")
def api_voices():
    voices = hardware.find_piper_voices()
    return jsonify({
        "ok": True,
        "voices": voices,
        "german_voice_count": len([v for v in voices if v.get("is_german") and v.get("usable")]),
        "model_dir": str(PIPER_DIR),
    })


@app.get("/api/presets")
def api_presets():
    return jsonify({"ok": True, "presets": tts.preset_list(), "default": tts.DEFAULT_PRESET_ID})


@app.get("/api/capabilities")
def api_capabilities():
    return jsonify({
        "ok": True,
        "piper": hardware.piper_status(),
        "onnxruntime": hardware.onnxruntime_status(),
        "xtts": tts.xtts_requirements(),
        "clone_possible": tts.xtts_requirements()["available"],
        "honest_note": (
            "Lokal mögliche Funktionen werden hier ehrlich aufgeführt. "
            "Ist etwas nicht vorhanden, kann die App es nicht ausführen."
        ),
    })


# ---------------------------------------------------------------------------
# Aufnahmen
# ---------------------------------------------------------------------------

@app.get("/api/recordings")
def api_recordings():
    recordings = storage.list_recordings()
    master_info = storage.get_master()
    return jsonify({
        "ok": True,
        "recordings": recordings,
        "master_id": master_info.get("id") if master_info else None,
        "count": len(recordings),
        "storage": storage.storage_summary(),
    })


@app.post("/api/recordings/upload")
def api_upload():
    if "file" not in request.files:
        return _json_error("Es wurde keine Datei übertragen.")
    upload = request.files["file"]
    if not upload.filename:
        return _json_error("Der Dateiname fehlt.")
    if not upload.filename.lower().endswith(".wav"):
        return _json_error(
            "Bitte nur WAV-Dateien importieren (PCM). Andere Formate bitte vorher umwandeln."
        )

    ensure_dirs()
    temp_name = f"{uuid.uuid4().hex}.wav"
    temp_path = TMP_DIR / temp_name
    try:
        upload.save(str(temp_path))
        record = storage.save_recording(
            temp_path,
            display_name=_safe_name(Path(upload.filename).stem),
            kind="import",
            original_name=upload.filename,
        )
    except WavError as exc:
        return _json_error(str(exc))
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass

    return jsonify({"ok": True, "recording": record})


@app.post("/api/recordings/mic")
def api_mic_upload():
    """Nimmt eine Mikrofonaufnahme aus dem Browser an (WAV-Daten als Formularfeld)."""
    if "file" not in request.files:
        return _json_error("Es wurden keine Aufnahmedaten übertragen.")
    upload = request.files["file"]
    ensure_dirs()
    temp_path = TMP_DIR / f"{uuid.uuid4().hex}.wav"
    try:
        upload.save(str(temp_path))
        size = temp_path.stat().st_size
        if size < 1024:
            return _json_error(
                "Die Aufnahme ist zu kurz oder leer. Bitte länger sprechen und erneut versuchen."
            )
        name = _safe_name(request.form.get("name"), f"Mikrofonaufnahme {time.strftime('%d.%m.%Y %H:%M')}")
        record = storage.save_recording(temp_path, display_name=name, kind="aufnahme")
    except WavError as exc:
        return _json_error(str(exc))
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass
    return jsonify({"ok": True, "recording": record})


@app.get("/api/recordings/<rec_id>")
def api_recording(rec_id: str):
    record = storage.get_recording(rec_id)
    if not record:
        return _json_error("Die Aufnahme wurde nicht gefunden.", 404)
    return jsonify({"ok": True, "recording": record})


@app.post("/api/recordings/<rec_id>/reanalyze")
def api_reanalyze(rec_id: str):
    record = storage.get_recording(rec_id)
    path = storage.recording_path(rec_id)
    if not record or not path:
        return _json_error("Die Aufnahme wurde nicht gefunden.", 404)
    from . import analysis as analysis_mod

    record["analysis"] = analysis_mod.analyze(path)
    storage.update_recording(record)
    return jsonify({"ok": True, "recording": record})


@app.get("/api/recordings/<rec_id>/audio")
def api_recording_audio(rec_id: str):
    path = storage.recording_path(rec_id)
    if not path:
        return _json_error("Die Audiodatei wurde nicht gefunden.", 404)
    return send_file(str(path), mimetype="audio/wav", conditional=True, max_age=0)


@app.get("/api/recordings/<rec_id>/download")
def api_recording_download(rec_id: str):
    path = storage.recording_path(rec_id)
    record = storage.get_recording(rec_id)
    if not path or not record:
        return _json_error("Die Audiodatei wurde nicht gefunden.", 404)
    filename = f"{_safe_name(record.get('name'), 'aufnahme')}.wav"
    return send_file(str(path), mimetype="audio/wav", as_attachment=True, download_name=filename)


@app.delete("/api/recordings/<rec_id>")
def api_delete_recording(rec_id: str):
    if not storage.get_recording(rec_id):
        return _json_error("Die Aufnahme wurde nicht gefunden.", 404)
    storage.delete_recording(rec_id)
    return jsonify({"ok": True, "deleted": rec_id})


# ---------------------------------------------------------------------------
# Master-Aufnahme
# ---------------------------------------------------------------------------

@app.get("/api/master")
def api_master():
    payload = master.master_overview()
    payload["base_voice"] = master.base_voice()
    return jsonify({"ok": True, **payload})


@app.post("/api/recordings/<rec_id>/master")
def api_set_master(rec_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        result = master.build_reference(
            rec_id,
            cleanup=bool(payload.get("cleanup", True)),
        )
    except WavError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        app.logger.exception("Master-Aufbereitung fehlgeschlagen")
        return _json_error(
            "Die Master-Aufnahme konnte nicht erstellt werden. "
            f"Technische Ursache: {type(exc).__name__}: {exc}",
            500,
        )
    STATUS_CACHE["value"] = None
    return jsonify({"ok": True, **result})


@app.delete("/api/master")
def api_clear_master():
    current = storage.get_master()
    if current:
        reference = storage.reference_path(current["id"])
        if reference:
            try:
                reference.unlink()
            except OSError:
                pass
    storage.clear_master()
    return jsonify({"ok": True})


@app.get("/api/master/reference")
def api_master_reference():
    current = storage.get_master()
    if not current:
        return _json_error("Es ist keine Master-Aufnahme festgelegt.", 404)
    path = storage.reference_path(current["id"])
    if not path:
        return _json_error("Die Referenzdatei der Master-Aufnahme fehlt.", 404)
    if request.args.get("download"):
        name = f"{_safe_name(current.get('name'), 'master')}-master.wav"
        return send_file(str(path), mimetype="audio/wav", as_attachment=True, download_name=name)
    return send_file(str(path), mimetype="audio/wav", conditional=True, max_age=0)


# ---------------------------------------------------------------------------
# Sprachausgabe (Hintergrund-Aufträge)
# ---------------------------------------------------------------------------

def _run_synthesis(job, payload: Dict[str, Any]) -> Dict[str, Any]:
    text = str(payload.get("text") or "")
    if len(text) > MAX_TEXT_CHARS:
        raise tts.EngineError(f"Der Text ist zu lang (höchstens {MAX_TEXT_CHARS} Zeichen).")
    options = tts.SynthesisOptions.from_payload(payload)
    out_path = _temp_path(job.id)
    meta = tts.synthesize_to_wav(
        text,
        out_path,
        options,
        progress=lambda percent, stage: job.update(percent, stage),
    )
    meta["temp_file"] = out_path.name
    meta["preview_url"] = f"/api/jobs/{job.id}/audio"
    meta["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["text"] = text
    return meta


@app.post("/api/tts")
def api_tts():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "").strip()
    if not text:
        return _json_error("Bitte einen Text eingeben.")
    if len(text) > MAX_TEXT_CHARS:
        return _json_error(f"Der Text ist zu lang (höchstens {MAX_TEXT_CHARS} Zeichen).")

    # Vorabprüfung: ehrliche Fehlermeldung, ohne Auftrag zu starten
    engine = (payload.get("engine") or "piper").lower()
    if engine == "xtts":
        requirements = tts.xtts_requirements()
        if not requirements["available"]:
            return _json_error(
                "Die eigene Stimmkopie ist auf diesem Laptop nicht ausführbar. Es fehlt: "
                + ", ".join(requirements["missing"])
                + ". Es wurde kein Modell erzeugt.",
                409,
                missing=requirements["missing"],
            )
        if not storage.get_master():
            return _json_error(
                "Für die Stimmkopie muss zuerst eine Master-Aufnahme festgelegt werden.",
                409,
            )
    else:
        piper = hardware.piper_status()
        if not piper["available"]:
            return _json_error(
                "Die lokale Sprach-Engine (Piper) ist nicht installiert. Es wurde kein Audio erzeugt.",
                409,
            )
        if not any(v.get("usable") for v in hardware.find_piper_voices()):
            return _json_error(
                "Es liegt kein Sprachmodell vor. Bitte eine Piper-Stimme nach data/modelle/piper legen.",
                409,
            )

    job = jobs.create("tts")
    jobs.start(job, lambda started: _run_synthesis(started, payload))
    return jsonify({"ok": True, "job": job.snapshot()})


@app.get("/api/jobs/<job_id>")
def api_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return _json_error("Der Auftrag wurde nicht gefunden.", 404)
    return jsonify({"ok": True, "job": job.snapshot()})


@app.post("/api/jobs/<job_id>/cancel")
def api_cancel_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return _json_error("Der Auftrag wurde nicht gefunden.", 404)
    jobs.cancel(job_id)
    return jsonify({"ok": True, "job": job.snapshot()})


@app.get("/api/jobs/<job_id>/audio")
def api_job_audio(job_id: str):
    path = _temp_path(job_id)
    if not path.exists():
        return _json_error("Für diesen Auftrag liegt keine Audiodatei vor.", 404)
    return send_file(str(path), mimetype="audio/wav", conditional=True, max_age=0)


@app.post("/api/benchmark")
def api_benchmark():
    """Kurzer Test: wie schnell rechnet dieser Laptop die Sprachausgabe?"""
    if not hardware.piper_status()["available"]:
        return _json_error("Die lokale Sprach-Engine (Piper) ist nicht installiert.", 409)
    if not any(v.get("usable") for v in hardware.find_piper_voices()):
        return _json_error("Es liegt kein Sprachmodell für den Test vor.", 409)
    payload = request.get_json(silent=True) or {}
    options = tts.SynthesisOptions.from_payload({
        **payload,
        "preset": payload.get("preset") or "neutral",
        "intensity": 0.0,
        "tempo": 1.0,
    })
    job = jobs.create("benchmark")
    test_text = payload.get("text") or (
        "Guten Tag. Dies ist ein kurzer Test der lokalen Sprachausgabe. "
        "Der Klang wird direkt auf diesem Laptop berechnet."
    )

    def runner(started):
        meta = tts.synthesize_to_wav(
            test_text,
            _temp_path(started.id),
            options,
            progress=lambda percent, stage: started.update(percent, f"Test läuft: {stage}"),
        )
        try:
            _temp_path(started.id).unlink()
        except OSError:
            pass
        return meta

    jobs.start(job, runner)
    return jsonify({"ok": True, "job": job.snapshot(), "test_text": test_text})


# ---------------------------------------------------------------------------
# Ergebnisse
# ---------------------------------------------------------------------------

@app.get("/api/results")
def api_results():
    return jsonify({
        "ok": True,
        "results": storage.list_results(),
        "storage": storage.storage_summary(),
    })


@app.post("/api/results")
def api_save_result():
    payload = request.get_json(silent=True) or {}
    job_id = str(payload.get("job_id") or "")
    job = jobs.get(job_id)
    if not job or job.status != "fertig":
        return _json_error("Der Auftrag ist nicht abgeschlossen – es wurde nichts gespeichert.")
    source = _temp_path(job_id)
    if not source.exists():
        return _json_error("Die erzeugte Audiodatei ist nicht mehr vorhanden. Bitte neu erzeugen.")

    meta = {
        key: value
        for key, value in job.result.items()
        if key not in ("temp_file", "preview_url")
    }
    name = _safe_name(
        payload.get("name"),
        f"Sprachausgabe {time.strftime('%d.%m.%Y %H:%M')}",
    )
    record = storage.save_result(source, name=name, meta=meta)
    return jsonify({"ok": True, "result": record})


@app.get("/api/results/<res_id>/audio")
def api_result_audio(res_id: str):
    path = storage.result_path(res_id)
    if not path:
        return _json_error("Die Ergebnisdatei wurde nicht gefunden.", 404)
    return send_file(str(path), mimetype="audio/wav", conditional=True, max_age=0)


@app.get("/api/results/<res_id>/download")
def api_result_download(res_id: str):
    path = storage.result_path(res_id)
    if not path:
        return _json_error("Die Ergebnisdatei wurde nicht gefunden.", 404)
    return send_file(str(path), mimetype="audio/wav", as_attachment=True, download_name=path.name)


@app.delete("/api/results/<res_id>")
def api_delete_result(res_id: str):
    if not storage.delete_result(res_id):
        return _json_error("Die Ergebnisdatei wurde nicht gefunden.", 404)
    return jsonify({"ok": True, "deleted": res_id})


# ---------------------------------------------------------------------------
# Fehlerbehandlung
# ---------------------------------------------------------------------------

@app.errorhandler(413)
def too_large(_error):
    return _json_error(
        f"Die Datei ist zu groß (Grenze {MAX_UPLOAD_MB} MB). Bitte eine kürzere Aufnahme verwenden.",
        413,
    )


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return _json_error("Die angeforderte Adresse existiert nicht.", 404)
    return error


@app.errorhandler(500)
def server_error(error):
    app.logger.error("Interner Fehler: %s", error)
    return _json_error(
        "Es ist ein interner Fehler aufgetreten. Details stehen im Terminalfenster der App.",
        500,
    )


@app.after_request
def add_headers(response: Response):
    # Nur lokal gedacht: keine Einbettung von außen, kein Caching von Audiodaten
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def _banner(status: Dict[str, Any], port: Optional[int] = None, moved: bool = False) -> None:
    line = "=" * 68
    shown_port = port or PORT
    print(line)
    print(f"  {APP_NAME} {APP_VERSION} – vollständig lokal")
    print(line)
    print(f"  Adresse:   http://{HOST}:{shown_port}")
    print(f"  Daten:     {hardware.DATA_DIR}")
    print(f"  Modelle:   {PIPER_DIR}")
    system = status["system"]
    ram = system.get("ram_available_mb")
    print(
        f"  Hardware:  {system['cpu_cores']} CPU-Kerne, "
        f"{ram if ram is not None else '?'} MB RAM frei, {system['disk_free_mb']} MB Speicher frei"
    )
    print(f"  Sprache:   {'bereit' if status['ready'] else 'NICHT bereit'}")
    for message in status["messages"][:6]:
        marker = {"error": "[!]", "warn": "[*]", "info": "[i]"}.get(message["severity"], "[i]")
        print(f"    {marker} {message['text']}")
    print(line)
    print(f"  {PRIVACY_NOTICE}")
    print(line)
    if moved:
        print(f"  [!] Port {PORT} war bereits belegt (läuft die App schon in einem")
        print(f"      anderen Fenster?). Darum läuft diese Instanz auf Port {shown_port}.")
        print(f"      Belegten Port finden:  ss -ltnp 'sport = :{PORT}'")
        print(f"      Prozess beenden:       fuser -k {PORT}/tcp")
        print(line)
    print("  Beenden mit Strg+C")
    print()


def create_app(testing: bool = False) -> Flask:
    ensure_dirs()
    cleanup_temp()
    if testing:
        app.config.update(TESTING=True)
    return app


def main() -> None:
    ensure_dirs()
    removed = cleanup_temp()
    if removed:
        print(f"[i] {removed} alte Vorschaudateien entfernt.")

    try:
        port, moved = find_free_port(HOST, PORT)
    except OSError as exc:
        print(f"[!] {exc}")
        raise SystemExit(1)

    try:
        PORT_FILE.write_text(str(port), encoding="utf-8")
    except OSError:
        pass

    try:
        status = _status()
        _banner(status, port=port, moved=moved)
    except Exception:
        traceback.print_exc()

    app.run(
        host=HOST,
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


if __name__ == "__main__":
    main()
