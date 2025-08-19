# # tests/test_vm_run_script.py
# import json
# from unittest.mock import MagicMock, patch
# from fastapi.testclient import TestClient

# # Import the FastAPI app from inside "app" folder, matching your import style.
# from main import app

# # --- Fixtures / helpers ------------------------------------------------------

# class FakeUser:
#     def __init__(self, id="u-1", login="tester"):
#         self.id = id
#         self.login = login

# class FakeStore:
#     def __init__(self, existing=None):
#         self._existing = existing
#         self.set_calls = []
#     def get_running_by_user(self, user_id: str):
#         return self._existing
#     def set(self, vmid, payload: dict):
#         self.set_calls.append((vmid, payload))

# def override_user():
#     return FakeUser(id="42", login="alice")

# def override_db():
#     return object()  # not used here

# def override_store(existing=None):
#     st = FakeStore(existing)
#     return st

# class FakeWS:
#     def __init__(self, http_port=6080):
#         self.http_port = http_port
#         self.start_calls = []
#     def start(self, vmid, target):
#         self.start_calls.append((vmid, target))
#         return self.http_port

# # Apply dependency overrides per-test so each is isolated
# def setup_overrides(app, *, user=None, store=None, ws=None):
#     from routers import vm as vm_router_mod
#     app.dependency_overrides[vm_router_mod.get_current_user] = (user or override_user)
#     app.dependency_overrides[vm_router_mod.get_db] = override_db
#     app.dependency_overrides[vm_router_mod.get_session_store] = (lambda: store)
#     app.dependency_overrides[vm_router_mod.get_websockify_service] = (lambda: ws)

# def clear_overrides(app):
#     app.dependency_overrides.clear()

# # --- Tests -------------------------------------------------------------------

# def test_run_script_returns_existing_without_boot(monkeypatch):
#     # Make SERVER_HOST deterministic for redirect URL
#     from configs import server_config
#     monkeypatch.setattr(server_config, "SERVER_HOST", "127.0.0.1", raising=False)

#     existing = {
#         "vmid": "vm-old",
#         "http_port": 7001,
#         "vnc_host": "127.0.0.1",
#         "vnc_port": 5901,
#         "pid": 2222,
#     }

#     store = override_store(existing=existing)
#     ws = FakeWS()
#     setup_overrides(app, store=store, ws=ws)

#     # Patch QemuOverlayManager so we can assert it is NOT used
#     with patch("routers.vm.QemuOverlayManager") as MockMgr:
#         client = TestClient(app)
#         r = client.post("api/run-script", json={"os_type": "alpine"})
#         assert r.status_code == 200
#         data = r.json()
#         assert "redirect" in data
#         assert "vm" in data and data["vm"]["vmid"] == existing["vmid"]

#         # No VM boot or websockify start for existing
#         MockMgr.assert_not_called()
#         assert ws.start_calls == []

#     clear_overrides(app)

# def test_run_script_happy_path_unix_socket(monkeypatch):
#     from configs import server_config
#     monkeypatch.setattr(server_config, "SERVER_HOST", "127.0.0.1", raising=False)

#     store = override_store(existing=None)
#     ws = FakeWS(http_port=7010)
#     setup_overrides(app, store=store, ws=ws)

#     # Deterministic vmid
#     monkeypatch.setattr("routers.vm.secrets.token_hex", lambda n: "deadbe", raising=False)

#     # Fake manager behavior
#     fake_mgr = MagicMock()
#     fake_mgr.create_overlay.return_value = "/tmp/ovl.qcow2"
#     fake_mgr.boot_vm.return_value = {"vnc_socket": "/tmp/vm.sock", "pid": 9999}

#     with patch("routers.vm.QemuOverlayManager", return_value=fake_mgr):
#         client = TestClient(app)
#         r = client.post("api/run-script", json={"os_type": "alpine"})
#         assert r.status_code == 200
#         data = r.json()

#         # Response shape
#         assert data["vm"]["vmid"] == "deadbe"
#         assert "redirect" in data

#         # websockify target (unix socket)
#         assert ws.start_calls == [("deadbe", "/tmp/vm.sock")]

#         # Store.set called with merged meta
#         assert len(store.set_calls) == 1
#         vmid, payload = store.set_calls[0]
#         assert vmid == "deadbe"
#         assert payload["user_id"] == "42"
#         assert payload["http_port"] == 7010
#         assert payload["os_type"] == "alpine"
#         assert payload["pid"] == 9999

#         # Manager methods called
#         fake_mgr.create_overlay.assert_called_once()
#         fake_mgr.boot_vm.assert_called_once_with("deadbe")

#     clear_overrides(app)

# def test_run_script_happy_path_host_port(monkeypatch):
#     from configs import server_config
#     monkeypatch.setattr(server_config, "SERVER_HOST", "127.0.0.1", raising=False)

#     store = override_store(existing=None)
#     ws = FakeWS(http_port=7020)
#     setup_overrides(app, store=store, ws=ws)

#     monkeypatch.setattr("routers.vm.secrets.token_hex", lambda n: "cafeba", raising=False)

#     fake_mgr = MagicMock()
#     fake_mgr.create_overlay.return_value = "/tmp/ovl2.qcow2"
#     fake_mgr.boot_vm.return_value = {"vnc_host": "127.0.0.1", "vnc_port": 5903, "pid": 1234}

#     with patch("routers.vm.QemuOverlayManager", return_value=fake_mgr):
#         client = TestClient(app)
#         r = client.post("api/run-script", json={"os_type": "alpine"})
#         assert r.status_code == 200
#         data = r.json()
#         assert data["vm"]["vmid"] == "cafeba"
#         assert ws.start_calls == [("cafeba", "127.0.0.1:5903")]

#     clear_overrides(app)

# def test_run_script_failure_returns_500(monkeypatch):
#     from configs import server_config
#     monkeypatch.setattr(server_config, "SERVER_HOST", "127.0.0.1", raising=False)

#     store = override_store(existing=None)
#     ws = FakeWS()
#     setup_overrides(app, store=store, ws=ws)

#     # Force failure
#     fake_mgr = MagicMock()
#     fake_mgr.create_overlay.side_effect = RuntimeError("boom")

#     with patch("routers.vm.QemuOverlayManager", return_value=fake_mgr):
#         client = TestClient(app)
#         r = client.post("api/run-script", json={"os_type": "alpine"})
#         assert r.status_code == 500

#     clear_overrides(app)

# def test_run_script_missing_pid_contract_violation(monkeypatch):
#     """
#     If boot_vm forgets to include 'pid', your code accesses meta['pid'] and should error.
#     This test locks that contract so regressions are caught.
#     """
#     from configs import server_config
#     monkeypatch.setattr(server_config, "SERVER_HOST", "127.0.0.1", raising=False)

#     store = override_store(existing=None)
#     ws = FakeWS()
#     setup_overrides(app, store=store, ws=ws)

#     fake_mgr = MagicMock()
#     fake_mgr.create_overlay.return_value = "/tmp/ovl.qcow2"
#     fake_mgr.boot_vm.return_value = {"vnc_socket": "/tmp/vm.sock"}  # no 'pid'

#     with patch("routers.vm.QemuOverlayManager", return_value=fake_mgr):
#         client = TestClient(app)
#         r = client.post("api/run-script", json={"os_type": "alpine"})
#         assert r.status_code == 500  # contract violation surfaces

#     clear_overrides(app)
