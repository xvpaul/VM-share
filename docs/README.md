# Project README

## 📌 Overview

The VM Access Platform allows users to launch and interact with fully operable virtual machines directly in their web browser.
No local installation is required — just open the app, log in, and start using your VM through a noVNC-powered graphical desktop. You can run any operating system supported by QEMU and noVNC, though the available choices on vmsl.ru are currently limited by the hosting server’s hardware and configuration.

**Built for:**

* Safe sandboxing and experimentation with Linux distributions
* Quick access to Linux environments for OS-specific tasks

### Tech Stack

* **Compute/Virtualization:** QEMU (headless), qcow2 overlays, snapshots
* **Remote Desktop:** noVNC + websockify (WebSocket bridge)
* **Backend:** FastAPI (Python), SQLAlchemy, Redis (sessions), PostgreSQL (users)
* **Auth:** JWT (python‑jose), Passlib/bcrypt, reCAPTCHA
* **Frontend:** HTML, CSS, JavaScript (vanilla), Tailwind CSS
* **Observability:** Prometheus (prometheus\_client), Grafana, metrics middleware
* **Ops/Alerts:** Telegram bot (optional)
* **Proxying:** Nginx (WebSocket upgrade; `/grafana` subpath)

---

## Features

* Single‑VM‑per‑user lifecycle with overlay or custom ISO boot
* JWT + HttpOnly cookie auth (reCAPTCHA on login/register)
* File upload endpoint to store per‑user ISOs
* Disk snapshot create/run/remove + quota accounting
* Prometheus `/metrics`, HTTP middleware metrics, per‑user CPU/RSS gauges
* Grafana iframe proxy under same origin (`/grafana`)
* Watchdog alerts for CPU/RAM/disk (sustained thresholds)

---

## Architecture Overview

```
Browser (noVNC) ← WebSocket/TCP → websockify :<http_port>
                                       │
                                       └─→ UNIX socket (VNC) → QEMU (headless)

Backend (FastAPI)
  ├─ Auth (JWT cookie) + reCAPTCHA
  ├─ VM API: overlays/ISO boot, run/cleanup, snapshots, listing
  ├─ Redis SessionStore (per‑VM hash + indices)
  ├─ PostgreSQL Users (bcrypt) + snapshot quota
  ├─ Observability: /metrics, Grafana proxy, watchdog → logs/Sentry/Telegram
  └─ Static for websockify (noVNC assets)
```

> Detailed subsystem docs live in the project canvas:
>
> * **Authentication — Project Docs**
> * **VM Lifecycle — Project Docs**
> * **API Reference — Project Docs**
> * **Observability — Project Docs**

---

## Prerequisites

* Linux host with **QEMU** (`qemu-system-x86_64`). KVM optional (currently disabled by flags).
* **Python 3.10+**, **Redis**, **PostgreSQL**.
* **websockify** available on PATH (or set `WEBSOCKIFY_BIN`).
* **noVNC** static in `/app/static` (or set `WEBSOCKIFY_WEB_DIR`).
* Optional: **Prometheus**, **Grafana**, **Sentry** DSN, **Telegram** bot.


## Authentication Summary

* `POST /register`, `POST /login`, `POST /token` (reCAPTCHA required) → issue JWT + set cookie.
* `GET /me`, `GET /user_info` → require auth via cookie or `Authorization: Bearer`.
* `POST /logout` → delete cookie and cleanup any active VM.

*See: **Authentication — Project Docs***

---

## VM Lifecycle Summary

* `POST /run-script` (overlay boot) or `POST /run-iso` (custom ISO).
* QEMU starts with VNC/QMP UNIX sockets; websockify exposes a per‑VM TCP port; Redis stores session.
* On disconnect, websockify monitor triggers `cleanup_vm` → kill processes, remove sockets/files, drop Redis keys.

---

## Snapshots & Quota

* `POST /snapshot` → create qcow2 snapshot and charge quota (base+overlay or existing snapshot).
* `POST /run_snapshot` → boot directly from snapshot qcow2.
* `GET /get_user_snapshots` → list; `POST /remove_snapshot` → delete and decrement quota.
* DB constraints enforce non‑negative values and `stored ≤ capacity`.

---

## Observability

* **Metrics:** `GET /metrics` (scrape or proxy with `?query=...`), `GET /metrics_json`.
* **Grafana:** `GET /grafana/panel_iframe_src` → `{ src }` for dashboard panel iframes.
* **Watchdog:** `resource_watchdog(stop_event)` sends alerts to logs/Sentry/Telegram for sustained CPU/RAM/disk conditions.

