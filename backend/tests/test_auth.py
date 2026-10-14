from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models import User

LOGIN = "/api/v1/auth/login"


def test_login_sets_session_and_me_returns_user(anon_client):
    response = anon_client.post(
        LOGIN, json={"email": "ADMIN@acme.example", "password": "admin-pass"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "hr_admin"
    assert "acme_session" in response.cookies
    assert anon_client.get("/api/v1/auth/me").json()["email"] == "admin@acme.example"


def test_wrong_password_and_unknown_email_get_the_same_answer(anon_client):
    wrong = anon_client.post(LOGIN, json={"email": "admin@acme.example", "password": "nope"})
    unknown = anon_client.post(LOGIN, json={"email": "who@acme.example", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["message"] == "Wrong email or password."


def test_inactive_user_cannot_sign_in(anon_client, db):
    db.query(User).filter_by(email="viewer@acme.example").update({"active": False})
    db.commit()
    response = anon_client.post(
        LOGIN, json={"email": "viewer@acme.example", "password": "viewer-pass"}
    )
    assert response.status_code == 401


def test_deactivated_user_loses_access_on_next_request(viewer_client, db):
    db.query(User).filter_by(email="viewer@acme.example").update({"active": False})
    db.commit()
    assert viewer_client.get("/api/v1/auth/me").status_code == 401


def test_login_validation_error_shape(anon_client):
    response = anon_client.post(LOGIN, json={"email": "not-an-email", "password": ""})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "invalid"
    assert set(body["details"]["fields"]) == {"email", "password"}


def test_endpoints_need_sign_in(anon_client):
    for path in (
        "/api/v1/auth/me",
        "/api/v1/employees",
        "/api/v1/meta",
        "/api/v1/insights/summary",
    ):
        response = anon_client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "unauthorized"


def test_logout_clears_the_session(admin_client):
    assert admin_client.post("/api/v1/auth/logout").status_code == 204
    assert admin_client.get("/api/v1/auth/me").status_code == 401


def test_login_is_rate_limited(anon_client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    body = {"email": "admin@acme.example", "password": "wrong"}
    codes = [anon_client.post(LOGIN, json=body).status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    blocked = anon_client.post(LOGIN, json=body)
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) > 0


def test_health_needs_no_sign_in_and_responses_carry_headers(anon_client):
    response = anon_client.get("/api/v1/health")
    assert response.json() == {"status": "ok", "commit": None}
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Request-ID"]


def test_health_reports_the_build_commit_when_the_image_sets_one(anon_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "git_commit", "390abb9c1d2e")
    assert anon_client.get("/api/v1/health").json() == {"status": "ok", "commit": "390abb9c1d2e"}
