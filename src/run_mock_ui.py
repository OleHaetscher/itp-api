"""
Serve the mock client of the ITP API.

The primary client of the API is a JavaScript application that does not exist
yet. ``ui/index.html`` stands in for it: one page, no build step, calling the
API from the browser the way that application will. This module serves it.

Serving the page from the API process would make it same-origin and hide the
CORS check, which is the opposite of what a mock client is for, so this is a
second process on a second origin. 5173 is tried first, because that is the
port the README names, but a leftover process or an unrelated service holding
it is no reason to stop: the next free port in 5173-5182 is taken instead, and
the API allows that whole range through CORS. Set ``ITP_UI_PORT`` to name a
port, which is then obeyed exactly. A port outside the range still works,
because the API reads the same variable when it builds its origin list --- but
only if it is set for both processes.

Being a second process also means this one cannot see which port the API
bound. It finds out the same way any other client does, by probing the API's
candidate range, and hands the answer to the page as ``mock-ui-config.json``
so the base URL field is filled in before the first request. ``ITP_API_BASE_URL``
or ``ITP_API_PORT`` short-circuits the search. The field stays editable either
way: discovery is a convenience, not a constraint.

Start the API first, in another terminal::

    python -m src.run_model_api

then::

    python -m src.run_mock_ui
"""

from __future__ import annotations

import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.utils.ports import (
    UI_PORT_CANDIDATES,
    UI_PORT_VARIABLE,
    discover_api_base_url,
    looks_like_itp_api,
    resolve_port,
)

UI_DIRECTORY = Path(__file__).resolve().parents[1] / "ui"

HOST = "127.0.0.1"

# Path the page reads its API base URL from. It is served from memory and never
# touches the UI directory, so no file of this name exists to go stale.
CONFIG_PATH = "/mock-ui-config.json"


class MockUIRequestHandler(SimpleHTTPRequestHandler):
    """
    Request handler serving the mock client without caching it.

    Args:

    Returns:
    """

    def __init__(
        self,
        *args: object,
        api_base_url: str,
        **kwargs: object,
    ) -> None:
        """
        Initialize the handler for one request.

        The base URL is stored before the base class runs, because the base
        class handles the request from inside its own initializer.

        Args:
            args: Positional arguments of the base handler.
            api_base_url: Base URL the page should address the API under.
            kwargs: Keyword arguments of the base handler.

        Returns:
        """

        self.api_base_url = api_base_url

        super().__init__(*args, **kwargs)

    def do_GET(
        self,
    ) -> None:
        """
        Serve one GET request, answering the configuration path from memory.

        Args:

        Returns:
        """

        if self.path.split("?")[0] == CONFIG_PATH:
            self.send_configuration()

            return

        super().do_GET()

    def send_configuration(
        self,
    ) -> None:
        """
        Send the page the base URL the API was found at.

        Args:

        Returns:
        """

        body = json.dumps({"apiBaseUrl": self.api_base_url}).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

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
    port: int | None = None,
    api_base_url: str | None = None,
) -> ThreadingHTTPServer:
    """
    Create the server for the mock client.

    Threading matters: the two-participant flow is two browser tabs, each
    holding a long poll open against the API while asking this server for
    assets, and a single-threaded server would serialize them.

    Args:
        host: Host the page is served on.
        port: Port the page is served on. Resolved from ``ITP_UI_PORT`` and the
            candidate range the API allows through CORS when not given.
        api_base_url: Base URL the page addresses the API under. Discovered
            when not given.

    Returns:
        Server for the mock client.
    """

    if not UI_DIRECTORY.is_dir():
        raise FileNotFoundError(f"No mock client directory at {UI_DIRECTORY}")

    if port is None:
        port = resolve_port(UI_PORT_CANDIDATES, UI_PORT_VARIABLE, host=host)

    if api_base_url is None:
        api_base_url = discover_api_base_url()

    handler = partial(
        MockUIRequestHandler,
        directory=str(UI_DIRECTORY),
        api_base_url=api_base_url,
    )

    return ThreadingHTTPServer((host, port), handler)


if __name__ == "__main__":
    api_base_url = discover_api_base_url()

    server = make_server(api_base_url=api_base_url)

    port = server.server_address[1]

    print(f"\n  ITP API mock client  ->  http://{HOST}:{port}\n")

    if port != UI_PORT_CANDIDATES[0]:
        print(
            f"  Port {UI_PORT_CANDIDATES[0]} is in use, serving on {port} instead."
            f"\n  The API allows {UI_PORT_CANDIDATES[0]}-{UI_PORT_CANDIDATES[-1]} "
            f"through CORS, so nothing else has to change.\n"
        )

    if looks_like_itp_api(api_base_url):
        print(f"  The API was found at {api_base_url}.\n")
    else:
        print(
            f"  No running API was found; the page will assume {api_base_url}."
            f"\n  Start it with python -m src.run_model_api, then restart this"
            f" server or edit the base URL field.\n"
        )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped\n")
    finally:
        server.server_close()
