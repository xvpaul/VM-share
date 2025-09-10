# Authentication (Project Documentation)

> **Scope:** Username/password auth backed by PostgreSQL, using bcrypt for password hashing and JWT for sessions. This document covers components, data flow, cookie/JWT handling, endpoints and responses, validation, security considerations, and cleanup behavior.

---

## High‑level Overview

* **User store:** PostgreSQL via SQLAlchemy `User` model (at minimum: `id`, `login`, `hashed_password`, optional `role`).
* **Passwords:** Hashed with **bcrypt** using Passlib `CryptContext`.
* **Sessions:** Short‑lived **JWT** (`exp`, `sub=<login>`) issued on successful register/login.
* **Transport:** JWT is returned in JSON **and** set as an **HttpOnly, Secure, SameSite=Lax** cookie named `access_token`.
* **Auth on requests:** `get_current_user` resolves the token from **cookie** (preferred) or `Authorization: Bearer` header, verifies JWT, then loads the `User` from DB.
* **Bot protection:** reCAPTCHA is required for `/register`, `/login`, and `/token` flows.
* **Logout:** Deletes the auth cookie. Also attempts to terminate any active VM session for the user.

---

## Components

### API Layer (FastAPI routers)

* **`/app/routers/auth.py`**

  * `POST /register` — Create account, returns JWT and sets cookie.
  * `POST /login` — Authenticate, returns JWT and sets cookie.
  * `POST /token` — Alias of `/login` with a slightly different JSON shape; also sets cookie.
  * `POST /logout` — Delete cookie; if a VM is running, calls `cleanup_vm` and clears session.
  * `GET /me` — Returns authenticated user profile (`id`, `login`, `role`).
  * `GET /user_info` — Convenience: returns currently running VM info for the authenticated user.

### Auth Core

* **`/app/methods/auth/auth.py`**

  * `Authentification` (login/password wrapper) with:

    * `authenticate_user(db)` — fetch user by `login` and verify password.
    * `verify_password` / `hash_password` — bcrypt via Passlib.
    * `create_access_token(payload, expires)` — sign JWT with `exp` and `sub`.
    * `decode_access_token(token)` — verify and decode JWT.
  * `get_current_user(request)` — Extract JWT from cookie or header, verify, then fetch `User` from DB.

### Session/State Interop

* **Cookie management:** `set_auth_cookie(resp, token)` sets `access_token` as HttpOnly, Secure, SameSite=Lax with `COOKIE_MAX_AGE`.
* **VM tie‑in:** `/logout` uses `SessionStore.get_running_by_user` and `cleanup_vm` to tear down any active VM on sign‑out.

---

## Data Model (PostgreSQL)

**User (users table)**

* `id: Integer` — PK, indexed
* `login: String` — unique, indexed, **NOT NULL**
* `hashed_password: String` — **NOT NULL**, bcrypt hash via Passlib
* `snapshot_storage_capacity: Integer` — **NOT NULL**, default **300** (units: app-defined; e.g., MB/GB)
* `snapshot_stored: Integer` — **NOT NULL**, default **0**
* `role: String` — **NOT NULL**, default **'user'**

**Constraints**

* `users_cap_nonneg`: `snapshot_storage_capacity >= 0`
* `users_stored_nonneg`: `snapshot_stored >= 0`
* `users_stored_le_cap`: `snapshot_stored <= snapshot_storage_capacity`


## End‑to‑End Flows

### 1) Register (`POST /register`)

1. Verify **reCAPTCHA** for the client IP.
2. Validate `login` & `password` are present.
3. **Uniqueness check** on `login`.
4. Hash password with bcrypt; insert new user into Database.
5. Issue **JWT** with claims `{ sub: <login>, exp: now + ACCESS_TOKEN_EXPIRE_MINUTES }`.
6. Return JSON `{ message, id, access_token, token_type }` and set **auth cookie**.

### 2) Login (`POST /login`) / Token alias (`POST /token`)

1. Verify **reCAPTCHA**.
2. Look up user at Database by `login`/`username`; verify password via bcrypt.
3. Issue **JWT** as above.
4. Return JSON with token and set **auth cookie**.

### 3) Authenticated requests

