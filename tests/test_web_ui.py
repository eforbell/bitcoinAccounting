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
    apple_touch_icon_response = client.get("/static/brand/apple-touch-icon.png")
    favicon_16_response = client.get("/static/brand/favicon-16x16.png")
    favicon_32_response = client.get("/static/brand/favicon-32x32.png")
    favicon_response = client.get("/static/brand/favicon.ico")

    assert css_response.status_code == 200
    assert css_response.headers["content-type"].startswith("text/css")
    assert ".page-shell" in css_response.text

    assert js_response.status_code == 200
    assert js_response.headers["content-type"].startswith("text/javascript")
    assert "api/tax/gains" in js_response.text
    assert "api/auth/login" in js_response.text
    assert "api/chain/status" in js_response.text
    assert "api/verification/proof-of-spend/run" in js_response.text
    assert "include_inactive" not in js_response.text
    assert "inactive-toggle" not in js_response.text

    assert logo_response.status_code == 200
    assert logo_response.headers["content-type"] == "image/png"
    for response in (apple_touch_icon_response, favicon_16_response, favicon_32_response):
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
    assert favicon_response.status_code == 200
    assert favicon_response.headers["content-type"] in {
        "image/x-icon",
        "image/vnd.microsoft.icon",
    }


def test_ui_shell_references_relative_asset_paths() -> None:
    app = create_app(WebConfig(auth_enabled=False, web_base_path="/bitcoin-accounting"))
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="sovereign-fonts.css"' in response.text
    assert 'href="static/sovereign-chassis.css"' in response.text
    assert 'href="static/tokens.css"' in response.text
    assert 'href="static/accounting-skin.css"' in response.text
    assert 'href="static/app.css"' in response.text
    assert 'src="static/brand/bitcoin-shield-logo.png"' in response.text
    assert 'rel="apple-touch-icon" sizes="180x180" href="static/brand/apple-touch-icon.png"' in response.text
    assert 'rel="icon" type="image/png" sizes="32x32" href="static/brand/favicon-32x32.png"' in response.text
    assert 'rel="icon" type="image/png" sizes="16x16" href="static/brand/favicon-16x16.png"' in response.text
    assert 'src="static/app.js"' in response.text
    assert "inactive-toggle" not in response.text
    assert 'id="wallet-proof-form"' in response.text
    assert 'id="wallet-proof-latest"' in response.text
    assert 'id="wallet-verification-history"' not in response.text


def test_sovereign_fonts_css_route_uses_env_source_selection(monkeypatch) -> None:
    app = create_app(WebConfig(auth_enabled=False))
    client = TestClient(app)

    monkeypatch.setenv("SOVEREIGN_FONT_SOURCE", "google")
    response = client.get("/sovereign-fonts.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert "fonts.googleapis.com" in response.text

    monkeypatch.setenv("SOVEREIGN_FONT_SOURCE", "off")
    response_off = client.get("/sovereign-fonts.css")
    assert response_off.status_code == 200
    assert "disabled" in response_off.text.lower()
