Virtual Machine Lifecycle
Project is built the way that one logged in user can operate only one Virtual Machine at once. Once user triggers /run-script endpoint VM lifecycle starts.
User runs VM (/app/routers/vm.py -> run_vm_script triggered) -> overlay is created via calling /app/methods/manager/OverlayManager.py create_overlay() method -> VM is booting at /app/methods/manager/OverlayManager.py boot_vm which creates unix-socket, executes VM booting, and creating PID file and then returns "user_id" "vmid":"os_type""overlay""vnc_socket" "qmp_socket""started_at" "pid"  which is stored at Redis database, which is used further to control VM lifecycle (SessionManager.py) -> we are getting back to vm.py run_vm_script. websockify process starts. get_websockify_service.start takes as arguments target which is newly created unix socket to connect to via websockify and generated using secrets vm id. it finds free TCP port to connect to by proxy unix socket to prevent port exhaustion (im not sure actully, needs clarification) -> at get_websockify_service.start here comes concurrency using threads. new thread is created to monitore shell output on a line containing disconnect information whichg then getting handled as user dissconects/closes tab with VM and cleanup logic starts at utils.cleanup_vm -> cleanup_vm extracts all the data from redis store and cleans up all the processess and overlays as well as sockets for a given vm to clean up. this finishes lifecyle.



# Virtual Machine Lifecycle (Project Documentation)

> **Scope:** Single-VM-per-user flow from launch to cleanup for the QEMU + noVNC/websockify stack. This document explains components, data flow, Redis schema, lifecycle steps, concurrency, and failure/cleanup behavior. It also calls out corrections and improvements where current code or comments may be misleading.

---

## High-level Overview

* **One VM per logged-in user** at any given time. Launch is initiated by `POST /run-script`.
* **Overlay-backed boot** for predefined OS types; ISO-only path for `os_type="custom"`.
* **QEMU is headless** (`-display none`) and exposes:

  * **VNC** over a **UNIX domain socket**: `RUN_DIR/vnc-<vmid>.sock`
  * **QMP** over a **UNIX domain socket**: `RUN_DIR/qmp-<vmid>.sock`
* **websockify** bridges the VNC UNIX socket to an ephemeral **public TCP port**, which the browser connects to via noVNC.
* **Session metadata** is kept in Redis via `SessionStore` and is the source of truth for the VM lifecycle.
* **Lifecycle end** is detected by monitoring the websockify stdout for disconnect lines (client tab closed) and/or process exit; cleanup then tears down processes, files, and sockets.

---

## Components

### API Layer

* **`/app/routers/vm.py → run_vm_script`**: Entry point for launching a VM. Enforces one-VM-per-user, orchestrates overlay creation, boot, websockify start, persists session, returns redirect for noVNC.

### VM/Overlay Management

* **`QemuOverlayManager` (OverlayManager.py)**

  * `create_overlay()` → makes qcow2 overlay on top of a base image using `qemu-img` (for non-`custom` OS types).
  * `boot_vm()` → launches `qemu-system-x86_64` as a daemon; writes PID to `RUN_DIR/qemu-<vmid>.pid`; returns VM metadata (`user_id`, `vmid`, `os_type`, `overlay`, `vnc_socket`, `qmp_socket`, `started_at`, `pid`).

### WebSocket Bridge

* **`WebsockifyService`**

  * `start(vmid, target)` → chooses an available TCP port, launches `websockify --web <static> 0.0.0.0:<port> --unix-target <vnc.sock>` and spawns a reader thread that monitors stdout for connects/disconnects and triggers cleanup.

### State / Session

* **`SessionStore` (Redis)**

  * Persists **per-VM hash** (`vm:<vmid>`), **active VM set**, **per-user sorted set**, **per-OS set**, and **PID→VMID** index.
  * Exposes convenience lookups like `get_running_by_user(user_id)` and `get_by_pid(pid)`.

### Utilities

* **`utils.find_free_port()`** binds to `127.0.0.1:0` to have the OS allocate an unused ephemeral port; returns that port number.
* **`utils.cleanup_vm(vmid, store)`** performs best-effort teardown of websockify + QEMU, removes overlay/ISO and sockets, and deletes the Redis session.

---

## Redis Data Model (summary)

* `vm:<vmid>` (HASH) → fields like `user_id`, `os_type`, `overlay` (or `iso`), `vnc_socket`, `qmp_socket`, `http_port`, `pid` (QEMU PID), `websockify_pid` (recommended), `started_at`, etc.
* `vms:active` (SET) → active VMIDs.
* `user:<uid>:vms` (ZSET) → VMIDs scored by `created_at` (ms).
* `vms:by_os:<os_type>` (SET) → VMIDs for quick grouping/filtering.
* `vm:by_pid:<pid>` (STRING) → reverse index PID→VMID for quick lookups.

