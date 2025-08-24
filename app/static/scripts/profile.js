// static/scripts/profile.js
// ------------------------------------------------------------------
// Fetch /auth/me for { id, login, role }, gate routes accordingly,
// and keep your original metrics behavior intact.
// ------------------------------------------------------------------

// Endpoints
const PROM_PROXY = '/metrics';
const APP_JSON = '/metrics_json';
const SNAPSHOTS_ENDPOINT = '/vm/get_user_snapshots';
const RUN_VM_ENDPOINT = '/vm/run-script'
const AUTH_ME = '/auth/me';
const AUTH_LOGOUT = '/auth/logout';
const logoutBtn = document.getElementById('logout-btn');

logoutBtn?.addEventListener('click', async () => {
  try {
    logoutBtn.disabled = true;
    const res = await fetch(AUTH_LOGOUT, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    });
    // Regardless of response, bounce the user to your main page
    window.location.href = 'http://5.101.67.252:8000/';
  } catch (e) {
    // Network hiccup — still try to navigate away
    window.location.href = 'http://5.101.67.252:8000/';
  } finally {
    logoutBtn.disabled = false;
  }
});


// DOM refs
const modal = document.getElementById('metrics-modal');
const openBtn = document.getElementById('metric-card');
const closeBtn = document.getElementById('metrics-close');

const tabGrafana  = document.getElementById('tab-grafana');
const tabProm     = document.getElementById('tab-prom');
const tabApp      = document.getElementById('tab-app');
const paneGrafana = document.getElementById('pane-grafana');
const paneProm    = document.getElementById('pane-prom');
const paneApp     = document.getElementById('pane-app');

const appRefresh  = document.getElementById('app-refresh');
const appStatus   = document.getElementById('app-status');
const appResults  = document.getElementById('app-results');

const promForm    = document.getElementById('prom-form');
const promQuery   = document.getElementById('prom-query');
const promStatus  = document.getElementById('prom-status');
const promResults = document.getElementById('prom-results');

const snapshotsRefresh = document.getElementById('snapshots-refresh');
const snapshotsStatus  = document.getElementById('snapshots-status');
const snapshotsResults = document.getElementById('snapshots-results');

const usernameEl = document.getElementById('ui-username');
const overviewLink = document.querySelector('[data-route="overview"]');

const ROUTES = ['overview','payments','snapshots'];
const SECTIONS = Object.fromEntries(ROUTES.map(r => [r, document.getElementById(`route-${r}`)]));
const NAV_LINKS = Array.from(document.querySelectorAll('#sidebar-nav .nav-link'));

let CURRENT_USER = { login: 'user', role: 'user' };

// --- Helpers ---
// Add near the top (helpers):
function extractActiveVms(families, currentUserId) {
  // 1) Prefer global total: vmshare_active_sessions
  const sess = families.find(f => f.name === 'vmshare_active_sessions');
  if (sess && Array.isArray(sess.samples)) {
    const s = sess.samples.find(s => s.name === 'vmshare_active_sessions');
    if (s && typeof s.value === 'number') return s.value;
  }

  // 2) Fallback: sum per-user series
  const per = families.find(f => f.name === 'vmshare_user_active_vms');
  if (per && Array.isArray(per.samples)) {
    // If you ever want per-admin total, we sum all users.
    // If you want per-current-user instead, filter by labels.user_id === currentUserId.
    let total = 0;
    for (const s of per.samples) {
      if (typeof s.value === 'number') total += s.value;
    }
    return total;
  }
  return null;
}

function setActiveRouteStyles(route) {
  NAV_LINKS.forEach(a => {
    const isActive = a.dataset.route === route;
    a.classList.toggle('bg-white/10', isActive);
    a.classList.toggle('ring-1', isActive);
    a.classList.toggle('ring-white/10', isActive);
  });
}

