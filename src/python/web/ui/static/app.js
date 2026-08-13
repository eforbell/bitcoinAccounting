var REDACTED = '•••••';
function denomFormat(btcAmount) {
  if (window.BtcPrivacy && BtcPrivacy.isEnabled()) return REDACTED;
  return window.BtcDenom ? BtcDenom.format(btcAmount) : Number(btcAmount).toFixed(8) + ' BTC';
}
function denomUnit() {
  return window.BtcDenom ? BtcDenom.unit() : 'BTC';
}
var FIAT_CURRENCIES = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY', 'CHF', 'USDC', 'USDT', 'GUSD', 'BUSD', 'DAI', 'PYUSD'];
function formatAmount(amount, curr) {
  if (window.BtcPrivacy && BtcPrivacy.isEnabled()) return REDACTED;
  var n = Number(amount);
  if (isNaN(n)) return '';
  var c = (curr || '').toUpperCase();
  var decimals = FIAT_CURRENCIES.indexOf(c) !== -1 ? 2 : 8;
  return n.toFixed(decimals) + ' ' + c;
}

const state = {
  session: null,
  policy: null,
  dashboard: null,
  chainStatus: null,
  chainStatusRefreshHandle: null,
  walletDetail: null,
  walletVerificationHistory: null,
  walletsList: [],
  currentPage: 'dashboard',
  currentWalletId: null,
  gainsFilters: { taxYear: 2024, coin: 'BTC', wallet: '' },
  forecastFilters: { coin: 'BTC', wallet: '', quantity: 0.1, salePriceUsd: 100000 },
  ledgerFilters: { coin: 'BTC', wallet: '', startDate: '', endDate: '', includeDeleted: false, page: 1, perPage: 50 },
  selectedTx: null,
  importState: { parsers: [], preview: null, duplicateIndices: [], step: 1, wallets: [] },
  tradesFilters: { exchange: '', page: 1, perPage: 50, view: 'trades' },
  reportsState: { range: 'all', wired: false },
};

function byId(id) {
  return document.getElementById(id);
}

function currency(value) {
  if (window.BtcPrivacy && BtcPrivacy.isEnabled()) return REDACTED;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderDataCards(containerId, cards, emptyMessage) {
  const container = byId(containerId);
  container.innerHTML = cards.length
    ? cards.join('')
    : `<div class="data-card data-card-empty">${escapeHtml(emptyMessage)}</div>`;
}

function dataCard(title, detail, values, actions = '') {
  return `<article class="data-card">
    <div class="data-card-heading">
      <div>
        <strong>${escapeHtml(title)}</strong>
        ${detail ? `<div class="data-card-detail">${escapeHtml(detail)}</div>` : ''}
      </div>
    </div>
    <div class="data-card-values">${values.map(([label, value]) => `
      <div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
    `).join('')}</div>
    ${actions ? `<div class="data-card-actions">${actions}</div>` : ''}
  </article>`;
}

function appBase() {
  const base = document.querySelector('base');
  if (base) return new URL(base.getAttribute('href'), window.location.origin).pathname;
  const path = window.location.pathname;
  const taxIdx = path.indexOf('/tax');
  if (taxIdx !== -1) return path.slice(0, taxIdx + 1);
  const ledgerIdx = path.indexOf('/ledger');
  if (ledgerIdx !== -1) return path.slice(0, ledgerIdx + 1);
  const recordIdx = path.indexOf('/record');
  if (recordIdx !== -1) return path.slice(0, recordIdx + 1);
  const walletsIdx = path.indexOf('/wallets');
  if (walletsIdx !== -1) return path.slice(0, walletsIdx + 1);
  const importIdx = path.indexOf('/import');
  if (importIdx !== -1) return path.slice(0, importIdx + 1);
  const walletIdx = path.indexOf('/wallet/');
  if (walletIdx !== -1) return path.slice(0, walletIdx + 1);
  return path.endsWith('/') ? path : path + '/';
}

function appPath(page) {
  const base = appBase();
  if (page === 'tax') return `${base}tax`;
  if (page === 'ledger') return `${base}ledger`;
  if (page === 'trades') return `${base}trades`;
  if (page === 'reports') return `${base}reports`;
  if (page === 'record') return `${base}record`;
  if (page === 'wallets') return `${base}wallets`;
  if (page === 'import') return `${base}import`;
  if (page === 'settings') return `${base}settings`;
  if (page === 'wallet' && state.currentWalletId) return `${base}wallet/${encodeURIComponent(state.currentWalletId)}`;
  return base;
}

function currentRouteFromLocation() {
  const path = window.location.pathname.replace(/\/+$/, '');
  if (path.endsWith('/tax')) return 'tax';
  if (path.endsWith('/reports')) return 'reports';
  if (path.endsWith('/trades')) return 'trades';
  if (path.endsWith('/record')) return 'record';
  if (path.endsWith('/wallets')) return 'wallets';
  if (path.endsWith('/import')) return 'import';
  if (path.endsWith('/settings')) return 'settings';
  if (path.endsWith('/ledger')) {
    const params = new URLSearchParams(window.location.search);
    if (params.get('wallet')) {
      state.ledgerFilters.wallet = params.get('wallet');
    }
    return 'ledger';
  }
  const walletMatch = path.match(/\/wallet\/([^/]+)$/);
  if (walletMatch) {
    state.currentWalletId = decodeURIComponent(walletMatch[1]);
    return 'wallet';
  }
  return 'dashboard';
}

function navigateTo(page, replace = false) {
  state.currentPage = page;
  const target = appPath(page);
  if (window.location.pathname !== target) {
    const method = replace ? 'replaceState' : 'pushState';
    window.history[method]({ page }, '', target);
  }
  renderPageState();
  if (page === 'wallet' && state.currentWalletId) {
    loadWalletDetail(state.currentWalletId);
  }
  if (page === 'ledger') {
    loadLedger();
  }
  if (page === 'trades') {
    loadTradesPage();
  }
  if (page === 'reports') {
    loadReports();
  }
  if (page === 'import') {
    loadImportPage();
  }
  if (page === 'wallets') {
    loadWalletsList();
  }
  if (page === 'tax') {
    loadGains();
    loadForecast();
  }
  if (page === 'record') {
    initRecordDates();
    loadRecordWalletOptions();
  }
  if (page === 'settings') {
    initSettingsPage();
  }
}

function initRecordDates() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000).toISOString().slice(0, 16);
  for (const id of ['buy-date', 'sell-date', 'transfer-date', 'interest-date']) {
    const el = byId(id);
    if (el && !el.value) el.value = local;
  }
}

const recordWalletSelectIds = [
  'buy-wallet',
  'sell-wallet',
  'transfer-from',
  'transfer-to',
  'interest-wallet',
];

function setActiveWalletOptions(select, walletIds, currentValue = select.value) {
  select.replaceChildren();
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = 'Select an active wallet';
  select.appendChild(placeholder);

  for (const walletId of walletIds) {
    const option = document.createElement('option');
    option.value = walletId;
    option.textContent = walletId;
    select.appendChild(option);
  }

  if (currentValue && !walletIds.includes(currentValue)) {
    const inactiveOption = document.createElement('option');
    inactiveOption.value = currentValue;
    inactiveOption.textContent = `${currentValue} (inactive)`;
    inactiveOption.disabled = true;
    select.appendChild(inactiveOption);
  }
  select.value = currentValue;
}

async function loadRecordWalletOptions(editWalletId = null) {
  try {
    const data = await api('api/wallets?active_only=true');
    const walletIds = (data.wallets || []).map((wallet) => wallet.wallet_id);
    for (const selectId of recordWalletSelectIds) {
      setActiveWalletOptions(byId(selectId), walletIds);
    }
    if (editWalletId !== null) {
      setActiveWalletOptions(byId('tx-edit-wallet'), walletIds, editWalletId);
    }
  } catch (_) {
    // The server remains the authority; leave existing choices untouched if loading fails.
  }
}

function initSettingsPage() {
  const themeToggle = byId('settings-theme-toggle');
  if (themeToggle) {
    const pref = window.BtcTheme ? BtcTheme.getPreference() : 'system';
    for (const btn of themeToggle.querySelectorAll('button')) {
      btn.classList.toggle('active', btn.dataset.value === pref);
      btn.onclick = function () {
        for (const b of themeToggle.querySelectorAll('button')) b.classList.remove('active');
        btn.classList.add('active');
        if (window.BtcTheme) BtcTheme.setPreference(btn.dataset.value);
      };
    }
  }
  const denomToggle = byId('settings-denom-toggle');
  if (denomToggle) {
    const pref = window.BtcDenom ? BtcDenom.getPreference() : 'btc';
    for (const btn of denomToggle.querySelectorAll('button')) {
      btn.classList.toggle('active', btn.dataset.value === pref);
      btn.onclick = function () {
        for (const b of denomToggle.querySelectorAll('button')) b.classList.remove('active');
        btn.classList.add('active');
        if (window.BtcDenom) BtcDenom.setPreference(btn.dataset.value);
      };
    }
  }
  const privacyToggle = byId('settings-privacy-toggle');
  if (privacyToggle) {
    const pref = window.BtcPrivacy ? BtcPrivacy.getPreference() : 'off';
    for (const btn of privacyToggle.querySelectorAll('button')) {
      btn.classList.toggle('active', btn.dataset.value === pref);
      btn.onclick = function () {
        for (const b of privacyToggle.querySelectorAll('button')) b.classList.remove('active');
        btn.classList.add('active');
        if (window.BtcPrivacy) BtcPrivacy.setPreference(btn.dataset.value);
      };
    }
  }
}

function navigateToWallet(walletId) {
  state.currentWalletId = walletId;
  navigateTo('wallet');
}

async function api(path, options = {}) {
  const headers = {
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers || {}),
  };

  const url = new URL(path, new URL(appBase(), window.location.origin)).href;

  const response = await fetch(url, {
    credentials: 'same-origin',
    headers,
    ...options,
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const body = await response.json();
      detail = body.detail || body.error || detail;
    } else {
      detail = await response.text() || detail;
    }
    throw new Error(detail);
  }

  if (response.headers.get('content-type')?.includes('application/json')) {
    return response.json();
  }
  return response;
}

function setAuthStatus(message, isError = false) {
  const status = byId('auth-status');
  status.textContent = message;
  status.style.color = isError ? 'var(--bad)' : 'var(--muted)';
}

function setSessionGlyph(authenticated) {
  byId('session-glyph').textContent = authenticated ? '↗' : '⌁';
}

function showLoggedOut() {
  clearChainStatusRefresh();
  byId('login-panel').classList.remove('hidden');
  byId('dashboard-view').classList.add('hidden');
  byId('tax-view').classList.add('hidden');
  byId('wallet-view').classList.add('hidden');
  byId('ledger-view').classList.add('hidden');
  byId('trades-view').classList.add('hidden');
  byId('reports-view').classList.add('hidden');
  byId('record-view').classList.add('hidden');
  byId('wallets-view').classList.add('hidden');
  byId('import-view').classList.add('hidden');
  byId('settings-view').classList.add('hidden');
  if (byId('operator-chip')) byId('operator-chip').textContent = 'operator';
  setSessionGlyph(false);
}

function showLoggedIn(username) {
  byId('login-panel').classList.add('hidden');
  if (byId('operator-chip')) byId('operator-chip').textContent = username;
  setSessionGlyph(true);
  renderPageState();
}

function clearChainStatusRefresh() {
  if (state.chainStatusRefreshHandle) {
    window.clearTimeout(state.chainStatusRefreshHandle);
    state.chainStatusRefreshHandle = null;
  }
}

function scheduleChainStatusRefresh(delayMs) {
  clearChainStatusRefresh();
  if (!state.session || state.currentPage !== 'dashboard') return;
  state.chainStatusRefreshHandle = window.setTimeout(async () => {
    try {
      await loadChainStatus();
    } catch (_) {
      // loadChainStatus already renders degraded state on failures
    }
  }, delayMs);
}

