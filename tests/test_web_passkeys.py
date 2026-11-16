"""Suite identity: passkeys. A parent opens Bitcoin Accounting with a passkey check that lasts a day on that device
(open-operator), and downloading an export (the 1099-B files, the PDF report) needs one in the last five minutes
(export-data). Kids never meet one: the gate refuses them first. static/passkey.js runs the checks in the page."""
from __future__ import annotations

import html
import json
import re
import subprocess
import time
from pathlib import Path

import pytest
from test_web_suite_identity import (
    BASE, HOST, KID, NAVIGATE, PARENT, SAME_ORIGIN, WRITE, passkey_cookie, tailnet_client, who,
)

from web.suite_identity import passkey_page

NO_PASSKEY = who("1001")
FRESH = {**who("1001"), "cookie": passkey_cookie(checked_ago=30)}
EXPORTS = ["/api/tax/1099b/export?year=2025", "/api/tax/1099b/worksheet?year=2025", "/api/reports/report.pdf?range=all"]


def step_up_of(page):
    found = re.search(r'<main id="passkey-check" data-step-up="([^"]*)">', page.text)
    return json.loads(html.unescape(found.group(1)))


def test_opening_the_app_without_a_check_answers_the_passkey_page():
    page = tailnet_client().get(f"{BASE}/tax", headers={**NAVIGATE, **NO_PASSKEY})
    assert page.status_code == 401 and page.headers["content-type"].startswith("text/html")
    assert page.headers["cache-control"] == "no-store"
    assert step_up_of(page) == {
        "error": "step_up_required", "policy": "open-operator", "level": "session", "kind": "any",
        "message": "Check with your passkey to open Bitcoin Accounting.",
    }
    assert f'<script src="{BASE}/static/passkey.js"></script>' in page.text
    assert "Check with your passkey, Pat" in page.text


def test_the_api_answers_the_librarys_step_up_json():
    response = tailnet_client().get(f"{BASE}/api/auth/me", headers={**SAME_ORIGIN, **NO_PASSKEY})
    assert response.status_code == 401 and response.headers["cache-control"] == "no-store"
    assert response.json() == {"error": "step_up_required", "policy": "open-operator", "level": "session", "kind": "any"}
    write = tailnet_client().post(f"{BASE}/api/nothing-here", headers={**WRITE, **NO_PASSKEY})
    assert write.status_code == 401 and write.json()["policy"] == "open-operator"


def test_a_check_opens_the_app_for_a_day():
    client = tailnet_client()
    assert client.get(f"{BASE}/", headers={**NAVIGATE, **PARENT}).status_code == 200
    assert client.get(f"{BASE}/api/auth/me", headers={**SAME_ORIGIN, **PARENT}).status_code == 200
    stale = {**who("1001"), "cookie": passkey_cookie(checked_ago=86400 + 60)}
    assert client.get(f"{BASE}/api/auth/me", headers={**SAME_ORIGIN, **stale}).status_code == 401


@pytest.mark.parametrize("cookie", [
    passkey_cookie(aud="smith-pulse.example-tailnet.ts.net"),
    passkey_cookie(sub="1003"),
    passkey_cookie(epoch=0),
    f"{passkey_cookie()}; {passkey_cookie()}",
    passkey_cookie().replace("__Host-", ""),
])
def test_only_this_members_cookie_for_this_hostname_counts(cookie):
    response = tailnet_client().get(f"{BASE}/api/auth/me", headers={**SAME_ORIGIN, **who("1001"), "cookie": cookie})
    assert response.status_code == 401


def test_kids_never_meet_a_passkey_check():
    page = tailnet_client().get(f"{BASE}/", headers={**NAVIGATE, **KID, "cookie": PARENT["cookie"]})
    assert page.status_code == 403 and "passkey" not in page.text.lower()


@pytest.mark.parametrize("path", EXPORTS + ["/API/Tax/1099B/Export", "/api/reports/report.pdf/"])
def test_an_export_needs_a_fresh_check(path):
    response = tailnet_client().get(f"{BASE}{path}", headers={**SAME_ORIGIN, **PARENT})
    assert (response.status_code, response.json()["policy"], response.json()["level"]) == (401, "export-data", "recent")


