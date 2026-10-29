"""Tests für die Nutzungsrechte-Übersicht (wichtig für Videos/YouTube).

Die Tabelle ist eine statische Zuordnung – hier wird geprüft, dass sie
vollständig, korrekt sortiert und über die Kommandozeile erreichbar ist.
"""

from __future__ import annotations

import json

from app import hardware, voice_licenses, voice_setup


def test_thorsten_is_cc0_and_commercial():
    info = voice_licenses.voice_license("de_DE-thorsten-medium")
    assert info["license"].startswith("CC0")
    assert info["commercial"] is True
    assert info["attribution"] == "nicht erforderlich"


def test_pavoque_is_not_allowed_for_monetized_videos():
    info = voice_licenses.voice_license("de_DE-pavoque-low")
    assert info["commercial"] is False
    assert "NC" in info["license"]


def test_mls_allows_commercial_but_needs_attribution():
    info = voice_licenses.voice_license("de_DE-mls-medium")
    assert info["commercial"] is True
    assert "CC BY 4.0" in info["license"]
    assert "MLS" in info["attribution"].upper()


def test_quality_suffixes_are_stripped():
    assert voice_licenses.voice_license("de_DE-thorsten_emotional-medium")["voice"] == "thorsten_emotional"
    assert voice_licenses.voice_license("de_DE-eva_k-x_low")["voice"] == "eva_k"
    assert voice_licenses.voice_license("de_DE-thorsten-high")["voice"] == "thorsten"


def test_other_languages_have_no_entry():
    assert voice_licenses.voice_license("en_US-lessac-medium") is None
    assert voice_licenses.voice_license("") is None


def test_license_table_lists_allowed_voices_first():
    rows = voice_licenses.license_table()
    flags = [row["commercial"] for row in rows]
    assert flags == sorted(flags, reverse=True)
    assert {row["voice"] for row in rows} == set(voice_licenses.VOICE_LICENSES)
    assert any(row["voice"] == "pavoque" for row in rows)


def test_xtts_note_states_the_non_commercial_limit():
    note = voice_licenses.XTTS_COMMERCIAL_NOTE
    assert "non-commercial" in note
    assert "direkt oder indirekt" in note
    assert "Piper" in note


def test_attribution_template_mentions_license_and_source():
    text = voice_licenses.ATTRIBUTION_TEMPLATE.format(voice="mls-medium", license="CC BY 4.0")
    assert "mls-medium" in text
    assert "CC BY 4.0" in text
    assert "openslr.org" in text


def test_cli_licenses_prints_table(capsys):
    assert voice_setup.main(["--licenses"]) == 0
    out = capsys.readouterr().out
    assert "Nutzungsrechte" in out
    assert "pavoque" in out
    assert "NEIN" in out
    assert "non-commercial" in out
    assert "coqui" not in out.lower() or "Coqui Public Model License" in out


def test_voice_metadata_carries_the_license(monkeypatch, tmp_path):
    """Die Oberfläche zeigt die Lizenz beim Auswählen der Stimme an."""
    config = {
        "audio": {"sample_rate": 22050},
        "language": {"code": "de"},
        "dataset": "thorsten",
        "num_speakers": 1,
    }
    (tmp_path / "de_DE-thorsten-medium.onnx").write_bytes(b"x")
    (tmp_path / "de_DE-thorsten-medium.onnx.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    monkeypatch.setattr(hardware, "PIPER_DIR", tmp_path)

    voice = next(v for v in hardware.find_piper_voices() if v["name"] == "de_DE-thorsten-medium")
    assert voice["license"].startswith("CC0")
    assert voice["commercial_use"] is True
    assert voice["attribution"] == "nicht erforderlich"
