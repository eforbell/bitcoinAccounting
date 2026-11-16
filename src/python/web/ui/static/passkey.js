'use strict';

// Passkey checks in tailnet mode (wire contract, section 8). Home Base serves its step-up helper on this app's hostname
// at /_sovereign/auth/stepup.js: it asks for a tap, runs the passkey check with Home Base, and sets the cookie the app
// reads. In local mode nothing asks for a check, so the helper loads only when an answer asks for one.
(function btcPasskey() {
  const HELPER = '/_sovereign/auth/stepup.js';
  const UNAVAILABLE = 'Bitcoin Accounting couldn\'t reach Home Base for a passkey check. Try again in a minute.';
  const CANCELLED = 'This needs a check with your passkey first.';
  const NOT_ACCEPTED = 'Your passkey check didn\'t go through. Try again.';
  const STILL_REFUSED = 'Your passkey check went through, but Bitcoin Accounting couldn\'t confirm it yet. Try again in a minute.';
  const MESSAGES = {
    'open-operator': 'Check with your passkey to keep using Bitcoin Accounting.',
    'export-data': 'Check with your passkey to download this.',
  };
  const RELOADED = 'btc-passkey-reloaded';
  let helper = null;

  // The reload after a check that went through: which page, for which policy, and when. Every page that loads this
  // script takes it (every page here is the same shell), so it only ever describes the reload that brought this page up.
  let reloaded = null;
  try { reloaded = JSON.parse(sessionStorage.getItem(RELOADED)); sessionStorage.removeItem(RELOADED); } catch { reloaded = null; }

  function loadHelper() {
    if (window.SovereignStepUp) return Promise.resolve(window.SovereignStepUp);
    if (!helper) {
      helper = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = HELPER;
        const failed = () => { helper = null; script.remove(); reject(new Error(UNAVAILABLE)); };
        script.onload = () => (window.SovereignStepUp ? resolve(window.SovereignStepUp) : failed());
        script.onerror = failed;
        document.head.append(script);
      });
    }
    return helper;
  }

  // One check at a time: requests sent together (a page load asks for several things at once) share it, since one check
  // sets the cookie each of them reads. A request whose answer comes back after a check has ended takes the outcome of
  // the first check that ended after it was sent: the one its batch shared. So a late answer neither asks again after a
  // cancel nor saves part of what the member cancelled. A request notes how many checks had ended when it was sent; the
  // next one to end is the one it waits on.
  let checking = null;
  const ended = [];   // the outcome of every check that ended, in order: null (through), false (cancelled), or an error
  const settle = (outcome) => { ended.push(outcome); };
  function satisfyOnce(stepUp, endedBeforeSend) {
    if (ended.length > endedBeforeSend) {
      const outcome = ended[endedBeforeSend];
      return outcome instanceof Error ? Promise.reject(outcome) : Promise.resolve(outcome);
    }
    if (!checking) {
      const ask = { ...stepUp, message: MESSAGES[stepUp.policy] || stepUp.message };
      checking = loadHelper().then((h) => h.satisfy(ask)).then(
        (done) => { settle(done === false ? false : null); return done; },
        (err) => { settle(err); throw err; },
      ).finally(() => { checking = null; });
    }
    return checking;
  }

  async function stepUpAsked(res) {
    if (res.status !== 401) return null;
    const body = await res.clone().json().catch(() => null);
    // Only the library's whole answer: which policy, at what level, with what kind of credential.
    const whole = body && body.error === 'step_up_required'
      && ['policy', 'level', 'kind'].every((key) => typeof body[key] === 'string' && body[key]);
    return whole ? body : null;
  }

  // fetch, and when the answer asks for a passkey check: the check, then the same request once more. The body must be
  // a string, a FormData (an import upload) or absent, all of which can be sent twice, so the retry sends exactly what
  // was asked.
  async function passkeyFetch(url, init = {}) {
    const endedBeforeSend = ended.length;
    const first = await fetch(url, init);
    const stepUp = await stepUpAsked(first);
    if (!stepUp) return first;
    if ((await satisfyOnce(stepUp, endedBeforeSend)) === false) throw new Error(CANCELLED);
    const retry = await fetch(url, init);
    if (await stepUpAsked(retry)) throw new Error(NOT_ACCEPTED);
    return retry;
  }

  // The page the app answers with when a parent opens it without a current check: run the check, then reload. If this
  // page comes back straight after a check for it went through (Home Base's new key or a changed access hasn't reached
  // the app yet), it waits for a tap rather than looping through checks. A different page, or a different check, runs
  // its own.
  function checkOnOpen(main) {
    const status = document.getElementById('passkey-status');
    const retry = document.getElementById('passkey-retry');
    let stepUp;
    try { stepUp = JSON.parse(main.dataset.stepUp); } catch { stepUp = null; }
    async function run() {
      retry.hidden = true;
      status.textContent = '';
      try {
        if (!stepUp) throw new Error(NOT_ACCEPTED);
        if ((await (await loadHelper()).satisfy(stepUp)) !== false) {
          const mark = { at: Date.now(), page: window.location.href, policy: stepUp.policy };
          try { sessionStorage.setItem(RELOADED, JSON.stringify(mark)); } catch { /* private mode: no loop guard to keep */ }
          window.location.reload();
          return;
        }
        status.textContent = CANCELLED;
      } catch (err) {
        status.textContent = err.message || NOT_ACCEPTED;
      }
      retry.hidden = false;
    }
    retry.addEventListener('click', run);
    const sameCheck = reloaded && stepUp && reloaded.page === window.location.href && reloaded.policy === stepUp.policy;
    if (sameCheck && Date.now() - Number(reloaded.at) < 60 * 1000) {
      status.textContent = STILL_REFUSED;
      retry.hidden = false;
      return;
    }
    run();
  }

  window.BtcPasskey = { fetch: passkeyFetch };
  const main = document.getElementById('passkey-check');
  if (main) checkOnOpen(main);
})();
