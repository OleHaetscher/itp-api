"""
Serve the mock client of the ITP API.

The primary client of the API is a JavaScript application that does not exist
yet. ``ui/index.html`` stands in for it: one page, no build step, calling the
API from the browser the way that application will. This module serves it.

The port is not arbitrary. ``APISpecification`` allows browser requests from
``http://localhost:5173`` and ``http://127.0.0.1:5173`` only, so a page served
anywhere else is refused by CORS before it reaches a route. Serving the page
from the API process instead would make it same-origin and hide that check,
which is the opposite of what a mock client is for.

Start the API first, in another terminal::

    python -m src.run_model_api

then::

    python -m src.run_mock_ui
"""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UI_DIRECTORY = Path(__file__).resolve().parents[1] / "ui"

HOST = "127.0.0.1"
PORT = 5173


class MockUIRequestHandler(SimpleHTTPRequestHandler):
    """
    Request handler serving the mock client without caching it.

    Args:

    Returns:
    """

    def end_headers(
        self,
    ) -> None:
        """
        Send the response headers, with caching disabled.

        A cached page is the classic way to spend ten minutes debugging an
        edit that was never loaded, and nothing here is worth caching.

        Args:

        Returns:
        """

        self.send_header("Cache-Control", "no-store")

        super().end_headers()

    def log_message(
        self,
        format: str,
        *args: object,
    ) -> None:
        """
        Log one served request.

        Args:
            format: Format string of the log line.
            args: Values of the log line.

        Returns:
        """

        print(f"  {self.address_string()} {format % args}")


def make_server(
    host: str = HOST,
    port: int = PORT,
) -> ThreadingHTTPServer:
    """
    Create the server for the mock client.

    Threading matters: the two-participant flow is two browser tabs, each
    holding a long poll open against the API while asking this server for
    assets, and a single-threaded server would serialize them.

    Args:
        host: Host the page is served on.
        port: Port the page is served on. The CORS list of the API allows 5173.

    Returns:
        Server for the mock client.
    """

    if not UI_DIRECTORY.is_dir():
        raise FileNotFoundError(f"No mock client directory at {UI_DIRECTORY}")

    handler = partial(MockUIRequestHandler, directory=str(UI_DIRECTORY))

    return ThreadingHTTPServer((host, port), handler)


if __name__ == "__main__":
    server = make_server()

    print(f"\n  ITP API mock client  ->  http://{HOST}:{PORT}\n")
    print("  The API is expected at http://127.0.0.1:8001 (python -m src.run_model_api).\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped\n")
    finally:
        server.server_close()
