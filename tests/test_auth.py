# # tests/test_auth.py
# import pytest, secrets
# from fastapi.testclient import TestClient
# from main import app

# client = TestClient(app)

# import secrets

# def test_signup_and_login():
#     # sign existing user up -> Conflict
#     r = client.post("/register", json={"login": "1", "password": "1"})
#     assert r.status_code == 409

#     # sign new user up -> Created
#     new_login = secrets.token_hex(4)
#     r = client.post("/register", json={"login": new_login, "password": "lvlvl"})
#     assert r.status_code in (200, 201)

#     # log existing user in -> OK
#     r = client.post("/login", json={"username": "1", "password": "1"})
#     assert r.status_code == 200
#     assert "access_token" in r.json()

#     # log new user in -> OK
#     r = client.post("/login", json={"username": new_login, "password": "lvlvl"})
#     assert r.status_code == 200
#     assert "access_token" in r.json()

#     # log non-existent user in -> Unauthorized
#     r = client.post("/login", json={"username": "12222", "password": "1"})
#     assert r.status_code == 401

#     # log in with wrong password -> Unauthorized
#     r = client.post("/login", json={"username": "1", "password": "WRONGPASS"})
#     assert r.status_code == 401

#     # sign up existing user with wrong password -> Conflict
#     r = client.post("/register", json={"login": "1", "password": "different"})
#     assert r.status_code == 401
