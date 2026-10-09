"""CLI entry point for running the TraceWise Dashboard V0 server.

Usage:
    python -m tracewise.dashboard [--host HOST] [--port PORT] [--no-browser]
"""

from __future__ import annotations

import argparse
import logging
import sys
import webbrowser

from tracewise.dashboard.server import TraceWiseDashboardServer
from tracewise.dashboard.service import TraceWiseService


def main() -> None:
    """Parse CLI arguments and launch TraceWise Dashboard server."""
    parser = argparse.ArgumentParser(
        description="Launch TraceWise Dashboard V0 (Traceability Inspection)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address to bind the HTTP server to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number to listen on",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not automatically open the dashboard in default browser",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    service = TraceWiseService()
    server = TraceWiseDashboardServer(
        host=args.host,
        port=args.port,
        service=service,
    )

    print("=" * 64)
    print("  TraceWise Dashboard V0")
    print(f"  Server listening at: {server.url}")
    print("  Supported datasets:  sample_project, iTrust, eTour")
    print("  Retrieval models:    B0 (TF-IDF), B1 (BM25), B2 (Semantic),")
    print("                       B3 (Structural), B4 (Hybrid RRF), B5 (LLM Rerank)")
    print("  Press Ctrl+C to terminate.")
    print("=" * 64)

    if not args.no_browser:
        try:
            webbrowser.open(server.url)
        except Exception:
            pass

    try:
        server.start(in_thread=False)
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt. Shutting down TraceWise Dashboard...")
    finally:
        server.shutdown()
        print("TraceWise Dashboard stopped.")


if __name__ == "__main__":
    sys.exit(main())
