---
title: VM Lifecycle
layout: default
permalink: /lifecycle/
---



# Virtual Machine Lifecycle

> **Scope:** Single-VM-per-user flow from launch to cleanup for the QEMU + noVNC/websockify stack. This document explains components, data flow, Redis schema, lifecycle steps, concurrency, and failure/cleanup behavior. 

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

---

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

## Concurrency & Observability

* **Threaded monitor**: The websockify stdout reader runs in a **daemon** thread per VM; it updates `last_seen` and triggers cleanup on disconnect or on process exit.
* **Registry**: `ProcRegistry` tracks `ws:<vmid> → Popen` so `WebsockifyService.stop(vmid)` can terminate it even if Redis lacks the `websockify_pid`.
* **Logging**: websockify is started with `--verbose`; QEMU launch success/failure is fully logged, including stderr.


# FAQs

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
---

## Appendix: Sequence (text diagram)

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
