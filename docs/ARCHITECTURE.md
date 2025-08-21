## 1. Components (Detailed)

### API Service (FastAPI)
* **Role**: The entry point for clients (browser or CLI).  
* **Responsibilities**:  
  - Expose REST endpoints, grouped into domains:
    - **Auth** (`/auth/*`) → login, logout, registration, token refresh.
    - **VMs** (`/vm/*`) → communicate with websockify and qemu manager, returns booted VM ready to use via noVNC.
    - **Users** (`/sessions/*`) → tracks current active sessions and returns List object listing them.
    - **Pages** (`/pages/*`) → returns html templates for app pages.
    - **Post** (`/post/*`) → file upload with size limit
    - **Metrics** (`/metrics`) → Prometheus-compatible scrape.
  - Run background tasks for reconciliation, VM cleanup, and metrics collection.  
  - Authenticate users (JWT in cookies) and enforce per-user quotas.  
  - Validate requests before provisioning (security + resource limits).  
* **Why FastAPI?**  
  - Async-first (handles many concurrent requests efficiently).  
  - Built-in Pydantic validation for safer request parsing.  
  - Easy integration with Prometheus, PostgreSQL, Redis.  
* **Scaling**: Runs behind Nginx, can scale horizontally (multiple API pods/containers).  

---

### VM Manager
* **Role**: Orchestrates QEMU processes and communicates with them via **QMP** (QEMU Machine Protocol).  
* **Responsibilities**:  
  - Start and stop VMs using the correct QEMU command-line arguments.  
  - Create qcow2 overlays on top of base images.  
  - Monitor QEMU health (via process checks or QMP events).  
  - Gracefully shut down VMs (`system_powerdown`) or force kill if stuck.  
* **Why separate from API?**  
  - Encapsulation: isolates VM lifecycle logic.  
  - Keeps API lightweight and focused on HTTP logic.  
* **Scaling**: Each host runs its own VM Manager for local QEMU control.  

---

### noVNC + Websockify
* **Role**: Provides remote desktop access from the browser.  
* **Responsibilities**:  
  - Websockify bridges **WebSockets ⇆ VNC TCP**.  
  - noVNC renders the VNC stream inside the user’s browser.  
  - Ensures sessions are authenticated (JWT-based token mapped to VM).  
* **Why needed?**  
  - Browsers cannot speak VNC directly.  
  - WebSockets allow tunneling over HTTPS (works behind firewalls).  
* **Scaling**: Stateless — can scale horizontally. Nginx routes sessions to the correct Websockify instance.  

---

### Storage (qcow2-based)
* **Role**: Provide per-VM disk images without duplicating large base OS images.  
* **Responsibilities**:  
  - Store **base images** (`/var/vms/base/...`) — read-only.  
  - Create **per-VM overlays** (`/var/vms/users/<uid>/<vmid>.qcow2`).  
  - Allow optional **snapshots** (qcow2 backing chain).  
* **Why qcow2 overlays?**  
  - Efficient: no need to copy full base image.  
  - Supports copy-on-write and snapshots.  
* **Scaling**: Local disk for now; future plan — offload to object storage (S3/MinIO).  

---

### Nginx
* **Role**: The **front door** to the platform.  
* **Responsibilities**:  
  - TLS termination (ACME auto-renew).  
  - Path routing: `/api` → API service, `/vnc` → Websockify, `/static` → frontend.  
  - Apply rate limits and connection caps (per-IP / per-user).  
  - Serve static frontend assets.  
* **Why Nginx?**  
  - Mature, widely used, lightweight.  
  - Handles TLS and load balancing better than exposing FastAPI directly.  
* **Scaling**: Can run as multiple replicas behind a load balancer.  

---

### Postgres
* **Role**: Persistent metadata store.  
* **Responsibilities**:  
  - Store user accounts, authentication info, quotas, billing/usage records.  
  - Keep VM metadata (template IDs, overlay paths, ownership).  
* **Why Postgres?**  
  - ACID transactions (needed for auth + quotas).  
  - Strong ecosystem, reliable.  
* **Scaling**: Vertical scaling or managed Postgres (e.g., RDS, CloudSQL).  

---

### Redis
* **Role**: Ephemeral state + coordination.  
* **Responsibilities**:  
  - Store active session info (user ↔ VM mappings).  
  - Queue lifecycle operations (`provision`, `destroy`).  
  - Support reconciliation logic (desired vs. actual state).  
* **Why Redis?**  
  - Very fast for ephemeral data.  
  - Supports pub/sub and atomic operations for safe concurrent updates.  
* **Scaling**: Single-node in MVP; cluster mode for HA in production.  

---

### Prometheus + Grafana
* **Role**: Observability and monitoring.  
* **Responsibilities**:  
  - Prometheus scrapes `/metrics` from API service + node exporters.  
  - Tracks host-level (CPU, RAM, I/O) and per-user VM metrics.  
  - Grafana provides dashboards + alerting via Alertmanager.  
* **Why Prometheus?**  
  - Cloud-native monitoring standard.  
  - Works with FastAPI easily.  
* **Scaling**: Prometheus HA setups if needed (federation, Thanos, Cortex).  
