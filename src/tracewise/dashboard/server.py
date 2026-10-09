"""HTTP server and REST API for TraceWise Dashboard V0.

Provides standard library-based threaded HTTP serving for static SPA assets
and JSON REST API endpoints for projects, requirements, and candidate retrieval.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from tracewise.dashboard.service import TraceWiseService

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Request handler implementing TraceWise REST API and static file delivery."""

    server: ThreadingHTTPServer  # Type hint for attached server

    def log_message(self, format: str, *args: Any) -> None:
        """Route request logs to Python logger instead of stderr directly."""
        logger.debug(
            "%s - - [%s] " + format,
            self.address_string(),
            self.log_date_time_string(),
            *args,
        )

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests for REST API endpoints and static assets."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query_params = urllib.parse.parse_qs(parsed.query)

        # Route 1: REST API
        if path.startswith("/api/"):
            self._handle_api(path, query_params)
            return

        # Route 2: Static files
        self._handle_static(path)

    def _send_cors_headers(self) -> None:
        """Send open CORS headers for local client communication."""
        self.send_header("Access-Control-Allow-Origin", "*")

    def _send_json(self, status: int, data: Any) -> None:
        """Send JSON response with proper headers."""
        try:
            body = json.dumps(data, indent=2).encode("utf-8")
        except Exception as exc:
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, f"Serialization error: {exc}"
            )
            return

        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str, details: Any = None) -> None:
        """Send structured JSON error message."""
        payload = {
            "error": message,
            "status": int(status),
        }
        if details is not None:
            payload["details"] = details
        self._send_json(status, payload)

    def _handle_api(self, path: str, query_params: dict[str, list[str]]) -> None:
        """Dispatch REST API endpoints."""
        service: TraceWiseService = getattr(self.server, "service")  # noqa: B009

        # 1. Health check
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {"status": "ok", "version": "0.1.0"})
            return

        # 2. Retrieval methods catalog
        if path == "/api/retrieval-methods":
            self._send_json(HTTPStatus.OK, service.get_supported_methods())
            return

        # 3. Projects list
        if path in ("/api/projects", "/api/projects/"):
            try:
                projects = service.get_projects()
                self._send_json(HTTPStatus.OK, projects)
            except Exception as exc:
                logger.exception("Error fetching projects")
                self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return

        # 4. Project-scoped endpoints: /api/projects/{project_id}/...
        parts = [p for p in path.strip("/").split("/") if p]
        # parts: ['api', 'projects', '<project_id>', ...]
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "projects":
            project_id = parts[2]

            # GET /api/projects/{project_id}
            if len(parts) == 3:
                try:
                    detail = service.get_project_details(project_id)
                    self._send_json(HTTPStatus.OK, detail)
                except KeyError as exc:
                    self._send_error(HTTPStatus.NOT_FOUND, str(exc))
                except Exception as exc:
                    logger.exception("Error fetching project %s", project_id)
                    self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                return

            # GET /api/projects/{project_id}/requirements
            if len(parts) == 4 and parts[3] == "requirements":
                mode = query_params.get("mode", ["evaluation"])[0]
                try:
                    reqs = service.get_requirements(project_id, mode=mode)
                    self._send_json(HTTPStatus.OK, reqs)
                except KeyError as exc:
                    self._send_error(HTTPStatus.NOT_FOUND, str(exc))
                except ValueError as exc:
                    self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                except Exception as exc:
                    logger.exception("Error fetching requirements for %s", project_id)
                    self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                return

            # Sub-routes: /api/projects/{project_id}/requirements/{req_id}/...
            if len(parts) >= 5 and parts[3] == "requirements":
                req_id = urllib.parse.unquote(parts[4])

                # GET /api/projects/{project_id}/requirements/{req_id}
                if len(parts) == 5:
                    mode = query_params.get("mode", ["evaluation"])[0]
                    try:
                        detail = service.get_requirement_detail(
                            project_id, req_id, mode=mode
                        )
                        self._send_json(HTTPStatus.OK, detail)
                    except KeyError as exc:
                        self._send_error(HTTPStatus.NOT_FOUND, str(exc))
                    except ValueError as exc:
                        self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    except Exception as exc:
                        logger.exception(
                            "Error fetching req %s in %s", req_id, project_id
                        )
                        self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                    return

                # GET /api/projects/{project_id}/requirements/{req_id}/candidates
                if len(parts) == 6 and parts[5] == "candidates":
                    method = query_params.get("method", ["b1_bm25"])[0]
                    top_k_str = query_params.get("top_k", ["20"])[0]
                    mode = query_params.get("mode", ["evaluation"])[0]
                    try:
                        top_k = int(top_k_str)
                        if top_k <= 0:
                            raise ValueError("top_k must be > 0")
                    except ValueError:
                        self._send_error(
                            HTTPStatus.BAD_REQUEST,
                            f"Invalid top_k: '{top_k_str}'. Must be a positive int.",
                        )
                        return

                    try:
                        candidates_data = service.get_candidates(
                            project_id=project_id,
                            requirement_id=req_id,
                            method=method,
                            top_k=top_k,
                            mode=mode,
                        )
                        self._send_json(HTTPStatus.OK, candidates_data)
                    except KeyError as exc:
                        self._send_error(HTTPStatus.NOT_FOUND, str(exc))
                    except ValueError as exc:
                        self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    except Exception as exc:
                        logger.exception(
                            "Error retrieving candidates for %s / %s",
                            project_id,
                            req_id,
                        )
                        self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
                    return

        self._send_error(HTTPStatus.NOT_FOUND, f"API endpoint not found: {path}")

    def _handle_static(self, path: str) -> None:
        """Serve static single-page application assets securely."""
        clean_path = path.lstrip("/")
        if clean_path == "favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_cors_headers()
            self.end_headers()
            return

        if not clean_path or clean_path in ("index.html", ""):
            file_path = STATIC_DIR / "index.html"
        else:
            file_path = (STATIC_DIR / clean_path).resolve()

        # Prevent directory traversal
        try:
            resolved_static = STATIC_DIR.resolve()
            file_path.relative_to(resolved_static)
        except ValueError:
            self._send_error(HTTPStatus.FORBIDDEN, "Access denied.")
            return

        if not file_path.is_file():
            # In SPA mode, if not found and not an asset file, fallback to index.html
            if "." not in file_path.name:
                file_path = STATIC_DIR / "index.html"
            else:
                self._send_error(
                    HTTPStatus.NOT_FOUND, f"Static asset not found: {path}"
                )
                return

        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            if file_path.suffix == ".css":
                content_type = "text/css"
            elif file_path.suffix == ".js":
                content_type = "application/javascript"
            elif file_path.suffix == ".html":
                content_type = "text/html"
            else:
                content_type = "application/octet-stream"

        try:
            body = file_path.read_bytes()
        except Exception as exc:
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, f"Error reading file: {exc}"
            )
            return

        self.send_response(HTTPStatus.OK)
        self._send_cors_headers()
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TraceWiseDashboardServer:
    """Threaded HTTP server running the TraceWise dashboard backend."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        service: TraceWiseService | None = None,
    ) -> None:
        """Initialize the dashboard server with host, port, and service instance."""
        self.host = host
        self.requested_port = port
        self.service = service or TraceWiseService()
        self._server = ThreadingHTTPServer(
            (self.host, self.requested_port), DashboardRequestHandler
        )
        self._server.service = self.service  # type: ignore[attr-defined]
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None
        self._is_running = False

    @property
    def port(self) -> int:
        """Effective bound server port (crucial when port 0 is used for tests)."""
        return int(self._server.server_port)

    @property
    def url(self) -> str:
        """Base URL to access the dashboard."""
        return f"http://{self.host}:{self.port}"

    def start(self, in_thread: bool = False) -> None:
        """Start listening for incoming HTTP requests."""
        if self._is_running:
            return

        self._is_running = True
        if in_thread:
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="TraceWiseDashboardServerThread",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "TraceWise Dashboard server running in background at %s", self.url
            )
        else:
            logger.info("TraceWise Dashboard server listening at %s", self.url)
            try:
                self._server.serve_forever()
            finally:
                self._is_running = False

    def shutdown(self) -> None:
        """Stop server execution and release system socket resources."""
        if not self._is_running:
            return

        self._server.shutdown()
        self._server.server_close()
        self._is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("TraceWise Dashboard server shut down.")

    def __enter__(self) -> TraceWiseDashboardServer:
        """Enter context manager by starting server in background thread."""
        self.start(in_thread=True)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager by gracefully shutting down server."""
        self.shutdown()


__all__ = ["DashboardRequestHandler", "STATIC_DIR", "TraceWiseDashboardServer"]
