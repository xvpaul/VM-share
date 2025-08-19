import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.mark.rate_limit
@pytest.mark.xfail(reason="Enable rate limiting middleware on /login to pass this test")
def test_login_bruteforce_hits_rate_limit():
    client = TestClient(app)
    hits, status_429 = 0, False
    for _ in range(50):  # burst
        r = client.post("/login", json={"login":"ghost", "password":"nope"})
        hits += 1
        if r.status_code == 429:
            status_429 = True
            break
    assert status_429, f"no 429 after {hits} attempts — add rate limiting"
