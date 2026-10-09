"""Real-browser verification runner for TraceWise Dashboard V0.

Automates Google Chrome via Chrome DevTools Protocol (CDP) to thoroughly verify
the dashboard interface across all datasets, baselines B0-B5, modes, and interactions.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import socket
import struct
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from tracewise.dashboard.reviews import ReviewStore
from tracewise.dashboard.server import TraceWiseDashboardServer
from tracewise.dashboard.service import TraceWiseService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("BrowserVerifier")


class ChromeCDPClient:
    """Minimal WebSocket client for Chrome DevTools Protocol."""

    def __init__(self, ws_url: str, timeout: float = 15.0) -> None:
        self.msg_id = 0
        self.console_errors: list[dict[str, Any]] = []
        self.console_logs: list[dict[str, Any]] = []

        # Parse ws://127.0.0.1:port/path
        parts = ws_url.replace("ws://", "").split("/", 1)
        host_port = parts[0].split(":")
        host = host_port[0]
        port = int(host_port[1])
        path = "/" + (parts[1] if len(parts) > 1 else "")

        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode("utf-8")
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(handshake.encode("utf-8"))
        resp = self.sock.recv(4096)
        if b"101" not in resp:
            raise RuntimeError(f"WebSocket handshake failed: {resp!r}")

    def send_cmd(self, method: str, params: dict[str, Any] | None = None) -> int:
        self.msg_id += 1
        payload = json.dumps(
            {"id": self.msg_id, "method": method, "params": params or {}}
        ).encode("utf-8")
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header = bytes([0x81, 0x80 | length])
        elif length < 65536:
            header = bytes([0x81, 0x80 | 126]) + struct.pack(">H", length)
        else:
            header = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", length)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + mask + masked)
        return self.msg_id

    def recv_frame(self) -> dict[str, Any] | None:
        head = self.sock.recv(2)
        if not head:
            return None
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self.sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self.sock.recv(8))[0]

        buf = bytearray()
        while len(buf) < length:
            chunk = self.sock.recv(min(8192, length - len(buf)))
            if not chunk:
                break
            buf.extend(chunk)

        try:
            msg = json.loads(buf.decode("utf-8"))
            if msg.get("method") == "Runtime.consoleAPICalled":
                params = msg.get("params", {})
                level = params.get("type", "log")
                args = [
                    a.get("value") or a.get("description")
                    for a in params.get("args", [])
                ]
                entry = {"level": level, "args": args}
                self.console_logs.append(entry)
                if level == "error":
                    self.console_errors.append(entry)
            elif msg.get("method") == "Log.entryAdded":
                entry = msg.get("params", {}).get("entry", {})
                if entry.get("level") == "error":
                    self.console_errors.append(entry)
            return msg
        except Exception:
            return None

    def call(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 12.0
    ) -> dict[str, Any]:
        target_id = self.send_cmd(method, params)
        t_end = time.time() + timeout
        while time.time() < t_end:
            msg = self.recv_frame()
            if msg and msg.get("id") == target_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error in {method}: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(f"CDP call {method} timed out after {timeout}s")

    def eval_js(self, expression: str, timeout: float = 10.0) -> Any:
        res = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
            timeout=timeout,
        )
        if "exceptionDetails" in res:
            exc = res["exceptionDetails"]
            text = exc.get("text", "")
            desc = exc.get("exception", {}).get("description", "")
            raise RuntimeError(f"JavaScript evaluation error: {text} {desc}")
        result_obj = res.get("result", {})
        if "value" in result_obj:
            return result_obj["value"]
        return result_obj

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


def run_browser_verification() -> dict[str, Any]:
    """Execute real-browser acceptance test for TraceWise Dashboard V0."""
    # Temporary profile and review store for test isolation
    profile_dir = Path("scratch/chrome_verification_profile").resolve()
    shutil.rmtree(profile_dir, ignore_errors=True)
    profile_dir.mkdir(parents=True, exist_ok=True)

    browser_review_db = profile_dir / "browser_reviews.db"
    review_store = ReviewStore(browser_review_db)

    logger.info("Starting local TraceWise Dashboard Server on ephemeral port...")
    service = TraceWiseService(review_store=review_store)
    server = TraceWiseDashboardServer(host="127.0.0.1", port=0, service=service)
    server.start(in_thread=True)
    server_url = server.url
    logger.info("Dashboard Server live at %s", server_url)

    # Launch Chrome
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    cdp_port = 9333
    chrome_cmd = [
        chrome_path,
        "--headless=new",
        f"--remote-debugging-port={cdp_port}",
        f"--user-data-dir={profile_dir}",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    logger.info("Launching Google Chrome headless with CDP port %d...", cdp_port)
    proc = subprocess.Popen(chrome_cmd)
    time.sleep(2.0)

    results: dict[str, Any] = {"steps": [], "errors": [], "success": False}

    try:
        # Create a new page target
        req = urllib.request.Request(
            f"http://127.0.0.1:{cdp_port}/json/new?about:blank", method="PUT"
        )
        with urllib.request.urlopen(req) as resp:
            target = json.loads(resp.read())

        ws_url = target["webSocketDebuggerUrl"]
        logger.info("Connecting to Chrome target: %s", ws_url)
        client = ChromeCDPClient(ws_url)

        # Enable runtime & console monitoring
        client.call("Runtime.enable")
        client.call("Page.enable")
        client.call("Log.enable")

        def wait_until(expr: str, expected: Any = None, timeout: float = 15.0) -> Any:
            t_end = time.time() + timeout
            last_v = None
            while time.time() < t_end:
                last_v = client.eval_js(expr)
                if expected is not None:
                    if last_v == expected:
                        return last_v
                elif last_v:
                    return last_v
                time.sleep(0.15)
            return last_v

        # Step 1: Navigate to Dashboard URL
        logger.info("[Step 1] Navigating to %s ...", server_url)
        client.call("Page.navigate", {"url": server_url})
        time.sleep(1.5)

        # Verify page title and header
        title = client.eval_js("document.title")
        assert "TraceWise Dashboard" in title, f"Unexpected title: {title}"
        logger.info("Page Title verified: '%s'", title)
        results["steps"].append("page_load_ok")

        # Step 2: Verify Projects Loaded (default sample_project)
        logger.info("[Step 2] Verifying initial project loading...")
        wait_until(
            "document.querySelectorAll('#project-select option').length > 1",
            True,
            timeout=10.0,
        )
        proj_opts = client.eval_js(
            "Array.from(document.querySelectorAll('#project-select option'))"
            ".map(o => o.value)"
        )
        assert "sample_project" in proj_opts, (
            f"sample_project missing from dropdown: {proj_opts}"
        )
        assert "itrust" in proj_opts, "itrust missing from dropdown"
        assert "etour" in proj_opts, "etour missing from dropdown"
        logger.info("Discovered projects in dropdown: %s", proj_opts)

        req_items_count = client.eval_js(
            "document.querySelectorAll('.req-item').length"
        )
        assert req_items_count == 10, (
            f"Expected 10 requirements for sample_project, got {req_items_count}"
        )
        logger.info("Sample project requirements count in DOM: %d", req_items_count)
        results["steps"].append("projects_dropdown_ok")

        # Step 3: Verify Default Candidate Hypotheses (B1 BM25, REQ-001)
        logger.info("[Step 3] Verifying initial candidate hypotheses for REQ-001...")
        time.sleep(0.5)
        detail_id = client.eval_js(
            "document.getElementById('detail-req-id').textContent"
        )
        assert detail_id == "REQ-001", f"Expected REQ-001, got {detail_id}"

        cands_count = client.eval_js(
            "document.querySelectorAll('.candidate-card').length"
        )
        assert cands_count == 20, (
            f"Expected 20 candidates for Top-20 cutoff, got {cands_count}"
        )
        top_target = client.eval_js(
            "document.querySelector('.candidate-target-id').textContent"
        )
        assert "AuthenticationService" in top_target, (
            f"Unexpected top candidate: {top_target}"
        )
        logger.info("REQ-001 Top Candidate: %s (total: %d)", top_target, cands_count)
        results["steps"].append("b1_candidates_ok")

        # Step 4: Verify Cutoff Top-K (Change to Top 5 and Top 10)
        logger.info("[Step 4] Testing Top-K cutoff changes (Top 5, Top 10)...")
        client.eval_js("""(() => {
            const sel = document.getElementById('topk-select');
            sel.value = '5';
            sel.dispatchEvent(new Event('change'));
        })()""")
        wait_until("document.querySelectorAll('.candidate-card').length === 5", True)
        cands_5 = client.eval_js("document.querySelectorAll('.candidate-card').length")
        assert cands_5 == 5, f"Expected 5 candidates for Top-5, got {cands_5}"

        client.eval_js("""(() => {
            const sel = document.getElementById('topk-select');
            sel.value = '10';
            sel.dispatchEvent(new Event('change'));
        })()""")
        wait_until("document.querySelectorAll('.candidate-card').length === 10", True)
        cands_10 = client.eval_js("document.querySelectorAll('.candidate-card').length")
        assert cands_10 == 10, f"Expected 10 candidates for Top-10, got {cands_10}"
        logger.info("Cutoff selector verified: 5 and 10 cards rendered correctly.")
        results["steps"].append("cutoff_topk_ok")

        # Reset back to 20
        client.eval_js("""(() => {
            const sel = document.getElementById('topk-select');
            sel.value = '20';
            sel.dispatchEvent(new Event('change'));
        })()""")
        wait_until("document.querySelectorAll('.candidate-card').length === 20", True)

        # Step 4.5: Verify Progressive Disclosure (3-5 candidates initially)
        logger.info("[Step 4.5] Verifying progressive disclosure (5 initial)...")
        cand_count_expr = (
            "Array.from(document.querySelectorAll('.candidate-card'))"
            ".filter(c => c.style.display !== 'none').length"
        )
        visible_cands = client.eval_js(cand_count_expr)
        assert visible_cands == 5, (
            f"Expected 5 visible candidates initially, got {visible_cands}"
        )
        reveal_text = client.eval_js(
            "document.getElementById('reveal-btn-text').textContent"
        )
        assert "15 more" in reveal_text, f"Unexpected reveal button text: {reveal_text}"

        # Click reveal button to expand all 20
        client.eval_js("document.getElementById('btn-reveal-candidates').click()")
        revealed_cands = client.eval_js(cand_count_expr)
        assert revealed_cands == 20, (
            f"Expected 20 visible candidates after reveal, got {revealed_cands}"
        )

        # Click reveal button again to collapse back to top 5
        client.eval_js("document.getElementById('btn-reveal-candidates').click()")
        recollapsed_cands = client.eval_js(cand_count_expr)
        assert recollapsed_cands == 5, (
            f"Expected 5 visible candidates after recollapse, got {recollapsed_cands}"
        )
        logger.info("Progressive disclosure verified: 5 -> 20 -> 5.")
        results["steps"].append("progressive_disclosure_ok")

        # Step 5: Verify B5 LLM Reranking (Cached Checkpoint)
        logger.info("[Step 5] Testing B5 LLM Reranking baseline...")
        client.eval_js("""(() => {
            const sel = document.getElementById('method-select');
            sel.value = 'b5_llm_rerank';
            sel.dispatchEvent(new Event('change'));
        })()""")
        wait_until(
            "document.getElementById('telemetry-cached').style.display !== 'none'", True
        )
        b5_meta = client.eval_js(
            "document.querySelector('.candidate-meta-row').textContent"
        )
        assert "LLM Relevance" in b5_meta, (
            f"Expected LLM Relevance in meta row, got: {b5_meta}"
        )
        assert "Original BM25 Rank" in b5_meta, (
            f"Expected Original BM25 Rank in meta row, got: {b5_meta}"
        )
        logger.info(
            "B5 LLM Reranking loaded from precomputed checkpoint: '%s'", b5_meta.strip()
        )
        results["steps"].append("b5_baseline_ok")

        # Step 6: Test Baselines B0, B2, B3, B4
        for baseline in ["b0_tfidf", "b2_semantic", "b3_structural", "b4_hybrid"]:
            logger.info("Testing baseline %s ...", baseline)
            client.eval_js(f"""(() => {{
                const sel = document.getElementById('method-select');
                sel.value = '{baseline}';
                sel.dispatchEvent(new Event('change'));
            }})()""")
            wait_until(
                "document.querySelectorAll('.candidate-card').length > 0",
                True,
                timeout=20.0,
            )
            card_count = client.eval_js(
                "document.querySelectorAll('.candidate-card').length"
            )
            assert card_count > 0, f"Expected candidates for {baseline}, got 0"
            logger.info("Baseline %s returned %d candidates", baseline, card_count)
        results["steps"].append("all_baselines_ok")

        # Step 7: Test Dataset Switching to iTrust and eTour
        logger.info("[Step 7] Testing dataset switching to iTrust...")
        client.eval_js("""(() => {
            const psel = document.getElementById('project-select');
            psel.value = 'itrust';
            psel.dispatchEvent(new Event('change'));
        })()""")
        wait_until(
            "document.querySelectorAll('.req-item').length === 131", True, timeout=15.0
        )
        itrust_req_count = client.eval_js(
            "document.querySelectorAll('.req-item').length"
        )
        assert itrust_req_count == 131, (
            f"Expected 131 requirements for iTrust, got {itrust_req_count}"
        )
        logger.info("iTrust loaded with %d requirements in DOM", itrust_req_count)

        logger.info("Testing dataset switching to eTour...")
        client.eval_js("""(() => {
            const psel = document.getElementById('project-select');
            psel.value = 'etour';
            psel.dispatchEvent(new Event('change'));
        })()""")
        wait_until(
            "document.querySelectorAll('.req-item').length === 58", True, timeout=15.0
        )
        etour_req_count = client.eval_js(
            "document.querySelectorAll('.req-item').length"
        )
        assert etour_req_count == 58, (
            f"Expected 58 requirements for eTour, got {etour_req_count}"
        )
        logger.info("eTour loaded with %d requirements in DOM", etour_req_count)
        results["steps"].append("datasets_switching_ok")

        # Switch back to sample_project for detailed checks
        client.eval_js("""(() => {
            const psel = document.getElementById('project-select');
            psel.value = 'sample_project';
            psel.dispatchEvent(new Event('change'));
        })()""")
        wait_until(
            "document.querySelectorAll('.req-item').length === 10", True, timeout=15.0
        )
        wait_until(
            "document.querySelectorAll('.candidate-card').length > 0",
            True,
            timeout=15.0,
        )

        # Step 8: Verify Collapsed Code Preview and Copy Button (Requirement 5)
        logger.info("[Step 8] Testing collapsed code preview and Copy Code button...")
        # Verify code preview is collapsed by default
        initially_collapsed = client.eval_js(
            "document.querySelector('.code-block-container').style.display === 'none'"
        )
        assert initially_collapsed, "Code preview block must be collapsed by default"
        logger.info("Verified code preview is collapsed by default.")

        # Click toggle to expand code block
        client.eval_js("document.querySelector('.btn-toggle-code').click()")
        time.sleep(0.2)
        expanded = client.eval_js(
            "document.querySelector('.code-block-container').style.display !== 'none'"
        )
        assert expanded, "Code block must expand after clicking View Code"

        code_lines = client.eval_js(
            "document.querySelector('.code-block-header span').textContent"
        )
        assert "lines" in code_lines, (
            f"Expected line count in header, got: {code_lines}"
        )
        code_text = client.eval_js(
            "document.querySelector('.code-block-content').textContent"
        )
        assert len(code_text) > 20, "Code preview content is empty"

        copy_btn_text = client.eval_js(
            "document.querySelector('.copy-code-btn').textContent"
        )
        assert copy_btn_text == "Copy Code", f"Unexpected button text: {copy_btn_text}"
        client.eval_js("document.querySelector('.copy-code-btn').click()")
        time.sleep(0.3)
        copied_text = client.eval_js(
            "document.querySelector('.copy-code-btn').textContent"
        )
        assert copied_text == "Copied!", f"Expected 'Copied!', got {copied_text}"

        # Click toggle again to verify collapsing
        client.eval_js("document.querySelector('.btn-toggle-code').click()")
        time.sleep(0.2)
        recollapsed = client.eval_js(
            "document.querySelector('.code-block-container').style.display === 'none'"
        )
        assert recollapsed, "Code block must collapse again after second click"
        logger.info(
            "Code preview expand/collapse and Copy Code verified: '%s'", code_lines
        )
        results["steps"].append("code_preview_copy_ok")

        # Step 9: Verify Operating Mode Separation (Ground Truth Isolation)
        logger.info(
            "[Step 9] Verifying Mode Separation (Research vs. Developer Mode)..."
        )
        # In evaluation mode: check that gold badges exist
        eval_gold_badge_count = client.eval_js(
            "document.querySelectorAll('.badge-gold-match').length"
        )
        assert eval_gold_badge_count > 0, (
            "Evaluation mode must display gold link badges"
        )
        eval_pills_visible = client.eval_js(
            "document.getElementById('detail-gold-links-section')"
            ".style.display !== 'none'"
        )
        assert eval_pills_visible, (
            "Evaluation mode must display ground truth links section"
        )
        logger.info(
            "Research Mode: Gold match badges visible (%d found)", eval_gold_badge_count
        )

        # Switch to Developer Workflow Mode (Blinded)
        logger.info("Switching to Developer Workflow Mode (Blinded)...")
        client.eval_js("""(() => {
            const msel = document.getElementById('mode-select');
            msel.value = 'developer';
            msel.dispatchEvent(new Event('change'));
        })()""")
        wait_until(
            "document.getElementById('detail-gold-links-section')"
            ".style.display === 'none'",
            True,
        )
        wait_until("document.querySelectorAll('.candidate-card').length > 0", True)
        wait_until(
            "document.querySelector('.badge-verification-status') !== null", True
        )
        wait_until("document.querySelectorAll('.badge-gold-match').length === 0", True)
        wait_until("document.querySelectorAll('.badge-gold-link').length === 0", True)

        # In developer mode: verify strict ground truth isolation
        dev_gold_badge_count = client.eval_js(
            "document.querySelectorAll('.badge-gold-match').length"
        )
        assert dev_gold_badge_count == 0, (
            f"Developer mode LEAKED gold link badges! Count: {dev_gold_badge_count}"
        )

        dev_unlinked_badge_count = client.eval_js(
            "document.querySelectorAll('.badge-unlinked').length"
        )
        assert dev_unlinked_badge_count == 0, (
            "Developer mode LEAKED negative gold badges! "
            f"Count: {dev_unlinked_badge_count}"
        )

        dev_pills_hidden = client.eval_js(
            "document.getElementById('detail-gold-links-section')"
            ".style.display === 'none'"
        )
        assert dev_pills_hidden, "Developer mode must hide ground truth links section"

        dev_telemetry_hidden = client.eval_js(
            "document.getElementById('telemetry-matched').style.display === 'none'"
        )
        assert dev_telemetry_hidden, (
            "Developer mode must hide gold retrieval count telemetry"
        )

        dev_sidebar_gold_count = client.eval_js(
            "document.querySelectorAll('.badge-gold-link').length"
        )
        assert dev_sidebar_gold_count == 0, (
            "Developer mode must hide sidebar gold count badges"
        )

        dev_verif_badge = client.eval_js(
            "document.querySelector('.badge-verification-status').textContent"
        )
        assert "Pending Review" in dev_verif_badge, (
            f"Unexpected verification status badge: {dev_verif_badge}"
        )

        logger.info(
            "Developer Mode: Ground truth strictly blinded "
            "(0 gold badges, telemetry hidden, links section hidden)"
        )
        results["steps"].append("mode_isolation_ok")

        # Step 10: Verify Keyboard Navigation (Requirement 10)
        logger.info("[Step 10] Testing keyboard navigation on requirements list...")
        client.eval_js("""(() => {
            const items = document.querySelectorAll('.req-item');
            if (items.length > 1) {
                const ev = new KeyboardEvent('keydown', {key: 'Enter', bubbles: true});
                items[1].dispatchEvent(ev);
            }
        })()""")
        wait_until(
            "document.getElementById('detail-req-id').textContent === 'REQ-002'", True
        )
        req2_id = client.eval_js("document.getElementById('detail-req-id').textContent")
        assert req2_id == "REQ-002", (
            f"Expected REQ-002 selected via keyboard, got {req2_id}"
        )
        logger.info(
            "Keyboard navigation verified: Enter key selected REQ-002 successfully."
        )
        results["steps"].append("keyboard_navigation_ok")

        # Step 11: Verify Search Filtering and Empty State
        logger.info("[Step 11] Testing requirement search filter and empty state...")
        client.eval_js("""(() => {
            const inp = document.getElementById('req-search-input');
            inp.value = 'nonexistent_query_xyz';
            inp.dispatchEvent(new Event('input'));
        })()""")
        time.sleep(0.3)
        empty_visible = client.eval_js(
            "document.getElementById('req-empty-state').style.display !== 'none'"
        )
        assert empty_visible, (
            "Empty state should be displayed when search yields no matches"
        )

        # Clear search
        client.eval_js("document.getElementById('clear-search-btn').click()")
        time.sleep(0.3)
        cleared_reqs = client.eval_js("document.querySelectorAll('.req-item').length")
        assert cleared_reqs == 10, (
            f"Expected 10 requirements restored, got {cleared_reqs}"
        )
        logger.info("Search filter and empty state verified successfully.")
        results["steps"].append("search_empty_state_ok")

        # Step 12: Verify Developer Review Decision Workflow (Milestone B6.2)
        logger.info("[Step 12] Testing developer review decision workflow...")

        # 12a: Verify review action buttons exist on candidate cards in developer mode
        action_bars_count = client.eval_js(
            "document.querySelectorAll('.review-action-bar').length"
        )
        assert action_bars_count >= 5, (
            f"Expected candidate review action bars in developer mode, "
            f"got {action_bars_count}"
        )

        # 12b: Click Accept on candidate #1 to open inline review form
        client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".btn-review-accept').click()"
        )
        wait_until(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".review-form-panel').style.display === 'flex'",
            True,
        )

        form_title = client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".review-form-title').textContent"
        )
        assert "Accept" in form_title, (
            f"Expected Accept in form title, got {form_title}"
        )

        # 12c: Test validation: Click Save Decision with empty rationale
        client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".btn-save-decision').click()"
        )
        time.sleep(0.2)
        error_display = client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".review-form-error').style.display"
        )
        assert error_display != "none", (
            "Error alert should be visible when required rationale is empty"
        )
        error_text = client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".review-form-error').textContent"
        )
        assert "rationale is required" in error_text.lower(), (
            f"Expected required rationale error message, got {error_text}"
        )

        # Candidate status badge should remain 'Pending Review' (no optimistic update)
        current_badge = client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".badge-verification-status').textContent"
        )
        assert "Pending Review" in current_badge, (
            f"Badge should not update optimistically on failed validation: "
            f"{current_badge}"
        )

        # 12d: Type non-empty rationale and save decision
        client.eval_js("""(() => {
            const card = document.querySelector('.candidate-card[data-rank="1"]');
            const ta = card.querySelector('.review-form-textarea');
            ta.value = "Verified auth service handles password validation.";
            ta.dispatchEvent(new Event('input'));
        })()""")
        client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".btn-save-decision').click()"
        )

        # Wait until review form panel closes upon successful submission
        wait_until(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".review-form-panel').style.display === 'none'",
            True,
        )

        # Confirm badge updated to '✓ Accepted'
        updated_badge = client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".badge-verification-status').textContent"
        )
        assert "Accepted" in updated_badge, (
            f"Expected Accepted badge, got {updated_badge}"
        )

        # Confirm confirmed banner displays rationale
        confirmed_rationale = client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".review-rationale-text').textContent"
        )
        assert (
            "Verified auth service handles password validation." in confirmed_rationale
        ), f"Rationale not displayed in confirmed banner: {confirmed_rationale}"

        # Confirm history button shows '(1)'
        hist_btn_text = client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".btn-review-history').textContent"
        )
        assert "(1)" in hist_btn_text, (
            f"Expected (1) in history button text, got {hist_btn_text}"
        )

        # 12e: Test persistence: Switch to REQ-001 and back to REQ-002
        logger.info("Testing decision persistence across requirement navigation...")
        client.eval_js("document.querySelectorAll('.req-item')[0].click()")
        wait_until(
            "document.getElementById('detail-req-id').textContent === 'REQ-001'", True
        )

        client.eval_js("document.querySelectorAll('.req-item')[1].click()")
        wait_until(
            "document.getElementById('detail-req-id').textContent === 'REQ-002'", True
        )
        persisted_badge = wait_until(
            "(() => {"
            '  const b = document.querySelector(\'.candidate-card[data-rank="1"] '
            "  .badge-verification-status');"
            "  return b ? b.textContent : '';"
            "})()",
            expected="✓ Accepted",
        )
        assert "Accepted" in persisted_badge, (
            f"Expected Accepted badge persisted after navigation, got {persisted_badge}"
        )

        persisted_rationale = client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".review-rationale-text').textContent"
        )
        assert "Verified auth service" in persisted_rationale, (
            f"Rationale lost after navigation: {persisted_rationale}"
        )

        # 12f: Test decision audit history inspection
        logger.info("Testing decision audit history viewer...")
        client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".btn-review-history').click()"
        )
        wait_until(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".review-history-panel').style.display === 'block'",
            True,
        )
        wait_until(
            'document.querySelectorAll(\'.candidate-card[data-rank="1"] '
            ".history-item').length > 0",
            True,
        )

        history_items_count = client.eval_js(
            'document.querySelectorAll(\'.candidate-card[data-rank="1"] '
            ".history-item').length"
        )
        assert history_items_count == 1, (
            f"Expected 1 history item, got {history_items_count}"
        )

        history_item_text = client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".history-item').textContent"
        )
        assert "Revision 1" in history_item_text, (
            f"Expected Revision 1 in history item: {history_item_text}"
        )
        assert "Accepted" in history_item_text, (
            f"Expected Accepted in history item: {history_item_text}"
        )

        # Close history panel
        client.eval_js(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".btn-review-history').click()"
        )
        wait_until(
            'document.querySelector(\'.candidate-card[data-rank="1"] '
            ".review-history-panel').style.display === 'none'",
            True,
        )

        # 12g: Verify mode isolation: Switch back to Research/Evaluation mode
        logger.info(
            "Testing mode isolation: review controls hidden in Research Mode..."
        )
        client.eval_js("""(() => {
            const sel = document.getElementById('mode-select');
            sel.value = 'evaluation';
            sel.dispatchEvent(new Event('change'));
        })()""")
        wait_until(
            "document.getElementById('active-mode-label')"
            ".textContent.includes('Research Mode')",
            True,
        )
        time.sleep(0.5)

        eval_action_bars = client.eval_js(
            "document.querySelectorAll('.review-action-bar').length"
        )
        assert eval_action_bars == 0, (
            f"Expected 0 review action bars in Research Mode, got {eval_action_bars}"
        )

        # Verify benchmark ground truth section restored in Evaluation Mode
        eval_gold_section = client.eval_js(
            "document.getElementById('detail-gold-links-section')"
            ".style.display !== 'none'"
        )
        assert eval_gold_section, (
            "Evaluation Mode should restore benchmark ground truth links section"
        )

        logger.info("Developer review decision workflow and mode isolation verified.")
        results["steps"].append("developer_review_workflow_ok")

        # Step 13: Verify Browser Console Errors
        logger.info("[Step 13] Inspecting browser console for errors...")
        time.sleep(0.5)
        # Drain remaining messages
        while True:
            try:
                frame = client.recv_frame()
                if not frame:
                    break
            except Exception:
                break

        console_errors = [
            err for err in client.console_errors if "favicon.ico" not in str(err)
        ]
        logger.info("Total console errors detected: %d", len(console_errors))
        if console_errors:
            for err in console_errors:
                logger.error("Console Error: %s", err)
            results["errors"] = console_errors
        else:
            logger.info("PASS: 0 browser console errors detected.")

        assert len(console_errors) == 0, (
            f"Detected browser console errors: {console_errors}"
        )
        results["steps"].append("zero_console_errors_ok")
        results["success"] = True

    finally:
        logger.info("Shutting down Chrome and test server...")
        try:
            client.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass
        server.shutdown()
        shutil.rmtree(profile_dir, ignore_errors=True)

    return results


if __name__ == "__main__":
    res = run_browser_verification()
    print("=" * 60)
    print("Browser Verification Result:", "PASS" if res["success"] else "FAIL")
    print("Steps Verified:", res["steps"])
    print("Errors:", res["errors"])
    print("=" * 60)
