# /app/observability/metrics.py
import os
import asyncio
import atexit
from collections import defaultdict
from datetime import datetime
from typing import Optional

import psutil
from fastapi import APIRouter, Response, HTTPException, Query, Request
from fastapi.responses import JSONResponse
import httpx

from prometheus_client import (
    Gauge,
    REGISTRY,
    CONTENT_TYPE_LATEST,
    generate_latest,
    Counter,
    Histogram,
    CollectorRegistry,
)
from prometheus_client import multiprocess  # NEW

from methods.database.database import SessionLocal
from methods.database.models import User
from methods.manager.SessionManager import get_session_store  # Redis-backed

# -----------------------
# Registry / multiprocess
# -----------------------
def _get_registry():
    """
    Use a per-process CollectorRegistry with MultiProcessCollector
    when PROMETHEUS_MULTIPROC_DIR is set; otherwise use the global REGISTRY.
    """
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        reg = CollectorRegistry()
        multiprocess.MultiProcessCollector(reg)
        # Ensure shard is cleaned when this worker exits
        atexit.register(multiprocess.mark_process_dead, os.getpid())
        return reg
    return REGISTRY

REG = _get_registry()

# -----------------------
# Config
# -----------------------
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")

# -----------------------
# HTTP request metrics (middleware will fill these)
# -----------------------
REQ_LATENCY = Histogram(
    "vmshare_request_duration_seconds",
    "Request duration (seconds)",
    ["path", "method", "status"],
    registry=REG,
)
REQ_COUNT = Counter(
    "vmshare_requests_total",
    "Total HTTP requests",
    ["path", "method", "status"],
    registry=REG,
)

# -----------------------
# Prometheus metrics
# -----------------------
# In multiprocess, avoid summing host-level gauges across workers:
# either (a) only sample from a single 'leader' worker (recommended),
# or (b) set multiprocess_mode="max". We do (a) below via should_run_samplers().
CPU_PCT       = Gauge("vmshare_host_cpu_percent", "Host CPU percent", registry=REG)
RAM_PCT       = Gauge("vmshare_host_ram_percent", "Host RAM percent", registry=REG)
USERS_TOTAL   = Gauge("vmshare_users_total", "Total registered users", registry=REG)
SESSIONS_CURR = Gauge("vmshare_active_sessions", "Active sessions (from Redis)", registry=REG)

# Per-user usage (labels must stay low-cardinality)
USER_ACTIVE_VMS = Gauge(
    "vmshare_user_active_vms",
    "Active VMs per user",
    ["user_id"],
    registry=REG,
)
USER_CPU_PCT = Gauge(
    "vmshare_user_cpu_percent",
    "Sum of VM CPU percent for the user (host view)",
    ["user_id"],
    registry=REG,
)
USER_RSS_BYTES = Gauge(
    "vmshare_user_rss_bytes",
    "Sum of VM RSS bytes for the user",
    ["user_id"],
    registry=REG,
)

router = APIRouter()

# -----------------------
# /metrics endpoint (scrape or proxy)
# -----------------------
@router.get("/metrics")
async def metrics(
    query: Optional[str] = Query(None, description="PromQL (instant)"),
    start: Optional[float] = Query(None, description="range start (unix seconds)"),
    end: Optional[float] = Query(None, description="range end (unix seconds)"),
    step: Optional[float] = Query(None, description="range step (seconds)"),
):
    # No PromQL params -> expose local metrics
    if query is None and start is None and end is None and step is None:
        return Response(generate_latest(REG), media_type=CONTENT_TYPE_LATEST)

    # Otherwise proxy to Prometheus HTTP API (for your UI)
    if query is None:
        raise HTTPException(status_code=400, detail="Missing 'query' parameter for Prometheus API")

    use_range = start is not None and end is not None and step is not None
    api_path = "/api/v1/query_range" if use_range else "/api/v1/query"
    params = {"query": query}
    if use_range:
        params.update({"start": start, "end": end, "step": step})

    url = f"{PROM_URL.rstrip('/')}{api_path}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
        try:
            data = r.json()
        except ValueError:
            snippet = (r.text or "")[:80]
            raise HTTPException(
                status_code=500,
                detail=f"Prometheus did not return JSON (check PROM_URL). First bytes: {snippet}"
            )
        return JSONResponse(status_code=r.status_code, content=data)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Prometheus unreachable: {e}")

# -----------------------
# HTTP middleware installer
# -----------------------
def install_http_metrics(app):
    @app.middleware("http")
    async def _metrics_middleware(request: Request, call_next):
        path = getattr(request.scope.get("route"), "path", request.url.path)
        method = request.method
        import time
        start = time.perf_counter()
        try:
            resp = await call_next(request)
            elapsed = time.perf_counter() - start
            status = str(resp.status_code)
            REQ_LATENCY.labels(path=path, method=method, status=status).observe(elapsed)
            REQ_COUNT.labels(path=path, method=method, status=status).inc()
            return resp
        except Exception:
            REQ_COUNT.labels(path=path, method=method, status="500").inc()
            REQ_LATENCY.labels(path=path, method=method, status="500").observe(0.0)
            raise

