# observability/metrics.py
import os
import asyncio
from collections import defaultdict
from datetime import datetime  # only for type completeness; not used now
from typing import Optional

import psutil
from fastapi import APIRouter, Response, HTTPException, Query
from fastapi.responses import JSONResponse
import httpx

from prometheus_client import (
    Gauge,
    REGISTRY,
    CONTENT_TYPE_LATEST,
    generate_latest,
)

from methods.database.database import SessionLocal
from methods.database.models import User
from methods.manager.SessionManager import get_session_store  # Redis-backed

# -----------------------
# Config
# -----------------------
# Point this at your Prometheus server (NOT an exporter):
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")

# -----------------------
# Prometheus metrics
# -----------------------
CPU_PCT       = Gauge("vmshare_host_cpu_percent", "Host CPU percent")
RAM_PCT       = Gauge("vmshare_host_ram_percent", "Host RAM percent")
USERS_TOTAL   = Gauge("vmshare_users_total", "Total registered users")
SESSIONS_CURR = Gauge("vmshare_active_sessions", "Active sessions (from Redis)")

# Per-user usage
USER_ACTIVE_VMS = Gauge(
    "vmshare_user_active_vms",
    "Active VMs per user",
    ["user_id"],
)
USER_CPU_PCT = Gauge(
    "vmshare_user_cpu_percent",
    "Sum of VM CPU percent for the user (host view)",
    ["user_id"],
)
USER_RSS_BYTES = Gauge(
    "vmshare_user_rss_bytes",
    "Sum of VM RSS bytes for the user",
    ["user_id"],
)

router = APIRouter()

# -----------------------
# Unified /metrics endpoint
# - No query params  -> return exporter text (for Prometheus scraping)
# - query=...        -> proxy to Prometheus /api/v1/query (JSON)
# - query_range      -> if start,end,step provided, call /api/v1/query_range
# -----------------------
@router.get("/metrics")
async def metrics(
    query: Optional[str] = Query(None, description="PromQL (instant)"),
    start: Optional[float] = Query(None, description="range start (unix seconds)"),
    end: Optional[float] = Query(None, description="range end (unix seconds)"),
    step: Optional[float] = Query(None, description="range step (seconds)"),
):
    # If no PromQL params -> return standard exposition text
    if query is None and start is None and end is None and step is None:
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    # Otherwise, proxy to Prometheus HTTP API and return JSON for the UI
    if query is None:
        raise HTTPException(status_code=400, detail="Missing 'query' parameter for Prometheus API")

    # Decide endpoint based on presence of range params
    use_range = start is not None and end is not None and step is not None
    api_path = "/api/v1/query_range" if use_range else "/api/v1/query"
    params = {"query": query}
    if use_range:
        params.update({"start": start, "end": end, "step": step})

    url = f"{PROM_URL.rstrip('/')}{api_path}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
        # Ensure JSON; if Prometheus is wrong target you'll get non-JSON
        try:
            data = r.json()
        except ValueError:
            # Fallback: show a helpful message including the first bytes
            snippet = (r.text or "")[:80]
            raise HTTPException(
                status_code=500,
                detail=f"Prometheus did not return JSON (check PROM_URL). First bytes: {snippet}"
            )
        return JSONResponse(status_code=r.status_code, content=data)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Prometheus unreachable: {e}")

# -----------------------
# Helpers
# -----------------------
def _as_text(v) -> str:
    """Normalize bytes/None/str to str."""
    if v is None:
        return ""
    return v.decode("utf-8", "ignore") if isinstance(v, (bytes, bytearray)) else str(v)

_QEMU_PREFIXES = ("qemu-system", "qemu-kvm")
_PROC_CACHE: dict[int, psutil.Process] = {}
_PREV_USERS: set[str] = set()

def _find_qemu_pid_by_vmid(vmid: str) -> Optional[int]:
    """Fallback: try to locate a qemu process whose cmdline contains the vmid."""
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
    """Cached psutil.Process with primed cpu_percent."""
    if pid in _PROC_CACHE:
        try:
            _ = _PROC_CACHE[pid].status()  # raises if not alive
            return _PROC_CACHE[pid]
        except Exception:
            _PROC_CACHE.pop(pid, None)
    try:
        pr = psutil.Process(pid)
        pr.cpu_percent(None)  # prime
        _PROC_CACHE[pid] = pr
        return pr
    except Exception:
        return None

def _clear_missing_user_series(seen_users: set[str]):
    """Remove series for users no longer active to avoid stale labels."""
    global _PREV_USERS
    for uid in list(_PREV_USERS - seen_users):
        try:
            USER_ACTIVE_VMS.remove(uid)
        except Exception:
            pass
        try:
            USER_CPU_PCT.remove(uid)
        except Exception:
            pass
        try:
            USER_RSS_BYTES.remove(uid)
        except Exception:
            pass
    _PREV_USERS = seen_users

def _to_int_or_none(s: str) -> Optional[int]:
    try:
        return int(s)
    except Exception:
        return None

# -----------------------
# Collector loop
# -----------------------
async def metrics_collector(_unused, stop_event: asyncio.Event, interval_sec: int = 15):
    """
    Scrape host metrics + users + sessions from Redis-backed SessionStore,
    and aggregate per-user VM CPU/RSS.
    """
    store = get_session_store()  # one store instance; pings in __init__
    psutil.cpu_percent(None)     # prime host CPU sampling

    while not stop_event.is_set():
        # ---- host ----
        CPU_PCT.set(psutil.cpu_percent(None))
        RAM_PCT.set(psutil.virtual_memory().percent)

        # ---- users (DB count only) ----
        try:
            with SessionLocal() as db:
                USERS_TOTAL.set(db.query(User).count())
        except Exception:
            # DB unavailable: skip quietly
            pass

        # ---- sessions (Redis) ----
        try:
            items = store.items()  # List[(vmid, dict)]
        except Exception:
            items = []

        SESSIONS_CURR.set(len(items))

        # ---- per-user aggregation ----
        per_user = defaultdict(lambda: {"vms": 0, "cpu": 0.0, "rss": 0})
        seen_users: set[str] = set()

        for vmid_raw, data in items:
            vmid = _as_text(vmid_raw)
            uid = _as_text(data.get("user_id")).strip() or "unknown"

            per_user[uid]["vms"] += 1
            seen_users.add(uid)

            # Prefer stored PID; fallback to search by vmid
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

        # publish per-user metrics
        for uid, agg in per_user.items():
            USER_ACTIVE_VMS.labels(user_id=uid).set(agg["vms"])
            USER_CPU_PCT.labels(user_id=uid).set(agg["cpu"])
            USER_RSS_BYTES.labels(user_id=uid).set(agg["rss"])

        _clear_missing_user_series(seen_users)

        # ---- sleep but wake immediately on shutdown ----
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_sec)
        except asyncio.TimeoutError:
            pass


@router.get("/metrics_json")
def metrics_json():
    """
    Return current metrics from the Python Prometheus REGISTRY as structured JSON.
    Useful for UI display without a Prometheus server.
    """
    families = []
    for mf in REGISTRY.collect():
        fam = {
            "name": mf.name,
            "type": mf.type,
            "documentation": getattr(mf, "documentation", "") or "",
            "samples": [],
        }
        for s in mf.samples:
            # s is a Sample(name, labels, value, timestamp, exemplar, metadata)
            fam["samples"].append({
                "name": s.name,
                "labels": s.labels,
                "value": s.value,
                "timestamp": s.timestamp,
            })
        families.append(fam)
    return JSONResponse(content={"status": "success", "data": families})