"""Nutzungsrechte der deutschen Piper-Stimmen (wichtig für Videos/YouTube).

Die Angaben stammen aus den MODEL_CARD-Dateien der Modellablage
rhasspy/piper-voices (Stand 2026-10). Sie sind eine Orientierung, keine
Rechtsberatung – im Zweifel die Lizenz beim Anbieter nachlesen.

Alles hier ist reine Information: keine Netzverbindung, keine API.
"""

from __future__ import annotations

from typing import List, Optional

# Angaben aus den MODEL_CARD-Dateien der Modellablage rhasspy/piper-voices
# (Stand 2026-10). "kommerziell" heißt: darf in Videos verwendet werden, mit
# denen du Geld verdienst (Werbung, Sponsoring, Produkte, Bezahlangebote).
VOICE_LICENSES = {
    "thorsten": {
        "license": "CC0 1.0 (Gemeinfreiheit)",
        "commercial": True,
        "attribution": "nicht erforderlich",
        "gender": "männlich",
        "note": "Von Thorsten Müller selbst freigegeben – die unkomplizierteste Wahl.",
    },
    "thorsten_emotional": {
        "license": "CC0 1.0 (Gemeinfreiheit)",
        "commercial": True,
        "attribution": "nicht erforderlich",
        "gender": "männlich",
        "note": "Wie Thorsten, zusätzlich mit Emotions-Kennungen im Text.",
    },
    "kerstin": {
        "license": "CC0 1.0 (Gemeinfreiheit)",
        "commercial": True,
        "attribution": "nicht erforderlich",
        "gender": "weiblich",
        "note": "Nur Qualitätsstufe „low“ (16 kHz) – für Video ok, aber weniger klar.",
    },
    "mls": {
        "license": "CC BY 4.0",
        "commercial": True,
        "attribution": "erforderlich (MLS-Datensatz + Piper nennen)",
        "gender": "236 Sprecher",
        "note": "Beste Auswahl für tiefe, ältere Männerstimmen – Namensnennung nötig.",
    },
    "eva_k": {
        "license": "M-AILABS (BSD-artig)",
        "commercial": True,
        "attribution": "erforderlich (Copyright-Hinweis M-AILABS beibehalten)",
        "gender": "weiblich",
        "note": "Sehr kleine Stimmprobe (x_low) – nur für kurze Einwürfe.",
    },
    "karlsson": {
        "license": "M-AILABS (BSD-artig)",
        "commercial": True,
        "attribution": "erforderlich (Copyright-Hinweis M-AILABS beibehalten)",
        "gender": "männlich",
        "note": "Nur „low“, eher rau.",
    },
    "ramona": {
        "license": "M-AILABS (BSD-artig)",
        "commercial": True,
        "attribution": "erforderlich (Copyright-Hinweis M-AILABS beibehalten)",
        "gender": "weiblich",
        "note": "Nur „low“.",
    },
    "pavoque": {
        "license": "CC BY-NC-SA 4.0",
        "commercial": False,
        "attribution": "erforderlich – aber kommerzielle Nutzung verboten",
        "gender": "männlich",
        "note": "NICHT für monetarisierte Kanäle oder Firmenvideos (NC = non-commercial).",
    },
}

XTTS_COMMERCIAL_NOTE = (
    "XTTS-v2 (eigene Stimmkopie) steht unter der Coqui Public Model License 1.0.0: "
    "„This license allows only non-commercial use of a machine learning model and "
    "its outputs.“ Sobald du direkt oder indirekt Geld mit dem Video verdienst "
    "(Werbung, Sponsoring, Produktlinks, Firmenkanal), ist die Nutzung der "
    "XTTS-Ausgabe nicht erlaubt. Für YouTube mit Monetarisierung also: Piper nehmen."
)

ATTRIBUTION_TEMPLATE = (
    "Sprachausgabe: Piper (MIT) – Stimme „{voice}“ ({license}), "
    "trainiert mit dem MLS-Datensatz (CC BY 4.0, https://www.openslr.org/94/)."
)


def voice_license(voice_name: str) -> Optional[dict]:
    """Ordnet einen Piper-Stimmenamen (z. B. de_DE-thorsten-medium) seiner Lizenz zu."""
    name = (voice_name or "").lower()
    if not name.startswith("de_de-"):
        return None
    rest = name[len("de_de-"):]
    # Stimmname endet vor der Qualitätsstufe (low/medium/high/x_low)
    for quality in ("x_low", "medium", "high", "low"):
        if rest.endswith("-" + quality):
            rest = rest[: -(len(quality) + 1)]
            break
    entry = VOICE_LICENSES.get(rest)
    if entry is None:
        return None
    return {"voice": rest, **entry}


def license_table() -> List[dict]:
    """Alle deutschen Stimmen mit Lizenz und kommerzieller Nutzbarkeit."""
    rows = []
    for voice, entry in VOICE_LICENSES.items():
        rows.append({"voice": voice, **entry})
    rows.sort(key=lambda row: (not row["commercial"], row["voice"]))
    return rows
