 // ====== Config ======
    const PROM_PROXY = '/metrics';       // for future Prometheus queries (?query=...)
    const APP_JSON   = '/metrics_json';  // works now (no Prometheus server needed)
    const SNAPSHOTS_ENDPOINT = '/snapshots';

    // ====== Current user (server can inject window.__USER__) ======
    const CURRENT_USER = window.__USER__ || { username: 'soledaco', role: 'user', memberSince: '2025' };
    document.getElementById('ui-username').textContent = CURRENT_USER.username || 'user';
    if (CURRENT_USER.memberSince) {
      document.getElementById('ui-member-since').textContent = `Member since ${CURRENT_USER.memberSince}`;
    }

    // ====== Modal controls (unchanged) ======
    const modal   = document.getElementById('metrics-modal');
    const openBtn = document.getElementById('metric-card');
    const closeBtn= document.getElementById('metrics-close');
    const openModal  = () => { modal?.classList.remove('hidden'); modal?.classList.add('flex'); };
    const closeModal = () => { modal?.classList.add('hidden');   modal?.classList.remove('flex'); };
    openBtn?.addEventListener('click', openModal);
    closeBtn?.addEventListener('click', closeModal);
    modal?.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal?.classList.contains('hidden')) closeModal(); });

    // ====== App Metrics (no Prometheus needed) ======
    const appRefresh = document.getElementById('app-refresh');
    const appStatus  = document.getElementById('app-status');
    const appResults = document.getElementById('app-results');

    function makeAppTable(families){
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

    async function fetchAppMetrics(){
      if(!appStatus || !appResults) return;
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
    appRefresh?.addEventListener('click', fetchAppMetrics);

    // ====== Prometheus runner (kept) ======
    const promForm   = document.getElementById('prom-form');
    const promQuery  = document.getElementById('prom-query');
    const promStatus = document.getElementById('prom-status');
    const promResults= document.getElementById('prom-results');

    function makePromTable(result){
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
        const labels = Object.entries(metric).filter(([k]) => k !== '__name__').map(([k,v]) => `${k}="${v}"`).join(', ');
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
          throw new Error('Proxy did not return JSON. Are you pointing to a Prometheus server API? First bytes: ' + text.slice(0, 60));
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

    // ====== Snapshots ======
    const snapshotsRefresh = document.getElementById('snapshots-refresh');
    const snapshotsStatus  = document.getElementById('snapshots-status');
    const snapshotsResults = document.getElementById('snapshots-results');

    function renderSnapshots(list){
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
          </tr>
        </thead>
        <tbody></tbody>`;
      const tbody = table.querySelector('tbody');
      if (!list || !list.length){
        const tr = document.createElement('tr');
        tr.className = 'odd:bg-white/0 even:bg-white/5';
        tr.innerHTML = `<td colspan="5" class="px-3 py-6 text-center text-neutral-400">No snapshots yet.</td>`;
        tbody.appendChild(tr);
      } else {
        list.forEach(s => {
          const tr = document.createElement('tr');
          tr.className = 'odd:bg-white/0 even:bg-white/5';
          const created = s.createdAt ? new Date(s.createdAt).toLocaleString() : '';
          const size = s.sizeBytes != null ? `${(s.sizeBytes/1024/1024).toFixed(1)} MB` : (s.size || '—');
          tr.innerHTML = `
            <td class="px-3 py-2 whitespace-nowrap">${s.name || s.id || '—'}</td>
            <td class="px-3 py-2">${s.vm || s.instance || '—'}</td>
            <td class="px-3 py-2">${size}</td>
            <td class="px-3 py-2">${created}</td>
            <td class="px-3 py-2 text-neutral-300">${s.notes || '—'}</td>`;
          tbody.appendChild(tr);
        });
      }
      return table;
    }

    async function fetchSnapshots(){
      if(!snapshotsStatus || !snapshotsResults) return;
      snapshotsStatus.textContent = 'Fetching…';
      snapshotsResults.innerHTML = '';
      try {
        const res = await fetch(SNAPSHOTS_ENDPOINT, { credentials: 'same-origin' });
        const ct = res.headers.get('content-type') || '';
        if(!ct.includes('application/json')){
          const text = await res.text();
          throw new Error('Expected JSON from /snapshots. First bytes: ' + text.slice(0, 60));
        }
        const data = await res.json();
        // Accept either {status:'success', data:[...]} or an array directly
        const list = Array.isArray(data) ? data : (data.data || data.snapshots || []);
        snapshotsStatus.textContent = `${list.length} snapshot${list.length===1?'':'s'}`;
        snapshotsResults.appendChild(renderSnapshots(list));
      } catch (err){
        snapshotsStatus.textContent = `Request failed: ${err.message}`;
      }
    }
    snapshotsRefresh?.addEventListener('click', fetchSnapshots);

    // ====== Simple client-side routing with role-gated Overview ======
    const ROUTES = ['overview','usage','settings','payments','snapshots'];
    const SECTIONS = Object.fromEntries(ROUTES.map(r => [r, document.getElementById(`route-${r}`)]));
    const NAV_LINKS = Array.from(document.querySelectorAll('#sidebar-nav .nav-link'));

    function showRoute(route){
      // Admin gate for overview
      if (route === 'overview' && CURRENT_USER.role !== 'admin') {
        route = 'usage'; // fallback
        // Also ensure URL reflects the fallback
        if (location.hash !== '#usage') history.replaceState(null, '', '#usage');
      }
      ROUTES.forEach(r => {
        const el = SECTIONS[r];
        if (!el) return;
        if (r === route) { el.classList.remove('hidden'); el.classList.add('block'); }
        else { el.classList.add('hidden'); el.classList.remove('block'); }
      });
      NAV_LINKS.forEach(a => {
        const isActive = a.dataset.route === route;
        a.classList.toggle('bg-white/10', isActive);
        a.classList.toggle('ring-1', isActive);
        a.classList.toggle('ring-white/10', isActive);
      });
      // Auto-load relevant data
      if (route === 'snapshots') fetchSnapshots();
      if (route === 'overview') fetchAppMetrics(); // keep metrics fresh when opening
    }

    function initialRoute(){
      const hash = (location.hash || '').replace('#','');
      let target = ROUTES.includes(hash) ? hash : 'overview';
      if (target === 'overview' && CURRENT_USER.role !== 'admin') target = 'usage';
      // Hide Overview link if not admin
      const overviewLink = document.querySelector('[data-route="overview"]');
      if (CURRENT_USER.role !== 'admin' && overviewLink) overviewLink.style.display = 'none';
      showRoute(target);
    }

    window.addEventListener('hashchange', () => {
      const hash = (location.hash || '').replace('#','');
      showRoute(ROUTES.includes(hash) ? hash : 'overview');
    });

    // Kick things off
    initialRoute();