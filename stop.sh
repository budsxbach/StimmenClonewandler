#!/usr/bin/env bash
# StimmenClonewandler – beendet ALLE laufenden Instanzen der App.
#
# Hintergrund: Wenn mehrere Terminalfenster die App gestartet haben, taucht bei
# `fuser -k 8765/tcp` immer wieder eine neue Prozessnummer auf. Dieses Skript
# beendet alle Instanzen auf einmal – auch solche, die auf einem Ausweichport
# (8766, 8767 …) laufen.

set -uo pipefail
cd "$(dirname "$0")"

echo
echo "=== StimmenClonewandler beenden ==="

found=0

# 1) Prozesse, die unser Servermodul ausführen
mapfile -t pids < <(pgrep -f "python.*-m app\.server" 2>/dev/null || true)
if [ "${#pids[@]}" -gt 0 ]; then
  found=1
  echo "[i] Gefundene Server-Prozesse: ${pids[*]}"
  ps -o pid=,ppid=,etime=,cmd= -p "${pids[@]}" 2>/dev/null | sed 's/^/    /' || true
  kill -TERM "${pids[@]}" 2>/dev/null || true
  sleep 1
  # Nachfassen, falls etwas hängen bleibt
  mapfile -t rest < <(pgrep -f "python.*-m app\.server" 2>/dev/null || true)
  if [ "${#rest[@]}" -gt 0 ]; then
    echo "[i] Beende hart: ${rest[*]}"
    kill -KILL "${rest[@]}" 2>/dev/null || true
    sleep 0.5
  fi
fi

# 2) Startskript-Reste (falls start.sh noch in einer Schleife läuft)
mapfile -t starter < <(pgrep -f "bash .*start\.sh" 2>/dev/null || true)
if [ "${#starter[@]}" -gt 0 ]; then
  found=1
  echo "[i] Beende Startskript-Prozesse: ${starter[*]}"
  kill -TERM "${starter[@]}" 2>/dev/null || true
  sleep 0.5
fi

# 3) Ports prüfen
echo
ports_busy=""
for port in $(seq 8765 8776); do
  if ss -ltn "sport = :${port}" 2>/dev/null | grep -q LISTEN; then
    ports_busy="${ports_busy} ${port}"
  fi
done

if [ -z "$ports_busy" ]; then
  echo "[ok] Kein Prozess der App lauscht mehr auf den Ports 8765–8776."
else
  echo "[!] Auf diesen Ports lauscht noch etwas:${ports_busy}"
  echo "    Details:  ss -ltnp 'sport = :8765'"
  echo "    Das gehört dann vermutlich nicht zur App – bitte prüfen, ob dort"
  echo "    ein anderes Programm läuft."
fi

if [ "$found" -eq 0 ] && [ -z "$ports_busy" ]; then
  echo "[i] Es lief keine Instanz der App."
fi

rm -f data/.port 2>/dev/null || true
echo
echo "Fertig. Neustart mit:  ./start.sh"
echo