function showRoute(route) {
  // Gate Overview for non-admins
  if (route === 'overview' && CURRENT_USER.role !== 'admin') {
    route = 'payments';
    if (location.hash !== '#payments') history.replaceState(null, '', '#payments');
  }

  ROUTES.forEach(r => {
    const el = SECTIONS[r];
    if (!el) return;
    if (r === route) { el.classList.remove('hidden'); el.classList.add('block'); }
    else { el.classList.add('hidden'); el.classList.remove('block'); }
  });

  setActiveRouteStyles(route);

  // Load data per route
  if (route === 'snapshots') fetchSnapshots();
  if (route === 'overview') fetchAppMetrics(); // keep metrics fresh
}

function initialRoute() {
  const hash = (location.hash || '').replace('#','');
  let target = ROUTES.includes(hash) ? hash : 'overview';
  if (target === 'overview' && CURRENT_USER.role !== 'admin') target = 'payments';

  // Show/hide Overview link based on role
  if (overviewLink) overviewLink.style.display = (CURRENT_USER.role === 'admin') ? '' : 'none';

  showRoute(target);
}

window.addEventListener('hashchange', () => {
  const hash = (location.hash || '').replace('#','');
  showRoute(ROUTES.includes(hash) ? hash : 'overview');
});

// --- Auth: get role + username from /auth/me ---
async function fetchMe() {
  try {
    const res = await fetch(AUTH_ME, { credentials: 'same-origin' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { login, role } = await res.json();
    CURRENT_USER = { login: login || 'user', role: role || 'user' };
  } catch {
    // default to restricted user if anything fails
    CURRENT_USER = { login: 'user', role: 'user' };
  }
  // Update UI
  if (usernameEl) usernameEl.textContent = CURRENT_USER.login;
}

// --- Metrics modal controls (unchanged behavior) ---
const openModal  = () => { modal?.classList.remove('hidden'); modal?.classList.add('flex'); };
const closeModal = () => { modal?.classList.add('hidden');   modal?.classList.remove('flex'); };
openBtn?.addEventListener('click', openModal);
closeBtn?.addEventListener('click', closeModal);
modal?.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal?.classList.contains('hidden')) closeModal(); });

// --- Tabs ---
function activate(tab) {
  const on  = (el) => el?.classList.add('bg-white/10');
  const off = (el) => el?.classList.remove('bg-white/10');
  const show = (el) => { el?.classList.remove('hidden'); el?.classList.add('block'); };
  const hide = (el) => { el?.classList.add('hidden'); el?.classList.remove('block'); };

  [tabGrafana, tabProm, tabApp].forEach(off);
  [paneGrafana, paneProm, paneApp].forEach(hide);

  if (tab === 'grafana') { on(tabGrafana); show(paneGrafana); }
  else if (tab === 'prom') { on(tabProm); show(paneProm); }
  else { on(tabApp); show(paneApp); }
}
tabGrafana?.addEventListener('click', () => activate('grafana'));
tabProm?.addEventListener('click', () => activate('prom'));
tabApp?.addEventListener('click', () => { activate('app'); fetchAppMetrics(); });
activate('app'); // default tab
// --- Grafana integration ---
const GRAFANA_PROXY = '/grafana/panel.png';

// Define which panels to show (dashboard UID + panel IDs)
const GRAFANA_PANELS = [
  { uid: '051610f9-e0cf-4fbe-ab97-1ac1644e02a5', panelId: 4,  title: 'Request rate (rps, 1m)' },
  { uid: '051610f9-e0cf-4fbe-ab97-1ac1644e02a5', panelId: 2,  title: 'User-count' },
  { uid: '051610f9-e0cf-4fbe-ab97-1ac1644e02a5', panelId: 1, title: 'Active-sessions(3h)' },
];

// Default time range for PNG renders
let grafanaRange = { from: 'now-1h', to: 'now' };
let grafanaTimer = null;

function clearGrafanaTimer() { if (grafanaTimer) { clearInterval(grafanaTimer); grafanaTimer = null; } }

