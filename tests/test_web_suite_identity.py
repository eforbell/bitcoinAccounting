"""Suite identity (Home Base Feature-10): in tailnet mode the request guard and the member gate decide who reaches
Bitcoin Accounting, and Home Base's directory replaces the passphrase. Startup refuses a bad configuration, and
local mode stays exactly as it was."""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from sovereign_auth import SnapshotState, parse_snapshot, sign_token

from web.app import create_app
from web.config import WebConfig
from web.suite_identity import create_suite_identity, home_base_uid, public_address

HOST = "smith-bitcoin-accounting.example-tailnet.ts.net"
ORIGIN = f"https://{HOST}"
# Home Base's signing key, as the snapshot publishes it: made here, for these tests only.
KEY = Ed25519PrivateKey.generate()
PUBLIC_KEY = base64.urlsafe_b64encode(KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).rstrip(b"=").decode()
BASE = "/bitcoin-accounting"
TAILNET_ENV = {
    "SOVEREIGN_AUTH_MODE": "tailnet",
    "SOVEREIGN_LISTEN": "unix:/run/sovereign-apps/bitcoin-accounting/app.sock",
    "SOVEREIGN_HOMEBASE_UID": "991",
    "APP_PUBLIC_URL": f"{ORIGIN}{BASE}/",
}


def _member(user_id, name, role, apps, status="active"):
    return {
        "user_id": user_id, "member_id": f"m_{user_id}", "login": f"{user_id}@example.com", "name": name,
        "role": role, "status": status, "epoch": 1, "apps": apps,
    }


SNAPSHOT = parse_snapshot({
    "format": 1, "household": "smith", "generation": 3, "written_at": "2026-11-14T12:00:00.000Z", "global_epoch": 1,
    "keys": [{"kid": "k1", "public_key": PUBLIC_KEY}],
    "members": [
        _member("1001", "Pat", "parent", ["bitcoin-accounting", "family-pulse"]),
        _member("1002", "Kit <b>", "kid", ["bitcoin-accounting"]),
        _member("1003", "Other parent", "parent", ["family-pulse"]),
        _member("1004", "Former", "parent", ["bitcoin-accounting"], status="disabled"),
    ],
})


class Reader:
    def __init__(self, ok=True):
        self.ok = ok

    def current(self):
        if self.ok:
            return SnapshotState(ok=True, snapshot=SNAPSHOT)
        return SnapshotState(ok=False, reason="stale", message="old")


def who(user_id):
    return {"x-sovereign-user-id": user_id, "x-sovereign-login": f"{user_id}@example.com"}


def passkey_cookie(user_id="1001", *, checked_ago=0, **claims):
    """The cookie Home Base's step-up helper sets on this hostname after a passkey check."""
    now = int(time.time())
    payload = {
        "typ": "assurance", "kid": "k1", "household": "smith", "aud": HOST, "sub": user_id, "sid": "s_1",
        "cred": "c_1", "kind": "synced", "epoch": 1, "global_epoch": 1,
        "auth_time": now - checked_ago, "iat": now - checked_ago, "exp": now + 3600, **claims,
    }
    return f"__Host-sv_assurance={sign_token(payload, KEY)}"


NAVIGATE = {"sec-fetch-site": "none", "sec-fetch-mode": "navigate", "sec-fetch-dest": "document"}
SAME_ORIGIN = {"sec-fetch-site": "same-origin", "sec-fetch-mode": "cors", "sec-fetch-dest": "empty"}
WRITE = {**SAME_ORIGIN, "origin": ORIGIN, "content-type": "application/json"}
KID, NO_ACCESS, DISABLED = who("1002"), who("1003"), who("1004")
# A parent who checked with a passkey an hour ago: enough to open the app (passkeys: test_web_passkeys.py).
PARENT = {**who("1001"), "cookie": passkey_cookie(checked_ago=3600)}
# Bitcoin Accounting as Home Base installs it today: the passphrase on and configured.
INSTALLED = WebConfig(web_base_path=BASE, auth_enabled=True, auth_passphrase="orange-hodl", session_secret="test-secret")


@pytest.fixture(autouse=True)
def _no_mode_from_the_environment(monkeypatch):
    monkeypatch.delenv("SOVEREIGN_AUTH_MODE", raising=False)


