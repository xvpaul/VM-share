# VM‑share — Project Documentation

> A lightweight, browser‑based platform to launch and interact with full Linux desktops inside QEMU via noVNC, powered by a FastAPI backend and PostgreSQL.

---

## 1) Overview

**VM‑share** lets you spin up ephemeral or persistent VMs on a Linux host and interact with them directly in the browser (GUI or terminal). It’s designed for demos, teaching, and hackathon‑friendly experiments—scalable to hundreds of concurrent users, not thousands.

### Goals

* One‑click, per‑user VM sessions with GUI access in the browser.
* Minimal frontend (plain HTML + Tailwind), simple auth, and clear APIs.
* Works even without KVM; supports lightweight desktop environments (XFCE/LXDE/Bodhi).

### Non‑Goals (current)

* Multi‑host orchestration or cloud autoscaling.
* Full enterprise IAM / SSO.
* Long‑term VM fleets (focus is short‑lived sessions with optional persistence).

---

## 2) Architecture

### Components

* **FastAPI service** (`get_vm.py`): REST endpoints to start/stop VMs, issue redirects to noVNC, manage sessions, and integrate telemetry.
* **QEMU runner**: spawns QEMU processes with user‑specified ISO / profiles and optional data disks.
* **Websockify subclass**: backend‑only connection status detection for VNC/WebSocket bridging (no frontend coupling).
* **noVNC**: in‑browser VNC client for the VM GUI.
* **PostgreSQL**: session state, users, and audit trails.
* **Observability**: Telegram alerts for disk/CPU/RAM events.

### High‑level Flow

```text
Browser ──▶ FastAPI ──▶ (start VM) ─┬─▶ QEMU (VNC)
        │            │               │
        │            └─▶ Websockify ─┘
        │                     ▲
        └───────▶ noVNC ◀────┘
```

---

## 2.1) Module inventory (from memory)

> This reflects what you’ve built and what your routes reference. Marked **confirmed** where we’ve seen exact paths; others are **inferred** from your code.

### Confirmed modules

* **`get_vm.py`** — FastAPI app & routers

  * Endpoints: `POST /run-iso` (ensures one VM per user, resolves ISO via profile rules, starts QEMU, returns noVNC redirect).
  * Uses: `get_current_user`, `get_session_store`, `get_websockify_service`, `_novnc_redirect`, `VM_PROFILES`, `start_qemu_session`.
* **`app/observability/report.py`** — Telegram reporting helper

  * Function: `telegram_reporting(message: str) -> None` (posts JSON to Telegram via `TG_BOT_TOKEN`, `TG_CHAT_ID`).
* **`configs/config.py`** — configuration loader

  * Exposes: `TG_BOT_TOKEN`, `TG_CHAT_ID` (and likely DB/env settings).

### Referenced / inferred modules & services

* **Auth (`auth.py` or `app/auth/`)** — custom class‑based auth

  * Providers: `get_current_user`, token/session issuance, signup/login endpoints.
* **Session store (`session_store.py`)** — per‑user VM enforcement & state

  * API: `get_running_by_user(user_id)`, allocator for VNC/HTTP ports, persistence in PostgreSQL.
* **Websockify service (`websockify_service.py`)** — connection status

  * Provider: `get_websockify_service`, tracks connect/disconnect, exposes status for a `vmid`.
* **QEMU runner/manager (`qemu_runner.py` or `vm/runner.py`)**

  * Functions: `boot_from_iso(...)` (BIOS‑only path, ISO sanity checks), `start_qemu_session(...)` (builds CLI, launches, returns `{ vmid, vnc_port, http_port, pid }`).
* **Redirect utilities (`utils/redirect.py`)**

  * Helper: `_novnc_redirect(req, f"ws/{port}")` to build a same‑origin noVNC URL.
* **Profiles/config (`profiles.py` or `settings/vm_profiles.py`)**

  * Dict: `VM_PROFILES["custom"]` supporting dir/file/template with `{uid}`, plus default CPU/RAM and port ranges.
* **Uploads route/handler** (Chrome issue noted; Safari OK)

  * Handles ISO uploads into `uploads/` with name `"{uid}.iso"` when `base_image` is a directory.

> Planned/ongoing: CPU/RAM/disk watchdogs that call `telegram_reporting()`; Cloudflare/Nginx same‑origin redirect hardening.

