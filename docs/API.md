---
title: API Reference
layout: default
permalink: /api/
---


# API Reference

> **Scope:** Public and authenticated HTTP endpoints for authentication, pages, file upload, sessions, VM lifecycle, and snapshots. Includes request/response schemas, status codes, auth requirements, and notable behaviors based on current code.

---

## Conventions

* **Base URL:** relative paths shown (e.g., `/login`). Prefix with your host (e.g., `https://example.com/login`).
* **Auth:** Unless stated otherwise, endpoints that depend on `get_current_user` accept **either**:

  * HttpOnly cookie `access_token`, **or**
  * `Authorization: Bearer <JWT>` header.
* **Content types:** JSON unless noted; file uploads use `multipart/form-data`.
* **Errors:** FastAPI style `{ "detail": "..." }` for `HTTPException`s; success payloads use `{ "message": "...", ... }` where implemented.
* **reCAPTCHA:** Required on `/register`, `/login`, `/token`.

---

## Authentication

### POST `/register`

Create a new account.

**Body**

```json
{
  "login": "alice",
  "password": "s3cret",
  "g_recaptcha_response": "<token>"
}
```

**Responses**

* `200 OK`

  ```json
  {
    "message": "User registered",
    "id": 42,
    "access_token": "<jwt>",
    "token_type": "bearer"
  }
  ```

  Sets `access_token` as HttpOnly, Secure, SameSite=Lax cookie.
* `400 Bad Request` — missing login or password.
* `409 Conflict` — **User exists** **(see note below)**.
* `401 Unauthorized` — **User exists, wrong password** (**current behavior; see note**).
* `500 Internal Server Error` — unexpected.

> **Note (current behavior):** If the user already exists, the implementation checks the provided password:
>
> * If it matches, returns **409** `"User exists"`.
> * If it does not, returns **401** `"User exists, wrong password"`.
>   This leaks account existence; recommended to always return **409** without checking the password.

---

### POST `/login`

Exchange credentials for a JWT (and cookie).

**Body**

```json
{
  "username": "alice",
  "password": "s3cret",
  "g_recaptcha_response": "<token>"
}
```

**Responses**

* `200 OK`

  ```json
  {
    "message": "Login successful",
    "id": 42,
    "access_token": "<jwt>",
    "token_type": "bearer"
  }
  ```

  Sets `access_token` cookie.
* `401 Unauthorized` — invalid username or password.
* `500 Internal Server Error` — unexpected.

---

### POST `/token`

Alias of `/login` with a slightly different response body.

**Body** — same as `/login`.

**Responses**

* `200 OK`

  ```json
  { "access_token": "<jwt>", "token_type": "bearer", "id": 42 }
  ```

  Sets `access_token` cookie.
* `401`, `500` as above.

---

### POST `/logout`

Clear the auth cookie and terminate any active VM for the user.

**Auth required**

**Responses**

* `200 OK`

  ```json
  { "message": "Logged out" }
  ```

> Notes:
>
> * Deletes `access_token` cookie (`path=/`).
> * If a VM is active, calls `cleanup_vm(vmid, store)` and removes the session.

---

### GET `/me`

Return the authenticated user profile.

**Auth required**

**Response**

```json
{ "id": 42, "login": "alice", "role": "user" }
```

---

### GET `/user_info`

Return the current user’s active VM info (if any).

**Auth required**

**Response**

```json
{ "os_type": "ubuntu", "vmid": "ab12cd34ef56" }
```

If no VM: `{ "os_type": null, "vmid": null }`.

---

## Pages (HTML)

### GET `/signup`

Serve the signup page. **Public**.

### GET `/profile`

Serve the profile page. **Public** (no auth enforced in router).

> If you intend `/profile` to be private, add `Depends(get_current_user)`.

---

## Files & Uploads

### POST `/api/post`

Upload a **custom ISO** file for the authenticated user. Saves to a resolved path based on `VM_PROFILES["custom"]`.

**Auth required**

**Request**

* `multipart/form-data` with `file` field (ISO content).

**Behavior**

* Builds destination path using `custom.base_image` and optional `prefix` (template supports `{uid}`).
* Ensures `.iso` suffix.
* Streams to disk with a hard size cap `MAX_ISO_BYTES`.

**Responses**

* `200 OK`

  ```json
  {
    "message": "ISO uploaded",
    "user_id": "42",
    "iso_path": "/path/to/uid.iso",
    "size": 123456789
  }
  ```
* `413 Payload Too Large` — file exceeds `MAX_ISO_BYTES`.
* `500 Internal Server Error` — misconfiguration or unexpected error.

> Security note: The response includes a server filesystem path. If you don’t want to expose paths publicly, return a logical handle instead.

---

### POST `/feedback`

Send feedback from an authenticated user. Forwards HTML‑escaped content to Telegram.

**Auth required**

**Body**

```json
{ "message": "text..." }
```

*or*

```json
{ "text": "text..." }
```

**Responses**

* `200 OK` → `{ "ok": true }`
* `400 Bad Request` — message missing/blank.

---

## Sessions

### GET `/sessions/active`

List active VM sessions. **Public** (no auth). Returns only fields in server‑side `EXPOSE_FIELDS`.

**Query params**

* `limit` (int, 1–1000, default 100) — maximum items.
* `user_id` (string, optional) — filter by user id.

**Response**