def tailnet_client(reader=None, config=INSTALLED):
    suite = create_suite_identity(TAILNET_ENV, reader=reader or Reader())
    return TestClient(create_app(config, suite=suite), follow_redirects=False)


def local_client(config=INSTALLED):
    return TestClient(create_app(config, suite=create_suite_identity({})), follow_redirects=False)


# --- startup ---------------------------------------------------------------------------------------------

def test_an_unset_mode_is_local_and_changes_nothing():
    suite = create_suite_identity({})
    assert not suite.tailnet and suite.guard is None
    response = local_client().get(f"{BASE}/", headers=NAVIGATE)
    assert response.status_code == 200 and "Sec-Fetch-Site" not in response.headers.get("vary", "")


def test_local_mode_ignores_identity_headers_and_fetch_metadata():
    client = local_client(WebConfig(web_base_path=BASE))
    assert client.post(f"{BASE}/api/nothing-here", headers={"origin": "https://evil.example"}).status_code == 404
    # The member Home Base names means nothing here: the passphrase still decides.
    assert local_client().get(f"{BASE}/api/auth/me", headers=PARENT).status_code == 401


def test_create_app_reads_the_mode_from_the_environment(monkeypatch):
    for key, value in TAILNET_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("SOVEREIGN_HOMEBASE_UID")
    with pytest.raises(ValueError, match="SOVEREIGN_HOMEBASE_UID"):
        create_app(INSTALLED)


@pytest.mark.parametrize("change, message", [
    ({"SOVEREIGN_AUTH_MODE": "Tailnet"}, "local or tailnet"),
    ({"SOVEREIGN_AUTH_MODE": ""}, "local or tailnet"),
    ({"SOVEREIGN_LISTEN": None}, "SOVEREIGN_LISTEN"),
    ({"SOVEREIGN_LISTEN": "127.0.0.1:3010"}, "SOVEREIGN_LISTEN"),
    ({"SOVEREIGN_HOMEBASE_UID": None}, "SOVEREIGN_HOMEBASE_UID"),
    ({"SOVEREIGN_HOMEBASE_UID": "0"}, "SOVEREIGN_HOMEBASE_UID"),
    ({"SOVEREIGN_HOMEBASE_UID": "-5"}, "SOVEREIGN_HOMEBASE_UID"),
    ({"SOVEREIGN_HOMEBASE_UID": "4294967295"}, "SOVEREIGN_HOMEBASE_UID"),
    ({"SOVEREIGN_HOMEBASE_UID": "１２"}, "SOVEREIGN_HOMEBASE_UID"),
    ({"APP_PUBLIC_URL": None}, "APP_PUBLIC_URL"),
    ({"APP_PUBLIC_URL": f"http://smith-bitcoin-accounting.example-tailnet.ts.net{BASE}/"}, "APP_PUBLIC_URL"),
    ({"APP_PUBLIC_URL": f"https://u:p@smith-bitcoin-accounting.example-tailnet.ts.net{BASE}/"}, "APP_PUBLIC_URL"),
    ({"APP_PUBLIC_URL": f"{ORIGIN}:8443{BASE}/"}, "default https port"),
    ({"APP_PUBLIC_URL": f"{ORIGIN}//elsewhere/"}, "plain path"),
    ({"APP_PUBLIC_URL": f"{ORIGIN}{BASE}/?next=x"}, "plain path"),
    ({"APP_PUBLIC_URL": f"{ORIGIN}{BASE}/#x"}, "plain path"),
    ({"APP_PUBLIC_URL": f"{ORIGIN}/bitcoin accounting/"}, "plain path"),
    ({"APP_PUBLIC_URL": f"{ORIGIN}{BASE}/../x/"}, "plain path"),
])
def test_a_bad_tailnet_configuration_refuses_to_start(change, message):
    env = {key: value for key, value in {**TAILNET_ENV, **change}.items() if value is not None}
    with pytest.raises(ValueError, match=message):
        # The real snapshot reader, so the uid check runs: it reads nothing until the first request.
        create_suite_identity(env)


@pytest.mark.parametrize("base_path", ["", "/accounting"])
def test_the_public_address_must_name_the_apps_own_mount(base_path):
    with pytest.raises(ValueError, match="must be the app's mount"):
        tailnet_client(config=WebConfig(web_base_path=base_path))