@pytest.mark.parametrize("path", EXPORTS)
def test_a_fresh_check_reaches_the_export(path):
    response = tailnet_client().get(f"{BASE}{path}", headers={**SAME_ORIGIN, **FRESH})
    assert response.status_code != 401, response.text


def test_the_fresh_check_still_needs_the_open_check():
    response = tailnet_client().get(f"{BASE}{EXPORTS[0]}", headers={**SAME_ORIGIN, **NO_PASSKEY})
    assert response.json()["policy"] == "open-operator"


@pytest.mark.parametrize("path", ["/api/tax/1099b/preview?year=2025", "/api/reports/series?range=all", "/api/tax/gains"])
def test_reading_what_the_page_shows_needs_only_the_open_check(path):
    assert tailnet_client().get(f"{BASE}{path}", headers={**SAME_ORIGIN, **PARENT}).status_code != 401


def test_the_passkey_page_script_is_a_page_asset():
    script = {"sec-fetch-site": "same-origin", "sec-fetch-mode": "no-cors", "sec-fetch-dest": "script"}
    response = tailnet_client().get(f"{BASE}/static/passkey.js", headers=script)
    assert response.status_code == 200 and "BtcPasskey" in response.text


def test_the_passkey_page_escapes_the_name_and_the_step_up():
    step_up = {"error": "step_up_required", "policy": "open-operator", "level": "session", "kind": "any",
               "reason": '"><script>x</script>'}
    page = passkey_page(step_up, "Kit <b>", f"{BASE}/")
    assert "Check with your passkey, Kit &lt;b&gt;" in page and "<b>" not in page and "<script>x" not in page


# --- static/passkey.js ------------------------------------------------------------------------------------

UI = Path(__file__).resolve().parent.parent / "src/python/web/ui"
PASSKEY_JS = (UI / "static/passkey.js").read_text("utf-8")
STEP_UP = {"error": "step_up_required", "policy": "open-operator", "level": "session", "kind": "any"}
PAGE = f"https://{HOST}{BASE}/"


def _run_passkey(script: str) -> dict:
    """Runs passkey.js under Node with a scripted fetch and Home Base's helper stubbed, then the given script."""
    harness = f"""
const window = {{ location: {{ reload() {{}} }} }};
const document = {{ getElementById: () => null }};
const sent = [];
const checks = [];
let answers = [];
async function fetch(url, init) {{
  sent.push({{ url, body: init.body instanceof FormData ? 'form:' + init.body.get('source') : init.body ?? null }});
  const [status, body] = answers.shift();
  return new Response(JSON.stringify(body), {{ status }});
}}
let outcome = null;
window.SovereignStepUp = {{ satisfy: async (stepUp) => {{ checks.push(stepUp); await new Promise((r) => setTimeout(r, 5)); return outcome; }} }};
{PASSKEY_JS}
(async () => {{
  const result = {{}};
{script}
  console.log(JSON.stringify({{ ...result, sent, checks }}));
}})();
"""
    done = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_a_step_up_answer_runs_one_check_and_sends_the_same_request_again():
    out = _run_passkey(f"""
  answers = [[401, {json.dumps(STEP_UP)}], [200, {{ ok: true }}]];
  const res = await window.BtcPasskey.fetch("{BASE}/api/ledger", {{ method: "POST", body: '{{"a":1}}' }});
  result.status = res.status;
""")
    assert out["status"] == 200
    assert out["sent"] == [{"url": f"{BASE}/api/ledger", "body": '{"a":1}'}] * 2
    assert [check["message"] for check in out["checks"]] == ["Check with your passkey to keep using Bitcoin Accounting."]


def test_an_upload_is_sent_again_whole_after_the_check():
    out = _run_passkey(f"""
  answers = [[401, {json.dumps(STEP_UP)}], [200, {{}}]];
  const form = new FormData();
  form.append("source", "coinbase");
  result.status = (await window.BtcPasskey.fetch("api/import/parse", {{ method: "POST", body: form }})).status;
""")
    assert out["status"] == 200 and [entry["body"] for entry in out["sent"]] == ["form:coinbase"] * 2


def test_an_export_asks_for_its_own_check_in_words_that_say_why():
    out = _run_passkey(f"""
  answers = [[401, {{ ...{json.dumps(STEP_UP)}, policy: "export-data", level: "recent" }}], [200, {{}}]];
  result.status = (await window.BtcPasskey.fetch("api/reports/report.pdf", {{}})).status;
""")
    assert out["status"] == 200 and out["checks"][0]["message"] == "Check with your passkey to download this."


