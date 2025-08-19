# tests/resilience/test_vm_failures.py
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# import app the same way your tests do elsewhere
from main import app

# --- helpers --------------------------------------------------------

class FakeUser:
    def __init__(self, id="u-1", login="alice"):
        self.id = id
        self.login = login

def set_overrides(*, store, ws, user=None):
    # override dependencies in the same module where they're referenced
    from routers import vm as vm_mod
    app.dependency_overrides[vm_mod.get_current_user] = (lambda: user or FakeUser())
    app.dependency_overrides[vm_mod.get_db] = (lambda: object())
    app.dependency_overrides[vm_mod.get_session_store] = (lambda: store)
    app.dependency_overrides[vm_mod.get_websockify_service] = (lambda: ws)

def clear_overrides():
    app.dependency_overrides.clear()

# --- tests ----------------------------------------------------------

def test_run_script_redis_down_returns_500(monkeypatch):
    """
    Simulate Redis outage on the first call: get_running_by_user raises.
    Expect: 500, and NO boot attempt.
    """
    # stable host for redirect composition
    from configs import server_config
    monkeypatch.setattr(server_config, "SERVER_HOST", "127.0.0.1", raising=False)

    # store that fails immediately
    store = MagicMock()
    store.get_running_by_user.side_effect = ConnectionError("redis down")
    ws = MagicMock()

    set_overrides(store=store, ws=ws)

    # QemuOverlayManager must not be called if store already fails
    with patch("routers.vm.QemuOverlayManager") as MockMgr:
        client = TestClient(app)
        r = client.post("/api/run-script", json={"os_type": "debian"})
        assert r.status_code == 500
        MockMgr.assert_not_called()

    clear_overrides()


def test_run_script_ws_start_failure_yields_500_no_store_set(monkeypatch):
    """
    Boot succeeds (manager returns meta), but websockify start crashes.
    Expect: 500, and store.set was never called (no partial state).
    """
    from configs import server_config
    monkeypatch.setattr(server_config, "SERVER_HOST", "127.0.0.1", raising=False)
    monkeypatch.setattr("routers.vm.secrets.token_hex", lambda n: "deadbe", raising=False)

    store = MagicMock()
    ws = MagicMock()
    ws.start.side_effect = RuntimeError("websockify boom")

    # fake manager OK
    fake_mgr = MagicMock()
    fake_mgr.create_overlay.return_value = "/tmp/ovl.qcow2"
    fake_mgr.boot_vm.return_value = {"vnc_socket": "/tmp/vm.sock", "pid": 9999}

    set_overrides(store=store, ws=ws)
    with patch("routers.vm.QemuOverlayManager", return_value=fake_mgr):
        client = TestClient(app)
        r = client.post("/api/run-script", json={"os_type": "debian"})
        assert r.status_code == 500
        # no session persisted after failure
        store.set.assert_not_called()

    clear_overrides()


def test_run_script_idempotent_when_existing_session(monkeypatch):
    """
    If a session already exists, endpoint should return 200 with redirect
    and NOT create a new VM nor start websockify.
    """
    from configs import server_config
    monkeypatch.setattr(server_config, "SERVER_HOST", "127.0.0.1", raising=False)

    existing = {
        "vmid": "oldvm",
        "http_port": 7001,
        "vnc_host": "127.0.0.1",
        "vnc_port": 5901,
        "pid": 2222,
    }
    store = MagicMock()
    store.get_running_by_user.return_value = existing
    ws = MagicMock()

    set_overrides(store=store, ws=ws)
    with patch("routers.vm.QemuOverlayManager") as MockMgr:
        client = TestClient(app)
        r = client.post("/api/run-script", json={"os_type": "debian"})
        assert r.status_code == 200
        data = r.json()
        assert data["vm"]["vmid"] == "oldvm"
        MockMgr.assert_not_called()
        ws.start.assert_not_called()

    clear_overrides()


def test_cleanup_vm_is_idempotent_double_call(monkeypatch, tmp_path, caplog):
    """
    Calling cleanup twice shouldn't crash: first removes files, second logs missing and returns.
    """
    import utils

    # operate in a temp run dir
    monkeypatch.setattr(utils, "RUN_DIR", tmp_path, raising=False)

    # create overlay & sockets
    ovl = tmp_path / "ovl.qcow2"
    (tmp_path / "vnc-vmX.sock").write_text("")
    (tmp_path / "qmp-vmX.sock").write_text("")
    ovl.write_text("x")

    store = MagicMock()
    store.get.return_value = {
        "user_id": "u",
        "os_type": "debian",
        "overlay_path": str(ovl),
        "qemu_pid": None,
        "websockify_pid": None,
    }

    # neuter pkill
    monkeypatch.setattr(utils.subprocess, "run", lambda *a, **k: None, raising=False)

    utils.cleanup_vm("vmX", store)
    # second call: no session
    store.get.return_value = None
    utils.cleanup_vm("vmX", store)

    assert any("No active session" in r.message for r in caplog.records)
