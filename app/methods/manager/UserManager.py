# /app/methods/manager/UserManager.py

from typing import Dict, Optional

SESSIONS: Dict[str, dict] = {}
WEBSOCKIFY_PROCS: Dict[str, object] = {} 

class SessionStore:
    """
    Minimal wrapper around the global SESSIONS dict.
    Allows future migration to Redis/DB without touching router code.
    """
    def __init__(self, backing: Dict[str, dict]):
        self._b = backing

    def get_running_by_user(self, user_id: str) -> Optional[dict]:
        for vmid, sess in self._b.items():
            if sess.get("user_id") == user_id:
                return {"vmid": vmid, **sess}
        return None

    def get(self, vmid: str) -> Optional[dict]:
        data = self._b.get(vmid)
        return {"vmid": vmid, **data} if data else None

    def set(self, vmid: str, payload: dict) -> None:
        self._b[vmid] = payload

    def update(self, vmid: str, **fields) -> None:
        if vmid in self._b:
            self._b[vmid].update(fields)

    def delete(self, vmid: str) -> None:
        self._b.pop(vmid, None)


def get_session_store() -> SessionStore:
    """
    Returns a SessionStore wrapping the global SESSIONS dict.
    Later this can be swapped to a Redis/DB implementation.
    """
    return SessionStore(SESSIONS)