def test_the_address_and_uid_parse_as_home_base_writes_them():
    assert public_address(f"{ORIGIN}{BASE}/") == (ORIGIN, f"{BASE}/")
    assert public_address(f"https://Smith-Bitcoin-Accounting.example-tailnet.ts.net:443{BASE}") == (ORIGIN, f"{BASE}/")
    assert home_base_uid(" 991\n") == 991


# --- the gate --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/health", "/api/ready"])
def test_home_base_probes_health_with_no_identity_and_no_fetch_metadata(path):
    response = tailnet_client(Reader(ok=False)).get(f"{BASE}{path}")
    assert response.status_code in (200, 503) and "code" not in response.json()


def test_a_parent_with_access_opens_the_app_and_every_answer_varies_on_fetch_metadata():
    response = tailnet_client().get(f"{BASE}/", headers={**NAVIGATE, **PARENT})
    assert response.status_code == 200 and "Bitcoin" in response.text
    assert all(name in response.headers["vary"] for name in ("Sec-Fetch-Site", "Sec-Fetch-Mode", "Sec-Fetch-Dest"))


def test_page_assets_need_no_member_but_still_pass_the_guard():
    client = tailnet_client()
    script = {"sec-fetch-site": "same-origin", "sec-fetch-mode": "no-cors", "sec-fetch-dest": "script"}
    for path in ["/static/app.js", "/static/vendor/chart.umd.min.js", "/static/brand/favicon.ico", "/sovereign-fonts.css"]:
        assert client.get(f"{BASE}{path}", headers=script).status_code == 200, path
    assert client.get(f"{BASE}/static/app.js").status_code == 403, "no fetch metadata"
    for path in ["/static/app.js.map", "/static/app.jsx", "/static/other/app.js", "/static/vendor/x/a.js", "/app.js",
                 "/static/vendor/LICENSE-chart.js.md"]:
        assert client.get(f"{BASE}{path}", headers=script).status_code == 403, f"{path} is not an asset"
    assert client.post(f"{BASE}/static/app.js", headers=WRITE).status_code == 403, "assets are reads only"


@pytest.mark.parametrize("headers, status, code", [
    ({}, 403, "not_member"),
    (NO_ACCESS, 403, "not_member"),
    (DISABLED, 403, "not_member"),
    ({"x-sovereign-user-id": "1001", "x-sovereign-login": "1003@example.com"}, 403, "not_member"),
    (KID, 403, "parents_only"),
])
def test_only_a_parent_with_access_gets_in(headers, status, code):
    client = tailnet_client()
    api = client.get(f"{BASE}/api/auth/me", headers={**SAME_ORIGIN, **headers})
    assert (api.status_code, api.json()["code"]) == (status, code)
    assert api.headers["cache-control"] == "no-store"
    page = client.get(f"{BASE}/tax", headers={**NAVIGATE, **headers})
    assert page.status_code == status and page.headers["content-type"].startswith("text/html")
    assert page.headers["cache-control"] == "no-store"


def test_a_kid_is_told_why_by_name_and_the_name_is_escaped():
    page = tailnet_client().get(f"{BASE}/", headers={**NAVIGATE, **KID})
    assert "Bitcoin Accounting is for parents, Kit &lt;b&gt;" in page.text and "<b>" not in page.text


def test_without_the_directory_the_app_says_so_rather_than_refusing_the_person():
    client = tailnet_client(Reader(ok=False))
    api = client.get(f"{BASE}/api/auth/me", headers={**SAME_ORIGIN, **PARENT})
    assert (api.status_code, api.json()["code"]) == (503, "directory")
    assert "check who you are right now" in client.get(f"{BASE}/", headers={**NAVIGATE, **PARENT}).text


def test_an_identity_header_sent_twice_is_no_identity():
    headers = [(b"x-sovereign-user-id", b"1001"), (b"x-sovereign-user-id", b"1001"), (b"x-sovereign-login", b"1001@example.com")]
    response = tailnet_client().get(f"{BASE}/api/auth/me", headers=[*SAME_ORIGIN.items(), *headers])
    assert response.json()["code"] == "not_member"


@pytest.mark.parametrize("path", ["/api/auth/me", "/API/auth/me", "/Api/reports/report.pdf", "/api"])
def test_the_api_answers_no_navigation_in_any_spelling(path):
    response = tailnet_client().get(f"{BASE}{path}", headers={**NAVIGATE, **PARENT})
    assert (response.status_code, response.json()["code"]) == (403, "not_a_page")


