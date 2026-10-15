"""The built React app as the production image serves it, from a fake dist folder."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import install_error_handlers
from app.main import ASSET_CACHE, _serve_frontend


@pytest.fixture
def site(tmp_path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "index-3f2a9c.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    app = FastAPI()
    install_error_handlers(app)
    _serve_frontend(app, tmp_path)
    return TestClient(app)


def test_hashed_asset_is_cached_for_a_year(site):
    response = site.get("/assets/index-3f2a9c.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == ASSET_CACHE


def test_missing_asset_is_404_and_not_cached(site):
    response = site.get("/assets/index-old.js")
    assert response.status_code == 404
    assert "cache-control" not in response.headers


def test_unchanged_asset_revalidates_with_304(site):
    etag = site.get("/assets/index-3f2a9c.js").headers["etag"]
    response = site.get("/assets/index-3f2a9c.js", headers={"If-None-Match": etag})
    assert response.status_code == 304


@pytest.mark.parametrize("path", ["/", "/people/42"])
def test_index_html_is_always_revalidated(site, path):
    response = site.get(path)
    assert response.status_code == 200
    assert response.text == "<html>app</html>"
    assert response.headers["cache-control"] == "no-cache"


def test_unhashed_root_file_is_served_without_long_cache(site):
    response = site.get("/favicon.svg")
    assert response.status_code == 200
    assert "immutable" not in response.headers.get("cache-control", "")


def test_unknown_api_path_is_404_not_index_html(site):
    assert site.get("/api/v1/nope").status_code == 404


def test_path_outside_dist_is_not_served(site, tmp_path):
    (tmp_path.parent / "secret.txt").write_text("secret")
    response = site.get("/..%2Fsecret.txt")
    assert "secret" not in response.text


def test_nothing_is_served_without_a_build(tmp_path):
    app = FastAPI()
    _serve_frontend(app, tmp_path)
    assert TestClient(app).get("/").status_code == 404
