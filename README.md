# StimmenClonewandler

Eine **kostenlose, vollständig lokale Web-App** für deutsche Sprachaufnahmen und
Sprachausgabe auf dem eigenen Laptop – gedacht für einen älteren Dell-Laptop
**ohne Grafikkarte**.

> **Datenschutz-Hinweis (auch in der App sichtbar):**
> „Alle Audiodateien und Sprachmodelle werden ausschließlich auf diesem Laptop
> verarbeitet. Es erfolgt kein Upload ins Internet.“

Die App läuft im Browser, aber der Browser spricht **nur** mit einem lokalen
Server auf `http://127.0.0.1:8765`. Es gibt keine Cloud, keine API, keinen
API-Schlüssel, keinen externen Voice-Anbieter und keine Telemetrie.

---

## Inhalt

1. [Was die App kann – und was ehrlich nicht](#1-was-die-app-kann--und-was-ehrlich-nicht)
2. [Installation unter Windows (Schritt für Schritt)](#2-installation-unter-windows-schritt-für-schritt)
3. [Sprachmodell lokal bereitstellen](#3-sprachmodell-lokal-bereitstellen)
4. [Deine eigene Stimme als Ausgangsstimme](#4-deine-eigene-stimme-als-ausgangsstimme)
5. [Benutzung](#5-benutzung)
6. [Langsamer CPU-Modus und Hardware-Prüfung](#6-langsamer-cpu-modus-und-hardware-prüfung)
7. [Dein Laptop: Dell Latitude 5530](#7-dein-laptop-dell-latitude-5530)
8. [Fehlermeldungen verstehen](#8-fehlermeldungen-verstehen)
9. [Datenschutz und Löschen der Daten](#9-datenschutz-und-löschen-der-daten)
10. [Projektstruktur](#10-projektstruktur)
11. [GitHub-Regeln dieses Projekts](#11-github-regeln-dieses-projekts)
12. [Rechtliches und Zustimmung](#12-rechtliches-und-zustimmung)
13. [Fehlersuche](#13-fehlersuche)
14. [Entwicklung und Tests](#14-entwicklung-und-tests)

---

## 1. Was die App kann – und was ehrlich nicht

### Funktioniert vollständig lokal

- **WAV-Dateien importieren** (PCM-WAV, 8/16/24/32 Bit, Mono/Stereo).
  Die Originaldatei bleibt unverändert; es wird eine Kopie abgelegt.
- **Direkt über das Mikrofon aufnehmen** (Browser-Mikrofon, Mono-WAV).
- **Anhören und vergleichen** – zwei Dateien (Aufnahme und/oder Ergebnis)
  einzeln oder nacheinander abspielen.
- **Werte anzeigen:** Samplerate, Kanäle, Bittiefe, Dauer, Spitzenpegel,
  Lautheit (RMS), Abstand Stimme/Grundgeräusch in dB.
- **Übersteuerung erkennen:** exakte Zählung der Samples am Vollausschlag,
  Warnung bei hörbaren Verzerrungen.
- **Starkes Hintergrundgeräusch erkennen:** Schätzung des Rauschabstands
  (Sprache gegen Grundgeräusch) mit Warnung.
- **Master-Aufnahme erstellen:** aufbereitete Referenz (Mono, Stille
  abgeschnitten, normalisiert, max. 30 s). Das Original bleibt erhalten.
- **Eigene Stimme als Ausgangsstimme:** Referenzaufnahme ablegen, Stimmlage
  messen, und die Modellstimme automatisch auf diese Sprechlage ziehen
  (Tonhöhen-Anpassung, Dauer bleibt gleich).
- **Grobe Stimmanalyse der Referenz:** geschätzte Sprechlage (Grundfrequenz),
  Tonhöhen-Schwankung und ein daraus abgeleiteter Stil-Vorschlag
  („Diesen Stil übernehmen“). Ausdrücklich eine Schätzung, keine Stimmkopie.
- **Master-Datei als WAV herunterladen.**
- **Deutschen Text eingeben und lokal vorlesen lassen** (Piper, CPU).
- **Ergebnis anhören und als WAV speichern** (`data/ergebnisse`).
- **Aufnahmen und Ergebnisse einzeln löschen.**
- **Fortschrittsanzeige** mit Abschnitt, Prozentwert, Laufzeit und Abbruch.
- **Deutsche Oberfläche, dunkles Design mit warmen Goldakzenten.**
- **Hardware-Prüfung beim Start** mit ehrlichen Meldungen.

### Was ehrlich *nicht* geht (und auch nicht behauptet wird)

- **Eine echte Stimmkopie auf diesem Laptop ist nicht realistisch.**
  Die App kann deine Stimme nicht mit zwei Minuten Aufnahme „nachbauen“.
  Das ist ein ehrliches Ergebnis der Hardware-Grenzen, kein Bug.
- **Piper erzeugt eine Modellstimme, nicht deine Stimme.** Der Stimmcharakter
  kommt aus dem lokalen Modell. Die App formt ihn mit Vorsicht in Richtung
  „männlich, etwas älter, warm, leicht tief, leicht rau, ruhig, mystisch,
  weise, langsam“ – aber sie behauptet nie, das sei eine Kopie deiner Stimme.
- **XTTS-v2 (echte Referenzstimm-Nachbildung)** ist optional einbaubar.
  Es braucht ~2 GB Modell, PyTorch und auf einer reinen CPU oft das 5- bis
  30-Fache der Sprechdauer. Ist es nicht vorhanden, sagt die App das klar –
  und meldet **nie** fälschlich, ein Modell sei erstellt worden.
- **Kein Modell-Download durch die App.** Modelle legst du selbst ab
  (siehe Abschnitt 3). So hast du die volle Kontrolle.

---

## 2. Installation unter Windows (Schritt für Schritt)

Voraussetzungen: Windows 10/11, ca. 1 GB freier Speicher, Internet
**nur einmalig** für die Installation der Python-Pakete.

1. **Python 3.9–3.12 installieren**
   - <https://www.python.org/downloads/windows/>
   - Beim Installieren unbedingt **„Add python.exe to PATH“** anhaken.
   - Prüfen: `Eingabeaufforderung` öffnen und `python --version` eingeben.

2. **Projektordner** an einen Ort deiner Wahl kopieren, z. B.
   `C:\Users\DeinName\StimmenClonewandler`.

3. **`start_windows.bat` doppelklicken.**
   Das Skript erledigt automatisch:
   - virtuelle Umgebung `.venv` anlegen,
   - die Pakete aus `requirements.txt` installieren (einmalig Internet),
   - die lokalen Ordner in `data\` anlegen,
   - den Server starten und den Browser öffnen.

4. Im Browser erscheint **<http://127.0.0.1:8765>**.
   Beenden: im schwarzen Fenster `Strg+C` drücken oder das Fenster schließen.

> Beim ersten Mikrofon-Aufnehmen fragt der Browser nach der Erlaubnis.
> Diese Erlaubnis gilt nur für `127.0.0.1`, also für diesen Laptop.

### Linux / macOS (zum Testen)

```bash
chmod +x start.sh
./start.sh
```

Oder manuell:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.server
```

### Manuelle Installation (falls das Startskript nicht verwendet werden soll)

```bat
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m app.server
```

Die App bindet ausschließlich an `127.0.0.1` und ist damit im Heimnetz
**nicht** erreichbar. Ein anderer Port lässt sich setzen:
`set SCW_PORT=8800` vor dem Start.

---

## 3. Sprachmodell lokal bereitstellen

Die App lädt **nichts** selbst herunter. Du entscheidest bewusst, welche
Stimme auf deinem Laptop liegt.

1. Ordner öffnen: `data\modelle\piper\`
2. Eine **deutsche Piper-Stimme** deiner Wahl hineinlegen. Benötigt werden
   immer **zwei** Dateien mit gleichem Namen:

   ```
   data/modelle/piper/de_DE-thorsten-medium.onnx
   data/modelle/piper/de_DE-thorsten-medium.onnx.json
   ```

3. In der App auf **System & Modell → Erneut prüfen** klicken.
   Unter „Sprachmodelle“ erscheint die Stimme als *Deutsch*.

**Empfehlung für die gewünschte Stimme:** eine **männliche deutsche
Piper-Stimme in mittlerer Qualität** (`-medium`, ca. 60 MB) – z. B.
`de_DE-thorsten-medium`. Sie klingt natürlich, läuft auf zwei Kernen und
lässt sich mit den Stil-Vorlagen gut in Richtung „warm, ruhig, leicht tief“
formen. Probiere die Stile in der App durch; die Klangfarbe selbst stammt
immer vom Modell.

**Wichtig zu den Modell-Dateien:**

- Modelle sind **kein Quellcode** und gehören **nicht** zu GitHub.
  Die `.gitignore` schließt `*.onnx` und `data/` vollständig aus.
- Modelle haben eigene Lizenzen (Piper selbst ist MIT-lizenziert, die
  einzelnen Stimmen oft CC BY / öffentlich). Prüfe die Lizenz der Stimme,
  bevor du sie nutzt.
- Nach dem Ablegen funktioniert die App **ohne Internet**.

### Optionale eigene Stimmkopie (XTTS-v2)

Nur wenn du das wirklich willst – auf einem älteren Laptop meist unbrauchbar:

```bat
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install coqui-tts
```

Danach ein XTTS-v2-Modell (Modell, `config.json`, `vocab.json`) nach
`data\modelle\xtts\` legen, in der App eine **Master-Aufnahme** festlegen
(mindestens 6 s, besser 12–30 s ruhige Sprache) und als Verfahren
„Eigene Stimmkopie (XTTS-v2)“ wählen. Fehlt etwas, meldet die App das
ehrlich und erzeugt **keine** Datei.

---

## 4. Deine eigene Stimme als Ausgangsstimme

Die App nimmt deine Referenzaufnahme als **Ausgangsstimme**. Wichtig ist, was
das ehrlich bedeutet – es sind drei Bausteine, die unterschiedlich viel können:

| Baustein | Was er tut | Grenze |
| --- | --- | --- |
| **Stimmprofil** | misst mittlere Sprechlage (Grundfrequenz), Tonumfang und einen Helligkeitswert deiner Aufnahme | reine Schätzung, kein Modell |
| **Tonhöhen-Anpassung** (aktiv) | verschiebt die Stimmlage der Modellstimme auf deine Lage, ohne die Sprechdauer zu verändern (WSOLA + Neubetastung, max. ±4 Halbtöne) | verändert **nicht** die Klangfarbe/Artikulation |
| **XTTS-v2** (optional) | bildet deine Stimmfarbe aus der Referenz nach | ~2 GB Modell, PyTorch, auf CPU sehr langsam; nur wenn du es bewusst installierst |

### So legst du deine Stimme fest

1. Tab **Aufnahmen** → deine WAV-Datei importieren (oder direkt aufnehmen).
2. Bei der Aufnahme **„Als Master festlegen“** drücken.
   Die App erzeugt daraus die aufbereitete Referenz (Mono, Stille abgeschnitten,
   normalisiert, maximal 30 s – bei längeren Dateien automatisch die
   aussagekräftigste Passage) und speichert das Stimmprofil in
   `data/master/ausgangsstimme.json`.
3. Im Tab **Aufnahmen → Master-Aufnahme** siehst du die gemessene Sprechlage und
   den Stil-Vorschlag („Diesen Stil übernehmen“).
4. Im Tab **Sprachausgabe** ist der Schalter
   **„Stimmlage an meine Ausgangsstimme anpassen“** aktiv. Unter dem Ergebnis
   stehen die Zahlen: Ziel-Frequenz, gemessene Modell-Frequenz und die
   tatsächlich verschobenen Halbtöne.

**Ehrlich gesagt:** Das macht aus der Modellstimme keine Kopie deiner Stimme.
Es gleicht die Sprechlage an – der Klang (Timbre, Artikulation, Charakter) bleibt
der des lokalen Modells. Eine echte Stimmnachbildung leistet nur XTTS-v2
(siehe Abschnitt 3). Die App behauptet nie mehr, als sie getan hat: Im Ergebnis
steht entweder „an Ausgangsstimme angeglichen“ oder „nicht angepasst“ mit Grund.

### Warum nur ±4 Halbtöne?

Stärkere Verschiebungen verändern die Formanten hörbar („Chipmunk“ bzw.
künstlich tief) und klingen nicht mehr glaubwürdig. Wenn deine Sprechlage und
die Modellstimme weiter auseinanderliegen, ist ein anderes Sprachmodell die
bessere Lösung als eine extreme Tonhöhenkorrektur.

### Deine Aufnahme bleibt lokal

Die Referenzdatei, das Profil und alle erzeugten Ergebnisse liegen
ausschließlich in `data/` (siehe `.gitignore`) und werden **nicht** zu GitHub
hochgeladen. Die Aufnahme, die du bereitgestellt hast, wurde einmalig in den
lokalen Ordner übernommen; im Repository ist sie nicht enthalten.

---

## 5. Benutzung

### Tab „Aufnahmen“

- **Importieren:** WAV-Datei in den gestrichelten Bereich ziehen oder klicken.
  Nicht-WAV-Dateien werden mit Hinweis abgelehnt.
- **Mikrofon:** „Aufnahme starten“, ruhig und gleichmäßig sprechen
  (ca. 20 cm Abstand), „Stoppen“. Der Pegelbalken zeigt die Aussteuerung;
  wird er rot, ist die Aufnahme zu laut.
- **Karten pro Aufnahme** zeigen alle Werte und Warnungen.
- **Aktionen:** Als Master festlegen, Herunterladen, Neu analysieren, Löschen.
- **Master-Aufnahme:** aufbereitete Referenz (max. 30 s) inkl. Qualitätsurteil.
- **Anhören & vergleichen:** Datei A und B wählen, einzeln oder
  „Erst A, dann B“ abspielen.

### Tab „Sprachausgabe“

1. Deutschen Text eingeben (bis 4000 Zeichen, „Beispieltext einfügen“ hilft).
2. **Sprachmodell** wählen (deine lokalen Stimmen).
3. **Stimm-Stil** wählen:
   - *Weise & warm (empfohlen)* – ruhig, leicht tief, warm, ganz leichte Rauheit,
   - *Warm & ruhig* – nur dezente Wärme,
   - *Mystisch & tief* – dunkler, langsamer, Hauch Raum,
   - *Nur ruhig & langsam* – reines Tempo,
   - *Neutral* – Modellausgabe pur zum Vergleich.
4. **Intensität** (0–150 %) und **Sprechtempo** (80–125 %) feinjustieren.
5. Optional **Langsamer CPU-Modus** aktivieren.
6. „Text vorlesen“ – die Fortschrittsanzeige zeigt Abschnitt, Prozent und
   Laufzeit; „Abbrechen“ beendet den Auftrag.
7. Ergebnis anhören, Namen vergeben, **„Als WAV speichern“**.

> Ehrlich: Der Klang entsteht lokal aus dem Modell. Die Stil-Vorlagen
> verändern Tempo, Tonfarbe und eine sehr milde Sättigung – sie erzeugen
> keine neue Identität.

### Tab „Ergebnisse“

Alle gespeicherten Sprachdateien mit Werten, Wiedergabe, Download und Löschen.
Dateien liegen in `data\ergebnisse\`.

### Tab „System & Modell“

Hardware-Prüfung, lokale Engines, Geschwindigkeitstest, Modellliste,
Speicherplatzbelegung.

---

## 6. Langsamer CPU-Modus und Hardware-Prüfung

**Beim Start prüft die App automatisch:**

| Prüfung | Konsequenz |
| --- | --- |
| CPU-Kerne | 1 Kern → Warnung + Empfehlung „langsamer CPU-Modus“; 2 Kerne → Hinweis |
| freier Arbeitsspeicher | < 512 MB → **Fehler**: Modell kann nicht geladen werden; < 1 GB → Warnung |
| freier Speicherplatz | < 300 MB → **Fehler** |
| SSE4.1-Unterstützung | fehlt sie, erscheint eine Warnung (onnxruntime braucht sie meist) |
| Piper / onnxruntime | fehlt → **Fehler**, Sprachausgabe nicht möglich |
| deutsches Modell | fehlt → Warnung mit Anleitung |

**Langsamer CPU-Modus** (Checkbox in der Sprachausgabe):

- nur **1 Rechenkern**, damit der Laptop bedienbar bleibt,
- einfachere ONNX-Optimierung, weniger Speicherverbrauch,
- Ergebnis: längere Rechenzeit, aber stabiler Betrieb auf alten Geräten.

Der **Geschwindigkeitstest** (Tab „System & Modell“) erzeugt einen kurzen
Satz und zeigt, wie viel Rechenzeit pro Sekunde Audio nötig war
(z. B. „2,5× Echtzeit“).

---

## 7. Dein Laptop: Dell Latitude 5530

Gemeldete Ausstattung: Dell Latitude 5530 · Intel Core i5-1235U (12 Threads,
2 P-Kerne + 8 E-Kerne) · 8 GiB RAM · Intel Iris Xe (ADL GT2) · Ubuntu 26.04.1 LTS.

**Was die App daraus automatisch ableitet:**

| Wert | Bedeutung |
| --- | --- |
| Rechenmodus | **normal** (Hardware reicht), langsamer Modus bleibt als Option |
| Threads | 4 vorgeschlagen, 8 wählbar (mehr bringt kaum Tempo, kostet Akku/Wärme) |
| Grafikprozessor | wird nicht benötigt – alles läuft auf der CPU |
| Piper-Synthese | sehr gut nutzbar, etwa **3–10× schneller als Echtzeit** je nach Modellgröße |

**Empfehlung für dieses Gerät**

- Sprachmodell der Qualitätsstufe `medium` (z. B. eine deutsche männliche
  `de_DE-…-medium`-Stimme). `low` ist noch schneller, `high` lohnt auf 2 Kernen nicht.
- 4 Threads, langsamer CPU-Modus nur bei Akkubetrieb oder Hitzeproblemen.
- Beim ersten Mal den **Geschwindigkeitstest** (Tab „System & Modell“) ausführen:
  Er zeigt dir den echten Echtzeitfaktor dieses Laptops.

**XTTS-v2 (echte Stimmkopie) auf diesem Laptop – ehrliche Einschätzung**

- PyTorch (CPU) + Modell belegen ~4–5 GB Arbeitsspeicher. Bei 8 GiB gesamt
  funktioniert es nur, wenn fast alles andere geschlossen ist. Die App warnt
  dich, wenn weniger als 4,5 GB frei sind.
- Rechenzeit: realistisch **10–30× langsamer als Echtzeit** – ein Satz von
  10 Sekunden braucht also 2–5 Minuten. Für kurze Tests brauchbar, für lange
  Texte nicht.
- Qualität: aus 30 s Referenz brauchbar, aber nicht mit deiner Stimme identisch.
  Die App kennzeichnet solche Ergebnisse klar als „lokal mit Referenzstimme erzeugt“.

**Ubuntu-Start**

```bash
cd StimmenClonewandler
./start.sh          # legt .venv an, installiert, startet auf http://127.0.0.1:8765
```

Falls `python3-venv` fehlt: `sudo apt install python3-venv python3-pip`.
Mikrofon: GNOME fragt beim ersten Zugriff – die Erlaubnis gilt nur für
`127.0.0.1`.

---

## 8. Fehlermeldungen verstehen

Die App zeigt Fehler im Klartext und **behauptet nie**, etwas sei fertig,
wenn es nicht ist. Beispiele:

- *„Die lokale Sprach-Engine (Piper) ist nicht installiert. Es wurde kein
  Audio erzeugt.“* → `start_windows.bat` erneut ausführen (Installation).
- *„Es liegt kein Sprachmodell vor …“* → Abschnitt 3 dieser README.
- *„Das Sprachmodell konnte auf diesem Laptop nicht geladen werden.
  Technische Ursache: …“* → meist zu wenig RAM oder eine unvollständige
  Modelldatei.
- *„Die eigene Stimmkopie ist auf diesem Laptop nicht ausführbar. Es fehlt: …“*
  → ehrliche Auskunft; es wird nichts gespeichert.
- *„Für die Stimmkopie muss zuerst eine Master-Aufnahme festgelegt werden.“*
- *„Die Aufnahme ist zu kurz oder leer …“* → erneut aufnehmen.
- *„Diese Datei ist keine gültige PCM-WAV-Datei …“* → vorher umwandeln
  (z. B. mit `ffmpeg -i eingabe.mp3 -ac 1 -ar 44100 ausgabe.wav`).

---

## 9. Datenschutz und Löschen der Daten

- Der Server hört **nur** auf `127.0.0.1` – kein Zugriff aus dem Netzwerk.
- Kein Upload, keine Cloud, keine API, keine Schlüssel, keine Telemetrie.
- Kein Modell- oder Voice-Download durch die App.
- **Löschen:** in der App bei jeder Aufnahme und jedem Ergebnis über
  „Löschen“, oder den Ordner `data/` im Dateimanager.
- Temporäre Vorschaudateien in `data/tmp/` werden nach 24 Stunden
  automatisch entfernt.
- Empfehlung: `data/` in eine Sicherung aufnehmen, die **nicht** in der
  Cloud liegt (externe Festplatte), wenn du Aufnahmen behalten willst.

---

## 10. Projektstruktur

```
StimmenClonewandler/
├── app/
│   ├── __init__.py
│   ├── config.py          Pfade, Grenzen, Datenschutzhinweis
│   ├── server.py          lokaler Flask-Server (nur 127.0.0.1)
│   ├── jobs.py            Hintergrund-Aufträge mit Fortschritt
│   ├── hardware.py        Hardware-Prüfung, Engine- und Modellerkennung
│   ├── wav_io.py          WAV lesen/schreiben/bearbeiten (nur Standard-Python)
│   ├── analysis.py        Pegel, Übersteuerung, Rauschabstand
│   ├── storage.py         lokale Ablage für Aufnahmen und Ergebnisse
│   ├── master.py          Master-Aufnahme aufbereiten, Ausgangsstimme verwalten
│   ├── voice_profile.py   grobe Stimmanalyse + Stil-Empfehlung
│   ├── dsp.py             Zeitdehnung (WSOLA) + Tonhöhen-Anpassung (numpy)
│   ├── tts.py             lokale Sprachausgabe (Piper, optional XTTS)
│   └── static/            Oberfläche (index.html, style.css, app.js, favicon)
├── data/                  NUR lokal – von Git ausgeschlossen
│   ├── aufnahmen/         Originale (unverändert)
│   ├── master/            aufbereitete Referenz + Stimmprofil (ausgangsstimme.json)
│   ├── ergebnisse/        erzeugte WAV-Dateien
│   ├── tmp/               temporäre Vorschau
│   └── modelle/
│       ├── piper/         deutsche Piper-Stimmen
│       └── xtts/          optionales XTTS-v2-Modell
├── tests/                 Tests (WAV, Analyse, Ablage, API, Sprachkette)
│   └── test_voice_factory.py  erzeugt eine *Teststimme* (Ton) für End-to-End-Tests
├── start_windows.bat      Startskript für Windows
├── start.sh               Startskript für Linux/macOS
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 11. GitHub-Regeln dieses Projekts

Dieses Repository enthält **ausschließlich**:

- Quellcode (`app/`),
- Konfigurationsvorlagen (`requirements.txt`),
- Dokumentation (`README.md`, `data/README.md`),
- Startskripte und `.gitignore`.

**Nicht im Repository – und das bleibt so:**

- keine WAV-Aufnahmen, keine Sprachproben,
- keine Voice-Modelle (`*.onnx`, `*.pth`, …),
- keine persönlichen Sprachdaten, keine Ergebnisdateien,
- keine Geheimnisse, Schlüssel oder Tokens.

Zusätzlich gilt:

- **Keine GitHub Actions** für Voice-Cloning.
- **GitHub Pages wird nicht als Voice-Server verwendet** (die App braucht
  einen lokalen Python-Prozess; Pages könnte das gar nicht).
- **Kein Push, kein Deployment und kein Upload** erfolgt ohne deine
  ausdrückliche Bestätigung. Der aktuelle Arbeitsstand wurde **nicht
  gepusht**.

Die `.gitignore` schließt zusätzlich virtuelle Umgebungen, Caches,
Editor-Dateien und alle Audio-/Modellformate aus.

---

## 12. Rechtliches und Zustimmung

- Verwende **ausschließlich deine eigene Stimme** oder Aufnahmen, für deren
  Nutzung du eine **ausdrückliche Erlaubnis** besitzt.
- Das Nachahmen fremder Stimmen ohne Einverständnis kann Persönlichkeits-
  rechte verletzen und ist in der EU (u. a. AI Act, DSGVO) rechtlich riskant.
- Kennzeichne erzeugte Sprachaufnahmen gegenüber Dritten als synthetisch.
- Piper ist MIT-lizenziert; einzelne Stimmen haben eigene Lizenzen.
  XTTS-v2 (Coqui) unterliegt der Coqui Public Model License
  (nicht-kommerziell) – prüfe das vor einer Nutzung.

---

## 13. Fehlersuche

| Problem | Lösung |
| --- | --- |
| „Python wurde nicht gefunden“ | Python neu installieren, „Add python.exe to PATH“ anhaken |
| Installation schlägt fehl | einmalig Internet nötig, Firewall/Proxy prüfen, `python -m pip install -r requirements.txt` manuell ausführen |
| Kein Mikrofonzugriff | Browsermenü → Berechtigungen → Mikrofon für `127.0.0.1` erlauben |
| Port 8765 belegt | `set SCW_PORT=8800` und erneut starten |
| Seite lädt nicht | Serverfenster offen lassen; `http://127.0.0.1:8765` (nicht `https`) |
| Sprachausgabe sehr langsam | „Langsamer CPU-Modus“ an, Text in kürzere Abschnitte teilen, andere Programme schließen |
| Stimme klingt nicht deutsch | deutsches Modell (`de_DE-…`) wählen, siehe Abschnitt 3 |
| Modell wird nicht erkannt | beide Dateien (`*.onnx` **und** `*.onnx.json`) im selben Ordner, dann „Erneut prüfen“ |

---

## 14. Entwicklung und Tests

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install pytest onnx   # nur für die Tests
.venv/bin/python -m pytest tests -q           # Tests laufen ohne echtes Modell
.venv/bin/python -m app.server          # lokaler Start
```

Die Tests prüfen: WAV-Rundlauf, Analyse (Stille, Übersteuerung, Rauschen),
Stimmprofil, Master-Aufbereitung, Speicher-/Löschfunktionen, ehrliche
Fehlermeldungen ohne Modell und die API-Endpunkte.

Für den End-to-End-Test der Sprachkette wird mit dem optionalen Paket `onnx`
eine **Teststimme** erzeugt: ein kleiner ONNX-Graph, der einen Ton ausgibt –
kein echtes Sprachmodell. Damit lässt sich die komplette Kette (espeak-
Phonemisierung, ONNX-Sitzung, Abschnitte, Klangformung, Fortschritt,
WAV-Ausgabe, Speichern) ohne großen Download prüfen. Fehlt `onnx`, werden
diese Tests übersprungen.

**Hinweis zur Teststimme:** `de_DE-TESTTON-…` in einem Datenordner ist nur
ein Platzhalter für Tests (Ton statt Sprache). Für echte Sprachausgabe eine
richtige deutsche Piper-Stimme ablegen (Abschnitt 3).

**Technischer Hinweis:** Die App nutzt bewusst nur Flask, Piper und die
Python-Standardbibliothek. WAV-Verarbeitung, Analyse und Klangformung sind
ohne schwere Zusatzpakete umgesetzt, damit alles auf einem schwachen
Laptop flüssig bleibt.