function renderPageState() {
  document.body.classList.add('app-has-nav');
  const page = state.currentPage;
  const titles = { dashboard: 'Dashboard', tax: 'Tax', wallet: 'Wallet', wallets: 'Wallets', ledger: 'Ledger', trades: 'Trades', reports: 'Reports', record: 'Record', import: 'Import', settings: 'Settings' };
  document.title = `Bitcoin Accounting | ${titles[page] || 'Dashboard'}`;
  byId('dashboard-view').classList.toggle('hidden', !state.session || page !== 'dashboard');
  byId('tax-view').classList.toggle('hidden', !state.session || page !== 'tax');
  byId('wallet-view').classList.toggle('hidden', !state.session || page !== 'wallet');
  byId('ledger-view').classList.toggle('hidden', !state.session || page !== 'ledger');
  byId('trades-view').classList.toggle('hidden', !state.session || page !== 'trades');
  byId('reports-view').classList.toggle('hidden', !state.session || page !== 'reports');
  byId('record-view').classList.toggle('hidden', !state.session || page !== 'record');
  byId('wallets-view').classList.toggle('hidden', !state.session || page !== 'wallets');
  byId('import-view').classList.toggle('hidden', !state.session || page !== 'import');
  byId('settings-view').classList.toggle('hidden', !state.session || page !== 'settings');

  const navRoute = (page === 'wallet') ? 'dashboard' : page;
  for (const item of document.querySelectorAll('[data-route]')) {
    item.classList.toggle('active', item.dataset.route === navRoute);
  }
  // Highlight "More" button when a page inside the sheet is active
  const moreBtn = document.getElementById('more-menu-toggle');
  if (moreBtn) {
    moreBtn.classList.toggle('active', ['reports', 'tax', 'wallets', 'import', 'settings'].includes(navRoute));
  }

  if (state.session && page === 'settings') {
    initSettingsPage();
  }

  if (page !== 'dashboard') {
    clearChainStatusRefresh();
  } else if (state.session && state.chainStatus) {
    const delayMs = state.chainStatus.available ? 60000 : 180000;
    scheduleChainStatusRefresh(delayMs);
  }
}

function renderWarnings(containerId, warnings) {
  const container = byId(containerId);
  if (!warnings || warnings.length === 0) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = warnings.map((warning) => `
    <div class="warning-item">
      <strong>${escapeHtml(warning.message)}</strong>
      ${warning.reference_doc ? `<div class="list-item-meta">${escapeHtml(warning.reference_doc)}</div>` : ''}
    </div>
  `).join('');
}

function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return '-';
  const total = Math.max(0, Number(seconds));
  if (total < 60) return `${Math.round(total)}s ago`;
  if (total < 3600) return `${Math.round(total / 60)}m ago`;
  if (total < 86400) return `${Math.round(total / 3600)}h ago`;
  return `${Math.round(total / 86400)}d ago`;
}

function formatBytes(bytes) {
  if (bytes == null || Number.isNaN(Number(bytes))) return '-';
  const value = Number(bytes);
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatRefreshTime(value) {
  if (!value) return '-';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '-';
  return `Updated ${dt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`;
}

function isChainStatusStale(status) {
  if (!status || !status.refreshed_at) return false;
  const refreshed = new Date(status.refreshed_at);
  if (Number.isNaN(refreshed.getTime())) return false;
  return (Date.now() - refreshed.getTime()) > 120000;
}

function renderChainStatus(status) {
  state.chainStatus = status;
  const panel = byId('chain-status-panel');
  const warning = byId('chain-status-warning');

  if (!status || !status.enabled) {
    panel.classList.add('hidden');
    warning.classList.add('hidden');
    return;
  }

  panel.classList.remove('hidden');
  byId('chain-height').textContent = status.block_height == null ? '-' : String(status.block_height);
  byId('chain-last-block').textContent = formatDuration(status.seconds_since_last_block);
  byId('chain-peers').textContent = status.peer_count == null ? '-' : String(status.peer_count);
  byId('chain-mempool').textContent = status.mempool_tx_count == null
    ? '-'
    : `${status.mempool_tx_count} tx · ${formatBytes(status.mempool_usage_bytes)}`;
  byId('chain-meta-network').textContent = status.network ? `${status.network} via ${status.source}` : status.source;
  const stale = isChainStatusStale(status);
  byId('chain-meta-sync').textContent = !status.available
    ? 'Node unavailable'
    : stale
      ? 'Status stale'
      : (status.is_synced ? 'Synced to tip' : `Syncing ${((status.verification_progress || 0) * 100).toFixed(2)}%`);
  byId('chain-meta-refresh').textContent = formatRefreshTime(status.refreshed_at);

  const chip = byId('chain-status-chip');
  chip.classList.remove('chip-live', 'chip-syncing', 'chip-down');
  if (!status.available || stale) {
    chip.textContent = 'unavailable';
    chip.classList.add('chip-down');
  } else if (status.is_synced) {
    chip.textContent = 'live';
    chip.classList.add('chip-live');
  } else {
    chip.textContent = 'syncing';
    chip.classList.add('chip-syncing');
  }

  if (status.warnings && status.warnings.length) {
    warning.textContent = status.warnings[0];
    warning.classList.remove('hidden');
  } else {
    warning.classList.add('hidden');
  }

  const delayMs = status.available ? 60000 : 180000;
  scheduleChainStatusRefresh(delayMs);
}

async function loadChainStatus() {
  try {
    const status = await api('api/chain/status');
    renderChainStatus(status);
  } catch (error) {
    renderChainStatus({
      enabled: true,
      available: false,
      source: 'bitcoind',
      network: null,
      block_height: null,
      header_height: null,
      verification_progress: null,
      is_synced: null,
      last_block_at: null,
      seconds_since_last_block: null,
      peer_count: null,
      mempool_tx_count: null,
      mempool_usage_bytes: null,
      pruned: null,
      warnings: [error.message || 'Bitcoin node status is currently unavailable.'],
      refreshed_at: new Date().toISOString(),
    });
  }
}

function renderDashboard(dashboard) {
  state.dashboard = dashboard;
  byId('dashboard-balance').textContent = denomFormat(dashboard.summary.total_balance);
  byId('dashboard-basis').textContent = dashboard.summary.average_cost_basis_usd == null
    ? 'Unpriced'
    : currency(dashboard.summary.average_cost_basis_usd);
  byId('dashboard-recent-count').textContent = `${dashboard.recent_transactions.length} tx`;
  byId('hero-wallet-count').textContent = `${dashboard.summary.active_wallet_count} of ${dashboard.summary.wallet_count} wallets`;
  renderDashboardVerificationPosture(dashboard.portfolio_verification);

  const warning = byId('custody-warning');
  if (dashboard.using_inferred_custody) {
    warning.textContent = 'Custody mix is partially inferred from wallet names because explicit wallet metadata is incomplete.';
    warning.classList.remove('hidden');
  } else {
    warning.classList.add('hidden');
  }

  var totalBal = Number(dashboard.summary.total_balance) || 0;
  var walletCount = dashboard.summary.wallet_count || 0;
  byId('custody-sub').textContent = totalBal > 0
    ? `Where your stack lives today · ${denomFormat(totalBal)} across ${walletCount} wallets`
    : 'Where your stack lives today.';

  byId('custody-gauge').innerHTML = dashboard.custody_breakdown.length
    ? dashboard.custody_breakdown.map((row) => {
        var cls = (row.custody || 'unknown').toLowerCase().replace(/[^a-z]/g, '');
        var pct = Math.max(row.percentage, 0.5);
        return `<div class="cg-seg ${cls}" style="width:${pct}%" title="${escapeHtml(row.custody)} ${row.percentage.toFixed(1)}%"></div>`;
      }).join('')
    : '';

  byId('custody-list').innerHTML = dashboard.custody_breakdown.length
    ? dashboard.custody_breakdown.map((row) => {
        var cls = (row.custody || 'unknown').toLowerCase().replace(/[^a-z]/g, '');
        return `<div class="custody-row">
          <div class="custody-dot ${cls}"></div>
          <div>${escapeHtml(row.custody)}</div>
          <div class="wallet-balance" style="font-weight:600; font-variant-numeric:tabular-nums">${denomFormat(row.balance)}</div>
          <div class="custody-pct">${row.percentage.toFixed(1)}%</div>
        </div>`;
      }).join('')
    : '<div class="custody-row" style="grid-template-columns:1fr"><div class="list-item-meta">No custody data yet.</div></div>';

  byId('wallet-list').innerHTML = dashboard.wallets.length
    ? dashboard.wallets.map((wallet) => `
        <a class="list-item list-item-link" href="${appBase()}wallet/${encodeURIComponent(wallet.wallet_id)}" data-wallet-id="${escapeHtml(wallet.wallet_id)}">
          <div class="wallet-main">
            <div class="wallet-title">${escapeHtml(wallet.wallet_id)}</div>
            <div class="tx-detail">
              <span class="wallet-badge">${escapeHtml(wallet.custody)}</span>
              ${renderWalletVerificationBadge(wallet)}
              <span>${escapeHtml(wallet.wallet_type)}</span>
              ${wallet.description ? `<span>${escapeHtml(wallet.description)}</span>` : ''}
              ${wallet.active ? '' : '<span>inactive</span>'}
            </div>
          </div>
          <div class="wallet-balance-wrap">
            <div class="wallet-balance">${denomFormat(wallet.balance)}</div>
            <div class="list-item-meta">${wallet.percentage.toFixed(1)}% of stack</div>
          </div>
        </a>
      `).join('')
    : '<div class="list-item"><div class="list-item-meta">No wallets with BTC balance yet.</div></div>';

  for (const link of byId('wallet-list').querySelectorAll('[data-wallet-id]')) {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      navigateToWallet(link.dataset.walletId);
    });
  }

  byId('recent-transactions-list').innerHTML = renderTransactionRows(dashboard.recent_transactions);
}

function renderDashboardVerificationPosture(posture) {
  const card = byId('dashboard-verification-card');
  const label = byId('dashboard-verification');
  const meta = byId('dashboard-verification-meta');
  card.classList.remove('summary-card-verified', 'summary-card-warning', 'summary-card-danger');

  if (!posture || posture.eligible_wallet_count === 0) {
    label.textContent = '🔰 Ineligible';
    meta.textContent = 'No active self-custodied or multisig wallets with BTC balance are eligible yet.';
    return;
  }

  if (posture.status === 'verified') {
    card.classList.add('summary-card-verified');
    label.textContent = '🔰 Verified';
    meta.textContent = `Wallets verified within ${posture.recency_window_days} days.`;
    return;
  }

  if (posture.status === 'failed' || posture.status === 'drift_detected') {
    card.classList.add('summary-card-danger');
  } else {
    card.classList.add('summary-card-warning');
  }

  const problemCount = posture.failed_wallet_count + posture.drift_wallet_count + posture.partial_wallet_count + posture.stale_wallet_count;
  label.textContent = '🔰 Not Fully Verified';
  meta.textContent = `${problemCount} wallet${problemCount !== 1 ? 's' : ''} need attention.`;
}

function renderWalletVerificationBadge(wallet) {
  if (!wallet.verification_eligible) return '';
  const status = wallet.verification_status;
  if (!status) {
    return '<span class="wallet-badge wallet-badge-warning">🔰 unverified</span>';
  }
  const label = verificationStatusLabel(status, wallet.verification_is_recent);
  let badgeClass = 'wallet-badge-warning';
  if (status === 'verified' && wallet.verification_is_recent && wallet.verification_coverage === 'full') {
    badgeClass = 'wallet-badge-verified';
  } else if (status === 'failed') {
    badgeClass = 'wallet-badge-danger';
  } else if (status === 'drift_detected') {
    badgeClass = 'wallet-badge-danger';
  }
  return `<span class="wallet-badge ${badgeClass}">🔰 ${escapeHtml(label.toLowerCase())}</span>`;
}

async function loadDashboard() {
  const params = new URLSearchParams({
    coin: 'BTC',
    recent_limit: '5',
  });
  const [dashboardResult, chainResult] = await Promise.allSettled([
    api(`api/portfolio/dashboard?${params.toString()}`),
    loadChainStatus(),
  ]);

  if (dashboardResult.status !== 'fulfilled') {
    throw dashboardResult.reason;
  }

  renderDashboard(dashboardResult.value);

  if (chainResult.status !== 'fulfilled') {
    throw chainResult.reason;
  }
}