> **Note:** `SessionStore.set()` will auto-populate `created_at` (ms) if not provided, and maintain the PID reverse index when `pid` exists.

---

## Socket & Protocol Topology (How the pieces connect)

**Goal:** let browsers (which speak WebSocket over TCP) control and view a local QEMU VNC server (which speaks raw bytes over a UNIX socket), while keeping management (QMP) separate.

```
Browser (noVNC)
    │  WebSocket over TCP  →  ws://<host>:<http_port>
    ▼
websockify (frontend listener on <http_port>)
    │  unwraps WebSocket frames ⇄ wraps raw bytes
    ▼
UNIX domain socket (VNC): /run/vms/vnc-<vmid>.sock
    ▼
QEMU process (VNC server; -vnc unix:...)

[Side-channel: management]
Backend / tools (API, ops)
    │  JSON QMP commands over UNIX socket
    ▼
UNIX domain socket (QMP): /run/vms/qmp-<vmid>.sock
    ▼
QEMU process (QMP; -qmp unix:...,server,nowait)
```

### What each socket/port is for

* **VNC UNIX socket** (`vnc-<vmid>.sock`): QEMU’s framebuffer I/O. Local-only. Not directly usable by browsers.
* **websockify TCP port** (`http_port`): Public-facing listener that turns **WebSocket ⇄ raw VNC bytes**. One port **per running VM**. noVNC connects here.
* **QMP UNIX socket** (`qmp-<vmid>.sock`): Machine control plane (powerdown, query status, snapshots, etc.). Never exposed to the browser.

### Who talks to what

* **Browser ↔ websockify**: WebSocket over TCP to `ws://<host>:<http_port>` (or `wss://` via reverse proxy).
* **websockify ↔ VNC socket**: Local connection to `/run/vms/vnc-<vmid>.sock` using `--unix-target`.
* **Ops/Backend ↔ QMP**: Local clients (e.g., `socat`, Python QMP) to `/run/vms/qmp-<vmid>.sock` for graceful shutdown or diagnostics.

### Creation & teardown timing

* **Created at boot**: both `vnc-<vmid>.sock` and `qmp-<vmid>.sock` when QEMU starts; `http_port` when websockify starts.
* **Removed at cleanup**: sockets and overlay/ISO are deleted; websockify and QEMU are SIGTERM’d; Redis keys are dropped.

### Notes & best practices

* Prefer binding websockify to `127.0.0.1` and exposing **WSS** via a reverse proxy. Externally you keep a single port (443), internally still one port per VM.
* If multiple tabs connect, consider tracking **connection count**; only cleanup when the last one disconnects.
* Optional graceful path: send QMP `system_powerdown` before SIGTERM.

## End-to-End Lifecycle

1. **Request**
   Client calls `POST /run-script` with `os_type`.

2. **Single-VM Enforcement**
   `SessionStore.get_running_by_user(user_id)` is checked; if a VM exists, return existing session + redirect.

3. **VMID Generation**
   A random hex `vmid` (e.g., `secrets.token_hex(6)`).

4. **Overlay Prep (non-custom)**
   `QemuOverlayManager.create_overlay()` creates a qcow2 overlay:
   `qemu-img create -f qcow2 -F qcow2 -b <base_image> <overlay_path>`
   If overlay already exists for this `<vmid>`, it is reused.

5. **Boot**
   `QemuOverlayManager.boot_vm(vmid)` builds sockets, removes stale ones, launches QEMU:

   * `-vnc unix:<vnc.sock>`
   * `-qmp unix:<qmp.sock>,server,nowait`
   * `-daemonize -pidfile <pidfile>`
     Then it spins until the pidfile is readable; returns metadata including the QEMU PID and socket paths.

6. **websockify Start**
   `WebsockifyService.start(vmid, target)` finds an available public **TCP** port via `find_free_port()`, starts `websockify` with `--unix-target` pointing at the VNC socket, and launches a daemon thread that tails stdout to detect connects/disconnects.

7. **Persist Session**
   `SessionStore.set(vmid, { **meta, user_id, os_type, http_port, pid })`

8. **Redirect**
   API responds with friendly message, session payload, and a noVNC redirect to `ws/<http_port>`.

9. **Disconnect / Close Tab**
   When a client disconnect line is observed in websockify logs, the monitor thread triggers `cleanup_vm(vmid, store)`.

10. **Cleanup**
    `cleanup_vm` best-effort SIGTERM to websockify + QEMU, removes overlay/ISO and sockets, and `store.delete(vmid)` to clear all indices.

