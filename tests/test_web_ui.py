"""Tests for the static web UI shell and bundled assets."""

from __future__ import annotations

from fastapi.testclient import TestClient

from web.app import create_app
from web.config import WebConfig


def test_static_assets_are_served_from_relative_paths() -> None:
    app = create_app(WebConfig(auth_enabled=False))
    client = TestClient(app)

    css_response = client.get("/static/app.css")
    js_response = client.get("/static/app.js")
    logo_response = client.get("/static/brand/bitcoin-shield-logo.png")

    assert css_response.status_code == 200
    assert css_response.headers["content-type"].startswith("text/css")
    assert "--orange-primary: #F7931A;" in css_response.text

    assert js_response.status_code == 200
    assert js_response.headers["content-type"].startswith("text/javascript")
    assert "api/tax/gains" in js_response.text
    assert "api/auth/login" in js_response.text

    assert logo_response.status_code == 200
    assert logo_response.headers["content-type"] == "image/png"


def test_ui_shell_references_relative_asset_paths() -> None:
    app = create_app(WebConfig(auth_enabled=False, web_base_path="/bitcoin-accounting"))
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="static/app.css"' in response.text
    assert 'src="static/brand/bitcoin-shield-logo.png"' in response.text
    assert 'src="static/app.js"' in response.text