async function loadGrafanaPanels() {
  if (!paneGrafana) return;
  clearGrafanaTimer();

  paneGrafana.innerHTML = '';
  const grid = document.createElement('div');
  grid.className = 'grid grid-cols-1 gap-4';
  paneGrafana.appendChild(grid);

  const makeCard = (title, src) => {
    const card = document.createElement('div');
    card.className = 'bg-white/5 rounded-xl p-3 shadow';
    card.innerHTML = `
      <div class="flex items-center justify-between mb-2">
        <h4 class="font-medium">${title}</h4>
        <span class="text-xs text-neutral-300">${grafanaRange.from} → ${grafanaRange.to}</span>
      </div>
      <img class="w-full rounded-md" loading="lazy" alt="${title}" />
    `;
    card.querySelector('img').src = src;
    return card;
  };

  const urlFor = ({ uid, panelId }) =>
    `${GRAFANA_PROXY}?uid=${encodeURIComponent(uid)}&panelId=${panelId}` +
    `&from=${encodeURIComponent(grafanaRange.from)}&to=${encodeURIComponent(grafanaRange.to)}` +
    `&theme=dark&width=1100&height=300&_=${Date.now()}`; // cache-bust

  // initial render
  GRAFANA_PANELS.forEach(p => grid.appendChild(makeCard(p.title, urlFor(p))));

  // auto-refresh every 20s
  grafanaTimer = setInterval(() => {
    [...grid.querySelectorAll('img')].forEach((img, i) => {
      img.src = urlFor(GRAFANA_PANELS[i]);
    });
  }, 20000);
}

// kill auto-refresh when modal closes or tab changes
modal?.addEventListener('click', (e) => { if (e.target === modal) { clearGrafanaTimer(); } });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') clearGrafanaTimer(); });
tabGrafana?.addEventListener('click', () => { activate('grafana'); loadGrafanaPanels(); });


// --- App Metrics (no Prometheus needed) ---
function makeAppTable(families) {
  const table = document.createElement('table');
  table.className = 'w-full text-sm';
  table.innerHTML = `
    <thead>
      <tr class="bg-white/5">
        <th class="text-left px-3 py-2">Family</th>
        <th class="text-left px-3 py-2">Type</th>
        <th class="text-left px-3 py-2">Sample</th>
        <th class="text-left px-3 py-2">Labels</th>
        <th class="text-left px-3 py-2">Value</th>
        <th class="text-left px-3 py-2">Timestamp</th>
      </tr>
    </thead>
    <tbody></tbody>`;
  const tbody = table.querySelector('tbody');
  families.forEach(f => {
    (f.samples || []).forEach(s => {
      const labels = Object.entries(s.labels || {}).map(([k, v]) => `${k}="${v}"`).join(', ');
      const tr = document.createElement('tr');
      tr.className = 'odd:bg-white/0 even:bg-white/5';
      tr.innerHTML = `
        <td class="px-3 py-2 whitespace-nowrap">${f.name}</td>
        <td class="px-3 py-2">${f.type}</td>
        <td class="px-3 py-2 whitespace-nowrap">${s.name}</td>
        <td class="px-3 py-2 text-neutral-300">${labels}</td>
        <td class="px-3 py-2">${s.value}</td>
        <td class="px-3 py-2">${s.timestamp ? new Date(s.timestamp * 1000).toLocaleString() : ''}</td>`;
      tbody.appendChild(tr);
    });
  });
  return table;
}

async function fetchAppMetrics() {
  if(!appStatus || !appResults) return;
  appStatus.textContent = 'Fetching…';
  appResults.innerHTML = '';
  try {
    const res = await fetch(APP_JSON, { credentials: 'same-origin' });
    const data = await res.json();
    if (data.status !== 'success') throw new Error('Unexpected response');
    const families = data.data || [];

    // NEW: update the KPI number
    const active = extractActiveVms(families, CURRENT_USER?.id);
    const kpi = document.getElementById('active-vms');
    if (kpi) kpi.textContent = (active ?? 0).toString();

    // existing table render
    appStatus.textContent = `${families.length} metric families`;
    appResults.appendChild(makeAppTable(families));
  } catch (err) {
    appStatus.textContent = `Request failed: ${err.message}`;
    const kpi = document.getElementById('active-vms');
    if (kpi) kpi.textContent = '0';
  }
}

appRefresh?.addEventListener('click', fetchAppMetrics);

