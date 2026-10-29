# Installation & Bedienung – StimmenClonewandler

Diese Anleitung führt dich von null bis zur ersten eigenen Sprachdatei.
Sie gilt für **Ubuntu/Linux** (dein Dell Latitude 5530) und für **Windows**.

**Kurzfassung** (wenn Python ≥ 3.11 vorhanden ist):

```bash
cd ~/Schreibtisch/AuronOrigin/StimmenClonewandler
./start.sh
.venv/bin/python -m app.voice_setup de_DE-thorsten-medium   # einmalig, mit Internet
# Browser: http://127.0.0.1:8765
```

---

## Inhalt

1. [Voraussetzungen](#1-voraussetzungen)
2. [Projekt herunterladen](#2-projekt-herunterladen)
3. [Installieren und starten](#3-installieren-und-starten)
4. [Sprachmodell besorgen](#4-sprachmodell-besorgen)
5. [Eigene Stimme als Ausgangsstimme festlegen](#5-eigene-stimme-als-ausgangsstimme-festlegen)
6. [Bedienung der App](#6-bedienung-der-app)
7. [Wo liegen meine Daten?](#7-wo-liegen-meine-daten)
8. [Probleme und Lösungen](#8-probleme-und-lösungen)
9. [Optional: echte Stimmkopie (XTTS-v2)](#9-optional-echte-stimmkopie-xtts-v2)
10. [Checkliste für den ersten Durchlauf](#10-checkliste-für-den-ersten-durchlauf)

---

## 1. Voraussetzungen

| Punkt | Anforderung |
| --- | --- |
| Rechner | Dell Latitude 5530 (i5-1235U, 8 GiB RAM) – reicht aus, keine Grafikkarte nötig |
| System | Ubuntu 26.04 LTS (Windows 10/11 ebenfalls möglich) |
| Python | **3.11 – 3.14** · getestet mit **3.14.4** und 3.11 |
| Platz | ~250 MB Programm + ~60 MB pro Sprachmodell + Platz für Aufnahmen |
| Internet | **einmalig** für die Installation der Pakete und den Stimmen-Download; danach offline |

Prüfen:

```bash
python3 --version     # z. B. Python 3.14.4
```

> Python 3.14 funktioniert. Für `onnxruntime`, `numpy` und `piper-tts` gibt es
> passende Wheels – es muss nichts kompiliert werden.

---

## 2. Projekt herunterladen

**Variante A – ZIP (ohne Git-Kenntnisse)**

1. <https://github.com/budsxbach/StimmenClonewandler> öffnen
2. **Code → Download ZIP**
3. Entpacken, z. B.:

```bash
mkdir -p ~/Schreibtisch/AuronOrigin
unzip ~/Downloads/StimmenClonewandler-main.zip -d ~/Schreibtisch/AuronOrigin/
```

**Variante B – mit Git**

```bash
git clone https://github.com/budsxbach/StimmenClonewandler.git
```

**Kontrolle:** Im Ordner müssen `app`, `data`, `requirements.txt`, `start.sh`
und `README.md` liegen:

```bash
cd ~/Schreibtisch/AuronOrigin/StimmenClonewandler
ls
```

> Im Repository sind **keine** Audiodateien und **keine** Sprachmodelle
> enthalten – das ist Absicht (Datenschutz). Die kommen in Schritt 4.

---

## 3. Installieren und starten

### 3.1 Ubuntu / Linux (empfohlen)

```bash
cd ~/Schreibtisch/AuronOrigin/StimmenClonewandler
chmod +x start.sh
./start.sh
```

Das Skript erledigt automatisch:

1. virtuelle Umgebung `.venv` anlegen
2. `flask` und `piper-tts` installieren (hier braucht es Internet)
3. Ordner unter `data/` anlegen
4. Hinweis anzeigen, falls noch kein Sprachmodell vorliegt
5. Server starten und Browser öffnen

### 3.2 Manuell (wenn du die Schritte einzeln sehen willst)

```bash
cd ~/Schreibtisch/AuronOrigin/StimmenClonewandler
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.server
```

Prüfen, ob die Sprach-Engine wirklich installiert ist:

```bash
.venv/bin/python -c "import piper, onnxruntime, numpy; print('onnxruntime', onnxruntime.__version__, '| numpy', numpy.__version__)"
```

### 3.3 Windows

`start_windows.bat` doppelklicken. Python muss bei der Installation mit
„Add python.exe to PATH“ installiert worden sein.

### 3.4 Was du beim Start siehst

```
====================================================================
  StimmenClonewandler 1.0.0 – vollständig lokal
====================================================================
  Adresse:   http://127.0.0.1:8765
  Daten:     …/StimmenClonewandler/data
  Modelle:   …/StimmenClonewandler/data/modelle/piper
  Hardware:  12 CPU-Kerne, … MB RAM frei, … MB Speicher frei
  Sprache:   NICHT bereit
    [*] Es liegt noch kein deutsches Sprachmodell lokal vor …
```

**„Sprache: NICHT bereit“ ist an dieser Stelle normal** – es fehlt nur das
Sprachmodell (Schritt 4). Alles andere (Aufnahmen, Analyse, Vergleich) funktioniert
schon.

### 3.5 App wieder beenden

```bash
./stop.sh          # beendet alle Instanzen (auch auf Ausweichports 8766+)
```

Im laufenden Terminal genügt `Strg+C`. Windows: `stop_windows.bat`.

Startest du die App ein zweites Mal, während sie schon läuft, startet sie
**keine** zweite Instanz, sondern meldet:

```
  StimmenClonewandler läuft bereits auf http://127.0.0.1:8765
  Es wird keine zweite Instanz gestartet.
```

### 3.6 Port belegt?

Startet die App mit `Port 8765 is in use`, wählt sie **automatisch den nächsten
freien Port** (8766, 8767 …) und schreibt die richtige Adresse in die Konsole:

```
  [!] Port 8765 war bereits belegt (läuft die App schon in einem
      anderen Fenster?). Darum läuft diese Instanz auf Port 8766.
```

Meist läuft die App schon in einem anderen Terminalfenster. Statt einzelne
Prozesse zu jagen, alle Instanzen auf einmal beenden:

```bash
./stop.sh
```

Manuell:

```bash
ss -ltnp 'sport = :8765'      # zeigt das Programm hinter dem Port
fuser -k 8765/tcp             # beendet genau diesen Prozess
pkill -f app.server           # beendet alle Instanzen der App
```

> **Wenn nach jedem `fuser -k` sofort eine neue Prozessnummer auftaucht**, wird
> die App von etwas anderem neu gestartet. Siehe Abschnitt 8.5.

Oder einen festen anderen Port verwenden:

```bash
SCW_PORT=8900 ./start.sh
```

Der Server ist **nur** unter `127.0.0.1` erreichbar – nicht aus dem Netzwerk.

---

## 4. Sprachmodell besorgen

Ohne Modell kann die App keine Stimme erzeugen. Der eingebaute Helfer lädt eine
Stimme **nur auf deinen ausdrücklichen Befehl** (die Web-App selbst bleibt offline).

```bash
cd ~/Schreibtisch/AuronOrigin/StimmenClonewandler

# 1) deutsche Stimmen anzeigen
.venv/bin/python -m app.voice_setup --list

# 2) empfohlene Stimme installieren (~60 MB, männliche deutsche Stimme)
.venv/bin/python -m app.voice_setup de_DE-thorsten-medium

# 3) prüfen, was lokal liegt (ohne Internet)
.venv/bin/python -m app.voice_setup --installed
```

Danach in der App: **Tab „System & Modell“ → „Erneut prüfen“**. Die Stimme
erscheint als *Deutsch*, oben steht „Bereit“.

### Empfehlung für deinen Laptop

- Qualitätsstufe **`medium`** (ca. 60 MB) – gutes Verhältnis aus Klang und Tempo
- `low` ist noch schneller und kleiner, klingt aber rauer
- `high` lohnt sich auf dieser CPU-Klasse nicht (mehrere Sekunden pro Satz)

### Alternativ: Dateien selbst kopieren

Beide Dateien einer Stimme (`.onnx` **und** `.onnx.json`) nach
`data/modelle/piper/` legen:

```
data/modelle/piper/de_DE-thorsten-medium.onnx
data/modelle/piper/de_DE-thorsten-medium.onnx.json
```

> Stimmen haben eigene Lizenzen – bitte in der jeweiligen Modellbeschreibung
> nachsehen. Modelldateien bleiben lokal und gehören **nicht** zu GitHub.

---

## 5. Eigene Stimme als Ausgangsstimme festlegen

1. Tab **Aufnahmen** → deine WAV-Datei in den gestrichelten Bereich ziehen
   (Original bleibt unverändert, es wird eine Kopie angelegt).
2. Bei der Aufnahme **„Als Master festlegen“** drücken.
   Die App erzeugt daraus die aufbereitete Referenz (Mono, beste 30-Sekunden-Passage,
   normalisiert) und misst deine Sprechlage.
3. Unter **Master-Aufnahme** erscheint das Stimmprofil, z. B.
   „mittel, ca. 121 Hz“ – mit Stil-Vorschlag und Button
   **„Diesen Stil übernehmen“**.

**Was das leistet – und was nicht:**

- ✅ Die **Tonhöhe** der Modellstimme wird an deine Sprechlage angeglichen
  (max. ±4 Halbtöne, Sprechdauer bleibt gleich).
- ❌ Deine **Klangfarbe und Artikulation** werden dabei *nicht* kopiert.
  Das kann nur XTTS-v2 (optional, siehe Abschnitt 9) – und auch dort ist das
  Ergebnis eine Annäherung, keine identische Kopie.

---

## 6. Bedienung der App

### Tab „Aufnahmen“

| Element | Funktion |
| --- | --- |
| Import-Bereich | WAV-Datei hineinziehen oder klicken (nur PCM-WAV) |
| Mikrofon | „Aufnahme starten“ → ruhig sprechen (~20 cm Abstand) → „Stoppen“; roter Pegelbalken = zu laut |
| Messwerte | Samplerate, Kanäle, Dauer, Bittiefe, Spitzenpegel, Lautheit, Stimme/Geräusch, Übersteuerung |
| Warnungen | erscheinen automatisch (Übersteuerung, starkes Rauschen, zu leise) |
| Aktionen | Als Master festlegen · Herunterladen · Neu analysieren · Löschen |
| Anhören & vergleichen | Datei A und B wählen, einzeln oder „Erst A, dann B“ |

### Tab „Sprachausgabe“

1. **Text** eingeben (bis 4000 Zeichen; „Beispieltext einfügen“ hilft).
2. **Sprachmodell** wählen (deine lokalen Stimmen).
3. **Stimm-Stil**: Weise & warm (empfohlen) · Warm & ruhig · Mystisch & tief ·
   Nur ruhig & langsam · Neutral.
4. **Intensität** (0–150 %) und **Sprechtempo** (80–125 %) feinjustieren.
5. **„Stimmlage an meine Ausgangsstimme anpassen“** ist aktiv, sobald eine
   Master-Aufnahme existiert; Feinregler **±5 Halbtöne** darunter.
6. **Langsamer CPU-Modus**: nur bei Akkubetrieb oder Hitzeproblemen nötig.
7. **CPU-Kerne**: 4 ist auf dem i5-1235U ein guter Wert (6–8 bringen kaum Tempo).
8. **„Text vorlesen“** → Fortschrittsbalken mit Abschnitt und Laufzeit,
   **„Abbrechen“** jederzeit möglich.
9. Ergebnis anhören → Namen vergeben → **„Als WAV speichern“**.

### Tab „Ergebnisse“

Alle gespeicherten WAV-Dateien mit Werten: Wiedergabe, Download, Löschen.

### Tab „System & Modell“

Hardware-Prüfung, Status der Engines, **Geschwindigkeitstest** (zeigt den
Echtzeitfaktor deines Laptops), Modellliste, Speicherbelegung.

---

## 7. Wo liegen meine Daten?

```
data/aufnahmen/    Originale deiner Aufnahmen
data/master/       Referenz (30 s) + Stimmprofil (ausgangsstimme.json)
data/ergebnisse/   erzeugte Sprachdateien
data/tmp/          Vorschau (wird nach 24 h automatisch gelöscht)
data/modelle/      Piper-Stimmen (+ optional XTTS)
```

- Alles bleibt **auf diesem Laptop**. Kein Upload, keine Cloud, keine API.
- **Löschen:** in der App über „Löschen“ oder den Ordner `data/` im Dateimanager.
- **Sicherung:** auf eine externe Festplatte – nicht in eine Cloud.
- Auf GitHub liegen nur Quellcode, Vorlagen und Doku. Die `.gitignore` schließt
  alle Audio- und Modelldateien aus.

---

## 8. Probleme und Lösungen

| Meldung / Problem | Lösung |
| --- | --- |
| `Port 8765 is in use` | App wählt automatisch den nächsten Port (siehe Konsole). Alte Instanz beenden: `./stop.sh` |
| Nach `fuser -k` erscheint sofort eine neue PID | Ein Neustarter ist aktiv – siehe Abschnitt 8.5 |
| `Sprache: NICHT bereit` | Schritt 4: Sprachmodell installieren, dann „Erneut prüfen“ |
| „Es liegt kein Sprachmodell vor“ | Beide Dateien (`.onnx` **und** `.onnx.json`) im selben Ordner nötig |
| `python3-venv` fehlt | `sudo apt install python3-venv python3-pip` |
| Installation scheitert an einem Paket | Version prüfen (`python3 --version`); Fallback mit `uv` siehe unten |
| `python3.12` nicht gefunden | Ubuntu 26.04 liefert 3.12 nicht aus – **nicht nötig**, 3.14 wird unterstützt |
| Kein Mikrofonzugriff | Browser fragt einmalig – Erlaubnis für `127.0.0.1` geben |
| Seite lädt nicht | Terminal offen lassen; Adresse **mit http**, nicht https |
| Sprache klingt nicht deutsch | deutsches Modell `de_DE-…` wählen |
| Sprachausgabe sehr langsam | kürzere Absätze, „Langsamer CPU-Modus“ **aus**, andere Programme schließen |

### 8.5 Nach jedem `fuser -k` kommt eine neue Prozessnummer

Das bedeutet: Nicht du startest die App neu, sondern ein anderer Prozess
(start.sh in einer Schleife, ein Autostart-Eintrag, ein systemd-Dienst oder ein
Skript). Erst herausfinden, **wer** neu startet:

```bash
# 1) alle Instanzen beenden
./stop.sh        # oder: pkill -f app.server

# 2) sofort prüfen, ob wieder etwas lauscht (nach ~2 s)
ss -ltnp 'sport = :8765'
#    → erscheint eine PID, ist ein Neustarter aktiv

# 3) Elternprozess dieser PID ansehen
ps -o pid,ppid,lstart,cmd -p <PID>
ps -o pid,cmd -p <PPID>
```

Häufige Ursachen und ihre Prüfung:

```bash
# a) systemd-Dienst (Benutzer)
systemctl --user list-units --type=service | grep -i stimm
systemctl --user stop stimmenclonewandler.service      # falls vorhanden

# b) Autostart-Eintrag im Desktop
grep -r "app.server\|start.sh" ~/.config/autostart ~/.config/systemd/user 2>/dev/null

# c) Startschleife in einem anderen Terminal
ps -ef | grep -E "start\.sh|app\.server" | grep -v grep
```

Läuft die App in einem Terminal, das du nicht mehr siehst: dieses Fenster
schließen oder `pkill -f app.server` verwenden. Danach `./stop.sh` zur Kontrolle.

Da die App seit Version 1.0 einen belegten Port automatisch überspringt
(8766, 8767 …), ist ein Beenden übrigens **nicht mehr nötig** – du kannst
einfach die Adresse aus der Konsole im Browser öffnen.

### Fallback ohne Administratorrechte (`uv`)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.local/bin/env

cd ~/Schreibtisch/AuronOrigin/StimmenClonewandler
rm -rf .venv
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m app.server
```

---

## 9. Optional: echte Stimmkopie (XTTS-v2)

Nur wenn du es wirklich willst – auf diesem Laptop ist es langsam.

```bash
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install coqui-tts
```

Danach ein XTTS-v2-Modell (`model.pth`, `config.json`, `vocab.json`) nach
`data/modelle/xtts/` legen, in der App als Verfahren
„Eigene Stimmkopie (XTTS-v2)“ wählen und eine Master-Aufnahme (12–30 s) festlegen.

**Ehrliche Erwartung:** ~4–5 GB Arbeitsspeicher (bei 8 GiB alles andere schließen)
und **10–30× langsamer als Echtzeit** – ein 10-Sekunden-Satz braucht 2–5 Minuten.
Fehlt etwas, meldet die App das und speichert **nichts**.

---

## 10. Checkliste für den ersten Durchlauf

```
[ ] Projekt entpackt / geklont
[ ] python3 --version geprüft (3.11–3.14)
[ ] ./start.sh ausgeführt, Browser zeigt die App
[ ] .venv/bin/python -m app.voice_setup de_DE-thorsten-medium
[ ] „Erneut prüfen“ → Stimme erscheint als „Deutsch“, Status „Bereit“
[ ] Geschwindigkeitstest im Tab „System & Modell“ laufen lassen
[ ] Eigene Aufnahme importieren → „Als Master festlegen“
[ ] Text eingeben → „Text vorlesen“ → anhören → „Als WAV speichern“
```

Viel Freude – und denk daran: nur eigene Stimme oder Aufnahmen mit
ausdrücklicher Erlaubnis verwenden.
