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

echo
echo "[i] Adresse: ${URL}"
echo "[i] Beenden mit Strg+C"
echo

if command -v xdg-open >/dev/null 2>&1; then
  ( sleep 3; xdg-open "$URL" >/dev/null 2>&1 || true ) &
elif command -v open >/dev/null 2>&1; then
  ( sleep 3; open "$URL" >/dev/null 2>&1 || true ) &
fi

exec "$VPY" -m app.server