---

## Concurrency & Observability

* **Threaded monitor**: The websockify stdout reader runs in a **daemon** thread per VM; it updates `last_seen` and triggers cleanup on disconnect or on process exit.
* **Registry**: `ProcRegistry` tracks `ws:<vmid> → Popen` so `WebsockifyService.stop(vmid)` can terminate it even if Redis lacks the `websockify_pid`.
* **Logging**: websockify is started with `--verbose`; QEMU launch success/failure is fully logged, including stderr.

---

## Cleanup Semantics (what gets removed)

* **Processes**:

  * websockify via stored `websockify_pid` (recommended) or via `ProcRegistry.stop()` (if wired through cleanup).
  * QEMU via `pid` (pidfile) or fallback `pkill -f <vmid>`.
* **Files**:

  * For non-`custom` OS: overlay qcow2 at `{overlay_dir}/{overlay_prefix}_{vmid}.qcow2`.
  * For `custom`: ISO path in `session['iso']` (if present).
* **Sockets**: `RUN_DIR/vnc-<vmid>.sock`, `RUN_DIR/qmp-<vmid>.sock`.
* **Redis keys**: the VM hash, membership in `vms:active`, user ZSET, OS SET, and `vm:by_pid:<pid>`.

> **Idempotence:** If no session exists, cleanup returns early. Double-invocation is safe.

---

## Corrections to Draft / Clarifications

1. **Reason for the TCP port / proxy**
   The project **does not proxy to avoid port exhaustion**. It proxies the **VNC UNIX socket to a TCP port** so the **browser (noVNC) can connect**. `find_free_port()` simply asks the OS for an unused ephemeral port to **avoid collisions**.

2. **`WebsockifyService.start` docstring vs implementation**
   The docstring mentions `port` and `store` parameters, but the actual signature is `start(vmid, target)` and the function internally resolves the store and port. The docstring should be updated.

3. **Session key naming for overlay**
   `boot_vm()` returns `overlay` (the actual image path). `cleanup_vm()` currently looks for `overlay_path` first. While it has a fallback using the profile, consider reading `overlay` as the primary source to avoid mismatches.

4. **websockify process termination**
   `cleanup_vm()` attempts to kill `websockify` using `websockify_pid`/`ws_pid` in the session, but **those fields are not currently persisted**. Without them, websockify may linger. Persisting the websockify PID or invoking `ProcRegistry.stop()` from cleanup is recommended (see “Recommended Improvements”).

5. **PID reverse index**
   `SessionStore` supports a `vm:by_pid:<pid>` reverse index, populated when `pid` is present. Ensure QEMU PID is stored under `pid` (it is), so reverse lookups work.

---

## Recommended Improvements (low-risk)

1. **Persist websockify PID**
   After `Popen`, save `proc.pid` into Redis so `cleanup_vm` can terminate it reliably:

   ```python
   # In WebsockifyService.start()
   store = get_session_store()
   ...
   proc = subprocess.Popen(...)
   self._registry.set(f"ws:{vmid}", proc)
   try:
       if store is not None:
           store.update(vmid, websockify_pid=str(proc.pid))
   except Exception:
       logger.exception("[websockify:%s] failed to persist websockify_pid", vmid)
   ```

   And in `cleanup_vm`, keep the current logic (`websockify_pid`/`ws_pid`)—it will now work.

2. **Align overlay field**
   Update `cleanup_vm` to consult `session.get("overlay")` before fallback:

   ```python
   overlay_path = session.get("overlay_path") or session.get("overlay")
   ```

3. **Docstring fix**
   Update `WebsockifyService.start` docstring to reflect current signature and behavior; remove stale params.

4. **Optional: explicit stop hook**
   If you want `cleanup_vm` to **also** stop websockify via the in-memory registry even when Redis lacks the pid, you can inject a small adapter:

   * Expose a global `get_websockify_registry()` or pass a stop callable into `cleanup_vm` (DI).
   * Or ensure every call-site of `cleanup_vm` first calls `WebsockifyService.stop(vmid)` (requires access).

5. **Graceful QEMU shutdown (future)**
   Before SIGTERM, optionally send a QMP `system_powerdown` or ACPI event (if the guest supports it). Keep TERM as a fallback.

6. **Safer fallback than `pkill -f <vmid>`**
   Consider tracking PIDs explicitly or scoping `pkill` by user/exec path to reduce the (low) risk of terminating an unrelated process containing the same hex in its args.

7. **Socket/dir existence**
   Ensure `RUN_DIR` exists and has secure permissions before creating sockets/pidfiles; log if the directory is missing.

8. **Idle timeout (optional)**
   Add a timer to auto-cleanup VMs with no `last_seen` updates for N minutes to handle clients that die without emitting a nice disconnect line.

