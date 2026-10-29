"""Tests für den automatischen Port-Fallback."""

from __future__ import annotations

import socket

import pytest

from app import server


def _occupy(host: str = "127.0.0.1"):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, 0))
    sock.listen(1)
    return sock, sock.getsockname()[1]


def test_free_port_is_detected():
    sock, port = _occupy()
    try:
        assert server.port_is_free("127.0.0.1", port) is False
    finally:
        sock.close()
    assert server.port_is_free("127.0.0.1", port) is True


def test_next_free_port_is_used():
    sock, port = _occupy()
    try:
        chosen, moved = server.find_free_port("127.0.0.1", port, attempts=5)
        assert moved is True
        assert chosen > port
        assert server.port_is_free("127.0.0.1", chosen) is True
    finally:
        sock.close()


def test_preferred_port_used_when_free():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()

    chosen, moved = server.find_free_port("127.0.0.1", free_port, attempts=3)
    assert chosen == free_port
    assert moved is False


def test_no_free_port_raises():
    sock, port = _occupy()
    others = []
    try:
        for offset in range(1, 3):
            extra = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                extra.bind(("127.0.0.1", port + offset))
            except OSError:
                extra.close()
                continue
            extra.listen(1)
            others.append(extra)
        if len(others) < 2:
            pytest.skip("Nachbarports nicht verfügbar")
        with pytest.raises(OSError):
            server.find_free_port("127.0.0.1", port, attempts=3)
    finally:
        sock.close()
        for extra in others:
            extra.close()


def test_port_is_free_again_right_after_shutdown():
    """Nach dem Schließen eines Servers darf der Port sofort wieder frei sein.

    Vor der Korrektur (SO_REUSEADDR) meldete die Prüfung hier fälschlich
    „belegt“ – die App startete dann auf einem Ausweichport, obwohl 8765 frei war.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(1)
    # eine echte Verbindung aufbauen und wieder schließen -> TIME_WAIT
    client = socket.create_connection(("127.0.0.1", port), timeout=1)
    conn, _ = sock.accept()
    conn.close()
    client.close()
    sock.close()

    assert server.port_is_free("127.0.0.1", port) is True