---

## 2.2) Module docs template (use this per file)

For each module, add a section like this:

**Path:** `app/<module>.py`

**Purpose**
Short summary of what the module is responsible for and what it should *not* do.

**Key responsibilities**

* Bullet list of core duties.

**Public API / Exports**

* Functions/classes/routers exposed for other modules.

**Key dependencies**

* Internal modules it imports and why.
* External libs it relies on.

**Configuration**

* Env vars or settings it reads.

**Runtime behavior**

* Lifecycle hooks, background tasks, side effects, I/O.

**Errors & edge cases**

* Common failure modes, exceptions raised, and how callers should handle them.

**Observability**

* Logs, metrics, traces emitted (names, labels).

**Security notes**

* Input validation, auth/perm checks, dangerous operations.

**Example use**

* Small code or curl snippet using the public API.

---

## 3) Key Features

* **Launch from ISO**: Run a custom ISO, with optional persistent data disk.
* **GUI access in browser**: via noVNC + Websockify bridge.
* **Session management**: enforce one running VM per user.
* **Lightweight GUI distros**: Debian+XFCE, LXDE, Bodhi, Void Linux, etc. (QEMU w/o KVM works; expect slower performance.)
* **Custom auth**: class‑based auth in `auth.py` with a simple modal UI (Log In / Sign Up) and dark/light theme toggle.
* **Resource monitoring & alerts**: Telegram reporting for capacity/usage spikes.

---

## 4) System Requirements

* **Host OS**: Linux with QEMU (and `qemu-img`). Works without KVM; KVM recommended when available.
* **Python**: 3.11+
* **PostgreSQL**: 14+ (configurable via `DATABASE_URL`)
* **noVNC + Websockify**: packaged with the app or installed separately.
* **Nginx** (recommended): TLS termination, reverse proxy to FastAPI + noVNC.

---

## 5) Quickstart

### 5.1 Clone & install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5.2 Configure environment

Create `.env` or use your config loader. Example variables:

```ini
# Database
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/vmshare

# Web
HOST=0.0.0.0
PORT=8000

# Security
SECRET_KEY=change-me
ACCESS_TOKEN_EXPIRE_MINUTES=120

# VM
VM_BASE_DIR=/var/lib/vmshare
NOVNC_BASE_URL=/novnc
WEBSOCKIFY_HOST=127.0.0.1
WEBSOCKIFY_BASE_PORT=5901

# Observability (Telegram)
TG_BOT_TOKEN=123456:ABC...
TG_CHAT_ID=123456789
```

### 5.3 Run services

```bash
# API
uvicorn get_vm:app --host $HOST --port $PORT --workers 2

# Websockify (if run separately; otherwise managed by the app)
websockify --web=/path/to/novnc 6080 127.0.0.1:5901
```

Open the browser at `https://<your-host>/novnc/?path=ws/<port>` (the API returns a `redirect` to this for convenience).

---

## 6) Configuration Model

### 6.1 VM Profiles

VM profiles describe how disks/ISOs are resolved and how ports are assigned. Your code supports flexible path resolution, including templates with `{uid}`.

```python
VM_PROFILES = {
  "custom": {
    # Can be a directory, a file, or a template containing {uid}
    "base_image": "/var/lib/vmshare/uploads",  # or "/var/lib/vmshare/{uid}.iso"
    "prefix": "{uid}.iso",                      # used when base_image is a directory
    "vnc_port_range": [5901, 5999],
    "http_port_range": [6101, 6199],            # for noVNC/http proxy
    "default_memory_mb": 2048,
    "default_cpus": 2
  }
}
```

### 6.2 Persistence vs Ephemeral

When launching from ISO you have two main persistence modes:

* **Ephemeral (stateless)**: `-snapshot` or RAM‑only changes. Fast but nothing is saved after shutdown.
* **Persistent (recommended)**: attach a qcow2 **install/data disk**. All OS installation and subsequent changes are saved there.

Your `boot_from_iso(...)` function allows:

* `data_disk_gb`: create a new qcow2 data disk of given size.
* `install_disk_path`: attach an existing qcow2 disk (recommended for re‑using a user’s workspace).

> **Tip:** Use qcow2 overlays per session/user: `qemu-img create -f qcow2 -b base.qcow2 -F qcow2 runs/<vmid>.qcow2` for copy‑on‑write efficiency.

