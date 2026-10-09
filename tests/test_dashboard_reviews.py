"""Comprehensive test suite for developer review decisions (Milestone B6.1).

Verifies SQLite persistence, thread-safety, validation rules, chronological
audit history, candidate link isolation, service integration, and REST APIs.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from tracewise.dashboard.reviews import (
    ReviewDecision,
    ReviewStore,
)
from tracewise.dashboard.server import TraceWiseDashboardServer
from tracewise.dashboard.service import TraceWiseService

# -----------------------------------------------------------------------------
# 1. ReviewStore SQLite Unit Tests
# -----------------------------------------------------------------------------


class TestReviewStore:
    """Verifies SQLite persistence, validation, audit logs, and isolation."""

    def test_record_decision_accepted_with_rationale(self, tmp_path: Path) -> None:
        store = ReviewStore(tmp_path / "reviews.db")
        decision = store.record_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id="src/auth.py#verify_password",
            decision="accepted",
            rationale="Directly validates credentials against database.",
        )

        assert isinstance(decision, ReviewDecision)
        assert decision.project_id == "sample_project"
        assert decision.requirement_id == "REQ-001"
        assert decision.target_id == "src/auth.py#verify_password"
        assert decision.decision == "accepted"
        assert decision.rationale == "Directly validates credentials against database."
        assert decision.revision_count == 1
        assert decision.created_at
        assert decision.updated_at == decision.created_at

    def test_record_decision_rejected_with_rationale(self, tmp_path: Path) -> None:
        store = ReviewStore(tmp_path / "reviews.db")
        decision = store.record_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id="src/utils.py#format_date",
            decision="rejected",
            rationale="Unrelated date utility with no auth logic.",
        )
        assert decision.decision == "rejected"
        assert decision.revision_count == 1
        assert "Unrelated date utility" in decision.rationale

    def test_record_decision_needs_review_optional_rationale(
        self, tmp_path: Path
    ) -> None:
        store = ReviewStore(tmp_path / "reviews.db")
        # With empty rationale: allowed for needs_review
        d1 = store.record_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id="src/session.py",
            decision="needs_review",
            rationale="",
        )
        assert d1.decision == "needs_review"
        assert d1.rationale == ""

        # With explicit rationale: also allowed
        d2 = store.record_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id="src/token.py",
            decision="needs_review",
            rationale="Uncertain if JWT handling is part of this requirement.",
        )
        assert d2.decision == "needs_review"
        assert "Uncertain if JWT" in d2.rationale

    def test_rejected_and_accepted_require_non_empty_rationale(
        self, tmp_path: Path
    ) -> None:
        store = ReviewStore(tmp_path / "reviews.db")

        with pytest.raises(ValueError, match="non-empty rationale is required"):
            store.record_decision(
                project_id="sample_project",
                requirement_id="REQ-001",
                target_id="src/auth.py",
                decision="accepted",
                rationale="",
            )

        with pytest.raises(ValueError, match="non-empty rationale is required"):
            store.record_decision(
                project_id="sample_project",
                requirement_id="REQ-001",
                target_id="src/auth.py",
                decision="rejected",
                rationale="   ",
            )

    def test_invalid_decision_status_rejected(self, tmp_path: Path) -> None:
        store = ReviewStore(tmp_path / "reviews.db")
        for bad_status in ("approved", "skip", "pending", "unknown", "yes"):
            with pytest.raises(ValueError, match="Invalid decision status"):
                store.record_decision(
                    project_id="sample_project",
                    requirement_id="REQ-001",
                    target_id="src/auth.py",
                    decision=bad_status,
                    rationale="Some comment",
                )

    def test_decision_revision_and_audit_history(self, tmp_path: Path) -> None:
        store = ReviewStore(tmp_path / "reviews.db")
        target = "src/auth.py#verify_password"

        # Revision 1: initial decision needs_review
        r1 = store.record_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id=target,
            decision="needs_review",
            rationale="Need to inspect verification helper.",
        )
        assert r1.revision_count == 1
        initial_created_at = r1.created_at

        # Revision 2: updated to accepted
        r2 = store.record_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id=target,
            decision="accepted",
            rationale="Confirmed verify_password directly enforces policy.",
        )
        assert r2.revision_count == 2
        assert r2.created_at == initial_created_at
        assert r2.decision == "accepted"

        # Revision 3: updated to rejected
        r3 = store.record_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id=target,
            decision="rejected",
            rationale="Superceded by oauth handler in security module.",
        )
        assert r3.revision_count == 3
        assert r3.decision == "rejected"

        # Verify current state in DB
        current = store.get_decision("sample_project", "REQ-001", target)
        assert current is not None
        assert current.revision_count == 3
        assert current.decision == "rejected"
        assert current.rationale == "Superceded by oauth handler in security module."

        # Verify chronological audit history
        history = store.get_history("sample_project", "REQ-001", target)
        assert len(history) == 3
        assert [h.revision_number for h in history] == [1, 2, 3]
        assert [h.decision for h in history] == [
            "needs_review",
            "accepted",
            "rejected",
        ]
        assert history[0].rationale == "Need to inspect verification helper."
        assert (
            history[1].rationale
            == "Confirmed verify_password directly enforces policy."
        )
        assert history[2].rationale == "Superceded by oauth handler in security module."

    def test_reopening_database_preserves_state_and_history(
        self, tmp_path: Path
    ) -> None:
        db_file = tmp_path / "persistent_reviews.db"
        store1 = ReviewStore(db_file)
        store1.record_decision(
            project_id="itrust",
            requirement_id="UC-01",
            target_id="edu.ncsu.csc.itrust.action.LoginAction",
            decision="accepted",
            rationale="Authenticates patient users.",
        )
        store1.record_decision(
            project_id="itrust",
            requirement_id="UC-01",
            target_id="edu.ncsu.csc.itrust.action.LoginAction",
            decision="rejected",
            rationale="Correction: handles admin login only.",
        )
        store1.close()

        # Reopen with a second store instance pointing to same file
        store2 = ReviewStore(db_file)
        current = store2.get_decision(
            "itrust", "UC-01", "edu.ncsu.csc.itrust.action.LoginAction"
        )
        assert current is not None
        assert current.decision == "rejected"
        assert current.revision_count == 2

        history = store2.get_history(
            "itrust", "UC-01", "edu.ncsu.csc.itrust.action.LoginAction"
        )
        assert len(history) == 2
        assert history[0].decision == "accepted"
        assert history[1].decision == "rejected"
        store2.close()

    def test_isolation_across_projects_and_candidates(self, tmp_path: Path) -> None:
        store = ReviewStore(tmp_path / "reviews.db")

        store.record_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id="src/auth.py",
            decision="accepted",
            rationale="Sample project auth link",
        )
        store.record_decision(
            project_id="sample_project",
            requirement_id="REQ-002",
            target_id="src/auth.py",
            decision="rejected",
            rationale="Not relevant for REQ-002",
        )
        store.record_decision(
            project_id="itrust",
            requirement_id="REQ-001",
            target_id="src/auth.py",
            decision="needs_review",
            rationale="Different project with same IDs",
        )

        d1 = store.get_decision("sample_project", "REQ-001", "src/auth.py")
        d2 = store.get_decision("sample_project", "REQ-002", "src/auth.py")
        d3 = store.get_decision("itrust", "REQ-001", "src/auth.py")

        assert d1 is not None and d1.decision == "accepted"
        assert d2 is not None and d2.decision == "rejected"
        assert d3 is not None and d3.decision == "needs_review"

        req1_decisions = store.get_decisions_for_requirement(
            "sample_project", "REQ-001"
        )
        assert len(req1_decisions) == 1
        assert req1_decisions[0].target_id == "src/auth.py"

    def test_concurrent_multithreaded_recording(self, tmp_path: Path) -> None:
        store = ReviewStore(tmp_path / "concurrent.db")
        num_threads = 8
        errors: list[Exception] = []

        def worker(thread_idx: int) -> None:
            try:
                for i in range(10):
                    store.record_decision(
                        project_id="sample_project",
                        requirement_id=f"REQ-00{thread_idx}",
                        target_id=f"src/file_{i}.py",
                        decision="accepted",
                        rationale=f"Thread {thread_idx} iteration {i}",
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(t,)) for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent execution produced errors: {errors}"
        for t in range(num_threads):
            decs = store.get_decisions_for_requirement("sample_project", f"REQ-00{t}")
            assert len(decs) == 10


# -----------------------------------------------------------------------------
# 2. TraceWiseService Integration Tests
# -----------------------------------------------------------------------------


class TestServiceReviewsIntegration:
    """Verifies service layer artifact validation and candidate enrichment."""

    def test_record_and_get_decision_via_service(self, tmp_path: Path) -> None:
        store = ReviewStore(tmp_path / "service_reviews.db")
        service = TraceWiseService(review_store=store)

        target = "src/auth/service.py#AuthenticationService.authenticate_user"
        saved = service.record_review_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id=target,
            decision="accepted",
            rationale="Direct requirement match for password verification.",
        )
        assert saved["decision"] == "accepted"
        assert saved["revision_count"] == 1
        # Ground truth blinding check: no gold indicators in response
        assert "is_gold_link" not in saved
        assert "gold_links" not in saved

        retrieved = service.get_review_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id=target,
        )
        assert retrieved is not None
        assert retrieved["decision"] == "accepted"
        assert "is_gold_link" not in retrieved

    def test_unknown_identifiers_raise_key_error(self, tmp_path: Path) -> None:
        store = ReviewStore(tmp_path / "service_reviews.db")
        service = TraceWiseService(review_store=store)
        valid_target = "src/auth/service.py#AuthenticationService.authenticate_user"

        # 1. Unknown project
        with pytest.raises(KeyError, match="Project 'non_existent' not found"):
            service.record_review_decision(
                project_id="non_existent",
                requirement_id="REQ-001",
                target_id=valid_target,
                decision="accepted",
                rationale="Reason",
            )

        # 2. Unknown requirement
        with pytest.raises(KeyError, match="Requirement 'REQ-999' not found"):
            service.record_review_decision(
                project_id="sample_project",
                requirement_id="REQ-999",
                target_id=valid_target,
                decision="accepted",
                rationale="Reason",
            )

        # 3. Unknown candidate target
        with pytest.raises(KeyError, match="Candidate target 'src/ghost.py' not found"):
            service.record_review_decision(
                project_id="sample_project",
                requirement_id="REQ-001",
                target_id="src/ghost.py",
                decision="accepted",
                rationale="Reason",
            )

    def test_candidate_retrieval_reflects_review_decision(self, tmp_path: Path) -> None:
        store = ReviewStore(tmp_path / "service_reviews.db")
        service = TraceWiseService(review_store=store)

        target = "src/auth/service.py#AuthenticationService.authenticate_user"

        # Initially unreviewed
        before = service.get_candidates(
            "sample_project", "REQ-001", method="b0_tfidf", top_k=5
        )
        cand_before = next(
            (c for c in before["candidates"] if c["target_id"] == target), None
        )
        assert cand_before is not None
        assert cand_before["candidate_type"] == "retrieval_hypothesis"
        assert cand_before["developer_verification_status"] == "unverified"
        assert cand_before["developer_verification_revision_count"] == 0

        # Record decision: accepted
        service.record_review_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id=target,
            decision="accepted",
            rationale="Verified code implements auth specification.",
        )

        after = service.get_candidates(
            "sample_project", "REQ-001", method="b0_tfidf", top_k=5
        )
        cand_after = next(
            (c for c in after["candidates"] if c["target_id"] == target), None
        )
        assert cand_after is not None
        # Candidate is STILL a hypothesis, but verification status reflects decision
        assert cand_after["candidate_type"] == "retrieval_hypothesis"
        assert cand_after["developer_verification_status"] == "accepted"
        assert (
            cand_after["developer_verification_note"]
            == "Verified code implements auth specification."
        )
        assert cand_after["developer_verification_revision_count"] == 1
        assert cand_after["developer_verification_updated_at"] is not None

    def test_developer_workflow_mode_remains_strictly_blinded(
        self, tmp_path: Path
    ) -> None:
        store = ReviewStore(tmp_path / "service_reviews.db")
        service = TraceWiseService(review_store=store)

        target = "src/auth/service.py#AuthenticationService.authenticate_user"
        service.record_review_decision(
            project_id="sample_project",
            requirement_id="REQ-001",
            target_id=target,
            decision="accepted",
            rationale="Verified by developer.",
        )

        # Developer mode candidate query
        dev_res = service.get_candidates(
            "sample_project",
            "REQ-001",
            method="b0_tfidf",
            top_k=5,
            mode="developer",
        )
        assert dev_res["mode"] == "developer"
        assert dev_res["gold_links_retrieved"] is None
        assert dev_res["total_gold_links"] is None
        assert dev_res["is_evaluable"] is None
        assert dev_res["gold_link_targets"] is None

        for c in dev_res["candidates"]:
            assert c["is_gold_link"] is None
            if c["target_id"] == target:
                assert c["developer_verification_status"] == "accepted"
                assert c["developer_verification_note"] == "Verified by developer."


# -----------------------------------------------------------------------------
# 3. HTTP Server REST API Endpoints Tests
# -----------------------------------------------------------------------------


@pytest.fixture
def review_server(
    tmp_path: Path,
) -> Generator[tuple[TraceWiseDashboardServer, TraceWiseService], None, None]:
    """Launch TraceWiseDashboardServer with an isolated review database."""
    store = ReviewStore(tmp_path / "api_reviews.db")
    service = TraceWiseService(review_store=store)
    server = TraceWiseDashboardServer(port=0, service=service)
    server.start(in_thread=True)
    try:
        yield server, service
    finally:
        server.shutdown()


def _http_request(
    url: str, method: str = "GET", payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, str], dict[str, Any]]:
    """Helper to perform HTTP request and parse JSON output."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return (
                resp.status,
                dict(resp.headers),
                json.loads(body.decode("utf-8")),
            )
    except urllib.error.HTTPError as err:
        body = err.read()
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:
            parsed = {"raw": body.decode("utf-8")}
        return err.code, dict(err.headers), parsed


