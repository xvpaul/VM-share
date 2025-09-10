---
title: VMShare   # change per page
---

# VMShare


# Observability (Project Documentation)

> **Scope:** Host & app observability for the VM platform: watchdog alerts (CPU/RAM/disk), Prometheus metrics (HTTP, users, sessions, per‑user), Grafana embedding proxy, DB instrumentation, and operational guidance. Covers components, configuration, endpoints, metric names, behaviors, and recommended improvements.

---

## High‑level Overview

* **Watchdog loop** (`resource_watchdog`) periodically samples host **CPU**, **RAM**, and **disk free**; raises alerts when thresholds are exceeded **sustainably** (for ≥ `SUSTAINED` seconds). Alerts go to **logs**, **Sentry** (`capture_message`), and **Telegram** (if configured).
* **Metrics** (`metrics.py`) expose Prometheus **/metrics** for scraping, plus a **Prometheus HTTP API proxy**. Includes app HTTP metrics, host gauges, user/session gauges, and **per‑user** VM resource gauges (CPU/RSS).
* **Grafana proxy** (`grafana_proxy.py`) builds **same‑origin** iframe URLs for embedding dashboards under `/grafana`.
* **DB metrics** (`db_metrics.py`) instrument SQLAlchemy for latency, error counters, and pool utilization.
* **Multiprocess‑safe** metrics supported via `PROMETHEUS_MULTIPROC_DIR` and a **leader** sampler toggle.

---

## Components

### 1) Watchdog (alerts)

**File:** `/app/observability/utils_observability.py`

* **Thresholds**

  * `CPU_THRESH = 80` (%), `RAM_THRESH = 80` (%)
  * `SUSTAINED = 30` seconds — condition must hold continuously before firing
  * `INTERVAL = 5` seconds between checks
  * `DISK_FREE_THRESHOLDS_GIB = {"/dev/vda2": 35}` — alert when free GiB ≤ threshold for SUSTAINED seconds (per device)
* **Alert sinks:** logger, `sentry_sdk.capture_message`, `telegram_reporting()` (no‑op fallback if import fails)
* **Sustained logic:** `_sustained(now, start, cond)` records the start timestamp when `cond` first becomes true; once `(now - start) ≥ SUSTAINED`, it **fires**. When `cond` is false, the timer resets.
* **CPU flow:** prime with `psutil.cpu_percent(None)`; on sustained ≥ threshold → **warning alert**; on sustained recovery `< threshold` → **info alert**.
* **RAM flow:** similar; additionally sums **RSS of qemu‑system* processes*\* for context in the alert message.
* **Disk flow:** maps real block devices via `psutil.disk_partitions`, filters pseudo FS; for each configured device, if `free_gib ≤ threshold` for SUSTAINED seconds → **warning alert** (includes mountpoint, fs type). (No explicit recovery message for disk.)

> **Tip:** device names vary by environment (`/dev/sda2`, `/dev/vda2`, LVM). Adjust `DISK_FREE_THRESHOLDS_GIB` accordingly.

---

### 2) Metrics & Export (`metrics.py`)

* **Registry & multiprocess**

  * Uses a per‑process `CollectorRegistry` with `multiprocess.MultiProcessCollector` **when** `PROMETHEUS_MULTIPROC_DIR` is set; otherwise falls back to global `REGISTRY`.
  * Registers `atexit.mark_process_dead(os.getpid())` to clean shards on exit.
  * Helper `should_run_samplers()` ensures background samplers execute once (single‑process OR `METRICS_LEADER=1`).

* **HTTP metrics (middleware)**

  * `REQ_LATENCY: Histogram(path, method, status)` — request duration seconds
  * `REQ_COUNT: Counter(path, method, status)` — total requests
  * `install_http_metrics(app)` wraps each request, records latency & count; on exception, increments `500` count (latency recorded as 0.0 in current code).

* **Host & app gauges**

  * `CPU_PCT: Gauge` — `vmshare_host_cpu_percent`
  * `RAM_PCT: Gauge` — `vmshare_host_ram_percent`
  * `USERS_TOTAL: Gauge` — total users (DB count)
  * `SESSIONS_CURR: Gauge` — active sessions (from Redis)

* **Per‑user gauges** *(low‑cardinality labels: `user_id`)*

  * `USER_ACTIVE_VMS: Gauge(user_id)` — count of active VMs
  * `USER_CPU_PCT: Gauge(user_id)` — sum of **process CPU%** for that user’s QEMU PIDs (host view)
  * `USER_RSS_BYTES: Gauge(user_id)` — sum of RSS bytes for those PIDs
  * Helper `_clear_missing_user_series()` removes old series when users disappear to avoid stale time series growth.

* **Collector loop** (`metrics_collector`)

  * Samples host CPU/RAM; queries DB for user count; reads Redis `SessionStore.items()`; aggregates per‑user metrics. If a VM PID is missing, attempts `_find_qemu_pid_by_vmid(vmid)` as a fallback.

* **Endpoints**

  * `GET /metrics` — **dual mode**

    * **Scrape mode (default):** no query params → returns Prometheus exposition (.txt) from the **local** registry.
    * **Proxy mode:** if `query` is present → proxies to Prometheus HTTP API (`/api/v1/query` or `/api/v1/query_range` depending on `start`, `end`, `step`).

      * Env: `PROM_URL` (default `http://localhost:9090`)
      * Errors surface as `400` (missing query), `500` (non‑JSON), or `502` (Prometheus unreachable).
  * `GET /metrics_json` — returns **JSON** dump of the current registry (metric families & samples). Useful for ad‑hoc UI or debugging.

---

### 3) Grafana Embedding Proxy (`grafana_proxy.py`)

