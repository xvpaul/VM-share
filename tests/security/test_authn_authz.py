from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from main import app

def test_protected_endpoint_requires_auth():
    client = TestClient(app)
    # /api/run-script requires get_current_user
    r = client.post("/api/run-script", json={"os_type": "debian"})
    assert r.status_code in (401, 403)  # unauthorized without credentials

def test_protected_endpoint_with_invalid_token(monkeypatch):
    client = TestClient(app)
    # Override dependency to emulate "invalid token"
    from routers import vm as vm_mod
    def bad_user():
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid token")
    app.dependency_overrides[vm_mod.get_current_user] = bad_user

    r = client.post("/api/run-script", json={"os_type": "debian"})
    assert r.status_code == 401

    app.dependency_overrides.clear()

def test_protected_endpoint_with_valid_user_but_no_side_effects(monkeypatch):
    """
    Smoke that a valid user can hit the route; we stub out manager/websockify
    so we don't actually boot anything.
    """
    client = TestClient(app)
    from routers import vm as vm_mod

    class FakeUser: id="u1"; login="alice"
    store = MagicMock(); store.get_running_by_user.return_value = {"vmid":"v1","http_port":7001,"pid":1,"vnc_host":"127.0.0.1","vnc_port":5900}
    ws = MagicMock()

    app.dependency_overrides[vm_mod.get_current_user] = lambda: FakeUser
    app.dependency_overrides[vm_mod.get_session_store] = lambda: store
    app.dependency_overrides[vm_mod.get_websockify_service] = lambda: ws
    app.dependency_overrides[vm_mod.get_db] = lambda: object()

    r = client.post("/api/run-script", json={"os_type": "debian"})
    assert r.status_code == 200
    # no new VM started because existing session returned
    ws.start.assert_not_called()

    app.dependency_overrides.clear()