---

## Operational Notes

* **One-VM-per-user policy** is enforced at launch; attempting to launch while one is active returns the existing VM metadata and redirect.
* **Re-entrancy**: If overlay exists for `<vmid>`, it is reused; stale sockets are removed prior to boot.
* **Error surfacing**: If QEMU fails, `boot_vm()` raises with detailed stdout/stderr; the API converts to `500`.
* **Idempotent teardown**: Double cleanups are safe; missing files/sockets are logged and ignored.

---

## Example Success Response (abridged)

```json
{
  "message": "VM for user alice launched (vmid=ab12cd34ef56)",
  "vm": {
    "vmid": "ab12cd34ef56",
    "user_id": "42",
    "os_type": "ubuntu",
    "overlay": "/var/vms/overlays/ubuntu_ab12cd34ef56.qcow2",
    "vnc_socket": "/run/vms/vnc-ab12cd34ef56.sock",
    "qmp_socket": "/run/vms/qmp-ab12cd34ef56.sock",
    "started_at": "2025-09-10T10:00:00Z",
    "pid": 12345
  },
  "redirect": "/ws/59001"
}
```

---

## FAQs

* **Q: How do the VNC UNIX socket, websockify TCP port, and QMP UNIX socket fit together?**
  **A:** QEMU exposes **VNC** on a local **UNIX socket** (`vnc-<vmid>.sock`). **websockify** listens on a per‑VM **TCP port** (`http_port`) and converts **WebSocket ⇄ raw VNC bytes**, connecting locally to that UNIX socket. **QMP** is a separate **UNIX socket** (`qmp-<vmid>.sock`) used by backend tools for management (powerdown, status, etc.) and is never exposed to the browser.

* **Q: Does a single VM use multiple TCP ports?**
  **A:** No. Each running VM uses **one** public TCP port (for websockify/noVNC). System‑wide you’ll see **many ports** if many VMs run at once. If you want only **one external port** (e.g., 443), put an HTTPS reverse proxy in front and route `wss:///ws/<vmid>` → the VM’s internal port (looked up in Redis).

* **Q: Why use UNIX sockets for VNC/QMP instead of TCP?**
  **A:** UNIX sockets are **local‑only**, simpler to permission, and avoid exposing extra public ports. Browsers can’t talk UNIX sockets, so websockify provides the one necessary **WebSocket/TCP** entry point.

* **Q: Who chooses the VM’s public port? Is this about port exhaustion?**
  **A:** `find_free_port()` asks the OS for a **free port** to avoid **collisions**, then websockify binds to it. This is **not** about "port exhaustion" of client ephemeral ports—just safe server‑side port selection per VM.

* **Q: How is cleanup triggered when a user closes the browser tab?**
  **A:** The websockify monitor thread watches stdout for disconnect lines (e.g., "client closed connection"). On detection, it calls `cleanup_vm(vmid, store)`. For multiple open tabs, consider tracking a **connection count** or adding a short **grace period** before teardown so the last connection drives cleanup.

* **Q: What is QMP used for in this setup?**
  **A:** QMP is the **management plane**. Use it for graceful operations (e.g., `system_powerdown`), querying VM status, or debugging. In cleanup, you may first send a QMP powerdown, then fall back to `SIGTERM` if needed.

* **Q: Security best practices?**
  **A:** Bind websockify to **127.0.0.1**, front it with an HTTPS reverse proxy to serve **WSS** with auth, never expose **QMP** externally, and firewall any `0.0.0.0:<port>` listeners if you must use them.

* **Q: What minimal fields must be stored in Redis for reliable lifecycle management?**
  **A:** `vmid`, `user_id`, `os_type`, `overlay` (or `iso` for custom), `vnc_socket`, `qmp_socket`, `http_port`, **`pid` (QEMU)**, **`websockify_pid`**, `started_at`, and optionally `last_seen`.

## Appendix: Sequence (text diagram): Sequence (text diagram)

```
Client → /run-script
API   → SessionStore: check existing
API   → OverlayMgr.create_overlay (if non-custom)
API   → OverlayMgr.boot_vm → QEMU (daemon) + sockets + PID
API   → Websockify.start(target=vnc.sock) → alloc TCP port + Popen + monitor thread
API   → SessionStore.set(meta + http_port)
API   → redirect to /ws/<port>
Browser ↔ websockify ↔ VNC UNIX socket ↔ QEMU
websockify monitor: on disconnect → utils.cleanup_vm(vmid)
cleanup_vm: TERM websockify + QEMU, delete overlay/ISO, remove sockets, SessionStore.delete
```

---

**End of document.**
