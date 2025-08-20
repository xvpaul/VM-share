# tests/chaos/test_network_chaos.py
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app

class FakeUser: id="u"; login="net"

def set_deps(store, ws):
    from routers import vm as vm_mod
    app.dependency_overrides[vm_mod.get_current_user] = lambda: FakeUser
    app.dependency_overrides[vm_mod.get_session_store] = lambda: store
    app.dependency_overrides[vm_mod.get_websockify_service] = lambda: ws
    app.dependency_overrides[vm_mod.get_db] = lambda: object()

def clear(): app.dependency_overrides.clear()

def test_redis_flaps_during_set_returns_500_and_no_duplicates(monkeypatch):
    from configs import server_config
    monkeypatch.setattr(server_config, "SERVER_HOST", "127.0.0.1", raising=False)

    store = MagicMock()
    store.get_running_by_user.return_value = None
    # Fail the first set call, then succeed on retrying the endpoint
    calls = {"i": 0}
    def _fail_first(*a, **k):
        calls["i"] += 1
        if calls["i"] == 1:
            raise ConnectionError("redis connection lost")
    store.set.side_effect = _fail_first

    ws = MagicMock()
    ws.start.return_value = 7011

    fake_mgr = MagicMock()
    fake_mgr.create_overlay.return_value = "/tmp/ovl.qcow2"
    fake_mgr.boot_vm.return_value = {"vnc_socket": "/tmp/vm.sock", "pid": 1111}

    set_deps(store, ws)
    with patch("routers.vm.QemuOverlayManager", return_value=fake_mgr):
        c = TestClient(app)
        r1 = c.post("/api/run-script", json={"os_type":"debian"})
        assert r1.status_code == 500   # fail fast, no duplicate state
        r2 = c.post("/api/run-script", json={"os_type":"debian"})
        assert r2.status_code == 200   # recover OK
    clear()
