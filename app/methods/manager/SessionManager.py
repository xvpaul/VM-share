# /app/methods/manager/SessionManager.py
from __future__ import annotations
from typing import Optional, Dict, List, Tuple
import time
import redis
from configs.config import get_redis

def now_ms() -> int:
    return int(time.time() * 1000)

class SessionStore:
    """
    Redis-backed session store with the SAME interface you used before.
    Keys:
      vm:{vmid}            (HASH)  → flat fields
      vms:active           (SET)   → vmids
      user:{uid}:vms       (ZSET)  → vmid score=created_at (ms)
      vms:by_os:{os}       (SET)   → vmids  (only used if os_type present)
      vm:by_pid:{pid}      (STR)   → vmid (PID→VM reverse index)
    """
    def __init__(self, r: Optional[redis.Redis] = None) -> None:
        self.r = r or get_redis()
        # fail fast if Redis is not reachable
        self.r.ping()

    # ----- key helpers
    def _k_vm(self, vmid: str) -> str:           return f"vm:{vmid}"
    def _k_active(self) -> str:                   return "vms:active"
    def _k_user_vms(self, uid: str) -> str:       return f"user:{uid}:vms"
    def _k_by_os(self, os_type: str) -> str:      return f"vms:by_os:{os_type}"
    # PID index (pid → vmid)
    def _k_pid(self, pid: str) -> str:            return f"vm:by_pid:{pid}"

    # ----- API (compat)
    def get_running_by_user(self, user_id: str) -> Optional[dict]:
        # newest first; check a few recent entries
        for vmid in self.r.zrevrange(self._k_user_vms(user_id), 0, 5):
            d = self.get(vmid)
            if d:
                return {"vmid": vmid, **d}
        return None

    def get(self, vmid: str) -> Optional[dict]:
        h = self.r.hgetall(self._k_vm(vmid))
        return {"vmid": vmid, **h} if h else None

    # NEW: quick reverse lookups
    def get_vmid_by_pid(self, pid: str) -> Optional[str]:
        if not pid:
            return None
        vmid = self.r.get(self._k_pid(str(pid)))
        return vmid if vmid else None

    def get_by_pid(self, pid: str) -> Optional[dict]:
        vmid = self.get_vmid_by_pid(pid)
        return self.get(vmid) if vmid else None

    def set(self, vmid: str, payload: dict) -> None:
        # flatten & stringify for Redis
        data = {k: ("" if v is None else str(v)) for k, v in payload.items()}
        uid     = data.get("user_id")
        os_type = data.get("os_type")
        created = float(data.get("created_at") or now_ms())
        pid     = data.get("pid") or ""

        pipe = self.r.pipeline()
        pipe.hset(self._k_vm(vmid), mapping=data)
        pipe.sadd(self._k_active(), vmid)
        if uid:
            pipe.zadd(self._k_user_vms(uid), {vmid: created})
        if os_type:
            pipe.sadd(self._k_by_os(os_type), vmid)
        # Maintain PID → VMID index if pid present
        if pid:
            pipe.set(self._k_pid(pid), vmid)
        pipe.execute()

    def update(self, vmid: str, **fields) -> None:
        if not fields:
            return

        # If PID is being updated, swap the reverse index atomically
        new_pid = fields.get("pid")
        if new_pid is not None:
            new_pid = "" if new_pid is None else str(new_pid)

            # fetch old pid (if any)
            old_pid = self.r.hget(self._k_vm(vmid), "pid")
            old_pid = "" if old_pid is None else str(old_pid)

            pipe = self.r.pipeline()
            # update hash fields
            pipe.hset(self._k_vm(vmid), mapping={k: ("" if v is None else str(v)) for k, v in fields.items()})

            # remove old pid mapping if it existed and changed
            if old_pid and old_pid != new_pid:
                pipe.delete(self._k_pid(old_pid))
            # set new pid mapping if provided
            if new_pid:
                pipe.set(self._k_pid(new_pid), vmid)
            pipe.execute()
        else:
            # normal field update
            self.r.hset(self._k_vm(vmid), mapping={k: ("" if v is None else str(v)) for k, v in fields.items()})

    def delete(self, vmid: str) -> None:
        d = self.get(vmid) or {}
        uid     = d.get("user_id")
        os_type = d.get("os_type")
        pid     = d.get("pid") or ""

        pipe = self.r.pipeline()
        pipe.delete(self._k_vm(vmid))
        pipe.srem(self._k_active(), vmid)
        if uid:
            pipe.zrem(self._k_user_vms(uid), vmid)
        if os_type:
            pipe.srem(self._k_by_os(os_type), vmid)
        # remove PID reverse index
        if pid:
            pipe.delete(self._k_pid(str(pid)))
        pipe.execute()

    # ----- helpers (optional but handy for shutdown/inspection)
    def items(self) -> List[Tuple[str, Dict[str, str]]]:
        vmids = list(self.r.smembers(self._k_active()))
        out: List[Tuple[str, Dict[str, str]]] = []
        for vmid in vmids:
            d = self.get(vmid)
            if d:
                out.append((vmid, d))
        return out

# DI factory (unchanged signature)
def get_session_store() -> SessionStore:
    return SessionStore()