function renderTransactionRows(transactions) {
  if (!transactions.length) {
    return '<div class="tx-row"><div class="list-item-meta">No transactions yet.</div></div>';
  }
  return transactions.map((tx) => {
    const direction = tx.buy_currency === 'BTC'
      ? denomFormat(tx.buy_amount || 0)
      : denomFormat(tx.sell_amount || 0);
    return `
      <div class="tx-row">
        <div class="tx-main">
          <div class="tx-title-row">
            <span class="tx-title">${escapeHtml(tx.wallet_id || 'Unknown wallet')}</span>
            <span class="tx-type-pill">${escapeHtml(tx.transaction_type || 'Tx')}</span>
          </div>
          <div class="tx-detail">
            <span>${escapeHtml(tx.created_at)}</span>
            ${tx.comment ? `<span>${escapeHtml(tx.comment)}</span>` : ''}
          </div>
        </div>
        <div class="tx-amount">${escapeHtml(direction)}</div>
      </div>
    `;
  }).join('');
}

function verificationStatusLabel(status, isRecent = true) {
  if (!status) return 'Unverified';
  if (status === 'verified' && !isRecent) return 'Stale';
  if (status === 'verified') return 'Verified';
  if (status === 'drift_detected') return 'Drift Detected';
  if (status === 'failed') return 'Failed';
  if (status === 'not_meaningful') return 'Not Meaningful';
  return status.replaceAll('_', ' ').replace(/\b\w/g, (match) => match.toUpperCase());
}

function verificationTone(latest) {
  if (!latest) return 'idle';
  if (latest.status === 'verified' && latest.is_recent) return 'verified';
  if (latest.status === 'verified' && !latest.is_recent) return 'stale';
  if (latest.status === 'drift_detected') return 'drift';
  if (latest.status === 'failed') return 'failed';
  if (latest.status === 'not_meaningful') return 'not-meaningful';
  if (latest.coverage === 'partial') return 'partial';
  return 'neutral';
}

function applyVerificationChip(el, latest) {
  el.classList.remove('chip-live', 'chip-syncing', 'chip-down');
  const tone = verificationTone(latest);
  if (tone === 'verified') el.classList.add('chip-live');
  if (tone === 'stale' || tone === 'drift' || tone === 'partial' || tone === 'not-meaningful') {
    el.classList.add('chip-syncing');
  }
  if (tone === 'failed') el.classList.add('chip-down');
}

function verificationRunChipClass(run) {
  const tone = verificationTone(run);
  if (tone === 'verified') return 'is-verified';
  if (tone === 'drift') return 'is-drift';
  if (tone === 'partial') return 'is-partial';
  if (tone === 'stale') return 'is-stale';
  if (tone === 'not-meaningful') return 'is-not-meaningful';
  if (tone === 'failed') return 'is-failed';
  return '';
}

