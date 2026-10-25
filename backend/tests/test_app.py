"""App-wide wiring: the built frontend, CORS, the API docs, shared error shapes and the
per-request database session."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import engine, get_db
from app.main import create_app


@pytest.fixture
def frontend(tmp_path, monkeypatch):
    """An app serving a tiny built frontend, with a secret file just outside its folder."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("secret")
    monkeypatch.setattr(get_settings(), "frontend_dist", dist)
    return TestClient(create_app())


def test_built_frontend_and_its_client_routes_are_served(frontend):
    assert frontend.get("/").text == "<html>app</html>"
    assert frontend.get("/people/42").text == "<html>app</html>"  # a reload on a client route
    assert frontend.get("/assets/app.js").text == "console.log(1)"
    assert frontend.get("/favicon.svg").text == "<svg/>"


@pytest.mark.parametrize(
    "path", ["/%2e%2e/secret.txt", "/..%2fsecret.txt", "/assets/..%2f..%2fsecret.txt"]
)
def test_frontend_never_serves_files_outside_its_folder(frontend, path):
    assert "secret" not in frontend.get(path).text


def test_unknown_api_paths_are_json_404s_not_the_app(frontend):
    response = frontend.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_shared_error_shape_for_unknown_paths_and_methods(anon_client):
    missing = anon_client.get("/api/v1/nope")
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
    wrong_method = anon_client.delete("/api/v1/health")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "method_not_allowed"


def test_api_docs_load_their_cdn_assets(anon_client):
    docs = anon_client.get("/api/v1/docs")
    assert docs.status_code == 200
    assert "Content-Security-Policy" not in docs.headers
    assert "Content-Security-Policy" in anon_client.get("/api/v1/health").headers


def test_cors_allows_only_configured_origins(monkeypatch):
    monkeypatch.setattr(get_settings(), "cors_origins", ["https://ui.acme.example"])
    client = TestClient(create_app())

    def preflight(origin):
        return client.options(
            "/api/v1/auth/me",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )

    allowed = preflight("https://ui.acme.example")
    assert allowed.headers["access-control-allow-origin"] == "https://ui.acme.example"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in preflight("https://evil.example").headers


def test_no_cors_headers_by_default(anon_client):
    response = anon_client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


async def test_request_session_is_rolled_back_and_closed(monkeypatch):
    calls = []

    async def record(name):
        calls.append(name)

    sessions = get_db()
    session = await anext(sessions)
    monkeypatch.setattr(session, "rollback", lambda: record("rollback"))
    monkeypatch.setattr(session, "close", lambda: record("close"))
    await sessions.aclose()
    assert calls == ["rollback", "close"]


def test_database_url_gets_an_async_driver():
    """`DATABASE_URL` keeps the sync form Alembic uses; the app runs it on psycopg's async mode."""
    assert (engine.dialect.driver, engine.dialect.is_async) == ("psycopg", True)