@pytest.mark.parametrize("path", [f"{BASE}{BASE}/api/auth/me", "/api/auth/me"])
def test_the_gate_judges_the_path_the_router_uses(path):
    client = tailnet_client()
    assert client.get(path, headers={**SAME_ORIGIN, **KID}).status_code in (403, 404)
    assert client.get(path, headers={**SAME_ORIGIN, **KID}).status_code != 200


# --- the guard -------------------------------------------------------------------------------------------

def test_a_parent_writes_json_from_the_apps_own_origin():
    # A route that doesn't exist: 404 means both the guard and the gate let it through, with no side effects.
    assert tailnet_client().post(f"{BASE}/api/nothing-here", headers={**WRITE, **PARENT}).status_code == 404


@pytest.mark.parametrize("change, reason", [
    ({"origin": None}, "origin_missing"),
    ({"origin": "https://smith-pulse.example-tailnet.ts.net", "sec-fetch-site": "same-site"}, "not_same_origin"),
    ({"origin": "https://smith-pulse.example-tailnet.ts.net", "sec-fetch-site": "same-origin"}, "origin_mismatch"),
    ({"content-type": "text/plain"}, "content_type"),
    ({"content-type": None}, "content_type"),
    ({"content-type": "application/x-www-form-urlencoded", "sec-fetch-site": "same-site"}, "not_same_origin"),
    ({"content-type": "multipart/form-data; boundary=x"}, "content_type"),
    ({"sec-fetch-site": None}, "fetch_metadata_missing"),
])
def test_the_guard_refuses_other_writes_before_the_gate_looks_at_who(change, reason):
    headers = {key: value for key, value in {**WRITE, **PARENT, **change}.items() if value is not None}
    response = tailnet_client().post(f"{BASE}/api/ledger/transactions", headers=headers)
    assert response.status_code == 403
    assert response.json()["reason"] == reason


def test_the_import_upload_takes_a_form_but_still_needs_the_apps_origin():
    client = tailnet_client()
    upload = {**SAME_ORIGIN, **PARENT, "origin": ORIGIN}
    files = {"file": ("coinbase.csv", b"not,a,real,export\n", "text/csv")}
    taken = client.post(f"{BASE}/api/import/parse", headers=upload, files=files, data={"source": "coinbase"})
    assert taken.status_code != 403, taken.text
    elsewhere = client.post(f"{BASE}/api/import/parse", headers={**upload, "origin": "https://evil.example"}, files=files)
    assert (elsewhere.status_code, elsewhere.json()["reason"]) == (403, "origin_mismatch")
    kid = client.post(f"{BASE}/api/import/parse", headers={**upload, **KID}, files=files)
    assert kid.json()["code"] == "parents_only"
    # Only that route: a form anywhere else is refused.
    other = client.post(f"{BASE}/api/import/commit", headers=upload, files=files)
    assert (other.status_code, other.json()["reason"]) == (403, "content_type")


def test_a_sibling_hostname_cannot_fetch_a_page_or_the_api():
    sibling = {"sec-fetch-site": "same-site", "sec-fetch-mode": "cors", "sec-fetch-dest": "empty", **PARENT}
    client = tailnet_client()
    assert client.get(f"{BASE}/api/auth/me", headers=sibling).json()["reason"] == "not_same_origin"
    framed = {**NAVIGATE, "sec-fetch-dest": "iframe", "sec-fetch-site": "same-site", **PARENT}
    assert client.get(f"{BASE}/", headers=framed).status_code == 403


# --- the directory replaces the passphrase -----------------------------------------------------------------

def test_a_parent_is_signed_in_by_the_directory_without_the_passphrase():
    client = tailnet_client()
    me = client.get(f"{BASE}/api/auth/me", headers={**SAME_ORIGIN, **PARENT})
    assert me.status_code == 200 and me.json() == {"authenticated": True, "username": "Pat", "tailnet": True}
    assert "ba_session" not in me.cookies


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/logout"])
def test_signing_in_and_out_is_refused_and_issues_no_session(path):
    response = tailnet_client().post(f"{BASE}{path}", headers={**WRITE, **PARENT}, json={"passphrase": "orange-hodl"})
    assert (response.status_code, response.json()["code"]) == (409, "tailnet_identity")
    assert "set-cookie" not in response.headers


