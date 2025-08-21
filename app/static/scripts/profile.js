 // --- Config ---
  const PROM_PROXY = '/metrics';        // for future Prometheus queries (?query=...)
  const APP_JSON   = '/metrics_json';   // works now (no Prometheus server needed)

  // --- Modal controls (unchanged) ---
  const modal = document.getElementById('metrics-modal');
  const openBtn = document.getElementById('metric-card');
  const closeBtn = document.getElementById('metrics-close');
  const openModal = () => { modal.classList.remove('hidden'); modal.classList.add('flex'); };
  const closeModal = () => { modal.classList.add('hidden'); modal.classList.remove('flex'); };
  openBtn.addEventListener('click', openModal);
  closeBtn.addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal.classList.contains('hidden')) closeModal(); });

  // --- Tabs ---
  const tabGrafana = document.getElementById('tab-grafana');
  const tabProm    = document.getElementById('tab-prom');
  const tabApp     = document.getElementById('tab-app');
  const paneGrafana = document.getElementById('pane-grafana');
  const paneProm    = document.getElementById('pane-prom');
  const paneApp     = document.getElementById('pane-app');

  function activate(tab) {
    const on  = (el) => el.classList.add('bg-white/10');
    const off = (el) => el.classList.remove('bg-white/10');

    const show = (el) => { el.classList.remove('hidden'); el.classList.add('block'); };
    const hide = (el) => { el.classList.add('hidden'); el.classList.remove('block'); };

    // reset tabs
    [tabGrafana, tabProm, tabApp].forEach(off);
    [paneGrafana, paneProm, paneApp].forEach(hide);

    if (tab === 'grafana') { on(tabGrafana); show(paneGrafana); }
    else if (tab === 'prom') { on(tabProm); show(paneProm); }
    else { on(tabApp); show(paneApp); }
  }
  tabGrafana.addEventListener('click', () => activate('grafana'));
  tabProm.addEventListener('click', () => activate('prom'));
  tabApp.addEventListener('click', () => { activate('app'); fetchAppMetrics(); });

  // default tab: app metrics (works immediately)
  activate('app');

  // --- Prometheus runner (unchanged; will work once you install Prometheus) ---
  const promForm = document.getElementById('prom-form');
  const promQuery = document.getElementById('prom-query');
  const promStatus = document.getElementById('prom-status');
  const promResults = document.getElementById('prom-results');

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
      <tbody></tbody>
    `;
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
        <td class="px-3 py-2">${ts ? new Date(ts * 1000).toLocaleString() : ''}</td>
      `;
      tbody.appendChild(tr);
    });
    return table;
  }

  if (promForm) {
    promForm.addEventListener('submit', async (e) => {
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
          throw new Error('Proxy did not return JSON. Are you pointing to a Prometheus server API? First bytes: ' + text.slice(0, 60));
        }
        const data = JSON.parse(text);
        if (data.status !== 'success') {
          promStatus.textContent = `Error: ${data.error || 'query failed'}`;
          return;
        }
        const result = data.data?.result || [];
        promStatus.textContent = `${result.length} series`;
        promResults.appendChild(makePromTable(result));
      } catch (err) {
        promStatus.textContent = `Request failed: ${err.message}`;
      }
    });
  }

  // --- App metrics (no Prometheus needed) ---
  const appRefresh = document.getElementById('app-refresh');
  const appStatus = document.getElementById('app-status');
  const appResults = document.getElementById('app-results');

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
      <tbody></tbody>
    `;
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
          <td class="px-3 py-2">${s.timestamp ? new Date(s.timestamp * 1000).toLocaleString() : ''}</td>
        `;
        tbody.appendChild(tr);
      });
    });
    return table;
  }

  async function fetchAppMetrics() {
    appStatus.textContent = 'Fetching…';
    appResults.innerHTML = '';
    try {
      const res = await fetch(APP_JSON, { credentials: 'same-origin' });
      const data = await res.json();
      if (data.status !== 'success') throw new Error('Unexpected response');
      const families = data.data || [];
      appStatus.textContent = `${families.length} metric families`;
      appResults.appendChild(makeAppTable(families));
    } catch (err) {
      appStatus.textContent = `Request failed: ${err.message}`;
    }
  }

  appRefresh.addEventListener('click', fetchAppMetrics);
  // auto-load when tab opens first time
  fetchAppMetrics();