---

## 7) API Reference

All endpoints are served under the FastAPI app in `get_vm.py`. Representative examples are included below.

### 7.1 Start a VM from a custom ISO

`POST /run-iso`

Starts (or returns) a per‑user VM session from a resolved ISO path, and responds with a redirect URL to open noVNC.

**Request** (JSON): *no body required* (ISO may be derived from profile+user context) or with optional fields depending on your implementation, e.g.:

```json
{
  "iso_path": "/var/lib/vmshare/uploads/abcd1234.iso",
  "memory_mb": 2048,
  "cpus": 2,
  "data_disk_gb": 16
}
```

**Behavior** (as implemented):

* Enforces **one running VM per user** via the session store.
* Resolves the ISO path using the `VM_PROFILES["custom"]` rules (dir/file/template with `{uid}`).
* Generates a unique `vmid` (e.g., `secrets.token_hex(6)`).
* Starts QEMU and registers VNC/HTTP ports.
* Returns a `redirect` pointing to the appropriate noVNC path.

**Response (200)**

```json
{
  "message": "VM already running for user alice",
  "vm": { "vmid": "fa32b0", "vnc_port": 5907, "http_port": 6107, "pid": 12345 },
  "redirect": "/novnc/?path=ws/6107"
}
```

or

```json
{
  "message": "VM started",
  "vm": { "vmid": "c9a2f1", "vnc_port": 5911, "http_port": 6111, "pid": 22341 },
  "redirect": "/novnc/?path=ws/6111"
}
```

### 7.2 Authentication

Class‑based custom auth in `auth.py` (email‑based Sign Up + Log In). Typical endpoints:

* `POST /auth/signup`
* `POST /auth/login`
* `POST /auth/logout`

Sessions/tokens are stored server‑side with expiration (`ACCESS_TOKEN_EXPIRE_MINUTES`).

### 7.3 Connection Status (Websockify subclass)

The backend emits/records VNC connection events (connect/disconnect) by subclassing Websockify. Expose a read endpoint such as:

* `GET /connections/{vmid}` → current status & last change timestamp
* `GET /connections` → recent events (for admin dashboards)

> Implementation note: status can be stored in PostgreSQL (or in‑memory + periodic flush) by the Websockify subclass.

### 7.4 Admin / Control (suggested)

* `POST /vms/{vmid}/stop`
* `POST /vms/{vmid}/restart`
* `GET /vms` → list current processes/ports

---

## 8) QEMU Launching

### 8.1 Typical flags (BIOS‑only path)

* Video: `-vga virtio` (or `std` for compatibility)
* Networking: `-netdev user,id=n1 -device virtio-net-pci,netdev=n1`
* Disks: `-drive file=<install_disk.qcow2>,if=virtio,cache=writeback`
* ISO: `-cdrom <path>.iso -boot order=d`
* No KVM: omit `-enable-kvm`

### 8.2 Snapshots & Saving Progress

* **Best practice**: use a **persistent qcow2** install disk; progress is saved automatically.
* **Temporary scratch**: run with `-snapshot` (writes to an ephemeral overlay, discarded on exit).
* **Point‑in‑time snapshots** (optional): with qcow2 backing and QEMU monitor `savevm/loadvm` commands. These are advanced and have performance/storage trade‑offs.

---

## 9) Frontend

* **Stack**: Plain HTML + Tailwind CSS.
* **Auth modal**: tabbed Log In / Sign Up, integrated with the custom auth endpoints.
* **Theme**: dark/light toggle; buttons styled according to active theme.
* **noVNC client**: open via API‑returned `redirect`.

> Known issue: **Chrome upload failures** while Safari works. See Troubleshooting.

---

## 10) Observability & Alerts

### 10.1 Telegram reporting helper

`app/observability/report.py` provides:

```python
def telegram_reporting(message: str) -> None:
    """Send a formatted message to the configured Telegram chat."""
    ...  # uses TG_BOT_TOKEN and TG_CHAT_ID
```

### 10.2 What to alert on

* **Disk capacity** thresholds (host volumes and per‑user storage)
* **High CPU** usage (process and system level)
* **High RAM** usage (system and per‑QEMU process)

