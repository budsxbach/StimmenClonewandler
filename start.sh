#!/usr/bin/env bash
# StimmenClonewandler – Startskript für Linux und macOS
# Startet die App ausschließlich lokal auf http://127.0.0.1:8765

set -euo pipefail
cd "$(dirname "$0")"

echo
echo "==========================================================="
echo "  StimmenClonewandler – lokaler Start"
echo "==========================================================="
echo

PYEXE=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYEXE="$candidate"
    break
  fi
done

if [ -z "$PYEXE" ]; then
  echo "[FEHLER] Python 3 wurde nicht gefunden."
  echo "         Bitte Python 3.9–3.12 installieren (z. B. 'sudo apt install python3 python3-venv')."
  exit 1
fi

"$PYEXE" --version

if [ ! -x ".venv/bin/python" ]; then
  echo "[i] Erste Einrichtung: virtuelle Umgebung wird erstellt …"
  "$PYEXE" -m venv .venv
fi

VPY=".venv/bin/python"

if ! "$VPY" -c "import flask, piper" >/dev/null 2>&1; then
  echo "[i] Benötigte Pakete werden installiert – einmalig mit Internet, danach offline."
  "$VPY" -m pip install --upgrade pip >/dev/null
  "$VPY" -m pip install -r requirements.txt
fi

mkdir -p data/aufnahmen data/ergebnisse data/master data/tmp data/modelle/piper data/modelle/xtts

PORT="${SCW_PORT:-8765}"
URL="http://127.0.0.1:${PORT}"

# Hinweis, wenn noch kein Sprachmodell vorliegt
if ! ls data/modelle/piper/*.onnx >/dev/null 2>&1; then
  echo
  echo "[!] Es liegt noch kein Sprachmodell vor – ohne Modell kann die App"
  echo "    keine Stimme erzeugen. Einmalig herunterladen (mit Internet):"
  echo
  echo "      .venv/bin/python -m app.voice_setup --list"
  echo "      .venv/bin/python -m app.voice_setup de_DE-thorsten-medium"
  echo
fi

echo
echo "[i] Adresse: ${URL}"
echo "[i] Beenden mit Strg+C"
echo "[i] Ist der Port belegt, wählt die App automatisch den nächsten freien."
echo

# Browser erst öffnen, wenn der Server läuft – und mit dem Port, den er
# tatsächlich benutzt (falls 8765 belegt war, weicht er aus).
rm -f data/.port
open_browser_later() {
  for _ in $(seq 1 30); do
    if [ -s data/.port ]; then
      real_port="$(cat data/.port 2>/dev/null || echo "$PORT")"
      sleep 1
      target="http://127.0.0.1:${real_port}"
      [ "$real_port" != "$PORT" ] && echo "[i] Browser: ${target} (Port ${PORT} war belegt)"
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$target" >/dev/null 2>&1 || true
      elif command -v open >/dev/null 2>&1; then
        open "$target" >/dev/null 2>&1 || true
      fi
      return
    fi
    sleep 0.5
  done
}

if command -v xdg-open >/dev/null 2>&1 || command -v open >/dev/null 2>&1; then
  open_browser_later &
fi

exec "$VPY" -m app.server
