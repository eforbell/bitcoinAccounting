const state = {
  session: null,
  policy: null,
  dashboard: null,
  walletDetail: null,
  currentPage: 'dashboard',
  currentWalletId: null,
  includeInactive: false,
  gainsFilters: { taxYear: 2024, coin: 'BTC', wallet: '' },
  forecastFilters: { coin: 'BTC', wallet: '', quantity: 0.1, salePriceUsd: 100000 },
};

function byId(id) {
  return document.getElementById(id);
}

function currency(value) {
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

function appBase() {
  const base = document.querySelector('base');
  if (base) return new URL(base.getAttribute('href'), window.location.origin).pathname;
  const path = window.location.pathname;
  const taxIdx = path.indexOf('/tax');
  if (taxIdx !== -1) return path.slice(0, taxIdx + 1);
  const walletIdx = path.indexOf('/wallet/');
  if (walletIdx !== -1) return path.slice(0, walletIdx + 1);
  return path.endsWith('/') ? path : path + '/';
}

function appPath(page) {
  const base = appBase();
  if (page === 'tax') return `${base}tax`;
  if (page === 'wallet' && state.currentWalletId) return `${base}wallet/${encodeURIComponent(state.currentWalletId)}`;
  return base;
}

function currentRouteFromLocation() {
  const path = window.location.pathname.replace(/\/+$/, '');
  if (path.endsWith('/tax')) return 'tax';
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
  status.style.color = isError ? 'var(--danger)' : 'var(--text-muted)';
}

function setSessionGlyph(authenticated) {
  byId('session-glyph').textContent = authenticated ? '↗' : '⌁';
}

function showLoggedOut() {
  byId('login-panel').classList.remove('hidden');
  byId('dashboard-view').classList.add('hidden');
  byId('tax-view').classList.add('hidden');
  byId('wallet-view').classList.add('hidden');
  byId('operator-chip').textContent = 'operator';
  setSessionGlyph(false);
}

function showLoggedIn(username) {
  byId('login-panel').classList.add('hidden');
  byId('operator-chip').textContent = username;
  setSessionGlyph(true);
  renderPageState();
}

function renderPageState() {
  document.body.classList.add('app-has-nav');
  const page = state.currentPage;
  const titles = { dashboard: 'Dashboard', tax: 'Tax', wallet: 'Wallet' };
  document.title = `Bitcoin Accounting | ${titles[page] || 'Dashboard'}`;
  byId('dashboard-view').classList.toggle('hidden', !state.session || page !== 'dashboard');
  byId('tax-view').classList.toggle('hidden', !state.session || page !== 'tax');
  byId('wallet-view').classList.toggle('hidden', !state.session || page !== 'wallet');

  const navRoute = page === 'wallet' ? 'dashboard' : page;
  for (const item of document.querySelectorAll('[data-route]')) {
    item.classList.toggle('active', item.dataset.route === navRoute);
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

function renderDashboard(dashboard) {
  state.dashboard = dashboard;
  byId('dashboard-balance').textContent = `${Number(dashboard.summary.total_balance).toFixed(8)} ${dashboard.summary.coin}`;
  byId('dashboard-basis').textContent = dashboard.summary.average_cost_basis_usd == null
    ? 'Unpriced'
    : currency(dashboard.summary.average_cost_basis_usd);
  byId('dashboard-active-wallets').textContent = String(dashboard.summary.active_wallet_count);
  byId('dashboard-recent-count').textContent = `${dashboard.recent_transactions.length} tx`;
  byId('hero-wallet-count').textContent = `${dashboard.summary.active_wallet_count} / ${dashboard.summary.wallet_count}`;

  const warning = byId('custody-warning');
  if (dashboard.using_inferred_custody) {
    warning.textContent = 'Custody mix is partially inferred from wallet names because explicit wallet metadata is incomplete.';
    warning.classList.remove('hidden');
  } else {
    warning.classList.add('hidden');
  }

  byId('custody-list').innerHTML = dashboard.custody_breakdown.length
    ? dashboard.custody_breakdown.map((row) => `
        <div class="custody-row">
          <div>
            <strong>${escapeHtml(row.custody)}</strong>
            <div class="list-item-meta">${row.percentage.toFixed(1)}% of stack</div>
          </div>
          <div class="wallet-balance">${Number(row.balance).toFixed(8)} BTC</div>
        </div>
      `).join('')
    : '<div class="custody-row"><div class="list-item-meta">No custody data yet.</div></div>';

  byId('wallet-list').innerHTML = dashboard.wallets.length
    ? dashboard.wallets.map((wallet) => `
        <a class="list-item list-item-link" href="${appBase()}wallet/${encodeURIComponent(wallet.wallet_id)}" data-wallet-id="${escapeHtml(wallet.wallet_id)}">
          <div class="wallet-main">
            <div class="wallet-title">${escapeHtml(wallet.wallet_id)}</div>
            <div class="tx-detail">
              <span class="wallet-badge">${escapeHtml(wallet.custody)}</span>
              <span>${escapeHtml(wallet.wallet_type)}</span>
              ${wallet.description ? `<span>${escapeHtml(wallet.description)}</span>` : ''}
              ${wallet.active ? '' : '<span>inactive</span>'}
            </div>
          </div>
          <div class="wallet-balance-wrap">
            <div class="wallet-balance">${Number(wallet.balance).toFixed(8)} BTC</div>
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

async function loadDashboard() {
  const params = new URLSearchParams({
    coin: 'BTC',
    include_inactive: state.includeInactive ? 'true' : 'false',
    recent_limit: '5',
  });
  const dashboard = await api(`api/portfolio/dashboard?${params.toString()}`);
  renderDashboard(dashboard);
}

function renderTransactionRows(transactions) {
  if (!transactions.length) {
    return '<div class="tx-row"><div class="list-item-meta">No transactions yet.</div></div>';
  }
  return transactions.map((tx) => {
    const direction = tx.buy_currency === 'BTC'
      ? `${Number(tx.buy_amount || 0).toFixed(8)} BTC`
      : `${Number(tx.sell_amount || 0).toFixed(8)} BTC`;
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
    byId('wallet-view-balance').textContent = `${Number(w.balance).toFixed(8)} BTC`;
    byId('wallet-view-pct').textContent = `${w.percentage.toFixed(1)}% of stack`;
    byId('wallet-view-type').textContent = w.wallet_type;
    byId('wallet-view-status').textContent = w.active ? 'Active' : 'Inactive';
    byId('wallet-view-tx-count').textContent = String(detail.recent_transactions.length);
    byId('wallet-view-pct-card').textContent = `${w.percentage.toFixed(1)}%`;

    byId('wallet-tx-list').innerHTML = renderTransactionRows(detail.recent_transactions);
  } catch (error) {
    byId('wallet-tx-list').innerHTML = `<div class="tx-row"><div class="list-item-meta">${escapeHtml(error.message)}</div></div>`;
  }
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
            <td>${Number(row.lot_quantity).toFixed(8)}</td>
            <td>${escapeHtml(row.acquire_date)}</td>
            <td>${escapeHtml(row.term)}</td>
            <td>${currency(row.gain_loss_usd)}</td>
          </tr>
        `).join('')
      : '<tr><td colspan="5" class="empty-row">No gains found for the selected filters.</td></tr>';
    byId('gains-table').innerHTML = rows;

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
    byId('forecast-balance').textContent = `${Number(forecast.current_balance).toFixed(8)} ${forecast.summary.coin}`;
    byId('forecast-proceeds').textContent = currency(forecast.summary.total_proceeds_usd);
    byId('forecast-cost').textContent = currency(forecast.summary.total_cost_basis_usd);
    byId('forecast-missing').textContent = Number(forecast.summary.missing_basis_quantity).toFixed(8);
    renderWarnings('forecast-warnings', forecast.warnings);

    const rows = forecast.lots.length
      ? forecast.lots.map((lot) => `
          <tr>
            <td>${escapeHtml(lot.acquire_date || 'UNKNOWN')}</td>
            <td>${Number(lot.quantity).toFixed(8)}</td>
            <td>${currency(lot.unit_cost_usd)}</td>
            <td>${escapeHtml(lot.term)}</td>
            <td>${currency(lot.cost_basis_usd)}</td>
          </tr>
        `).join('')
      : '<tr><td colspan="5" class="empty-row">No forecast lots available.</td></tr>';
    byId('forecast-table').innerHTML = rows;
  } catch (error) {
    byId('forecast-table').innerHTML = `<tr><td colspan="5" class="empty-row">${escapeHtml(error.message)}</td></tr>`;
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

async function refreshSession() {
  try {
    const session = await api('api/auth/me');
    state.session = session;
    showLoggedIn(session.username);
    const loaders = [loadDashboard(), loadPolicy(), loadGains(), loadHistory(), loadPresets(), loadForecast()];
    if (state.currentPage === 'wallet' && state.currentWalletId) {
      loaders.push(loadWalletDetail(state.currentWalletId));
    }
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
    });
  }

  window.addEventListener('popstate', () => {
    const previousWalletId = state.currentWalletId;
    state.currentPage = currentRouteFromLocation();
    renderPageState();
    if (state.currentPage === 'wallet' && state.currentWalletId && state.currentWalletId !== previousWalletId) {
      loadWalletDetail(state.currentWalletId);
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
      const postLogin = [loadDashboard(), loadPolicy(), loadGains(), loadHistory(), loadPresets(), loadForecast()];
      if (state.currentPage === 'wallet' && state.currentWalletId) {
        postLogin.push(loadWalletDetail(state.currentWalletId));
      }
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

  byId('inactive-toggle').addEventListener('change', async (event) => {
    state.includeInactive = event.target.checked;
    await loadDashboard();
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
}

state.currentPage = currentRouteFromLocation();
bindEvents();
renderPageState();
refreshSession();
