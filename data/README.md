# Lokaler Datenordner

Hier liegen **nur auf deinem Laptop** alle persönlichen Dateien. Dieser Ordner
gehört **nicht** zu GitHub – die `.gitignore` schließt ihn vollständig aus.

| Ordner | Inhalt |
| --- | --- |
| `aufnahmen/` | importierte und aufgenommene Original-WAV-Dateien (unverändert) |
| `master/` | aufbereitete Referenz der Ausgangsstimme (Mono, max. 30 s) + `ausgangsstimme.json` (gemessene Sprechlage) |
| `ergebnisse/` | erzeugte Sprachdateien als WAV |
| `tmp/` | temporäre Vorschaudateien (werden nach 24 h automatisch gelöscht) |
| `modelle/piper/` | deutsche Piper-Stimmen (`*.onnx` + `*.onnx.json`) |
| `modelle/xtts/` | optionales XTTS-v2-Modell für die eigene Stimmkopie |

Die eigene Referenzaufnahme (Ausgangsstimme) und das daraus erzeugte
Stimmprofil liegen ebenfalls hier – sie sind persönliche Sprachdaten.

Diese Dateien niemals committen, hochladen oder in ein Repository legen.
Löschen kannst du sie jederzeit direkt in der App oder im Dateimanager.
