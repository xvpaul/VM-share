# /app/methods/manager/SessionManager.py
from __future__ import annotations
from typing import Optional, Dict, List, Tuple
import time
import redis
from configs.redis_config import get_redis

def now_ms() -> int:
    return int(time.time() * 1000)

class SessionStore:
    """
    Redis-backed session store with the SAME interface you used before.
    Keys:
      vm:{vmid}           (HASH)  → flat fields
      vms:active          (SET)   → vmids
      user:{uid}:vms      (ZSET)  → vmid score=created_at (ms)
      vms:by_os:{os}      (SET)   → vmids  (only used if os_type present)
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

    # ----- API (compat)
    def get_running_by_user(self, user_id: str) -> Optional[dict]:
        # newest first; check a few recent entries
        for vmid in self.r.zrevrange(self._k_user_vms(user_id), 0, 5):
            d = self.get(vmid)
            if d and d.get("state") == "running":
                return {"vmid": vmid, **d}
        return None

    def get(self, vmid: str) -> Optional[dict]:
        h = self.r.hgetall(self._k_vm(vmid))
        return {"vmid": vmid, **h} if h else None

    def set(self, vmid: str, payload: dict) -> None:
        # flatten & stringify for Redis
        data = {k: ("" if v is None else str(v)) for k, v in payload.items()}
        uid     = data.get("user_id")
        os_type = data.get("os_type")
        created = float(data.get("created_at") or now_ms())

        pipe = self.r.pipeline()
        pipe.hset(self._k_vm(vmid), mapping=data)
        pipe.sadd(self._k_active(), vmid)
        if uid:
            pipe.zadd(self._k_user_vms(uid), {vmid: created})
        if os_type:
            pipe.sadd(self._k_by_os(os_type), vmid)
        pipe.execute()

    def update(self, vmid: str, **fields) -> None:
        if not fields:
            return
        self.r.hset(self._k_vm(vmid), mapping={k: ("" if v is None else str(v)) for k, v in fields.items()})

    def delete(self, vmid: str) -> None:
        d = self.get(vmid) or {}
        uid     = d.get("user_id")
        os_type = d.get("os_type")
        pipe = self.r.pipeline()
        pipe.delete(self._k_vm(vmid))
        pipe.srem(self._k_active(), vmid)
        if uid:
            pipe.zrem(self._k_user_vms(uid), vmid)
        if os_type:
            pipe.srem(self._k_by_os(os_type), vmid)
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