def test_an_old_session_cookie_means_nothing_in_tailnet_mode():
    local = local_client()
    local.post(f"{BASE}/api/auth/login", json={"passphrase": "orange-hodl"})
    cookie = local.cookies.get("ba_session")
    assert cookie
    refused = tailnet_client().get(f"{BASE}/api/auth/me", headers={**SAME_ORIGIN, **NO_ACCESS, "cookie": f"ba_session={cookie}"})
    assert refused.json()["code"] == "not_member"


def test_local_mode_keeps_its_sign_in():
    client = local_client()
    assert client.get(f"{BASE}/api/auth/me").status_code == 401
    signed_in = client.post(f"{BASE}/api/auth/login", json={"passphrase": "orange-hodl"})
    assert signed_in.json() == {"authenticated": True, "username": "operator"}
    assert client.get(f"{BASE}/api/auth/me").json() == {"authenticated": True, "username": "operator"}
    assert client.post(f"{BASE}/api/auth/logout").json() == {"authenticated": False, "username": "operator"}


# --- the page --------------------------------------------------------------------------------------------

APP_JS = (Path(__file__).resolve().parent.parent / "src/python/web/ui/static/app.js").read_text("utf-8")


def _function(name: str) -> str:
    return re.search(rf"\n(async )?function {name}\(.*?\n\}}\n", APP_JS, re.S).group(0)


def _node(script: str) -> dict:
    return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)


def test_every_write_the_page_sends_is_json():
    out = _node(f"""
const sent = [];
const window = {{ location: {{ origin: 'https://h.example' }} }};
const state = {{}};
const appBase = () => '/bitcoin-accounting/';
const fetch = async (url, init) => {{ sent.push([init.method || 'GET', init.headers['Content-Type'] || null]); return {{ ok: true, headers: {{ get: () => 'application/json' }}, json: async () => ({{}}) }}; }};
{_function('api')}
(async () => {{
  await api('api/auth/logout', {{ method: 'POST' }});
  await api('api/wallets/1', {{ method: 'delete' }});
  await api('api/ledger', {{ method: 'POST', body: '{{}}' }});
  await api('api/auth/me');
  console.log(JSON.stringify(sent));
}})();
""")
    assert out == [["POST", "application/json"], ["delete", "application/json"], ["POST", "application/json"], ["GET", None]]


def test_every_download_goes_through_api_and_no_link_points_into_it():
    for name in ("downloadReportPdf", "downloadTaxArtifact", "saveDownload"):
        assert "fetch(" not in _function(name), name
    # api() and apiUpload() send everything, through the passkey retry when the page has it (static/passkey.js).
    assert len(re.findall(r"(?<![\w.])fetch\(", APP_JS)) == 0
    assert APP_JS.count("const send = window.BtcPasskey ? window.BtcPasskey.fetch : fetch;") == 2
    assert "byId('reports-pdf-link').addEventListener('click', downloadReportPdf)" in APP_JS


@pytest.mark.parametrize("tailnet, hidden", [(True, True), (None, False)])
def test_tailnet_mode_offers_no_sign_out(tailnet, hidden):
    out = _node(f"""
const nodes = {{}};
const el = (tag) => ({{ tagName: tag, classes: new Set(), classList: {{ toggle(c, on) {{ on ? this.owner.classes.add(c) : this.owner.classes.delete(c); }}, add() {{}} }} }});
for (const [id, tag] of [['session-action', 'BUTTON'], ['mobile-session-action', 'BUTTON'], ['divider', 'HR']]) {{ nodes[id] = el(tag); nodes[id].classList.owner = nodes[id]; }}
nodes['mobile-session-action'].previousElementSibling = nodes.divider;
const byId = (id) => nodes[id] || {{ classList: {{ add() {{}} }} }};
const state = {{ session: {{ username: 'Pat', tailnet: {json.dumps(tailnet)} }} }};
const setSessionGlyph = () => {{}};
const renderPageState = () => {{}};
{_function('showLoggedIn')}
{_function('showSessionControls')}
showLoggedIn('Pat');
console.log(JSON.stringify(Object.fromEntries(Object.entries(nodes).map(([k, v]) => [k, v.classes.has('hidden')]))));
""")
    assert out == {"session-action": hidden, "mobile-session-action": hidden, "divider": hidden}
