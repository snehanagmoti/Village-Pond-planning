"""Check real frontend/API routing and startup validation for single-host deployment."""

import pytest
from starlette.testclient import TestClient

from web import create_app


def test_frontend_and_api_share_origin_without_hiding_api_errors(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>pond frontend</html>")
    (tmp_path / "assets" / "app-123.js").write_text("console.log('pond')")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    with TestClient(create_app(tmp_path)) as client:
        page = client.get("/")
        assert page.status_code == 200 and "pond frontend" in page.text
        assert page.headers["cache-control"] == "no-store"
        asset = client.get("/assets/app-123.js")
        assert asset.status_code == 200
        assert "immutable" in asset.headers["cache-control"]
        assert client.get("/health/live").json()["status"] == "ok"
        assert client.get("/docs").status_code == 200
        assert "/api/analyze-contour" in client.get("/openapi.json").json()["paths"]
        assert client.post("/api/analyze-contour").status_code == 422
        assert client.get("/api/does-not-exist").status_code == 404
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/", headers={"Host": "untrusted.invalid"}).status_code == 400


def test_missing_frontend_stops_startup(tmp_path):
    with pytest.raises(RuntimeError, match="Frontend build missing"):
        create_app(tmp_path)