def test_requests_sent_together_share_one_check():
    out = _run_passkey(f"""
  answers = [[401, {json.dumps(STEP_UP)}], [401, {json.dumps(STEP_UP)}], [401, {json.dumps(STEP_UP)}], [200, {{}}], [200, {{}}], [200, {{}}]];
  const all = await Promise.all(["a", "b", "c"].map((p) => window.BtcPasskey.fetch(p, {{}})));
  result.statuses = all.map((res) => res.status);
""")
    assert out["statuses"] == [200, 200, 200] and len(out["checks"]) == 1


def test_a_cancelled_check_sends_nothing_more_and_says_why():
    out = _run_passkey(f"""
  outcome = false;
  answers = [[401, {json.dumps(STEP_UP)}]];
  try {{ await window.BtcPasskey.fetch("api/x", {{ method: "POST", body: "{{}}" }}); }} catch (err) {{ result.error = err.message; }}
""")
    assert out["error"] == "This needs a check with your passkey first." and len(out["sent"]) == 1


def test_other_answers_pass_straight_through():
    out = _run_passkey("""
  answers = [[401, { detail: "Authentication required" }], [403, { code: "parents_only" }],
             [401, { error: "step_up_required" }], [401, { error: "step_up_required", policy: "open-operator", level: "session" }]];
  result.statuses = [];
  for (const path of ["a", "b", "c", "d"]) result.statuses.push((await window.BtcPasskey.fetch(path, {})).status);
""")
    assert out["statuses"] == [401, 403, 401, 401] and out["checks"] == [] and len(out["sent"]) == 4


def test_the_page_loads_passkey_js_before_app_js():
    index = (UI / "index.html").read_text("utf-8")
    assert index.index('<script src="static/passkey.js">') < index.index('<script src="static/app.js">')


def _open_passkey_page(marker, *, href=PAGE, passkey_page=True) -> dict:
    """Loads passkey.js under Node as a page would, with sessionStorage holding `marker` (the reload after a check)."""
    harness = f"""
const store = new Map({json.dumps([["btc-passkey-reloaded", json.dumps(marker)]] if marker else [])});
const sessionStorage = {{ getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) }};
const out = {{ checks: 0, reloads: 0 }};
const window = {{ location: {{ href: {json.dumps(href)}, reload() {{ out.reloads += 1; }} }} }};
window.SovereignStepUp = {{ satisfy: async () => {{ out.checks += 1; return null; }} }};
const status = {{ textContent: "" }};
const retry = {{ hidden: true, addEventListener() {{}} }};
const main = {{ dataset: {{ stepUp: {json.dumps(json.dumps(STEP_UP))} }} }};
const document = {{ getElementById: (id) => ({{ "passkey-check": {"main" if passkey_page else "null"}, "passkey-status": status, "passkey-retry": retry }})[id] ?? null }};
{PASSKEY_JS}
setTimeout(() => {{
  out.status = status.textContent;
  out.left = store.get("btc-passkey-reloaded") ?? null;
  console.log(JSON.stringify(out));
}}, 20);
"""
    done = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def _marker(seconds_ago=1, **change):
    return {"at": int(time.time() * 1000) - seconds_ago * 1000, "page": PAGE, "policy": "open-operator", **change}


def test_the_passkey_page_runs_its_check_and_reloads():
    out = _open_passkey_page(None)
    assert (out["checks"], out["reloads"]) == (1, 1) and json.loads(out["left"])["policy"] == "open-operator"


def test_the_same_page_back_straight_after_its_check_waits_for_a_tap():
    out = _open_passkey_page(_marker())
    assert (out["checks"], out["reloads"]) == (0, 0) and "went through" in out["status"]


@pytest.mark.parametrize("marker, href", [
    (_marker(), f"{PAGE}tax"),
    (_marker(seconds_ago=61), PAGE),
])
def test_any_other_check_runs_as_usual(marker, href):
    assert _open_passkey_page(marker, href=href)["checks"] == 1


def test_a_page_that_loaded_takes_the_reload_marker():
    out = _open_passkey_page(_marker(), passkey_page=False)
    assert out["left"] is None and out["checks"] == 0