// --- Prometheus (unchanged) ---
function makePromTable(result) {
  const table = document.createElement('table');
  table.className = 'w-full text-sm';
  table.innerHTML = `
    <thead>
      <tr class="bg-white/5">
        <th class="text-left px-3 py-2">Metric</th>
        <th class="text-left px-3 py-2">Labels</th>
        <th class="text-left px-3 py-2">Value</th>
        <th class="text-left px-3 py-2">Timestamp</th>
      </tr>
    </thead>
    <tbody></tbody>`;
  const tbody = table.querySelector('tbody');
  result.forEach(row => {
    const { metric, value } = row;
    const [ts, val] = value || [null, null];
    const name = metric.__name__ || '(no name)';
    const labels = Object.entries(metric)
      .filter(([k]) => k !== '__name__')
      .map(([k, v]) => `${k}="${v}"`).join(', ');
    const tr = document.createElement('tr');
    tr.className = 'odd:bg-white/0 even:bg-white/5';
    tr.innerHTML = `
      <td class="px-3 py-2 whitespace-nowrap">${name}</td>
      <td class="px-3 py-2 text-neutral-300">${labels}</td>
      <td class="px-3 py-2">${val}</td>
      <td class="px-3 py-2">${ts ? new Date(ts * 1000).toLocaleString() : ''}</td>`;
    tbody.appendChild(tr);
  });
  return table;
}
promForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = promQuery.value.trim();
  if (!q) return;
  promStatus.textContent = 'Running…';
  promResults.innerHTML = '';
  try {
    const url = `${PROM_PROXY}?query=${encodeURIComponent(q)}`;
    const res = await fetch(url, { credentials: 'same-origin' });
    const ct = res.headers.get('content-type') || '';
    const text = await res.text();
    if (!ct.includes('application/json')) {
      throw new Error('Proxy did not return JSON. First bytes: ' + text.slice(0, 60));
    }
    const data = JSON.parse(text);
    if (data.status !== 'success') { promStatus.textContent = `Error: ${data.error || 'query failed'}`; return; }
    const result = data.data?.result || [];
    promStatus.textContent = `${result.length} series`;
    promResults.appendChild(makePromTable(result));
  } catch (err) {
    promStatus.textContent = `Request failed: ${err.message}`;
  }
});

// --- Snapshots ---
const uiToast  = (msg, lvl = 'ok')  => (window.toast ? window.toast(msg, lvl) : console.log(`[toast:${lvl}] ${msg}`));
const uiStatus = (txt, lvl = 'info') => (window.setStatus ? window.setStatus(txt, lvl) : console.log(`[status:${lvl}] ${txt}`));

// Helper: extract os_type (2nd segment) from "{user}__{os_type}__{vmid}[.ext]"
function extractOsTypeFromSnapshotId(id) {
  if (!id) return 'unknown';
  const base = String(id).split(/[\\/]/).pop();
  const parts = base.split('__');
  return (parts.length >= 3 && parts[1]) ? parts[1] : 'unknown';
}

async function runSnapshot(s, btn) {
  if (btn) { btn.disabled = true; btn.textContent = 'Running…'; }
  try {
    const snapshotId = s.name || s.id || s.path || s.file;
    if (!snapshotId) throw new Error('No snapshot identifier');

    const osType = extractOsTypeFromSnapshotId(snapshotId);

    const res = await fetch(RUN_VM_ENDPOINT, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ os_type: osType, snapshot: snapshotId })
    });

    let redirectUrl = null;
    let msg = res.ok ? 'VM starting…' : 'Failed to start VM';

    try {
      const ct = res.headers.get('content-type') || '';
      if (ct.includes('application/json')) {
        const data = await res.json();
        if (data?.redirect) redirectUrl = data.redirect;
        const id = data.id || data.name || data.snapshot || '';
        if (res.ok && id && !redirectUrl) msg = `VM starting from ${id}…`;
      } else {
        redirectUrl = res.headers.get('Location');
        if (!redirectUrl) {
          const text = (await res.text()).trim();
          const m = text.match(/https?:\/\/\S+/);
          if (m) redirectUrl = m[0];
          if (text && !redirectUrl) msg = text;
        }
      }
    } catch {}

    if (res.ok && redirectUrl) {
      uiToast('Opening console…', 'ok');
      window.location.assign(redirectUrl);
      return;
    }

    uiToast(msg, res.ok ? 'ok' : 'err');
    uiStatus(res.ok ? 'Starting…' : 'Error', res.ok ? 'ok' : 'err');

  } catch (e) {
    uiToast(e.message || 'Start failed', 'err');
    uiStatus('Error', 'err');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Run'; }
  }
}

