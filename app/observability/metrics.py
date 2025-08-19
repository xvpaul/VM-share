# observability/metrics.py
import asyncio
from collections import defaultdict
from datetime import datetime  # only for type completeness; not used now
from typing import Optional

import psutil
from fastapi import APIRouter, Response
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

@router.get("/metrics")
def prometheus_metrics():
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

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
