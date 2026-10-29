"""Tests für Doppelstart-Erkennung und Stopp-Verhalten."""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import server


class _HealthHandler(BaseHTTPRequestHandler):
    """Minimaler Nachbau des /api/health-Endpunkts."""

    payload = b'{"ok": true, "app": "StimmenClonewandler", "version": "1.0.0", "pid": 4242}'
    status = 200
    body = payload

    def do_GET(self):  # noqa: N802
        if self.path != "/api/health":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        return


def _serve(handler):
    httpd = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, httpd.server_address[1]


def test_detects_running_app():
    httpd, port = _serve(_HealthHandler)
    try:
        version = server.running_instance("127.0.0.1", port)
        assert version == "1.0.0"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_ignores_foreign_service():
    class Foreign(_HealthHandler):
        body = b'{"hello": "world"}'

    httpd, port = _serve(Foreign)
    try:
        assert server.running_instance("127.0.0.1", port) is None
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_ignores_error_status():
    class Broken(_HealthHandler):
        status = 500

    httpd, port = _serve(Broken)
    try:
        assert server.running_instance("127.0.0.1", port) is None
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_ignores_non_json_answer():
    class Html(_HealthHandler):
        body = b"<html>kein json</html>"

    httpd, port = _serve(Html)
    try:
        assert server.running_instance("127.0.0.1", port) is None
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_free_port_returns_none():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()
    assert server.running_instance("127.0.0.1", free_port, timeout=0.3) is None


def test_health_endpoint_reports_instance(client):
    payload = client.get("/api/health").get_json()
    assert payload["ok"] is True
    assert payload["app"] == "StimmenClonewandler"
    assert payload["version"]
    assert isinstance(payload["pid"], int)
