# tests/chaos/test_process_chaos.py
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from main import app

class FakeUser: 
    id = "u-chaos"; login = "chaos"

def _set_deps(store, ws):
    from routers import vm as vm_mod
    app.dependency_overrides[vm_mod.get_current_user] = lambda: FakeUser
    app.dependency_overrides[vm_mod.get_session_store] = lambda: store
    app.dependency_overrides[vm_mod.get_websockify_service] = lambda: ws
    app.dependency_overrides[vm_mod.get_db] = lambda: object()

def _clear(): app.dependency_overrides.clear()

def test_websockify_crash_during_launch_returns_500_and_no_state(monkeypatch):
    # deterministic host + vmid
    from configs import server_config
    monkeypatch.setattr(server_config, "SERVER_HOST", "127.0.0.1", raising=False)
    monkeypatch.setattr("routers.vm.secrets.token_hex", lambda n: "cafeba", raising=False)

    # Boot OK, then websockify blows up
    fake_mgr = MagicMock()
    fake_mgr.create_overlay.return_value = "/tmp/ovl.qcow2"
    fake_mgr.boot_vm.return_value = {"vnc_socket": "/tmp/vm.sock", "pid": 4242}

    store = MagicMock()
    ws = MagicMock()
    ws.start.side_effect = RuntimeError("websockify died")

    _set_deps(store, ws)
    with patch("routers.vm.QemuOverlayManager", return_value=fake_mgr):
        r = TestClient(app).post("/api/run-script", json={"os_type":"debian"})
        assert r.status_code == 500
        store.set.assert_not_called()      # no partial session persisted
    _clear()

def test_qemu_crash_after_launch_triggers_cleanup(monkeypatch):
    """
    Simulate QEMU pid exists then 'dies': cleanup_vm should remove overlay/sockets and delete session.
    """
    import utils
    from pathlib import Path
    run_tmp = Path("/tmp") / "qemu-chaos"
    run_tmp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(utils, "RUN_DIR", run_tmp, raising=False)

    overlay = run_tmp / "ovl.qcow2"
    overlay.write_text("x")
    (run_tmp / "vnc-xyz.sock").write_text("")
    (run_tmp / "qmp-xyz.sock").write_text("")

    store = MagicMock()
    store.get.return_value = {
        "user_id":"u", "os_type":"debian",
        "overlay_path": str(overlay),
        "qemu_pid": "99999", "websockify_pid": "88888",
    }

    killed = []
    monkeypatch.setattr(utils.os, "kill", lambda pid, sig: killed.append((int(pid), sig)), raising=False)
    monkeypatch.setattr(utils.subprocess, "run", lambda *a, **k: None, raising=False)

    # First cleanup simulates crash handling
    utils.cleanup_vm("xyz", store)
    assert (99999, 15) in killed and (88888, 15) in killed
    assert not overlay.exists()
    store.delete.assert_called_once_with("xyz")
