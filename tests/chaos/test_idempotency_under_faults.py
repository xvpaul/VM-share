# tests/chaos/test_idempotency_under_faults.py
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app

class User: id="u-1"; login="idem"

def set_deps(store, ws):
    from routers import vm as vm_mod
    app.dependency_overrides[vm_mod.get_current_user] = lambda: User
    app.dependency_overrides[vm_mod.get_session_store] = lambda: store
    app.dependency_overrides[vm_mod.get_websockify_service] = lambda: ws
    app.dependency_overrides[vm_mod.get_db] = lambda: object()

def clear(): app.dependency_overrides.clear()

def test_run_script_retry_does_not_duplicate_vm(monkeypatch):
    # first attempt fails AFTER boot but BEFORE set (simulated by ws.start raising)
    store = MagicMock()
    store.get_running_by_user.return_value = None

    ws = MagicMock()
    ws.start.side_effect = [RuntimeError("boom"), 7002]  # fail, then succeed

    fake_mgr = MagicMock()
    fake_mgr.create_overlay.return_value = "/tmp/ovl.qcow2"
    fake_mgr.boot_vm.return_value = {"vnc_socket": "/tmp/vm.sock", "pid": 7}

    set_deps(store, ws)
    with patch("routers.vm.QemuOverlayManager", return_value=fake_mgr):
        c = TestClient(app)
        r1 = c.post("/api/run-script", json={"os_type":"debian"})
        assert r1.status_code == 500
        # On retry, BEFORE launching, code should see no persisted running session (since set failed)
        r2 = c.post("/api/run-script", json={"os_type":"debian"})
        assert r2.status_code == 200
        # Only one successful set call across both attempts
        assert store.set.call_count == 1
    clear()
