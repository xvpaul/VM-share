# /app/methods/manager/SessionManager.py
from __future__ import annotations
from typing import Dict, Optional
from threading import RLock

class SessionStore:
    """
    Dict-backed session store. Swap later for Redis while keeping the interface.
    """
    def __init__(self, backing: Dict[str, dict]) -> None:
        self._b = backing
        self._lock = RLock()

    def get_running_by_user(self, user_id: str) -> Optional[dict]:
        with self._lock:
            for vmid, sess in self._b.items():
                if sess.get("user_id") == user_id:
                    return {"vmid": vmid, **sess}
        return None

    def get(self, vmid: str) -> Optional[dict]:
        with self._lock:
            data = self._b.get(vmid)
            return {"vmid": vmid, **data} if data else None

    def set(self, vmid: str, payload: dict) -> None:
        with self._lock:
            self._b[vmid] = payload

    def update(self, vmid: str, **fields) -> None:
        with self._lock:
            if vmid in self._b:
                self._b[vmid].update(fields)

    def delete(self, vmid: str) -> None:
        with self._lock:
            self._b.pop(vmid, None)


SESSIONS: Dict[str, dict] = {}

def get_session_store() -> SessionStore:
    return SessionStore(SESSIONS)
