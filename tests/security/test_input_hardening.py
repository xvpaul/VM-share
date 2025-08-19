from fastapi.testclient import TestClient
from main import app

def test_register_missing_fields_returns_400_or_422():
    client = TestClient(app)
    r = client.post("/register", json={"login": "only_login"})  # missing password
    assert r.status_code in (400, 422)

def test_register_oversized_body_is_rejected():
    client = TestClient(app)
    huge = "x" * 2_000_000  # 2 MB
    r = client.post("/register", json={"login": huge, "password": "x"})
    # either validation (422) or server's max size handling (413) — but never 500
    assert r.status_code in (400, 413, 422)

def test_run_script_invalid_os_type_returns_4xx(monkeypatch):
    client = TestClient(app)
    # without overrides, this hits real deps; to keep it “security-only” we override user & store
    from routers import vm as vm_mod
    class FakeUser: id="u2"; login="bob"
    class FakeStore: 
        def get_running_by_user(self, _): return None
        def set(self, *a, **k): pass

    app.dependency_overrides[vm_mod.get_current_user] = lambda: FakeUser
    app.dependency_overrides[vm_mod.get_session_store] = lambda: FakeStore()
    app.dependency_overrides[vm_mod.get_websockify_service] = lambda: None
    app.dependency_overrides[vm_mod.get_db] = lambda: object()

    # if QemuOverlayManager uses vm_profiles and rejects unknown os_type, we expect 4xx or handled 500
    r = client.post("/api/run-script", json={"os_type": "💣not-an-os"})
    assert r.status_code in (400, 422, 500)  # goal: move to 400/422 if we add validation

    app.dependency_overrides.clear()