class TestDashboardReviewsApi:
    """Verifies all REST API routes for recording and querying review decisions."""

    def test_post_and_get_decision_flow(
        self,
        review_server: tuple[TraceWiseDashboardServer, TraceWiseService],
    ) -> None:
        server, _ = review_server
        base_url = (
            f"{server.url}/api/projects/sample_project/requirements/REQ-001/decisions"
        )

        # 1. Initially no decision found
        target = "src/auth/service.py#AuthenticationService.authenticate_user"
        enc_target = urllib.parse.quote(target)
        status, _, body = _http_request(
            f"{base_url}?target_id={enc_target}", method="GET"
        )
        assert status == 404
        assert "error" in body

        # 2. Record accepted decision
        post_payload = {
            "target_id": target,
            "decision": "accepted",
            "rationale": "Directly implements password verification.",
        }
        status, _, body = _http_request(base_url, method="POST", payload=post_payload)
        assert status == 200
        assert body["project_id"] == "sample_project"
        assert body["requirement_id"] == "REQ-001"
        assert body["target_id"] == target
        assert body["decision"] == "accepted"
        assert body["rationale"] == "Directly implements password verification."
        assert body["revision_count"] == 1

        # 3. GET specific decision
        status, _, body = _http_request(
            f"{base_url}?target_id={enc_target}", method="GET"
        )
        assert status == 200
        assert body["decision"] == "accepted"
        assert body["revision_count"] == 1

        # 4. Revise decision to needs_review
        revise_payload = {
            "target_id": target,
            "decision": "needs_review",
            "rationale": "Revisiting pending test results.",
        }
        status, _, body = _http_request(base_url, method="POST", payload=revise_payload)
        assert status == 200
        assert body["decision"] == "needs_review"
        assert body["revision_count"] == 2

        # 5. GET all decisions for REQ-001
        status, _, body = _http_request(base_url, method="GET")
        assert status == 200
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["target_id"] == target
        assert body[0]["revision_count"] == 2

        # 6. GET audit history for candidate
        history_url = f"{base_url}/history?target_id={enc_target}"
        status, _, history_body = _http_request(history_url, method="GET")
        assert status == 200
        assert isinstance(history_body, list)
        assert len(history_body) == 2
        assert history_body[0]["revision_number"] == 1
        assert history_body[0]["decision"] == "accepted"
        assert history_body[1]["revision_number"] == 2
        assert history_body[1]["decision"] == "needs_review"

    def test_post_rejected_and_empty_rationale_validation(
        self,
        review_server: tuple[TraceWiseDashboardServer, TraceWiseService],
    ) -> None:
        server, _ = review_server
        url = f"{server.url}/api/projects/sample_project/requirements/REQ-001/decisions"
        valid_target = "src/auth/service.py#AuthenticationResult"

        # Missing rationale for rejected -> 400
        status, _, body = _http_request(
            url,
            method="POST",
            payload={
                "target_id": valid_target,
                "decision": "rejected",
                "rationale": "",
            },
        )
        assert status == 400
        assert "rationale" in body.get("error", "").lower()

        # Valid rationale for rejected -> 200
        status, _, body = _http_request(
            url,
            method="POST",
            payload={
                "target_id": valid_target,
                "decision": "rejected",
                "rationale": "Result container rather than core auth logic.",
            },
        )
        assert status == 200
        assert body["decision"] == "rejected"

    def test_post_unknown_artifacts_return_404(
        self,
        review_server: tuple[TraceWiseDashboardServer, TraceWiseService],
    ) -> None:
        server, _ = review_server
        valid_target = "src/auth/service.py#AuthenticationService.authenticate_user"

        # Unknown project
        status, _, _ = _http_request(
            f"{server.url}/api/projects/unknown_proj/requirements/REQ-001/decisions",
            method="POST",
            payload={
                "target_id": valid_target,
                "decision": "accepted",
                "rationale": "Reason",
            },
        )
        assert status == 404

        # Unknown requirement
        status, _, _ = _http_request(
            f"{server.url}/api/projects/sample_project/requirements/REQ-999/decisions",
            method="POST",
            payload={
                "target_id": valid_target,
                "decision": "accepted",
                "rationale": "Reason",
            },
        )
        assert status == 404

        # Unknown target
        status, _, _ = _http_request(
            f"{server.url}/api/projects/sample_project/requirements/REQ-001/decisions",
            method="POST",
            payload={
                "target_id": "src/non_existent.py",
                "decision": "accepted",
                "rationale": "Reason",
            },
        )
        assert status == 404

    def test_cors_options_preflight(
        self,
        review_server: tuple[TraceWiseDashboardServer, TraceWiseService],
    ) -> None:
        server, _ = review_server
        req = urllib.request.Request(
            f"{server.url}/api/projects/sample_project/requirements/REQ-001/decisions",
            method="OPTIONS",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 204
            allow_methods = resp.headers.get("Access-Control-Allow-Methods", "")
            assert "POST" in allow_methods
            assert "GET" in allow_methods

    def test_post_malformed_and_invalid_payloads(
        self,
        review_server: tuple[TraceWiseDashboardServer, TraceWiseService],
    ) -> None:
        server, _ = review_server
        url = f"{server.url}/api/projects/sample_project/requirements/REQ-001/decisions"
        valid_target = "src/auth/service.py#AuthenticationService.authenticate_user"

        # 1. Missing target_id
        st, _, body = _http_request(
            url,
            method="POST",
            payload={"decision": "accepted", "rationale": "Valid reason"},
        )
        assert st == 400
        assert "target_id" in body.get("error", "").lower()

        # 2. Missing decision
        st, _, body = _http_request(
            url,
            method="POST",
            payload={"target_id": valid_target, "rationale": "Valid reason"},
        )
        assert st == 400
        assert "decision" in body.get("error", "").lower()

        # 3. Invalid decision status string
        st, _, body = _http_request(
            url,
            method="POST",
            payload={
                "target_id": valid_target,
                "decision": "confirmed",
                "rationale": "Valid reason",
            },
        )
        assert st == 400
        assert "invalid decision status" in body.get("error", "").lower()

        # 4. Non-string rationale
        st, _, body = _http_request(
            url,
            method="POST",
            payload={
                "target_id": valid_target,
                "decision": "accepted",
                "rationale": 12345,
            },
        )
        assert st == 400
        assert "rationale" in body.get("error", "").lower()

        # 5. Non-JSON raw body
        raw_req = urllib.request.Request(
            url,
            data=b"not-valid-json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(raw_req) as resp:
                assert resp.status == 400
        except urllib.error.HTTPError as err:
            assert err.code == 400

    def test_get_history_all_targets_for_requirement(
        self,
        review_server: tuple[TraceWiseDashboardServer, TraceWiseService],
    ) -> None:
        server, _ = review_server
        base_url = (
            f"{server.url}/api/projects/sample_project/requirements/REQ-001/decisions"
        )
        t1 = "src/auth/service.py#AuthenticationService.authenticate_user"
        t2 = "src/auth/service.py#AuthenticationResult"

        _http_request(
            base_url,
            method="POST",
            payload={"target_id": t1, "decision": "accepted", "rationale": "R1"},
        )
        _http_request(
            base_url,
            method="POST",
            payload={"target_id": t2, "decision": "rejected", "rationale": "R2"},
        )

        # GET history without target_id returns all events for REQ-001
        status, _, events = _http_request(f"{base_url}/history", method="GET")
        assert status == 200
        assert isinstance(events, list)
        assert len(events) >= 2
        event_targets = [e["target_id"] for e in events]
        assert t1 in event_targets
        assert t2 in event_targets

    def test_multiple_candidate_decisions_isolation_in_api(
        self,
        review_server: tuple[TraceWiseDashboardServer, TraceWiseService],
    ) -> None:
        server, _ = review_server
        base_url = (
            f"{server.url}/api/projects/sample_project/requirements/REQ-001/decisions"
        )
        t1 = "src/auth/service.py#AuthenticationService.authenticate_user"
        t2 = "src/auth/service.py#AuthenticationResult"

        # Record accepted for t1, rejected for t2
        _http_request(
            base_url,
            method="POST",
            payload={
                "target_id": t1,
                "decision": "accepted",
                "rationale": "Primary entrypoint",
            },
        )
        _http_request(
            base_url,
            method="POST",
            payload={
                "target_id": t2,
                "decision": "rejected",
                "rationale": "Data structure only",
            },
        )

        # Candidates API check
        cand_url = (
            f"{server.url}/api/projects/sample_project/requirements/REQ-001/candidates"
            "?method=b0_tfidf&top_k=5"
        )
        status, _, cand_data = _http_request(cand_url, method="GET")
        assert status == 200
        cands = {c["target_id"]: c for c in cand_data["candidates"]}

        assert cands[t1]["developer_verification_status"] == "accepted"
        assert cands[t1]["developer_verification_note"] == "Primary entrypoint"
        assert cands[t1]["developer_verification_revision_count"] == 1

        assert cands[t2]["developer_verification_status"] == "rejected"
        assert cands[t2]["developer_verification_note"] == "Data structure only"
        assert cands[t2]["developer_verification_revision_count"] == 1

    def test_unexpected_internal_exception_security_hardening(
        self,
        review_server: tuple[TraceWiseDashboardServer, TraceWiseService],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        server, service = review_server
        base_url = (
            f"{server.url}/api/projects/sample_project/requirements/REQ-001/decisions"
        )
        secret_trace = "CRITICAL_INTERNAL_DATABASE_CRASH_SECRET_998877"
        valid_target = "src/auth/service.py#AuthenticationService.authenticate_user"

        # 1. Test POST endpoint failure hardening
        def _failing_record(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(secret_trace)

        monkeypatch.setattr(service, "record_review_decision", _failing_record)
        post_status, _, post_body = _http_request(
            base_url,
            method="POST",
            payload={
                "target_id": valid_target,
                "decision": "accepted",
                "rationale": "Valid reason.",
            },
        )
        assert post_status == 500
        assert secret_trace not in json.dumps(post_body)
        assert post_body["error"] == "Internal server error."

        # 2. Test GET endpoint failure hardening
        def _failing_get(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("CRITICAL_GET_CRASH_TOKEN_112233")

        monkeypatch.setattr(service, "get_review_decision", _failing_get)
        enc_target = urllib.parse.quote(valid_target)
        get_status, _, get_body = _http_request(
            f"{base_url}?target_id={enc_target}",
            method="GET",
        )
        assert get_status == 500
        assert "CRITICAL_GET_CRASH_TOKEN_112233" not in json.dumps(get_body)
        assert get_body["error"] == "Internal server error."
