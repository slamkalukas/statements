from .conftest import ADMIN_EMAIL, ADMIN_PASSWORD


def test_login_success_and_me(client):
    res = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert res.status_code == 200, res.text
    token = res.json()["token"]
    assert res.json()["user"]["email"] == ADMIN_EMAIL

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == ADMIN_EMAIL


def test_login_wrong_password(client):
    res = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "nope"})
    assert res.status_code == 401


def test_login_is_case_insensitive_on_email(client):
    res = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD}
    )
    assert res.status_code == 200


def test_protected_routes_require_auth(client):
    assert client.get("/api/periods").status_code == 401
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_change_password(client):
    headers = {
        "Authorization": "Bearer "
        + client.post(
            "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        ).json()["token"]
    }
    # Wrong current password is rejected.
    bad = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong", "new_password": "brandnew123"},
        headers=headers,
    )
    assert bad.status_code == 400

    ok = client.post(
        "/api/auth/change-password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "brandnew123"},
        headers=headers,
    )
    assert ok.status_code == 204

    # Old password no longer works; new one does.
    assert (
        client.post(
            "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": ADMIN_EMAIL, "password": "brandnew123"}
        ).status_code
        == 200
    )
