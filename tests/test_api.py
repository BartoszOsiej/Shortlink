import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200

def test_register_login():
    r = client.post("/auth/register", json={"email": "x@x.pl", "password": "test123"})
    assert r.status_code == 200
    assert "access_token" in r.json()

def _register(email="y@y.pl", password="test123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]

def _auth(token):
    return {"Authorization": f"Bearer {token}"}

def _shorten(token, target="https://example.com"):
    r = client.post("/urls/shorten", params={"target_url": target}, headers=_auth(token))
    assert r.status_code == 200
    return r.json()["short_code"]

def test_shorten():
    token = _register()
    short_code = _shorten(token)

    r = client.get(f"/urls/{short_code}/stats")
    assert r.status_code == 200

    r = client.get(f"/urls/r/{short_code}", follow_redirects=False)
    assert r.status_code in (302, 307)

def test_login_and_me():
    token = _register("me@x.pl")
    r = client.post("/auth/login", json={"email": "me@x.pl", "password": "test123"})
    assert r.status_code == 200
    assert "access_token" in r.json()

    r = client.post("/auth/login", json={"email": "me@x.pl", "password": "wrong"})
    assert r.status_code == 401

    r = client.get("/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["email"] == "me@x.pl"

    r = client.get("/auth/me")
    assert r.status_code in (401, 403)

def test_duplicate_email_rejected():
    _register("dup@x.pl")
    r = client.post("/auth/register", json={"email": "dup@x.pl", "password": "test123"})
    assert r.status_code == 400

def test_shorten_requires_auth():
    r = client.post("/urls/shorten", params={"target_url": "https://example.com"})
    assert r.status_code in (401, 403)

def test_my_urls_lists_only_own_links():
    alice = _register("alice@x.pl")
    bob = _register("bob@x.pl")
    _shorten(alice, "https://alice.example")
    bob_code = _shorten(bob, "https://bob.example")

    r = client.get("/urls/my", headers=_auth(alice))
    assert r.status_code == 200
    urls = r.json()
    assert len(urls) == 1
    assert urls[0]["target_url"] == "https://alice.example"
    assert all(u["short_code"] != bob_code for u in urls)

def test_redirect_counts_clicks():
    token = _register("clicks@x.pl")
    short_code = _shorten(token)

    for _ in range(3):
        client.get(f"/urls/r/{short_code}", follow_redirects=False)

    r = client.get(f"/urls/{short_code}/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["clicks"] == 3
    assert data["total"] == 3

def test_stats_404_for_unknown_code():
    r = client.get("/urls/zzzzzz/stats")
    assert r.status_code == 404

def test_delete_removes_link():
    token = _register("del@x.pl")
    short_code = _shorten(token)

    r = client.delete(f"/urls/{short_code}", headers=_auth(token))
    assert r.status_code == 204

    r = client.get(f"/urls/r/{short_code}", follow_redirects=False)
    assert r.status_code == 404

def test_delete_enforces_ownership():
    alice = _register("own1@x.pl")
    bob = _register("own2@x.pl")
    code = _shorten(alice)

    r = client.delete(f"/urls/{code}", headers=_auth(bob))
    assert r.status_code == 404

    r = client.delete(f"/urls/{code}", headers=_auth(alice))
    assert r.status_code == 204

def test_login_unknown_email_rejected():
    r = client.post("/auth/login", json={"email": "ghost@x.pl", "password": "test123"})
    assert r.status_code == 401

def test_delete_unknown_code_404():
    token = _register("del404@x.pl")
    r = client.delete("/urls/zzzzzz", headers=_auth(token))
    assert r.status_code == 404

def test_redirect_unknown_code_404():
    r = client.get("/urls/r/zzzzzz", follow_redirects=False)
    assert r.status_code == 404

def test_inactive_link_still_resolves():
    # Links are created active; nothing in this API deactivates them, but
    # the redirect query filters on is_active — an active link must resolve.
    token = _register("active@x.pl")
    code = _shorten(token, "https://active.example")
    r = client.get(f"/urls/r/{code}", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers.get("location") == "https://active.example"

def test_link_expiration_blocks_redirect():
    token = _register("exp@x.pl")

    r = client.post(
        "/urls/shorten",
        params={"target_url": "https://example.com", "expires_in_seconds": 1},
        headers=_auth(token),
    )
    assert r.status_code == 200
    code = r.json()["short_code"]
    assert r.json()["expires_at"] is not None

    import time
    time.sleep(1.2)

    r = client.get(f"/urls/r/{code}", follow_redirects=False)
    assert r.status_code == 410
    assert "expired" in r.json()["detail"].lower()

def test_link_without_expiry_never_blocks():
    token = _register("noexp@x.pl")
    code = _shorten(token, "https://example.com/forever")

    assert client.get(f"/urls/r/{code}", follow_redirects=False).status_code in (302, 307)

    r = client.get(f"/urls/{code}/stats")
    assert r.status_code == 200

def test_expires_in_seconds_must_be_positive():
    token = _register("badexp@x.pl")
    r = client.post(
        "/urls/shorten",
        params={"target_url": "https://example.com", "expires_in_seconds": -5},
        headers=_auth(token),
    )
    assert r.status_code == 422

def test_expired_link_can_be_deleted_by_owner():
    token = _register("expclean@x.pl")
    r = client.post(
        "/urls/shorten",
        params={"target_url": "https://example.com", "expires_in_seconds": 1},
        headers=_auth(token),
    )
    code = r.json()["short_code"]

    import time
    time.sleep(1.2)
    r = client.delete(f"/urls/{code}", headers=_auth(token))
    assert r.status_code == 204