function formatVerificationTime(value) {
  if (!value) return 'Unknown time';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function renderWalletVerificationEligibility(eligibility) {
  const helperEl = byId('wallet-verification-eligibility');
  const modeEl = byId('wallet-verification-mode');
  const descriptorEl = byId('wallet-verification-descriptor');
  const externalEl = byId('wallet-verification-external');
  const changeEl = byId('wallet-verification-change');
  const ceilingEl = byId('wallet-verification-ceiling');
  const submitEl = byId('wallet-verification-submit');

  const eligible = !eligibility || eligibility.eligible;
  const disabled = !eligible;
  modeEl.disabled = disabled;
  descriptorEl.disabled = disabled;
  externalEl.disabled = disabled;
  changeEl.disabled = disabled;
  ceilingEl.disabled = disabled;
  submitEl.disabled = disabled;

  if (!eligibility) {
    helperEl.textContent = 'Use a combined wallet descriptor when possible. First-run scan depth defaults to 50 addresses.';
    return;
  }

  ceilingEl.value = String(eligibility.recommended_first_scan_ceiling || 50);
  helperEl.textContent = eligibility.eligible
    ? 'Eligible for descriptor-based verification. Combined wallet descriptors are preferred, but receive/change descriptors are also supported.'
    : (eligibility.reason || 'This wallet is not eligible for descriptor-based verification.');
}

function updateVerificationModeUI() {
  const mode = byId('wallet-verification-mode').value;
  const branchFields = byId('wallet-verification-branch-fields');
  const combinedField = byId('wallet-verification-descriptor').closest('.field');
  const useBranches = mode === 'branches';
  branchFields.classList.toggle('hidden', !useBranches);
  combinedField.classList.toggle('hidden', useBranches);
}

function renderWalletVerificationSummary(latest, walletBalance) {
  const chip = byId('wallet-verification-chip');
  const statusEl = byId('wallet-verification-status');
  const captionEl = byId('wallet-verification-caption');
  const coverageEl = byId('wallet-verification-coverage');
  const scanEl = byId('wallet-verification-scan');
  const balanceEl = byId('wallet-verification-balance');
  const driftEl = byId('wallet-verification-drift');
  const messageEl = byId('wallet-verification-message');
  const ceilingInput = byId('wallet-verification-ceiling');

  applyVerificationChip(chip, latest);

  if (!latest) {
    chip.textContent = 'unverified';
    statusEl.textContent = 'Unverified';
    captionEl.textContent = 'No verification has been run for this wallet yet.';
    coverageEl.textContent = '-';
    scanEl.textContent = 'No scan metadata yet.';
    balanceEl.textContent = `${denomFormat(walletBalance || 0)} ledger`;
    driftEl.textContent = 'Paste a descriptor and run the first verification.';
    messageEl.textContent = 'Paste a wallet descriptor to run the first verification.';
    messageEl.style.color = 'var(--muted)';
    ceilingInput.value = '50';
    return;
  }

  const label = verificationStatusLabel(latest.status, latest.is_recent);
  chip.textContent = label.toLowerCase();
  statusEl.textContent = label;
  captionEl.textContent = `${latest.is_recent ? 'Recent under current policy.' : 'Outside the current recency window.'} Last run ${formatVerificationTime(latest.verified_at)}.`;
  coverageEl.textContent = latest.coverage === 'full' ? 'Full' : latest.coverage === 'partial' ? 'Partial' : latest.coverage;

  const scanBits = [];
  if (latest.highest_scanned_index != null) scanBits.push(`scanned through #${latest.highest_scanned_index}`);
  if (latest.scan_ceiling != null) scanBits.push(`ceiling ${latest.scan_ceiling}`);
  if (latest.gap_limit != null) scanBits.push(`gap ${latest.gap_limit}`);
  scanEl.textContent = scanBits.length ? scanBits.join(' · ') : 'No scan metadata recorded.';

  if (latest.verified_balance == null) {
    balanceEl.textContent = '-';
    driftEl.textContent = latest.warning_text || latest.error_text || 'No verified balance recorded.';
  } else {
    const drift = Number(latest.drift_btc || 0);
    balanceEl.textContent = denomFormat(latest.verified_balance);
    driftEl.textContent = `Ledger ${denomFormat(latest.ledger_balance || 0)} · Drift ${drift >= 0 ? '+' : ''}${denomFormat(Math.abs(drift))}`;
  }

  messageEl.textContent = latest.error_text || latest.warning_text || `${label} as of ${formatVerificationTime(latest.verified_at)}.`;
  messageEl.style.color = latest.status === 'failed'
    ? 'var(--bad)'
    : (latest.status === 'drift_detected' || !latest.is_recent || latest.coverage === 'partial')
      ? 'var(--warn)'
      : 'var(--ok)';
  ceilingInput.value = String(latest.scan_ceiling || 50);
}

function renderWalletVerificationHistory(data) {
  state.walletVerificationHistory = data;
  const list = byId('wallet-verification-history');
  const runs = (data && data.runs) || [];
  if (!runs.length) {
    list.innerHTML = '<div class="list-item"><div class="list-item-meta">No verification history yet.</div></div>';
    return;
  }

  list.innerHTML = runs.map((run) => `
    <div class="list-item verification-list-item">
      <div class="verification-list-main">
        <div class="verification-list-title">
          <span>${escapeHtml(verificationStatusLabel(run.status, run.is_recent))}</span>
          <span class="verification-run-chip ${verificationRunChipClass(run)}">${escapeHtml(run.coverage)}</span>
        </div>
        <div class="tx-detail">
          <span>${escapeHtml(formatVerificationTime(run.verified_at))}</span>
          ${run.scan_ceiling != null ? `<span>ceiling ${escapeHtml(String(run.scan_ceiling))}</span>` : ''}
          ${run.highest_scanned_index != null ? `<span>through #${escapeHtml(String(run.highest_scanned_index))}</span>` : ''}
        </div>
        <div class="list-item-meta">
          ${run.verified_balance == null ? escapeHtml(run.warning_text || run.error_text || 'No verified balance recorded.') : `${denomFormat(run.verified_balance)} vs ledger ${denomFormat(run.ledger_balance || 0)}`}
        </div>
      </div>
    </div>
  `).join('');
}

async function loadWalletVerificationHistory(walletId) {
  try {
    const data = await api(`api/verification/wallets/${encodeURIComponent(walletId)}`);
    renderWalletVerificationHistory(data);
  } catch (error) {
    byId('wallet-verification-history').innerHTML = `<div class="list-item"><div class="list-item-meta">${escapeHtml(error.message)}</div></div>`;
  }
}

async function loadWalletDetail(walletId) {
  try {
    const params = new URLSearchParams({ coin: 'BTC', recent_limit: '20' });
    const detail = await api(`api/portfolio/wallet/${encodeURIComponent(walletId)}?${params.toString()}`);
    state.walletDetail = detail;

    const w = detail.wallet;
    byId('wallet-view-name').textContent = w.wallet_id;
    byId('wallet-view-title').textContent = w.wallet_id;
    byId('wallet-view-custody').textContent = w.custody;
    byId('wallet-view-desc').textContent = w.description || '';
    byId('wallet-view-balance').textContent = denomFormat(w.balance);
    byId('wallet-view-pct').textContent = `${w.percentage.toFixed(1)}% of stack`;
    byId('wallet-view-type').textContent = w.wallet_type;
    byId('wallet-view-status').textContent = w.active ? 'Active' : 'Inactive';
    byId('wallet-view-tx-count').textContent = String(detail.recent_transactions.length);
    byId('wallet-view-pct-card').textContent = `${w.percentage.toFixed(1)}%`;

    renderWalletVerificationEligibility(detail.verification_eligibility);
    renderWalletVerificationSummary(detail.latest_verification, w.balance);
    byId('wallet-tx-list').innerHTML = renderTransactionRows(detail.recent_transactions);
    await loadWalletVerificationHistory(walletId);

    const viewAllLink = byId('wallet-view-all-link');
    viewAllLink.href = `${appBase()}ledger?wallet=${encodeURIComponent(walletId)}`;
    viewAllLink.onclick = (event) => {
      event.preventDefault();
      state.ledgerFilters = { ...state.ledgerFilters, wallet: walletId, page: 1 };
      byId('ledger-wallet').value = walletId;
      navigateTo('ledger');
    };
  } catch (error) {
    renderWalletVerificationEligibility({
      eligible: false,
      reason: 'Wallet verification is unavailable right now.',
      recommended_first_scan_ceiling: 50,
    });
    renderWalletVerificationSummary(null, 0);
    byId('wallet-verification-history').innerHTML = '<div class="list-item"><div class="list-item-meta">Verification history unavailable.</div></div>';
    byId('wallet-tx-list').innerHTML = `<div class="tx-row"><div class="list-item-meta">${escapeHtml(error.message)}</div></div>`;
  }
}

async function loadLedger() {
  const f = state.ledgerFilters;
  const params = new URLSearchParams({ coin: f.coin, page: String(f.page), per_page: String(f.perPage) });
  if (f.wallet) params.set('wallet', f.wallet);
  if (f.startDate) params.set('start_date', f.startDate);
  if (f.endDate) params.set('end_date', f.endDate);
  if (f.includeDeleted) params.set('include_deleted', 'true');

  try {
    const data = await api(`api/ledger?${params.toString()}`);
    renderLedger(data);
  } catch (error) {
    byId('ledger-table').innerHTML = `<tr><td colspan="7" class="empty-row">${escapeHtml(error.message)}</td></tr>`;
  }
}

function renderLedger(data) {
  const s = data.summary;
  byId('ledger-balance').textContent = denomFormat(s.balance);
  byId('ledger-credits').textContent = denomFormat(s.credits);
  byId('ledger-debits').textContent = denomFormat(s.debits);
  byId('ledger-fees').textContent = denomFormat(s.fees);
  byId('ledger-count').textContent = `Showing ${data.transactions.length} of ${data.total} transactions (page ${data.page})`;

  if (!data.transactions.length) {
    byId('ledger-table').innerHTML = '<tr><td colspan="7" class="empty-row">No transactions match the current filters.</td></tr>';
    byId('ledger-cards').innerHTML = '';
  } else {
    byId('ledger-table').innerHTML = data.transactions.map((tx) => `
      <tr class="ledger-row${tx.deleted ? ' ledger-row-deleted' : ''}" data-tx-id="${tx.transaction_id}">
        <td>${escapeHtml(tx.created_at)}</td>
        <td>${escapeHtml(tx.transaction_type || '')}</td>
        <td>${tx.buy_amount != null ? ((tx.buy_currency || 'BTC') === 'BTC' ? denomFormat(tx.buy_amount) : formatAmount(tx.buy_amount, tx.buy_currency)) : ''}</td>
        <td>${tx.sell_amount != null ? ((tx.sell_currency || 'BTC') === 'BTC' ? denomFormat(tx.sell_amount) : formatAmount(tx.sell_amount, tx.sell_currency)) : ''}</td>
        <td>${tx.fee_amount != null ? ((tx.fee_currency || 'BTC') === 'BTC' ? denomFormat(tx.fee_amount) : formatAmount(tx.fee_amount, tx.fee_currency)) : ''}</td>
        <td>${escapeHtml(tx.wallet_id || '')}</td>
        <td>${escapeHtml(tx.comment || '')}</td>
      </tr>
    `).join('');

    byId('ledger-cards').innerHTML = data.transactions.map((tx) => {
      const type = (tx.transaction_type || 'tx').toLowerCase();
      const typeClass = type === 'buy' || type === 'deposit' ? 'deposit'
        : type === 'sell' || type === 'withdrawal' ? 'withdraw'
        : type === 'trade' ? 'trade' : '';
      const glyph = type.charAt(0).toUpperCase();
      const amount = tx.buy_amount != null ? denomFormat(tx.buy_amount)
        : tx.sell_amount != null ? denomFormat(tx.sell_amount) : '';
      const datePart = (tx.created_at || '').replace('T', ' ').slice(0, 16);
      const wallet = tx.wallet_id || '';
      const comment = tx.comment || '';
      const sub = [datePart, wallet, comment].filter(Boolean).join(' · ');
      return `<div class="ledger-card ${typeClass}" data-tx-id="${tx.transaction_id}">
        <div class="lc-glyph">${glyph}</div>
        <div>
          <div class="lc-type-label">${escapeHtml(tx.transaction_type || 'Tx')}</div>
          <div class="lc-sub">${escapeHtml(sub)}</div>
        </div>
        <div style="text-align: right; font-variant-numeric: tabular-nums; font-size: 13px; font-weight: 600;">${amount}</div>
      </div>`;
    }).join('');

    for (const row of byId('ledger-table').querySelectorAll('[data-tx-id]')) {
      row.addEventListener('click', () => openTransactionDetail(Number(row.dataset.txId)));
    }
    for (const card of byId('ledger-cards').querySelectorAll('[data-tx-id]')) {
      card.addEventListener('click', () => openTransactionDetail(Number(card.dataset.txId)));
    }
  }

  const totalPages = Math.ceil(data.total / data.per_page);
  if (totalPages <= 1) {
    byId('ledger-pagination').innerHTML = '';
  } else {
    const buttons = [];
    if (data.page > 1) buttons.push(`<button class="button button-ghost" data-ledger-page="${data.page - 1}">Prev</button>`);
    buttons.push(`<span class="list-item-meta">Page ${data.page} of ${totalPages}</span>`);
    if (data.page < totalPages) buttons.push(`<button class="button button-ghost" data-ledger-page="${data.page + 1}">Next</button>`);
    byId('ledger-pagination').innerHTML = buttons.join(' ');

    for (const btn of byId('ledger-pagination').querySelectorAll('[data-ledger-page]')) {
      btn.addEventListener('click', () => {
        state.ledgerFilters.page = Number(btn.dataset.ledgerPage);
        loadLedger();
      });
    }
  }
}

async function openTransactionDetail(txId) {
  try {
    const tx = await api(`api/ledger/${txId}`);
    await loadRecordWalletOptions(tx.wallet_id || '');
    state.selectedTx = tx;
    byId('tx-detail-title').textContent = `${tx.transaction_type || 'Transaction'} Detail`;
    byId('tx-detail-id').textContent = `#${tx.transaction_id}`;
    byId('tx-edit-date').value = tx.created_at || '';
    byId('tx-edit-type').value = tx.transaction_type || '';
    byId('tx-edit-buy').value = tx.buy_amount != null ? tx.buy_amount : '';
    byId('tx-edit-buy-curr').value = tx.buy_currency || '';
    byId('tx-edit-sell').value = tx.sell_amount != null ? tx.sell_amount : '';
    byId('tx-edit-sell-curr').value = tx.sell_currency || '';
    byId('tx-edit-fee').value = tx.fee_amount != null ? tx.fee_amount : '';
    byId('tx-edit-fee-curr').value = tx.fee_currency || '';
    byId('tx-edit-group').value = tx.group || '';
    byId('tx-edit-comment').value = tx.comment || '';

    const warning = byId('tx-transfer-warning');
    if (tx.group && (tx.transaction_type === 'Deposit' || tx.transaction_type === 'Withdrawal')) {
      warning.classList.remove('hidden');
    } else {
      warning.classList.add('hidden');
    }

    byId('tx-delete-btn').classList.toggle('hidden', tx.deleted);
    byId('tx-restore-btn').classList.toggle('hidden', !tx.deleted);
    byId('tx-edit-status').classList.add('hidden');
    byId('tx-detail-overlay').classList.remove('hidden');
    document.body.classList.add('modal-open');
  } catch (error) {
    byId('tx-detail-overlay').classList.add('hidden');
    document.body.classList.remove('modal-open');
  }
}

function closeTransactionDetail() {
  byId('tx-detail-overlay').classList.add('hidden');
  document.body.classList.remove('modal-open');
  state.selectedTx = null;
}

function toggleLedgerFilters(force) {
  const panel = byId('ledger-form');
  const btn = byId('ledger-filter-toggle');
  const shouldOpen = typeof force === 'boolean' ? force : panel.classList.contains('hidden');
  panel.classList.toggle('hidden', !shouldOpen);
  btn.setAttribute('aria-expanded', String(shouldOpen));
  sessionStorage.setItem('ledger-filters-open', shouldOpen ? '1' : '0');
}

function showTxStatus(message, isError = false) {
  const el = byId('tx-edit-status');
  el.textContent = message;
  el.style.color = isError ? 'var(--bad)' : 'var(--ok)';
  el.classList.remove('hidden');
}

async function loadPolicy() {
  const policy = await api('api/tax/policy');
  state.policy = policy;
  byId('policy-summary').textContent = policy.summary;
}

async function loadGains() {
  const params = new URLSearchParams({
    tax_year: String(state.gainsFilters.taxYear),
    coin: state.gainsFilters.coin,
  });
  if (state.gainsFilters.wallet) {
    params.set('wallet', state.gainsFilters.wallet);
  }

  try {
    const report = await api(`api/tax/gains?${params.toString()}`);
    byId('gains-proceeds').textContent = currency(report.summary.proceeds_usd);
    byId('gains-cost').textContent = currency(report.summary.cost_basis_usd);
    byId('gains-net').textContent = currency(report.summary.gain_loss_usd);
    byId('gains-lots').textContent = String(report.summary.lot_count);
    renderWarnings('gains-warnings', report.warnings);

    const rows = report.worksheet.length
      ? report.worksheet.map((row) => `
          <tr>
            <td>${escapeHtml(row.sale_date)}</td>
            <td>${denomFormat(row.lot_quantity)}</td>
            <td>${escapeHtml(row.acquire_date)}</td>
            <td>${escapeHtml(row.term)}</td>
            <td>${currency(row.gain_loss_usd)}</td>
          </tr>
        `).join('')
      : '<tr><td colspan="5" class="empty-row">No gains found for the selected filters.</td></tr>';
    byId('gains-table').innerHTML = rows;
    renderDataCards('gains-cards', report.worksheet.map((row) => dataCard(
      row.sale_date,
      `${row.term} term`,
      [
        ['Lot quantity', denomFormat(row.lot_quantity)],
        ['Acquired', row.acquire_date],
        ['Gain/loss', currency(row.gain_loss_usd)],
      ],
    )), 'No gains found for the selected filters.');

    const showPolicy = report.warnings.some((warning) => warning.code === 'wallet_required_2025');
    const banner = byId('policy-warning');
    if (showPolicy) {
      banner.textContent = 'For tax year 2025 and later, exports require an explicit wallet filter.';
      banner.classList.remove('hidden');
    } else {
      banner.classList.add('hidden');
    }
  } catch (error) {
    byId('gains-table').innerHTML = `<tr><td colspan="5" class="empty-row">${escapeHtml(error.message)}</td></tr>`;
    renderDataCards('gains-cards', [], error.message);
  }
}

async function loadForecast() {
  const params = new URLSearchParams({
    coin: state.forecastFilters.coin,
    quantity: String(state.forecastFilters.quantity),
    sale_price_usd: String(state.forecastFilters.salePriceUsd),
  });
  if (state.forecastFilters.wallet) {
    params.set('wallet', state.forecastFilters.wallet);
  }

  try {
    const forecast = await api(`api/tax/forecast?${params.toString()}`);
    byId('forecast-balance').textContent = denomFormat(forecast.current_balance);
    byId('forecast-proceeds').textContent = currency(forecast.summary.total_proceeds_usd);
    byId('forecast-cost').textContent = currency(forecast.summary.total_cost_basis_usd);
    byId('forecast-missing').textContent = denomFormat(forecast.summary.missing_basis_quantity);
    renderWarnings('forecast-warnings', forecast.warnings);

    const rows = forecast.lots.length
      ? forecast.lots.map((lot) => `
          <tr>
            <td>${escapeHtml(lot.acquire_date || 'UNKNOWN')}</td>
            <td>${denomFormat(lot.quantity)}</td>
            <td>${currency(lot.unit_cost_usd)}</td>
            <td>${escapeHtml(lot.term)}</td>
            <td>${currency(lot.cost_basis_usd)}</td>
          </tr>
        `).join('')
      : '<tr><td colspan="5" class="empty-row">No forecast lots available.</td></tr>';
    byId('forecast-table').innerHTML = rows;
    renderDataCards('forecast-cards', forecast.lots.map((lot) => dataCard(
      lot.acquire_date || 'Unknown acquisition date',
      `${lot.term} term`,
      [
        ['Quantity', denomFormat(lot.quantity)],
        ['Unit cost', currency(lot.unit_cost_usd)],
        ['Basis', currency(lot.cost_basis_usd)],
      ],
    )), 'No forecast lots available.');
  } catch (error) {
    byId('forecast-table').innerHTML = `<tr><td colspan="5" class="empty-row">${escapeHtml(error.message)}</td></tr>`;
    renderDataCards('forecast-cards', [], error.message);
  }
}

async function loadPresets() {
  const presets = await api('api/tax/presets');
  byId('presets-list').innerHTML = presets.length
    ? presets.map((preset) => `
        <div class="list-item">
          <div class="wallet-main">
            <strong>${escapeHtml(preset.name)}</strong>
            <div class="list-item-meta">${escapeHtml(preset.preset_type.toUpperCase())} · ${escapeHtml(preset.coin)}${preset.tax_year ? ` · ${preset.tax_year}` : ''}${preset.wallet_id ? ` · ${escapeHtml(preset.wallet_id)}` : ''}</div>
          </div>
          <button class="button button-ghost" type="button" data-preset-id="${escapeHtml(preset.preset_id)}">Delete</button>
        </div>
      `).join('')
    : '<div class="list-item"><div class="list-item-meta">No saved presets yet.</div></div>';

  for (const button of byId('presets-list').querySelectorAll('[data-preset-id]')) {
    button.addEventListener('click', async () => {
      await api(`api/tax/presets/${button.dataset.presetId}`, { method: 'DELETE' });
      await loadPresets();
    });
  }
}

async function loadHistory() {
  const history = await api('api/tax/history?limit=8');
  byId('history-list').innerHTML = history.length
    ? history.map((entry) => `
        <div class="list-item">
          <div class="wallet-main">
            <strong>${escapeHtml(entry.action)}</strong>
            <div class="list-item-meta">${escapeHtml(entry.coin)}${entry.tax_year ? ` · ${entry.tax_year}` : ''}${entry.wallet_id ? ` · ${escapeHtml(entry.wallet_id)}` : ''}</div>
          </div>
          <div class="list-item-meta">${new Date(entry.created_at).toLocaleString()}</div>
        </div>
      `).join('')
    : '<div class="list-item"><div class="list-item-meta">No web history yet.</div></div>';
}

function currentPresetPayload() {
  const presetType = byId('preset-type').value;
  const payload = {
    name: byId('preset-name').value.trim(),
    preset_type: presetType,
    coin: presetType === 'forecast' ? state.forecastFilters.coin : state.gainsFilters.coin,
  };

  if (presetType === 'forecast') {
    payload.wallet_id = state.forecastFilters.wallet || null;
    payload.quantity = Number(state.forecastFilters.quantity);
    payload.sale_price_usd = Number(state.forecastFilters.salePriceUsd);
  } else {
    payload.tax_year = Number(state.gainsFilters.taxYear);
    payload.wallet_id = state.gainsFilters.wallet || null;
  }

  return payload;
}

function downloadTaxArtifact(kind) {
  const params = new URLSearchParams({
    tax_year: String(state.gainsFilters.taxYear),
    coin: state.gainsFilters.coin,
  });
  if (state.gainsFilters.wallet) {
    params.set('wallet', state.gainsFilters.wallet);
  }
  window.location.href = `${appBase()}api/tax/${kind}?${params.toString()}`;
}

async function populateLedgerWalletDropdown() {
  try {
    const data = await api('api/wallets');
    const select = byId('ledger-wallet');
    const current = select.value;
    select.innerHTML = '<option value="">All wallets</option>' +
      data.wallets.map((w) =>
        `<option value="${escapeHtml(w.wallet_id)}"${w.wallet_id === current ? ' selected' : ''}>${escapeHtml(w.wallet_id)}</option>`
      ).join('');
  } catch (_) {
    // Keep the existing options if the API call fails
  }
}

async function loadWalletsList() {
  const activeOnly = byId('wallets-active-toggle').checked;
  const params = new URLSearchParams();
  if (activeOnly) params.set('active_only', 'true');
  try {
    const data = await api(`api/wallets?${params.toString()}`);
    state.walletsList = data.wallets;
    renderWalletsList(data.wallets);
  } catch (error) {
    byId('wallets-table').innerHTML = `<tr><td colspan="6" class="empty-row">${escapeHtml(error.message)}</td></tr>`;
    renderDataCards('wallets-cards', [], error.message);
  }
}

function walletActionsMarkup(w) {
  const walletId = escapeHtml(w.wallet_id);
  return `<button class="button button-ghost button-inline" data-wallet-open="${walletId}">Open</button>
    <button class="button button-ghost button-inline" data-wallet-edit="${walletId}">Edit</button>
    <button class="button button-ghost button-inline" data-wallet-toggle="${walletId}" data-active="${w.active}">${w.active ? 'Deactivate' : 'Activate'}</button>
    <button class="button button-ghost button-inline" data-wallet-rename="${walletId}" data-tx-count="${w.transaction_count}">Rename</button>
    <button class="button button-ghost button-inline" data-wallet-merge="${walletId}" data-tx-count="${w.transaction_count}">Merge</button>`;
}

function bindWalletActions(container) {
  for (const btn of container.querySelectorAll('[data-wallet-open]')) {
    btn.addEventListener('click', () => navigateToWallet(btn.dataset.walletOpen));
  }
  for (const btn of container.querySelectorAll('[data-wallet-edit]')) {
    btn.addEventListener('click', () => openWalletEdit(btn.dataset.walletEdit));
  }
  for (const btn of container.querySelectorAll('[data-wallet-toggle]')) {
    btn.addEventListener('click', () => toggleWalletActive(btn.dataset.walletToggle, btn.dataset.active === 'true'));
  }
  for (const btn of container.querySelectorAll('[data-wallet-rename]')) {
    btn.addEventListener('click', () => openWalletRename(btn.dataset.walletRename, Number(btn.dataset.txCount)));
  }
  for (const btn of container.querySelectorAll('[data-wallet-merge]')) {
    btn.addEventListener('click', () => openWalletMerge(btn.dataset.walletMerge, Number(btn.dataset.txCount)));
  }
}

function renderWalletsList(wallets) {
  if (!wallets.length) {
    byId('wallets-table').innerHTML = '<tr><td colspan="6" class="empty-row">No wallets found.</td></tr>';
    renderDataCards('wallets-cards', [], 'No wallets found.');
    return;
  }
  byId('wallets-table').innerHTML = wallets.map((w) => `
    <tr>
      <td><strong>${escapeHtml(w.wallet_id)}</strong>${w.description ? `<br><span class="list-item-meta">${escapeHtml(w.description)}</span>` : ''}</td>
      <td>${escapeHtml(w.wallet_type)}</td>
      <td>${escapeHtml(w.custody)}</td>
      <td>${w.active ? 'Active' : 'Inactive'}</td>
      <td>${w.transaction_count}</td>
      <td class="actions-cell">${walletActionsMarkup(w)}</td>
    </tr>
  `).join('');
  renderDataCards('wallets-cards', wallets.map((w) => dataCard(
    w.wallet_id,
    w.description || `${w.wallet_type} · ${w.custody}`,
    [
      ['Type', w.wallet_type],
      ['Custody', w.custody],
      ['Status', w.active ? 'Active' : 'Inactive'],
      ['Transactions', String(w.transaction_count)],
    ],
    walletActionsMarkup(w),
  )), 'No wallets found.');
  bindWalletActions(byId('wallets-table'));
  bindWalletActions(byId('wallets-cards'));
}

function openWalletEdit(walletId) {
  const w = (state.walletsList || []).find((w) => w.wallet_id === walletId);
  if (!w) return;
  byId('wallet-form-mode').value = 'edit';
  byId('wallet-form-original-id').value = walletId;
  byId('wallet-form-title').textContent = `Edit: ${walletId}`;
  byId('wallet-form-submit').textContent = 'Save Changes';
  byId('wallet-form-id').value = walletId;
  byId('wallet-form-id').setAttribute('disabled', 'disabled');
  byId('wallet-form-type').value = w.wallet_type;
  byId('wallet-form-custody').value = w.custody;
  byId('wallet-form-desc').value = w.description || '';
  byId('wallet-form-notes').value = w.notes || '';
  byId('wallet-form-status').classList.add('hidden');
  byId('wallet-form-panel').classList.remove('hidden');
  byId('wallet-form-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function toggleWalletActive(walletId, currentlyActive) {
  try {
    await api(`api/wallets/${encodeURIComponent(walletId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ active: !currentlyActive }),
    });
    await loadWalletsList();
  } catch (error) {
    const statusEl = byId('wallets-status');
    statusEl.textContent = error.message;
    statusEl.style.color = 'var(--bad)';
    statusEl.classList.remove('hidden');
  }
}

function openWalletRename(walletId, txCount) {
  byId('wallet-rename-old-id').value = walletId;
  byId('wallet-rename-new-id').value = '';
  byId('wallet-rename-info').textContent = `Renaming "${walletId}" (${txCount} transaction${txCount !== 1 ? 's' : ''} will be updated).`;
  byId('wallet-rename-status').classList.add('hidden');
  byId('wallet-rename-panel').classList.remove('hidden');
  byId('wallet-rename-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function openWalletMerge(sourceId, txCount) {
  byId('wallet-merge-source-id').value = sourceId;
  byId('wallet-merge-info').textContent = `Merge "${sourceId}" (${txCount} transaction${txCount !== 1 ? 's' : ''}) into another wallet. The source wallet will be deleted.`;
  byId('wallet-merge-status').classList.add('hidden');
  const options = (state.walletsList || [])
    .filter((w) => w.wallet_id !== sourceId)
    .map((w) => `<option value="${escapeHtml(w.wallet_id)}">${escapeHtml(w.wallet_id)}</option>`)
    .join('');
  byId('wallet-merge-target').innerHTML = options || '<option value="">No other wallets</option>';
  byId('wallet-merge-panel').classList.remove('hidden');
  byId('wallet-merge-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Load the data for whichever page is currently active. Centralized so every
// entry point (nav click, session restore, login, browser back/forward) loads
// the same way and no page is forgotten.
function loadPageData(page) {
  switch (page) {
    case 'wallet':
      return state.currentWalletId ? loadWalletDetail(state.currentWalletId) : Promise.resolve();
    case 'ledger':
      return loadLedger();
    case 'trades':
      return loadTradesPage();
    case 'wallets':
      return loadWalletsList();
    case 'reports':
      loadReports();
      return Promise.resolve();
    case 'record':
      initRecordDates();
      return loadRecordWalletOptions();
    default:
      return Promise.resolve();
  }
}

async function refreshSession() {
  try {
    const session = await api('api/auth/me');
    state.session = session;
    showLoggedIn(session.username);
    const loaders = [loadDashboard(), loadPolicy(), loadGains(), loadHistory(), loadPresets(), loadForecast(), populateLedgerWalletDropdown()];
    loaders.push(loadPageData(state.currentPage));
    await Promise.all(loaders);
  } catch (_) {
    state.session = null;
    showLoggedOut();
  }
}

function bindNavigation() {
  for (const link of document.querySelectorAll('[data-route]')) {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      navigateTo(link.dataset.route);
      if (state.session && link.dataset.route === 'dashboard') {
        loadDashboard();
      }
    });
  }

  window.addEventListener('popstate', () => {
    const previousWalletId = state.currentWalletId;
    state.currentPage = currentRouteFromLocation();
    renderPageState();
    if (!state.session) return;
    if (state.currentPage === 'wallet') {
      if (state.currentWalletId && state.currentWalletId !== previousWalletId) {
        loadWalletDetail(state.currentWalletId);
      }
    } else if (state.currentPage === 'dashboard') {
      loadDashboard();
    } else {
      loadPageData(state.currentPage);
    }
  });
}

function bindEvents() {
  bindNavigation();

  byId('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const session = await api('api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ passphrase: byId('passphrase').value }),
      });
      state.session = session;
      setAuthStatus('Authenticated.');
      showLoggedIn(session.username);
      const postLogin = [loadDashboard(), loadPolicy(), loadGains(), loadHistory(), loadPresets(), loadForecast(), populateLedgerWalletDropdown()];
      postLogin.push(loadPageData(state.currentPage));
      await Promise.all(postLogin);
    } catch (error) {
      setAuthStatus(error.message, true);
    }
  });

  async function handleSessionAction() {
    if (state.session) {
      await api('api/auth/logout', { method: 'POST' });
      state.session = null;
      showLoggedOut();
      setAuthStatus('Signed out.');
      return;
    }
    await refreshSession();
  }

  byId('session-action').addEventListener('click', handleSessionAction);
  byId('mobile-session-action').addEventListener('click', handleSessionAction);

  // More-menu slide-up sheet
  const moreToggle = byId('more-menu-toggle');
  const moreSheet = byId('more-menu-sheet');
  const moreOverlay = byId('more-menu-overlay');

  function openMoreMenu() {
    moreOverlay.classList.add('visible');
    moreSheet.classList.add('visible');
    moreOverlay.setAttribute('aria-hidden', 'false');
  }
  function closeMoreMenu() {
    moreSheet.classList.remove('visible');
    moreOverlay.classList.remove('visible');
    moreOverlay.setAttribute('aria-hidden', 'true');
  }

  moreToggle.addEventListener('click', () => {
    if (moreSheet.classList.contains('visible')) closeMoreMenu();
    else openMoreMenu();
  });
  moreOverlay.addEventListener('click', closeMoreMenu);

  // Close more-menu when navigating from it
  for (const link of moreSheet.querySelectorAll('a[data-route]')) {
    link.addEventListener('click', closeMoreMenu);
  }

  // Record tab switching
  for (const tab of document.querySelectorAll('.record-tab')) {
    tab.addEventListener('click', () => {
      for (const t of document.querySelectorAll('.record-tab')) t.classList.remove('active');
      tab.classList.add('active');
      for (const f of document.querySelectorAll('.record-form')) f.classList.add('hidden');
      document.getElementById(`record-${tab.dataset.recordTab}-form`).classList.remove('hidden');
      byId('record-status').classList.add('hidden');
    });
  }

  function showRecordStatus(message, isError = false) {
    const el = byId('record-status');
    el.textContent = message;
    el.style.color = isError ? 'var(--bad)' : 'var(--ok)';
    el.classList.remove('hidden');
  }

  function todayLocal() {
    const now = new Date();
    const offset = now.getTimezoneOffset();
    return new Date(now.getTime() - offset * 60000).toISOString().slice(0, 16);
  }

  byId('record-buy-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await api('api/ledger/buy', {
        method: 'POST',
        body: JSON.stringify({
          trade_date: byId('buy-date').value,
          buy: Number(byId('buy-amount').value),
          sell: Number(byId('buy-cost').value),
          exchange: byId('buy-wallet').value,
          fee: Number(byId('buy-fee').value) || 0,
          fee_curr: byId('buy-fee-curr').value.trim() || 'USD',
          comment: byId('buy-comment').value.trim(),
        }),
      });
      showRecordStatus('Buy recorded successfully.');
      byId('record-buy-form').reset();
      byId('buy-date').value = todayLocal();
    } catch (error) {
      showRecordStatus(error.message, true);
    }
  });

  byId('record-sell-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await api('api/ledger/sell', {
        method: 'POST',
        body: JSON.stringify({
          trade_date: byId('sell-date').value,
          sell: Number(byId('sell-amount').value),
          buy: Number(byId('sell-proceeds').value),
          exchange: byId('sell-wallet').value,
          fee: Number(byId('sell-fee').value) || 0,
          fee_curr: byId('sell-fee-curr').value.trim() || 'USD',
          comment: byId('sell-comment').value.trim(),
        }),
      });
      showRecordStatus('Sale recorded successfully.');
      byId('record-sell-form').reset();
      byId('sell-date').value = todayLocal();
    } catch (error) {
      showRecordStatus(error.message, true);
    }
  });

  byId('record-transfer-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await api('api/ledger/transfer', {
        method: 'POST',
        body: JSON.stringify({
          transfer_date: byId('transfer-date').value,
          amount: Number(byId('transfer-amount').value),
          from_wallet: byId('transfer-from').value,
          to_wallet: byId('transfer-to').value,
          fee: Number(byId('transfer-fee').value) || 0,
          fee_coin: byId('transfer-fee-curr').value.trim() || 'BTC',
          comment: byId('transfer-comment').value.trim(),
        }),
      });
      showRecordStatus('Transfer recorded successfully.');
      byId('record-transfer-form').reset();
      byId('transfer-date').value = todayLocal();
    } catch (error) {
      showRecordStatus(error.message, true);
    }
  });

  byId('record-interest-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      await api('api/ledger/interest', {
        method: 'POST',
        body: JSON.stringify({
          interest_date: byId('interest-date').value,
          amount: Number(byId('interest-amount').value),
          currency: byId('interest-currency').value.trim() || 'BTC',
          exchange: byId('interest-wallet').value,
          comment: byId('interest-comment').value.trim(),
        }),
      });
      showRecordStatus('Interest recorded successfully.');
      byId('record-interest-form').reset();
      byId('interest-date').value = todayLocal();
    } catch (error) {
      showRecordStatus(error.message, true);
    }
  });

  byId('ledger-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    state.ledgerFilters = {
      coin: byId('ledger-coin').value.trim() || 'BTC',
      wallet: byId('ledger-wallet').value.trim(),
      startDate: byId('ledger-start').value,
      endDate: byId('ledger-end').value,
      includeDeleted: byId('ledger-deleted-toggle').checked,
      page: 1,
      perPage: state.ledgerFilters.perPage,
    };
    await loadLedger();
  });

  byId('wallet-verification-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!state.currentWalletId) return;

    const mode = byId('wallet-verification-mode').value;
    const descriptor = byId('wallet-verification-descriptor').value.trim();
    const externalDescriptor = byId('wallet-verification-external').value.trim();
    const changeDescriptor = byId('wallet-verification-change').value.trim();
    const statusEl = byId('wallet-verification-message');
    const submitBtn = byId('wallet-verification-submit');
    const ceilingValue = Number(byId('wallet-verification-ceiling').value || 50);

    if (mode === 'combined' && !descriptor) {
      statusEl.textContent = 'Paste an output descriptor before running verification.';
      statusEl.style.color = 'var(--bad)';
      return;
    }

    if (mode === 'branches' && !externalDescriptor && !changeDescriptor) {
      statusEl.textContent = 'Paste at least one receive or change descriptor before running verification.';
      statusEl.style.color = 'var(--bad)';
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Running...';
    statusEl.textContent = `Running wallet verification for ${state.currentWalletId}...`;
    statusEl.style.color = 'var(--muted)';

    try {
      const response = await api('api/verification/run', {
        method: 'POST',
        body: JSON.stringify({
          wallet_id: state.currentWalletId,
          descriptor: mode === 'combined' ? descriptor : null,
          external_descriptor: mode === 'branches' ? (externalDescriptor || null) : null,
          change_descriptor: mode === 'branches' ? (changeDescriptor || null) : null,
          first_scan_ceiling: Math.max(1, Math.floor(ceilingValue || 50)),
        }),
      });
      statusEl.textContent = response.meaningful_to_verify
        ? `${verificationStatusLabel(response.result.status, response.result.is_recent)} completed.`
        : 'This wallet has no meaningful on-chain activity to verify yet.';
      statusEl.style.color = response.result.status === 'failed'
        ? 'var(--bad)'
        : (response.result.status === 'drift_detected' ? 'var(--warn)' : 'var(--ok)');
      await loadWalletDetail(state.currentWalletId);
    } catch (error) {
      statusEl.textContent = error.message;
      statusEl.style.color = 'var(--bad)';
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Run Verification';
    }
  });

  byId('wallet-verification-mode').addEventListener('change', updateVerificationModeUI);
  updateVerificationModeUI();

  byId('tx-detail-close').addEventListener('click', closeTransactionDetail);

  byId('tx-detail-overlay').addEventListener('click', (event) => {
    if (event.target === byId('tx-detail-overlay')) closeTransactionDetail();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !byId('tx-detail-overlay').classList.contains('hidden')) {
      closeTransactionDetail();
    }
  });

  byId('ledger-filter-toggle').addEventListener('click', () => toggleLedgerFilters());

  if (sessionStorage.getItem('ledger-filters-open') === '1') {
    toggleLedgerFilters(true);
  }

  function saveTxEdits() {
    if (!state.selectedTx) return;
    const txId = state.selectedTx.transaction_id;
    const body = {};
    const fields = [
      ['tx-edit-date', 'created_at'],
      ['tx-edit-type', 'transaction_type'],
      ['tx-edit-buy', 'buy_amount'],
      ['tx-edit-buy-curr', 'buy_currency'],
      ['tx-edit-sell', 'sell_amount'],
      ['tx-edit-sell-curr', 'sell_currency'],
      ['tx-edit-fee', 'fee_amount'],
      ['tx-edit-fee-curr', 'fee_currency'],
      ['tx-edit-wallet', 'wallet_id'],
      ['tx-edit-group', 'group'],
      ['tx-edit-comment', 'comment'],
    ];
    const orig = state.selectedTx;
    const origMap = {
      created_at: orig.created_at || '',
      transaction_type: orig.transaction_type || '',
      buy_amount: orig.buy_amount,
      buy_currency: orig.buy_currency || '',
      sell_amount: orig.sell_amount,
      sell_currency: orig.sell_currency || '',
      fee_amount: orig.fee_amount,
      fee_currency: orig.fee_currency || '',
      wallet_id: orig.wallet_id || '',
      group: orig.group || '',
      comment: orig.comment || '',
    };
    for (const [elId, key] of fields) {
      const val = byId(elId).value;
      const isNumeric = ['buy_amount', 'sell_amount', 'fee_amount'].includes(key);
      const newVal = isNumeric ? (val !== '' ? Number(val) : null) : val;
      const origVal = origMap[key];
      if (isNumeric ? newVal !== origVal : val !== (origVal || '')) {
        body[key] = newVal;
      }
    }
    if (Object.keys(body).length === 0) {
      showTxStatus('No changes detected.');
      return;
    }
    (async () => {
      try {
        await api(`api/ledger/${txId}`, { method: 'PATCH', body: JSON.stringify(body) });
        showTxStatus('Transaction updated.');
        await loadLedger();
        await openTransactionDetail(txId);
      } catch (error) {
        showTxStatus(error.message, true);
      }
    })();
  }

  byId('tx-edit-form').addEventListener('submit', (event) => {
    event.preventDefault();
    saveTxEdits();
  });

  byId('tx-save-btn').addEventListener('click', () => saveTxEdits());

  byId('tx-delete-btn').addEventListener('click', async () => {
    if (!state.selectedTx) return;
    if (!confirm('Soft-delete this transaction? It can be restored later.')) return;
    const txId = state.selectedTx.transaction_id;
    try {
      await api(`api/ledger/${txId}`, { method: 'DELETE' });
      showTxStatus('Transaction deleted.');
      await loadLedger();
      await openTransactionDetail(txId);
    } catch (error) {
      showTxStatus(error.message, true);
    }
  });

  byId('tx-restore-btn').addEventListener('click', async () => {
    if (!state.selectedTx) return;
    const txId = state.selectedTx.transaction_id;
    try {
      await api(`api/ledger/${txId}/restore`, { method: 'POST' });
      showTxStatus('Transaction restored.');
      await loadLedger();
      await openTransactionDetail(txId);
    } catch (error) {
      showTxStatus(error.message, true);
    }
  });

  byId('ledger-clear').addEventListener('click', async () => {
    byId('ledger-coin').value = 'BTC';
    byId('ledger-wallet').value = '';
    byId('ledger-start').value = '';
    byId('ledger-end').value = '';
    byId('ledger-deleted-toggle').checked = false;
    state.ledgerFilters = { coin: 'BTC', wallet: '', startDate: '', endDate: '', includeDeleted: false, page: 1, perPage: 50 };
    await loadLedger();
  });

  byId('gains-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    state.gainsFilters = {
      taxYear: Number(byId('gains-year').value),
      coin: byId('gains-coin').value.trim() || 'BTC',
      wallet: byId('gains-wallet').value.trim(),
    };
    await loadGains();
    await loadHistory();
  });

  byId('forecast-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    state.forecastFilters = {
      coin: byId('forecast-coin').value.trim() || 'BTC',
      wallet: byId('forecast-wallet').value.trim(),
      quantity: Number(byId('forecast-quantity').value),
      salePriceUsd: Number(byId('forecast-price').value),
    };
    await loadForecast();
    await loadHistory();
  });

  byId('preset-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    await api('api/tax/presets', {
      method: 'POST',
      body: JSON.stringify(currentPresetPayload()),
    });
    byId('preset-name').value = '';
    await Promise.all([loadPresets(), loadHistory()]);
  });

  byId('export-1099b').addEventListener('click', () => downloadTaxArtifact('1099b/export'));
  byId('export-worksheet').addEventListener('click', () => downloadTaxArtifact('1099b/worksheet'));

  // --- Wallet Management ---

  byId('wallet-create-btn').addEventListener('click', () => {
    byId('wallet-form-mode').value = 'create';
    byId('wallet-form-original-id').value = '';
    byId('wallet-form-title').textContent = 'New Wallet';
    byId('wallet-form-submit').textContent = 'Create Wallet';
    byId('wallet-form-id').value = '';
    byId('wallet-form-id').removeAttribute('disabled');
    byId('wallet-form-type').value = 'exchange';
    byId('wallet-form-custody').value = 'self-custodied';
    byId('wallet-form-desc').value = '';
    byId('wallet-form-notes').value = '';
    byId('wallet-form-status').classList.add('hidden');
    byId('wallet-form-panel').classList.remove('hidden');
    byId('wallet-form-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });

  byId('wallet-form-close').addEventListener('click', () => {
    byId('wallet-form-panel').classList.add('hidden');
  });

  byId('wallet-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const mode = byId('wallet-form-mode').value;
    const statusEl = byId('wallet-form-status');
    try {
      if (mode === 'create') {
        await api('api/wallets', {
          method: 'POST',
          body: JSON.stringify({
            wallet_id: byId('wallet-form-id').value.trim(),
            wallet_type: byId('wallet-form-type').value,
            custody: byId('wallet-form-custody').value,
            description: byId('wallet-form-desc').value.trim() || null,
            notes: byId('wallet-form-notes').value.trim() || null,
          }),
        });
        statusEl.textContent = 'Wallet created.';
        statusEl.style.color = 'var(--ok)';
      } else {
        const walletId = byId('wallet-form-original-id').value;
        const orig = (state.walletsList || []).find((w) => w.wallet_id === walletId) || {};
        const body = {};
        const wt = byId('wallet-form-type').value;
        const cust = byId('wallet-form-custody').value;
        const desc = byId('wallet-form-desc').value.trim();
        const notes = byId('wallet-form-notes').value.trim();
        if (wt && wt !== orig.wallet_type) body.wallet_type = wt;
        if (cust && cust !== orig.custody) body.custody = cust;
        if (desc !== (orig.description || '')) body.description = desc || null;
        if (notes !== (orig.notes || '')) body.notes = notes || null;
        await api(`api/wallets/${encodeURIComponent(walletId)}`, {
          method: 'PATCH',
          body: JSON.stringify(body),
        });
        statusEl.textContent = 'Wallet updated.';
        statusEl.style.color = 'var(--ok)';
      }
      statusEl.classList.remove('hidden');
      await loadWalletsList();
    } catch (error) {
      statusEl.textContent = error.message;
      statusEl.style.color = 'var(--bad)';
      statusEl.classList.remove('hidden');
    }
  });

  byId('wallet-sync-btn').addEventListener('click', async () => {
    const statusEl = byId('wallets-status');
    try {
      const result = await api('api/wallets/sync', { method: 'POST' });
      statusEl.textContent = `Sync complete. ${result.created} wallet(s) created.`;
      statusEl.style.color = 'var(--ok)';
      statusEl.classList.remove('hidden');
      await loadWalletsList();
    } catch (error) {
      statusEl.textContent = error.message;
      statusEl.style.color = 'var(--bad)';
      statusEl.classList.remove('hidden');
    }
  });

  byId('wallets-active-toggle').addEventListener('change', () => loadWalletsList());

  byId('wallet-rename-close').addEventListener('click', () => {
    byId('wallet-rename-panel').classList.add('hidden');
  });

  byId('wallet-rename-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const oldId = byId('wallet-rename-old-id').value;
    const newId = byId('wallet-rename-new-id').value.trim();
    const statusEl = byId('wallet-rename-status');
    try {
      await api('api/wallets/rename', {
        method: 'POST',
        body: JSON.stringify({ wallet_id: oldId, new_wallet_id: newId }),
      });
      statusEl.textContent = `Renamed to "${newId}".`;
      statusEl.style.color = 'var(--ok)';
      statusEl.classList.remove('hidden');
      await loadWalletsList();
    } catch (error) {
      statusEl.textContent = error.message;
      statusEl.style.color = 'var(--bad)';
      statusEl.classList.remove('hidden');
    }
  });

  byId('wallet-merge-close').addEventListener('click', () => {
    byId('wallet-merge-panel').classList.add('hidden');
  });

  byId('wallet-merge-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const sourceId = byId('wallet-merge-source-id').value;
    const targetId = byId('wallet-merge-target').value;
    if (!confirm(`Merge "${sourceId}" into "${targetId}"? This cannot be undone.`)) return;
    const statusEl = byId('wallet-merge-status');
    try {
      await api('api/wallets/merge', {
        method: 'POST',
        body: JSON.stringify({ source_wallet_id: sourceId, target_wallet_id: targetId }),
      });
      statusEl.textContent = `Merged into "${targetId}".`;
      statusEl.style.color = 'var(--ok)';
      statusEl.classList.remove('hidden');
      await loadWalletsList();
    } catch (error) {
      statusEl.textContent = error.message;
      statusEl.style.color = 'var(--bad)';
      statusEl.classList.remove('hidden');
    }
  });
}

/* ── Import Center ──────────────────────────────────────── */

async function apiUpload(path, formData) {
  const url = new URL(path, new URL(appBase(), window.location.origin)).href;
  const response = await fetch(url, { method: 'POST', credentials: 'same-origin', body: formData });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try { const err = await response.json(); detail = err.detail || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}

async function loadImportPage() {
  showImportStep(1);
  await Promise.all([loadImportParsers(), loadImportWallets(), loadImportHistory()]);
}

async function loadImportParsers() {
  try {
    const data = await api('api/import/parsers');
    state.importState.parsers = data.parsers || [];
    const sel = byId('import-parser');
    sel.innerHTML = '<option value="">Auto-detect</option>';
    for (const p of state.importState.parsers) {
      const opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = `${p.display_name} (${p.source_type})`;
      sel.appendChild(opt);
    }
  } catch {}
}

async function loadImportWallets() {
  try {
    const data = await api('api/wallets');
    state.importState.wallets = (data.wallets || []).map(w => w.wallet_id);
    for (const selId of ['import-wallet-name', 'import-withdraw-to']) {
      const sel = byId(selId);
      const placeholder = sel.options[0];
      sel.innerHTML = '';
      sel.appendChild(placeholder);
      for (const id of state.importState.wallets) {
        const opt = document.createElement('option');
        opt.value = id;
        opt.textContent = id;
        sel.appendChild(opt);
      }
    }
  } catch {}
}

function showImportStep(step) {
  state.importState.step = step;
  byId('import-step-1').classList.toggle('hidden', step !== 1);
  byId('import-step-2').classList.toggle('hidden', step !== 2);
  byId('import-step-3').classList.toggle('hidden', step !== 3);
}

function updateImportWalletField() {
  const sel = byId('import-parser');
  const parser = state.importState.parsers.find(p => p.name === sel.value);
  const show = parser && parser.source_type === 'wallet';
  byId('import-wallet-field').style.display = show ? '' : 'none';
}

async function handleImportUpload(event) {
  event.preventDefault();
  const fileInput = byId('import-file');
  const statusEl = byId('import-status');
  if (!fileInput.files || !fileInput.files.length) {
    statusEl.textContent = 'Please select a file.';
    statusEl.style.color = 'var(--bad)';
    return;
  }
  statusEl.textContent = 'Uploading and parsing...';
  statusEl.style.color = 'var(--muted)';

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('parser', byId('import-parser').value);
  formData.append('wallet_name', byId('import-wallet-name').value);
  formData.append('withdraw_to', byId('import-withdraw-to').value);

  try {
    const data = await apiUpload('api/import/parse', formData);
    state.importState.preview = data;
    statusEl.textContent = '';
    renderImportPreview(data);
    // Auto-check duplicates
    await checkImportDuplicates(data.transactions);
    showImportStep(2);
  } catch (error) {
    statusEl.textContent = error.message;
    statusEl.style.color = 'var(--bad)';
  }
}

function renderImportPreview(data) {
  byId('import-preview-title').textContent = `Preview — ${data.display_name || data.parser_used}`;
  byId('import-preview-meta').textContent = `${data.row_count} transactions from ${escapeHtml(data.filename)}`;

  // Validation summary
  const v = data.validation;
  const valEl = byId('import-validation-summary');
  if (v.error_count > 0 || v.warning_count > 0) {
    let html = '<div class="import-validation">';
    if (v.error_count > 0) html += `<p class="text-danger">${v.error_count} error(s) found — these rows will be skipped.</p>`;
    if (v.warning_count > 0) html += `<p class="text-warning">${v.warning_count} warning(s) — review before importing.</p>`;
    html += '</div>';
    valEl.innerHTML = html;
  } else {
    valEl.innerHTML = '<p class="text-success">All rows valid.</p>';
  }

  // Preview table — show all transactions
  const tbody = byId('import-preview-table');
  const txs = data.transactions;
  if (!txs.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty-row">No transactions parsed.</td></tr>';
    return;
  }
  tbody.innerHTML = txs.map((tx, i) => {
    const buy = tx.buy ? ((tx.buy_curr || 'BTC') === 'BTC' ? denomFormat(tx.buy) : formatAmount(tx.buy, tx.buy_curr)) : '';
    const sell = tx.sell ? ((tx.sell_curr || 'BTC') === 'BTC' ? denomFormat(tx.sell) : formatAmount(tx.sell, tx.sell_curr)) : '';
    const fee = tx.fee ? ((tx.fee_curr || 'BTC') === 'BTC' ? denomFormat(tx.fee) : formatAmount(tx.fee, tx.fee_curr)) : '';
    return `<tr data-idx="${i}">
      <td><input type="checkbox" class="import-row-check" data-idx="${i}" checked></td>
      <td>${escapeHtml(tx.trans_type || '')}</td>
      <td>${escapeHtml((tx.created_date || '').slice(0, 16))}</td>
      <td>${buy}</td>
      <td>${sell}</td>
      <td>${fee}</td>
      <td>${escapeHtml(tx.exchange || '')}</td>
      <td>${escapeHtml(tx.comment || '')}</td>
    </tr>`;
  }).join('');
}

async function checkImportDuplicates(transactions) {
  try {
    const data = await api('api/import/check-duplicates', {
      method: 'POST',
      body: JSON.stringify({ transactions }),
    });
    state.importState.duplicateIndices = data.duplicate_indices || [];
    const banner = byId('import-duplicate-banner');
    if (data.duplicate_count > 0) {
      banner.innerHTML = `<div class="import-warning"><strong>${data.duplicate_count} potential duplicate(s)</strong> found in your ledger. Duplicates are unchecked by default — re-check to import anyway.</div>`;
      banner.classList.remove('hidden');
      // Uncheck duplicate rows
      for (const idx of data.duplicate_indices) {
        const row = byId('import-preview-table').querySelector(`tr[data-idx="${idx}"]`);
        if (row) {
          row.classList.add('import-duplicate-row');
          const cb = row.querySelector('.import-row-check');
          if (cb) cb.checked = false;
        }
      }
    } else {
      banner.classList.add('hidden');
    }
  } catch {}
}

async function handleImportCommit() {
  const btn = byId('import-commit-btn');
  btn.disabled = true;
  btn.textContent = 'Importing...';

  const preview = state.importState.preview;
  if (!preview) return;

  // Collect unchecked indices
  const checkboxes = byId('import-preview-table').querySelectorAll('.import-row-check');
  const skipIndices = [];
  checkboxes.forEach(cb => { if (!cb.checked) skipIndices.push(Number(cb.dataset.idx)); });

  try {
    const result = await api('api/import/commit', {
      method: 'POST',
      body: JSON.stringify({
        transactions: preview.transactions,
        parser_name: preview.parser_used,
        filename: preview.filename,
        skip_indices: skipIndices,
      }),
    });

    byId('import-result-banner').innerHTML = `
      <div class="import-success">
        <h3>Import Complete</h3>
        <p><strong>${result.imported}</strong> transactions imported, <strong>${result.skipped}</strong> skipped.</p>
        <p class="muted">Source: ${escapeHtml(result.parser_name)} — ${escapeHtml(result.filename)}</p>
      </div>`;
    showImportStep(3);
    loadImportHistory();
  } catch (error) {
    byId('import-result-banner').innerHTML = `<div class="import-error"><p>${escapeHtml(error.message)}</p></div>`;
    showImportStep(3);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Import Transactions';
  }
}

async function loadImportHistory() {
  try {
    const data = await api('api/import/history');
    const list = byId('import-history-list');
    const imports = data.imports || [];
    if (!imports.length) {
      list.innerHTML = '<p class="muted">No imports yet.</p>';
      return;
    }
    list.innerHTML = imports.map(entry => `
      <div class="history-entry">
        <div class="history-entry-heading">
          <span class="history-entry-title">${escapeHtml(entry.parser_name || 'unknown')} — ${escapeHtml(entry.filename || '')}</span>
          <span class="history-entry-date">${escapeHtml((entry.timestamp || '').slice(0, 16))}</span>
        </div>
        <p class="muted">${entry.imported} imported, ${entry.skipped} skipped</p>
      </div>`).join('');
  } catch {}
}

function resetImportForm() {
  state.importState.preview = null;
  state.importState.duplicateIndices = [];
  byId('import-file').value = '';
  byId('import-parser').value = '';
  byId('import-wallet-name').value = '';
  byId('import-withdraw-to').value = '';
  byId('import-status').textContent = '';
  byId('import-duplicate-banner').classList.add('hidden');
  updateImportWalletField();
  showImportStep(1);
}

function bindImportEvents() {
  byId('import-upload-form').addEventListener('submit', handleImportUpload);
  byId('import-parser').addEventListener('change', updateImportWalletField);
  byId('import-commit-btn').addEventListener('click', handleImportCommit);
  byId('import-back-btn').addEventListener('click', () => showImportStep(1));
  byId('import-another-btn').addEventListener('click', resetImportForm);
}

// ── Reports & Visualizations ──

function reportsUrl(path, range, bust) {
  const params = new URLSearchParams({ range });
  if (bust) {
    // Bypass both the browser cache (unique URL) and the service-side byte
    // cache (refresh flag) so a hard refresh re-renders from live data.
    params.set('refresh', 'true');
    params.set('t', String(Date.now()));
  }
  const rel = `api/reports/${path}?${params.toString()}`;
  return new URL(rel, new URL(appBase(), window.location.origin)).href;
}

function setReportImage(imgId, chart, range, bust, settle) {
  const img = byId(imgId);
  if (!img) {
    settle(false);
    return;
  }
  const frame = img.closest('.report-chart-frame');
  if (frame) frame.classList.remove('is-error', 'is-loaded');
  if (frame) frame.classList.add('is-loading');
  img.onload = () => {
    if (frame) {
      frame.classList.remove('is-loading', 'is-error');
      frame.classList.add('is-loaded');
    }
    settle(true);
  };
  img.onerror = () => {
    if (frame) {
      frame.classList.remove('is-loading', 'is-loaded');
      frame.classList.add('is-error');
    }
    settle(false);
  };
  img.src = reportsUrl(`chart/${chart}.png`, range, bust);
}

function loadReports(bust = false) {
  const rangeSeg = byId('reports-range');
  const range = state.reportsState.range || 'all';

  // Wire the range selector once.
  if (!state.reportsState.wired) {
    state.reportsState.wired = true;
    if (rangeSeg) {
      for (const btn of rangeSeg.querySelectorAll('button')) {
        btn.addEventListener('click', () => {
          if (state.reportsState.range === btn.dataset.value) return;
          state.reportsState.range = btn.dataset.value;
          loadReports(true);
        });
      }
    }
  }

  // Reflect active range in the selector.
  if (rangeSeg) {
    for (const btn of rangeSeg.querySelectorAll('button')) {
      btn.classList.toggle('active', btn.dataset.value === range);
    }
  }

  // Point the PDF download link at the current range.
  const pdfLink = byId('reports-pdf-link');
  if (pdfLink) {
    pdfLink.href = reportsUrl('report.pdf', range, bust);
    pdfLink.setAttribute('download', `btc_report_${new Date().toISOString().slice(0, 10)}.pdf`);
  }

  const status = byId('reports-status');
  if (status) status.textContent = 'Rendering charts…';

  const charts = [
    ['report-img-orange', 'orange'],
    ['report-img-balance', 'balance'],
    ['report-img-custody', 'custody'],
  ];
  let pending = charts.length;
  let anyError = false;
  const settle = (ok) => {
    pending -= 1;
    if (!ok) anyError = true;
    if (pending === 0 && byId('reports-status')) {
      byId('reports-status').textContent = anyError
        ? 'Some charts could not be rendered for this range (no data or price feed unavailable).'
        : '';
    }
  };

  for (const [imgId, chart] of charts) {
    setReportImage(imgId, chart, range, bust, settle);
  }
}

// ── Trades & Liquidity ──

async function loadTradesPage() {
  const view = state.tradesFilters.view;
  // Populate exchange filter from liquidity data (complete exchange list)
  populateTradesExchangeDropdown();
  if (view === 'liquidity') {
    await loadLiquidity();
  } else {
    await loadTrades();
  }
  updateTradesTabs();
}

async function populateTradesExchangeDropdown() {
  try {
    // Fetch the exchange list from the trades endpoint (includes all exchanges, not just buy-side)
    const data = await api('api/trades/exchanges');
    const select = byId('trades-exchange-filter');
    const current = state.tradesFilters.exchange;
    const opts = ['<option value="">All exchanges</option>'];
    for (const ex of data.exchanges) {
      opts.push(`<option value="${escapeHtml(ex)}"${ex === current ? ' selected' : ''}>${escapeHtml(ex)}</option>`);
    }
    select.innerHTML = opts.join('');
  } catch {}
}

function updateTradesTabs() {
  const view = state.tradesFilters.view;
  byId('trades-tab-history').classList.toggle('active', view === 'trades');
  byId('trades-tab-liquidity').classList.toggle('active', view === 'liquidity');
  byId('trades-history-panel').classList.toggle('hidden', view !== 'trades');
  byId('trades-liquidity-panel').classList.toggle('hidden', view !== 'liquidity');
}

async function loadTrades() {
  const f = state.tradesFilters;
  const params = new URLSearchParams({ page: String(f.page), per_page: String(f.perPage) });
  if (f.exchange) params.set('exchange', f.exchange);

  try {
    const data = await api(`api/trades?${params.toString()}`);
    renderTrades(data);
  } catch (error) {
    byId('trades-table').innerHTML = `<tr><td colspan="7" class="empty-row">${escapeHtml(error.message)}</td></tr>`;
  }
}

function renderTrades(data) {
  byId('trades-count').textContent = `Showing ${data.trades.length} of ${data.total} trades (page ${data.page})`;

  if (!data.trades.length) {
    byId('trades-table').innerHTML = '<tr><td colspan="7" class="empty-row">No trades match the current filters.</td></tr>';
    byId('trades-cards').innerHTML = '';
  } else {
    byId('trades-table').innerHTML = data.trades.map((t) => `
      <tr>
        <td>${escapeHtml(t.date)}</td>
        <td>${escapeHtml(t.trade_type)}</td>
        <td>${denomFormat(t.quantity)}</td>
        <td>${escapeHtml(t.trade_currency)}</td>
        <td>${t.unit_cost_usd != null ? currency(t.unit_cost_usd) : '-'}</td>
        <td>${t.total_cost_usd != null ? currency(t.total_cost_usd) : '-'}</td>
        <td>${escapeHtml(t.exchange || '')}</td>
      </tr>
    `).join('');

    byId('trades-cards').innerHTML = data.trades.map((t) => {
      var ex = t.exchange || '?';
      var glyph = ex.length <= 2 ? ex.toUpperCase() : ex.charAt(0).toUpperCase();
      var typeClass = (t.trade_type || '').toLowerCase() === 'sell' ? 'sell' : '';
      var tag = escapeHtml((t.trade_type || '').toUpperCase());
      var unitCost = t.unit_cost_usd != null ? `@ ${currency(t.unit_cost_usd)}/${denomUnit()}` : '';
      var datePart = (t.date || '').slice(0, 10);
      var sub = [datePart, unitCost].filter(Boolean).join(' · ');
      var qty = denomFormat(t.quantity);
      var total = t.total_cost_usd != null ? currency(t.total_cost_usd) : '';
      return `<div class="trade-card">
        <div class="tc-glyph">${escapeHtml(glyph)}</div>
        <div class="tc-main">
          <div class="tc-title">
            <span>${escapeHtml(ex)}</span>
            <span class="tc-tag ${typeClass}">${tag}</span>
          </div>
          <div class="tc-sub">${escapeHtml(sub)}</div>
        </div>
        <div class="tc-amount">
          <span class="tc-qty">${qty}</span>
          ${total ? `<span class="tc-cost">${total}</span>` : ''}
        </div>
      </div>`;
    }).join('');
  }

  // Pagination
  const totalPages = Math.ceil(data.total / data.per_page);
  if (totalPages <= 1) {
    byId('trades-pagination').innerHTML = '';
  } else {
    const buttons = [];
    if (data.page > 1) buttons.push(`<button class="button button-ghost" data-trades-page="${data.page - 1}">Prev</button>`);
    buttons.push(`<span class="list-item-meta">Page ${data.page} of ${totalPages}</span>`);
    if (data.page < totalPages) buttons.push(`<button class="button button-ghost" data-trades-page="${data.page + 1}">Next</button>`);
    byId('trades-pagination').innerHTML = buttons.join(' ');

    for (const btn of byId('trades-pagination').querySelectorAll('[data-trades-page]')) {
      btn.addEventListener('click', () => {
        state.tradesFilters.page = Number(btn.dataset.tradesPage);
        loadTrades();
      });
    }
  }

}

async function loadLiquidity() {
  try {
    const data = await api('api/trades/liquidity');
    renderLiquidity(data);
  } catch (error) {
    byId('liquidity-table').innerHTML = `<tr><td colspan="4" class="empty-row">${escapeHtml(error.message)}</td></tr>`;
    renderDataCards('liquidity-cards', [], error.message);
  }
}

function renderLiquidity(data) {
  const exchanges = data.exchanges;
  byId('liquidity-count').textContent = `Showing ${exchanges.length} exchanges with purchase history`;

  if (!exchanges.length) {
    byId('liquidity-table').innerHTML = '<tr><td colspan="4" class="empty-row">No exchange liquidity data found.</td></tr>';
  } else {
    byId('liquidity-table').innerHTML = exchanges.map((e) => `
      <tr>
        <td>${escapeHtml(e.exchange)}</td>
        <td>${denomFormat(e.total_purchased)}</td>
        <td>${denomFormat(e.current_balance)}</td>
        <td>${e.avg_cost_usd != null ? currency(e.avg_cost_usd) : '-'}</td>
      </tr>
    `).join('');
  }
  renderDataCards('liquidity-cards', exchanges.map((e) => dataCard(
    e.exchange,
    'Exchange liquidity',
    [
      ['Purchased', denomFormat(e.total_purchased)],
      ['Current balance', denomFormat(e.current_balance)],
      ['Average cost', e.avg_cost_usd != null ? currency(e.avg_cost_usd) : '-'],
    ],
  )), 'No exchange liquidity data found.');

  // Summary cards
  const s = data.summary;
  byId('liq-total-purchased').textContent = denomFormat(s.total_purchased);
  byId('liq-total-usd').textContent = currency(s.total_usd_spent);
  byId('liq-avg-cost').textContent = s.avg_cost_basis_usd != null ? `${currency(s.avg_cost_basis_usd)} / ${denomUnit()}` : '-';
  byId('liq-at-exchanges').textContent = denomFormat(s.still_at_exchanges);
  byId('liq-cold-storage').textContent = denomFormat(s.in_cold_storage);
  byId('liq-total-holdings').textContent = denomFormat(s.total_holdings);

}

function bindTradesEvents() {
  byId('trades-tab-history').addEventListener('click', () => {
    state.tradesFilters.view = 'trades';
    updateTradesTabs();
    loadTrades();
  });
  byId('trades-tab-liquidity').addEventListener('click', () => {
    state.tradesFilters.view = 'liquidity';
    updateTradesTabs();
    loadLiquidity();
  });
  byId('trades-filter-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    state.tradesFilters.exchange = byId('trades-exchange-filter').value;
    state.tradesFilters.page = 1;
    await loadTrades();
  });
  byId('trades-clear').addEventListener('click', async () => {
    byId('trades-exchange-filter').value = '';
    state.tradesFilters.exchange = '';
    state.tradesFilters.page = 1;
    await loadTrades();
  });
}

bindTradesEvents();
bindImportEvents();

state.currentPage = currentRouteFromLocation();
bindEvents();
renderPageState();
refreshSession();

window.addEventListener('btc:denom-change', function () {
  var page = state.currentPage;
  if (page === 'dashboard' && state.dashboard) renderDashboard(state.dashboard);
  if (page === 'ledger') loadLedger();
  if (page === 'wallet' && state.currentWalletId) loadWalletDetail(state.currentWalletId);
  if (page === 'wallets') renderWalletsList(state.walletsList);
  if (page === 'trades') loadTradesPage();
  if (page === 'tax') { loadGains(); loadForecast(); }
  if (page === 'settings') initSettingsPage();
});

window.addEventListener('btc:privacy-change', function () {
  var page = state.currentPage;
  if (page === 'dashboard' && state.dashboard) renderDashboard(state.dashboard);
  if (page === 'ledger') loadLedger();
  if (page === 'wallet' && state.currentWalletId) loadWalletDetail(state.currentWalletId);
  if (page === 'wallets') renderWalletsList(state.walletsList);
  if (page === 'trades') loadTradesPage();
  if (page === 'tax') { loadGains(); loadForecast(); }
  if (page === 'settings') initSettingsPage();
});