```json
[
  { "vmid": "ab12cd...", /* plus keys from EXPOSE_FIELDS */ },
  { "vmid": "cd34ef..." }
]
```

> Sorted by `created_at` (desc) if available.

---

## VM Lifecycle

### POST `/run-script`

Launch a VM from a **profile overlay**.

**Auth required**

**Body**

```json
{ "os_type": "ubuntu" }
```

**Responses**

* `200 OK` (new VM)

  ```json
  {
    "message": "VM for user alice launched (vmid=ab12cd)",
    "vm": {
      "vmid": "ab12cd",
      "user_id": "42",
      "os_type": "ubuntu",
      "overlay": "/path/overlay.qcow2",
      "vnc_socket": "/run/vms/vnc-ab12cd.sock",
      "qmp_socket": "/run/vms/qmp-ab12cd.sock",
      "started_at": "2025-09-10T10:00:00Z",
      "pid": 12345
    },
    "redirect": "/ws/59001"
  }
  ```
* `200 OK` (VM already running for user)

  ```json
  {
    "message": "VM already running for user alice",
    "vm": { /* existing session meta */ },
    "redirect": "/ws/<existing_http_port>"
  }
  ```
* `500 Internal Server Error` — launch failure.

---

### POST `/run-iso`

Launch a VM for the current user **from a custom ISO** (no overlay). Assumes the ISO has already been uploaded to the resolved path.

**Auth required**

**Behavior**

* Resolves ISO path from `VM_PROFILES["custom"]` (`base_image`, optional `prefix`).
* Validates file exists, is not a directory, and size ≥ 1 MiB.
* Boots QEMU, starts websockify, persists session.

**Responses**

* `200 OK` — same shape as `/run-script`, with `os_type: "custom"` and `redirect` including `reconnect=1&reconnect_delay=1500`.
* `404 Not Found` — ISO missing/invalid.
* `500 Internal Server Error` — unexpected.

---

## Snapshots & Quota

### POST `/snapshot`

Create a disk snapshot for the currently running VM and update quota usage.

**Auth required**

**Body**

```json
{ "os_type": "ubuntu", "vmid": "ab12cd" }
```

`vmid` optional; if omitted, the current running VM for the user is used.

**Behavior**

* Reads user quota from DB: `snapshot_storage_capacity` (cap MB), `snapshot_stored` (used MB).
* Determines **charge size**:

  * If overlay exists → charge **base\_image + overlay** (on‑disk allocated bytes).
  * Else → charge existing snapshot file size for this VM.
* If `used + charge > cap` →  `413 Payload Too Large` with a descriptive message.
* On success, creates snapshot (e.g., qcow2), persists new `snapshot_stored` in DB.

**Responses**

* `200 OK`

  ```json
  {
    "status": "ok",
    "snapshot": "42__ubuntu__ab12cd.qcow2",
    "path": "/snapshots/42__ubuntu__ab12cd.qcow2",
    "size_mb": 512,
    "charged_from": "base+overlay",
    "total_mb": 1024,
    "cap_mb": 2048
  }
  ```
* `400 Bad Request` — missing `os_type`.
* `404 Not Found` — no running VM or user not found.
* `409 Conflict` — neither overlay nor prior snapshot to base size on.
* `413 Payload Too Large` — over quota.
* `500 Internal Server Error` — snapshot error or unexpected.

---

### POST `/run_snapshot`

Boot a VM directly **from a snapshot image**.

**Auth required**

**Body**

```json
{ "os_type": "ignored", "snapshot": "42__ubuntu__ab12cd.qcow2" }
```

Note: `os_type` is present in the model but unused here; the server parses it from the snapshot name.

**Behavior**

* Parses `<userId>__<os_type>__<vmid>.qcow2` into `user_id`, `os_type`, `vmid`.
* Validates the snapshot file exists (absolute or under `SNAPSHOTS_PATH`).
* Boots QEMU with `drive_path=snapshot` (no overlay), starts websockify, persists session.

**Responses**

* `200 OK` — same shape as `/run-script`.
* `400 Bad Request` — missing `snapshot`.
* `404 Not Found` — snapshot file not found.
* `500 Internal Server Error` — unexpected.

---

### GET `/get_user_snapshots`

List snapshot files belonging to the authenticated user.

**Auth required**

**Response**

```json
[
  {
    "name": "42__ubuntu__ab12cd.qcow2",
    "os_type": "ubuntu",
    "vmid": "ab12cd",
    "size_mb": 123.45,
    "modified": "2025-09-10T10:00:00Z",
    "path": "/snapshots/42__ubuntu__ab12cd.qcow2"
  }
]
```

**Behavior**

* Scans `SNAPSHOTS_PATH` for files starting with `<user.id>__`.
* Sorts by `modified` (desc).

---

### POST `/remove_snapshot`

Remove a snapshot file and decrement the user’s stored quota.

**Auth required**

**Body (either)**

```json
{ "snapshot": "42__ubuntu__ab12cd.qcow2" }
```


**Responses**

* `200 OK`

  ```json
  { "status": "ok", "removed": true, "snapshot": "42__ubuntu__ab12cd.qcow2", "freed_mb": 512, "total_mb": 256 }
  ```
* `200 OK` (file not found): `{ "status": "ok", "removed": false, ... }`
* `400 Bad Request` — neither `snapshot` nor (`os_type` + `vmid`) provided.
* `404 Not Found` — user not found.
* `500 Internal Server Error` — unlink failure or unexpected.