* `get_current_user` extracts token from **cookie**, verifies signature and `exp`, extracts `sub=login`, fetches user from DB, and injects it into the route.

### 4) Logout (`POST /logout`)

* Delete `access_token` cookie (path `/`).
* If a VM is running for the user, call `cleanup_vm(vmid, store)` and remove session keys.

---

## Cookie & JWT Handling

* **Cookie:** `HttpOnly`, `Secure`, `SameSite=Lax`, `path=/`, `max_age=COOKIE_MAX_AGE`.

* **JWT:** HS‑signed (JOSE), claims include at least:

  * `sub` — the user `login`.
  * `exp` — expiration instant.
* **Where tokens live:** Returned in JSON **and** cookie. The app prefers the cookie in `get_current_user`.
* **DB lookup per request:** After decoding the token, the user is fetched from DB to ensure existence and allow status checks.

---

## Validation & Errors

* **Missing credentials:** `400 Bad Request` with `"Missing login or password"` on register.
* **Invalid credentials:** `401 Unauthorized` on login.
* **User exists:** `409 Conflict` on register when `login` already exists.
* **JWT issues:** `401 Unauthorized` for invalid/expired tokens; `500` on unexpected errors.

---

## Security Considerations

* **Password hashing:** bcrypt via Passlib `CryptContext`.
* **Bot protection:** reCAPTCHA check on register/login/token.
* **Cookie safety:** HttpOnly to block JS access; Secure to require HTTPS; SameSite=Lax to mitigate CSRF on top‑level navigations.
* **CSRF:** Because you accept cookie auth, add a CSRF token for **state‑changing** endpoints if they can be triggered cross‑site, or require `Authorization: Bearer` for such endpoints. Lax helps but is not a complete CSRF defense.
* **Brute force / enumeration:** Add rate limiting and uniform error messages to avoid revealing whether a username exists.
* **Logout semantics:** Deleting the cookie signs the user out on this device. JWTs remain valid until `exp`; for hard revocation, store a `jti` and use a deny‑list in Redis (optional enhancement).
* **Quotas (snapshots):** The database **enforces non‑negative values and capacity limits**. Add matching **application‑level checks** before modifying `snapshot_stored` to return friendly errors instead of 500s on constraint violations.

---

## FAQs

* **Q: Cookie or Authorization header—which does the app use?**
  **A:** Both are accepted. `get_current_user` prefers the **cookie** (`access_token`) and falls back to the `Authorization: Bearer` header.

* **Q: Why JWT + cookie instead of localStorage?**
  **A:** The **HttpOnly** cookie prevents JavaScript access (mitigates XSS token theft). You still get stateless auth with JWT expiration.

* **Q: Does logout revoke the JWT server‑side?**
  **A:** No, it deletes the cookie. The JWT remains valid until `exp`. For true revocation, add a **deny‑list** using `jti`.

* **Q: Why does `/register` return 409 when a user already exists?**
  **A:** To avoid **user enumeration** and password probing. Registration should not confirm credential validity for existing accounts.

* **Q: What about CSRF?**
  **A:** SameSite=Lax reduces risk, but for POST/DELETE that can be cross‑site, add a **CSRF token** or require `Authorization: Bearer` headers.

* **Q: How are snapshot limits enforced?**
  **A:** At the **database level** via three check constraints: non‑negative capacity, non‑negative stored, and `stored ≤ capacity`. The application should also validate before updates (e.g., when creating or pruning VM snapshots) and return a clear 4xx if a request would exceed the quota.

* **Q: What are the defaults for new users?**
  **A:** `snapshot_storage_capacity=300`, `snapshot_stored=0`, `role='user'` (all via DB `server_default`). These can be changed later via admin flows or migrations.

## Appendix: Sequence (text diagram): Sequence (text diagram)

```
Client → POST /register (login, password, reCAPTCHA)
API   → validate + hash → insert user → JWT → set HttpOnly cookie → 200

Client → POST /login (login, password, reCAPTCHA)
API   → verify creds → JWT → set HttpOnly cookie → 200

Client → Authenticated request
API   → read cookie / Bearer → verify JWT → load User from DB → 200

Client → POST /logout
API   → delete cookie → cleanup VM (if any) → 200
```

---

**End of document.**
