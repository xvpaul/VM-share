# tests/conftest.py
import pytest
from datetime import datetime, timedelta
from typing import Dict, Optional
import os, sys
from pathlib import Path

# repo root = folder that contains both `app/` and `tests/`
REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"

# Make `from main import app` and `from routers...` work
sys.path.insert(0, str(APP_DIR))

# Make relative paths inside app/ (like "static") resolve correctly
os.chdir(APP_DIR)

class FakeSessionStore:
    """Mimics your SessionStore interface, backed by an in‑memory dict."""
    def __init__(self):
        self._b: Dict[str, dict] = {}

    def get_running_by_user(self, user_id: str) -> Optional[dict]:
        for vmid, sess in self._b.items():
            if sess.get("user_id") == user_id:
                return {"vmid": vmid, **sess}
        return None

    def get(self, vmid: str) -> Optional[dict]:
        data = self._b.get(vmid)
        return {"vmid": vmid, **data} if data else None

    def set(self, vmid: str, payload: dict) -> None:
        self._b[vmid] = dict(payload)

    def update(self, vmid: str, **fields):
        if vmid not in self._b:
            raise KeyError(vmid)
        self._b[vmid].update(fields)

    def delete(self, vmid: str) -> None:
        self._b.pop(vmid, None)

@pytest.fixture()
def fake_store():
    return FakeSessionStore()

@pytest.fixture()
def sample_session_payload():
    return {
        "user_id": "u-123",
        "os_type": "alpine",
        "overlay_path": "/tmp/qemu/ovl-u-123.qcow2",
        "created_at": datetime.now(datetime.timezone.utc).isoformat(),
        "vnc_port": 5903,
        "ws_port": 6080,
        "status": "starting",
    }