* **Purpose:** Build a same‑origin iframe **src** for a single Grafana panel to avoid cross‑origin issues.
* **Config:** `GRAFANA_IFRAME_BASE` (default `/grafana`) — base path behind your reverse proxy.
* **Endpoints**

  * `GET /grafana/panel_iframe_src` → `{ "src": "<iframe-url>" }`

    * **Query:** `uid` (dashboard UID), `panelId` (int), `from` (default `now-1h`), `to` (`now`), `refresh` (`10s`), `theme` (`dark`), `orgId` (`1`), `kiosk` (`true` → presence‑only flag in query string)
    * Returns a URL like: `/grafana/d-solo/<uid>/view?panelId=2&from=now-1h&to=now&refresh=10s&theme=dark&orgId=1&kiosk`
  * `GET /grafana/panel.png` — **Deprecated**, returns `410 Gone` with guidance to use iframes instead (no headless renderer required).

---

### 4) Database Metrics (`db_metrics.py`)

* **Instruments SQLAlchemy** engine with events:

  * `before_cursor_execute` / `after_cursor_execute` → `DB_LAT: Histogram(op)` with op derived from SQL verb (`select`, `insert`, `update`, etc.).
  * `handle_error` → `DB_ERR: Counter(op)` increments on engine‑level errors.
  * `checkout` / `checkin` → `POOL_IN_USE: Gauge` tracks checked‑out connections.
* **Default buckets** for `DB_LAT`: `(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10)` seconds.

---

## Configuration

* **Environment variables**

  * `PROM_URL` — Prometheus base URL for proxy mode (default `http://localhost:9090`).
  * `PROMETHEUS_MULTIPROC_DIR` — directory for Prometheus client multiprocess files (enables multiprocess mode).
  * `METRICS_LEADER` — set to `1` in exactly **one** worker to run samplers in multiprocess deployments.
  * `GRAFANA_IFRAME_BASE` — base path for embedded Grafana (default `/grafana`).
  * `TG_BOT_TOKEN`, `TG_CHAT_ID` — Telegram alerting config.
* **Watchdog thresholds**

  * `CPU_THRESH`, `RAM_THRESH`, `SUSTAINED`, `INTERVAL`, `DISK_FREE_THRESHOLDS_GIB`.

> In containerized environments, ensure `/proc`, `/sys`, and block devices are visible enough for `psutil` to report meaningful CPU/RAM/disk stats.

---

## Exposed Endpoints (Observability)

* `GET /metrics` — Prometheus exposition (default) **or** Prometheus HTTP API proxy (when `query` provided). Supports `query`, `start`, `end`, `step`.
* `GET /metrics_json` — registry dump in JSON.
* `GET /grafana/panel_iframe_src` — returns `{ src }` for Grafana iframe embedding.
* `GET /grafana/panel.png` — deprecated; returns `410`.

---

## Metric Names (Quick Reference)

**HTTP**

* `vmshare_request_duration_seconds` — Histogram{path,method,status}
* `vmshare_requests_total` — Counter{path,method,status}

**Host & platform**

* `vmshare_host_cpu_percent` — Gauge
* `vmshare_host_ram_percent` — Gauge
* `vmshare_users_total` — Gauge
* `vmshare_active_sessions` — Gauge

**Per‑user** *(labels: `user_id`)*

* `vmshare_user_active_vms` — Gauge
* `vmshare_user_cpu_percent` — Gauge
* `vmshare_user_rss_bytes` — Gauge

**Database**

* `vmshare_db_query_seconds` — Histogram{op}
* `vmshare_db_errors_total` — Counter{op}
* `vmshare_db_pool_in_use` — Gauge

---

## Operational Notes & Security

* **Protect metrics endpoints**: `/metrics` and `/metrics_json` often expose internal details; restrict via IP allow‑list, auth, or network policy.
* **Label cardinality:** `user_id` labels grow with users; `_clear_missing_user_series` prunes stale series, but keep cardinality bounded (e.g., don’t label by `vmid`).
* **CPU% semantics:** `USER_CPU_PCT` sums **process** CPU% across cores; on multi‑core hosts, values can exceed 100.
* **Telegram TLS:** `telegram_reporting` uses an **unverified SSL context**. Prefer verified TLS (default) unless constrained by environment.
* **Grafana embedding:** keep Grafana under the same origin (`/grafana`) to avoid CSP/CORS issues; the proxy returns a **URL only**, the frontend must render the `<iframe>`.


## FAQs

* **Q: How do I enable multiprocess metrics with Gunicorn/Uvicorn?**
  **A:** Set `PROMETHEUS_MULTIPROC_DIR=/tmp/prom` before starting workers; ensure the directory is writable. Run background samplers only in one worker by setting `METRICS_LEADER=1` there (or run samplers in a separate singleton process).

* **Q: Can I both scrape `/metrics` and query Prometheus via the same endpoint?**
  **A:** Yes. No query params → scrape local registry. Provide `?query=...` (and optionally `start,end,step`) → proxy to Prometheus HTTP API.

* **Q: Why can `vmshare_user_cpu_percent` exceed 100?**
  **A:** It sums per‑process CPU% which can be **per‑core**. On N‑core machines, a fully busy VM can report up to \~N×100% in total.

* **Q: What if my root disk isn’t `/dev/vda2`?**
  **A:** Update `DISK_FREE_THRESHOLDS_GIB` with your actual device(s). Use `psutil.disk_partitions()` at runtime to see devices and mountpoints.

* **Q: How often do metrics update?**
  **A:** The collector loop defaults to **15s** (`interval_sec`). Host CPU/RAM gauges are updated each cycle; HTTP metrics are updated per request.