# -----------------------
# Helpers (unchanged except where noted)
# -----------------------
def _as_text(v) -> str:
    if v is None:
        return ""
    return v.decode("utf-8", "ignore") if isinstance(v, (bytes, bytearray)) else str(v)

_QEMU_PREFIXES = ("qemu-system", "qemu-kvm")
_PROC_CACHE: dict[int, psutil.Process] = {}
_PREV_USERS: set[str] = set()

def _find_qemu_pid_by_vmid(vmid: str) -> Optional[int]:
    try:
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            name = (p.info.get("name") or "")
            if not name.startswith(_QEMU_PREFIXES):
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            if vmid and vmid in cmd:
                return int(p.info["pid"])
    except Exception:
        pass
    return None

def _get_proc(pid: int) -> Optional[psutil.Process]:
    if pid in _PROC_CACHE:
        try:
            _ = _PROC_CACHE[pid].status()
            return _PROC_CACHE[pid]
        except Exception:
            _PROC_CACHE.pop(pid, None)
    try:
        pr = psutil.Process(pid)
        pr.cpu_percent(None)
        _PROC_CACHE[pid] = pr
        return pr
    except Exception:
        return None

def _clear_missing_user_series(seen_users: set[str]):
    global _PREV_USERS
    for uid in list(_PREV_USERS - seen_users):
        for g in (USER_ACTIVE_VMS, USER_CPU_PCT, USER_RSS_BYTES):
            try:
                g.remove(uid)
            except Exception:
                pass
    _PREV_USERS = seen_users

def _to_int_or_none(s: str) -> Optional[int]:
    try:
        return int(s)
    except Exception:
        return None

def should_run_samplers() -> bool:
    """
    Run background samplers in single-process OR when METRICS_LEADER=1.
    This prevents double-counting host gauges in multiprocess deployments.
    """
    if "PROMETHEUS_MULTIPROC_DIR" not in os.environ:
        return True
    return os.getenv("METRICS_LEADER") == "1"

# -----------------------
# Collector loop (unchanged logic)
# -----------------------
async def metrics_collector(_unused, stop_event: asyncio.Event, interval_sec: int = 15):
    store = get_session_store()
    psutil.cpu_percent(None)

    while not stop_event.is_set():
        # Host
        try:
            CPU_PCT.set(psutil.cpu_percent(None))
            RAM_PCT.set(psutil.virtual_memory().percent)
        except Exception:
            pass

        # Users
        try:
            with SessionLocal() as db:
                USERS_TOTAL.set(db.query(User).count())
        except Exception:
            pass

        # Sessions
        try:
            items = store.items()
        except Exception:
            items = []
        SESSIONS_CURR.set(len(items))

        # Per-user agg
        per_user = defaultdict(lambda: {"vms": 0, "cpu": 0.0, "rss": 0})
        seen_users: set[str] = set()

        for vmid_raw, data in items:
            vmid = _as_text(vmid_raw)
            uid = _as_text(data.get("user_id")).strip() or "unknown"

            per_user[uid]["vms"] += 1
            seen_users.add(uid)

            pid_txt = _as_text(data.get("pid"))
            pid = _to_int_or_none(pid_txt) if pid_txt else None
            if pid is None:
                pid = _find_qemu_pid_by_vmid(vmid)

            if pid:
                pr = _get_proc(pid)
                if pr:
                    try:
                        per_user[uid]["cpu"] += pr.cpu_percent(None)
                        per_user[uid]["rss"] += pr.memory_info().rss
                    except Exception:
                        pass

        for uid, agg in per_user.items():
            USER_ACTIVE_VMS.labels(user_id=uid).set(agg["vms"])
            USER_CPU_PCT.labels(user_id=uid).set(agg["cpu"])
            USER_RSS_BYTES.labels(user_id=uid).set(agg["rss"])

        _clear_missing_user_series(seen_users)

        # Sleep with interrupt
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass

@router.get("/metrics_json")
def metrics_json():
    families = []
    for mf in REG.collect():  # <-- use REG
        fam = {
            "name": mf.name,
            "type": mf.type,
            "documentation": getattr(mf, "documentation", "") or "",
            "samples": [],
        }
        for s in mf.samples:
            families.append if False else None  # keep linter calm
            fam["samples"].append({
                "name": s.name,
                "labels": s.labels,
                "value": s.value,
                "timestamp": s.timestamp,
            })
        families.append(fam)
    return JSONResponse(content={"status": "success", "data": families})