function renderSnapshots(list) {
  const table = document.createElement('table');
  table.className = 'w-full text-sm';
  table.innerHTML = `
    <thead>
      <tr class="bg-white/5">
        <th class="text-left px-3 py-2">Name</th>
        <th class="text-left px-3 py-2">VM</th>
        <th class="text-left px-3 py-2">Size</th>
        <th class="text-left px-3 py-2">Created</th>
        <th class="text-left px-3 py-2">Notes</th>
        <th class="text-left px-3 py-2">Run</th>
      </tr>
    </thead>
    <tbody></tbody>`;
  const tbody = table.querySelector('tbody');

  if (!list || !list.length) {
    const tr = document.createElement('tr');
    tr.className = 'odd:bg-white/0 even:bg-white/5';
    tr.innerHTML = `<td colspan="6" class="px-3 py-6 text-center text-neutral-400">No snapshots yet.</td>`;
    tbody.appendChild(tr);
    return table;
  }

  list.forEach(s => {
    const tr = document.createElement('tr');
    tr.className = 'odd:bg-white/0 even:bg-white/5';

    const name = s.name || s.id || '—';
    const vm   = s.vm || s.instance || s.vmid || '—';

    // Size: prefer bytes->MB, else provided string
    let sizeStr = '—';
    if (typeof s.sizeBytes === 'number') {
      sizeStr = `${(s.sizeBytes / 1024 / 1024).toFixed(1)} MB`;
    } else if (typeof s.size_mb === 'number') {
      sizeStr = `${s.size_mb.toFixed(1)} MB`;
    } else if (s.size) {
      sizeStr = s.size;
    }

    // Created: support createdAt or modified (ISO)
    const createdISO = s.createdAt || s.modified || '';
    const createdStr = createdISO ? new Date(createdISO).toLocaleString() : '—';

    tr.innerHTML = `
      <td class="px-3 py-2 whitespace-nowrap">${name}</td>
      <td class="px-3 py-2">${vm}</td>
      <td class="px-3 py-2">${sizeStr}</td>
      <td class="px-3 py-2">${createdStr}</td>
      <td class="px-3 py-2 text-neutral-300">${s.notes || '—'}</td>
      <td class="px-3 py-2"></td>
    `;

    // Run button
    const runTd = tr.lastElementChild;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'px-3 py-1 rounded bg-white/10 hover:bg-white/20';
    btn.textContent = 'Run';
    btn.addEventListener('click', () => runSnapshot(s, btn));
    runTd.appendChild(btn);

    tbody.appendChild(tr);
  });

  return table;
}

async function fetchSnapshots() {
  if (!snapshotsStatus || !snapshotsResults) return;
  snapshotsStatus.textContent = 'Fetching…';
  snapshotsResults.innerHTML = '';
  try {
    const res = await fetch(SNAPSHOTS_ENDPOINT, { credentials: 'same-origin' });
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      const text = await res.text();
      throw new Error('Expected JSON from /snapshots. First bytes: ' + text.slice(0, 60));
    }
    const data = await res.json();
    const list = Array.isArray(data) ? data : (data.data || data.snapshots || []);
    snapshotsStatus.textContent = `${list.length} snapshot${list.length===1?'':'s'}`;
    snapshotsResults.appendChild(renderSnapshots(list));
  } catch (err) {
    snapshotsStatus.textContent = `Request failed: ${err.message}`;
  }
}

snapshotsRefresh?.addEventListener('click', fetchSnapshots);


// --- Boot: fetch /auth/me first, then route ---
(async function boot() {
  // Optional: reduce flicker by hiding all sections until role is known
  Object.values(SECTIONS).forEach(el => el?.classList.add('hidden'));
  if (overviewLink) overviewLink.style.display = 'none';

  await fetchMe();
  initialRoute();
})();
