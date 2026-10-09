"""Tests for TraceWise Dashboard HTTP server and REST API."""

import json
import urllib.error
import urllib.request
from collections.abc import Generator

import pytest

from tracewise.dashboard.server import TraceWiseDashboardServer
from tracewise.dashboard.service import TraceWiseService


@pytest.fixture(scope="module")
def dashboard_server() -> Generator[TraceWiseDashboardServer, None, None]:
    """Launch TraceWiseDashboardServer on an ephemeral port for automated testing."""
    service = TraceWiseService()
    server = TraceWiseDashboardServer(port=0, service=service)
    server.start(in_thread=True)
    try:
        yield server
    finally:
        server.shutdown()


def _get(url: str) -> tuple[int, dict[str, str], bytes]:
    """Helper to perform HTTP GET and return status code, headers, and body."""
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read()


class TestDashboardServerApi:
    """Verifies all REST API endpoints served by TraceWiseDashboardServer."""

    def test_health_check(self, dashboard_server: TraceWiseDashboardServer) -> None:
        status, headers, body = _get(f"{dashboard_server.url}/api/health")
        assert status == 200
        assert "application/json" in headers.get("Content-Type", "")
        data = json.loads(body)
        assert data["status"] == "ok"
        assert "version" in data

    def test_retrieval_methods_catalog(
        self, dashboard_server: TraceWiseDashboardServer
    ) -> None:
        status, _, body = _get(f"{dashboard_server.url}/api/retrieval-methods")
        assert status == 200
        methods = json.loads(body)
        assert len(methods) >= 6
        ids = [m["id"] for m in methods]
        assert "b0_tfidf" in ids
        assert "b1_bm25" in ids
        assert "b5_llm_rerank" in ids

    def test_list_projects(self, dashboard_server: TraceWiseDashboardServer) -> None:
        status, _, body = _get(f"{dashboard_server.url}/api/projects")
        assert status == 200
        projects = json.loads(body)
        pids = [p["project_id"] for p in projects]
        assert "sample_project" in pids
        assert "itrust" in pids
        assert "etour" in pids

    def test_get_project_detail(
        self, dashboard_server: TraceWiseDashboardServer
    ) -> None:
        status, _, body = _get(f"{dashboard_server.url}/api/projects/sample_project")
        assert status == 200
        data = json.loads(body)
        assert data["project_id"] == "sample_project"
        assert data["num_requirements"] == 10

    def test_get_project_detail_not_found(
        self, dashboard_server: TraceWiseDashboardServer
    ) -> None:
        status, _, body = _get(f"{dashboard_server.url}/api/projects/non_existent")
        assert status == 404
        data = json.loads(body)
        assert "error" in data

    def test_list_requirements(
        self, dashboard_server: TraceWiseDashboardServer
    ) -> None:
        status, _, body = _get(
            f"{dashboard_server.url}/api/projects/sample_project/requirements"
        )
        assert status == 200
        reqs = json.loads(body)
        assert len(reqs) == 10
        assert reqs[0]["requirement_id"] == "REQ-001"

    def test_get_requirement_detail(
        self, dashboard_server: TraceWiseDashboardServer
    ) -> None:
        status, _, body = _get(
            f"{dashboard_server.url}/api/projects/sample_project/requirements/REQ-001"
        )
        assert status == 200
        detail = json.loads(body)
        assert detail["requirement_id"] == "REQ-001"
        assert "gold_links" in detail
        assert len(detail["gold_links"]) > 0

    def test_candidates_retrieval_b1(
        self, dashboard_server: TraceWiseDashboardServer
    ) -> None:
        url = (
            f"{dashboard_server.url}/api/projects/sample_project/requirements/"
            "REQ-001/candidates?method=b1_bm25&top_k=5"
        )
        status, _, body = _get(url)
        assert status == 200
        data = json.loads(body)
        assert data["method"] == "b1_bm25"
        assert len(data["candidates"]) == 5
        cand0 = data["candidates"][0]
        assert cand0["rank"] == 1
        assert cand0["candidate_type"] == "retrieval_hypothesis"
        assert cand0["developer_verification_status"] == "unverified"
        assert "code_preview" in cand0

    def test_candidates_retrieval_b5_cached(
        self, dashboard_server: TraceWiseDashboardServer
    ) -> None:
        url = (
            f"{dashboard_server.url}/api/projects/sample_project/requirements/"
            "REQ-001/candidates?method=b5_llm_rerank&top_k=5"
        )
        status, _, body = _get(url)
        assert status == 200
        data = json.loads(body)
        assert data["method"] == "b5_llm_rerank"
        assert data["is_cached"] is True
        assert len(data["candidates"]) == 5
        assert "llm_score" in data["candidates"][0]["metadata"]

    def test_candidates_retrieval_invalid_top_k(
        self, dashboard_server: TraceWiseDashboardServer
    ) -> None:
        url = (
            f"{dashboard_server.url}/api/projects/sample_project/requirements/"
            "REQ-001/candidates?method=b1_bm25&top_k=-5"
        )
        status, _, body = _get(url)
        assert status == 400
        data = json.loads(body)
        assert "error" in data

    def test_candidates_retrieval_developer_mode_blinded(
        self, dashboard_server: TraceWiseDashboardServer
    ) -> None:
        url = (
            f"{dashboard_server.url}/api/projects/sample_project/requirements/"
            "REQ-001/candidates?method=b1_bm25&top_k=5&mode=developer"
        )
        status, _, body = _get(url)
        assert status == 200
        data = json.loads(body)
        assert data["mode"] == "developer"
        assert data["gold_links_retrieved"] is None
        assert data["gold_link_targets"] is None
        assert data["is_evaluable"] is None
        for cand in data["candidates"]:
            assert cand["is_gold_link"] is None


class TestDashboardServerStatic:
    """Verifies static asset delivery and traversal security."""

    def test_serve_index_html(self, dashboard_server: TraceWiseDashboardServer) -> None:
        status, headers, body = _get(f"{dashboard_server.url}/")
        assert status == 200
        assert "text/html" in headers.get("Content-Type", "")
        assert b"TraceWise Dashboard V0" in body

    def test_serve_style_css(self, dashboard_server: TraceWiseDashboardServer) -> None:
        status, headers, body = _get(f"{dashboard_server.url}/style.css")
        assert status == 200
        assert "text/css" in headers.get("Content-Type", "")
        assert b"--bg-primary" in body

    def test_serve_app_js(self, dashboard_server: TraceWiseDashboardServer) -> None:
        status, headers, body = _get(f"{dashboard_server.url}/app.js")
        assert status == 200
        assert "javascript" in headers.get("Content-Type", "")
        assert b"TraceWise Dashboard V0 Client Application" in body

    def test_prevent_directory_traversal(
        self, dashboard_server: TraceWiseDashboardServer
    ) -> None:
        status, _, _ = _get(f"{dashboard_server.url}/../../secret.txt")
        # Must be forbidden (403) or not found (404), never 200 with sensitive files
        assert status in (403, 404)