> Implement watchers with `psutil` (polling) + debouncing to avoid spam. Send HTML‑formatted messages via `telegram_reporting()` with concise context (hostname, PID, top offenders, thresholds, timestamps).

---

## 11) Security Considerations

* **Process isolation**: consider cgroups/CPU & memory quotas per VM.
* **Networking**: default to user‑mode networking; restrict host access; avoid exposing QEMU VNC directly.
* **Secrets**: load via environment; never hardcode tokens or DB creds.
* **Rate limiting**: throttle VM creation per user/IP.
* **Validation**: strictly validate ISO paths (prevent directory traversal); resolve to absolute canonical paths.

---

## 12) Scaling & Ops

* Run multiple FastAPI workers; ensure unique port allocation (lock or DB row per port).
* Use a **session store** to enforce one VM per user.
* Pre‑warm base images; use qcow2 backing to speed launches.
* Monitor port exhaustion; recycle ports after VM exit with a cool‑down.
* Centralized logs with VM `vmid` correlation IDs.

---

## 13) Troubleshooting

* **noVNC shows blank screen**: verify Websockify target is reachable; check VNC password/`-vnc :N` mapping.
* **Chrome upload fails, Safari works**:

  * Confirm `Content-Type` for multipart/form‑data.
  * Check `Content-Security-Policy` and CORS headers on the upload route.
  * For large files, ensure reverse proxy allows big bodies (`client_max_body_size` in Nginx) and that chunked uploads are handled.
  * Verify temporary directory permissions under `VM_BASE_DIR`.
* **QEMU fails to start**: validate ISO size (>10MB), absolute path, and file readability.
* **Port conflicts**: ensure VNC/HTTP port allocators handle concurrency; check lingering processes.
* **Slow VM without KVM**: prefer lighter DEs (XFCE/LXDE), reduce RAM/CPU if host is oversubscribed.

---

## 14) Roadmap

* Chrome upload reliability fix.
* Connection status API & admin dashboard.
* Snapshot UX: one‑click create/restore using qcow2 overlays.
* Prebuilt Debian+XFCE and Void Linux images.
* Optional KVM path with capability detection.

---

## 15) Contributing

* Open a PR with a clear description and test plan.
* For new endpoints, include OpenAPI examples and update this document.

## 16) License

Choose a license (MIT/Apache‑2.0/BSD‑3‑Clause). Add `LICENSE` at repo root.

---

## Appendix A — Example: ISO Boot Endpoint (simplified)

```python
@router.post("/run-iso")
async def run_custom_iso(
    req: Request,
    user: User = Depends(get_current_user),
    store: SessionStore = Depends(get_session_store),
    ws: WebsockifyService = Depends(get_websockify_service),
):
    user_id = str(user.id)
    existing = store.get_running_by_user(user_id)
    if existing:
        return JSONResponse({
            "message": f"VM already running for user {user.login}",
            "vm": existing,
            "redirect": _novnc_redirect(req, f"ws/{existing['http_port']}")
        })

    # Resolve ISO from VM_PROFILES["custom"] (dir/file/template with {uid})
    # Validate size >= 10MB, sanity‑check header, then start QEMU.
    vm = await start_qemu_session(user_id=user_id, profile="custom")
    return JSONResponse({
        "message": "VM started",
        "vm": vm,
        "redirect": _novnc_redirect(req, f"ws/{vm['http_port']}")
    })
```

## Appendix B — Telegram Alert Examples

```text
🚨 High CPU on vmshare‑host1
Time: 2025‑09‑09 10:11:03Z
Top processes: qemu‑system‑x86_64 (312%), postgres (120%)
Action: scaled down new launches, investigating user vmid=c9a2f1
```

```text
⚠️ Disk usage 92% on /var/lib/vmshare
Largest: runs/ (120G), uploads/ (64G)
Action: vacuum old overlays > 7 days
```

## Appendix C — Recommended QEMU CLI (no KVM)

```bash
qemu-system-x86_64 \
  -m 2048 -smp 2 \
  -cdrom /var/lib/vmshare/uploads/abcd1234.iso \
  -drive file=/var/lib/vmshare/runs/c9a2f1.qcow2,if=virtio,cache=writeback,discard=unmap \
  -netdev user,id=n1 -device virtio-net-pci,netdev=n1 \
  -vga virtio -display none -vnc :11
```
