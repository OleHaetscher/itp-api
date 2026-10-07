"""
Tests of the port policy in src/utils/ports.py.

The runners rely on two rules: an explicit port is obeyed exactly or refused,
and without one the first free candidate is taken. Clients rely on the
discovery order: base URL variable, port variable, the note a running API
leaves, then a probe of the candidate range. Every test here uses ports the OS
hands out, never the real candidate ranges, so a running API on this machine
cannot change the outcome.

Run from the repository root::

    python -m pytest tests
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.utils import ports

HOST = "127.0.0.1"

# Kept before the autouse fixture stubs it, for the one test of the note itself.
READ_ANNOUNCED = ports.read_announced_api_base_url


def free_port() -> int:
    """
    Ask the OS for a port nothing holds at this moment.

    Args:

    Returns:
        Port number.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))

        return probe.getsockname()[1]


@pytest.fixture
def held_port() -> Iterator[int]:
    """
    Hold a port with a listening socket for the length of a test.

    Args:

    Returns:
        Port number that is in use.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind((HOST, 0))
        holder.listen()

        yield holder.getsockname()[1]


def serve_json(payload: object) -> tuple[ThreadingHTTPServer, str]:
    """
    Start a throwaway HTTP server answering every GET with one JSON body.

    Args:
        payload: Body to answer with.

    Returns:
        The server, to be shut down by the caller, and its base URL.
    """

    body = json.dumps(payload).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer((HOST, 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    return server, f"http://{HOST}:{server.server_address[1]}"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Remove every port variable, so the shell a test runs in cannot leak in.

    Args:
        monkeypatch: Pytest fixture.

    Returns:
    """

    for variable in (
        ports.API_PORT_VARIABLE,
        ports.UI_PORT_VARIABLE,
        ports.VISUALIZATION_PORT_VARIABLE,
        ports.API_BASE_URL_VARIABLE,
    ):
        monkeypatch.delenv(variable, raising=False)

    # The real note at the repository root belongs to whatever API is running.
    monkeypatch.setattr(ports, "read_announced_api_base_url", lambda: None)


def test_is_port_free_tells_held_from_free(held_port: int) -> None:
    assert not ports.is_port_free(held_port)
    assert ports.is_port_free(free_port())


def test_resolve_port_skips_held_candidates(held_port: int) -> None:
    spare = free_port()

    assert ports.resolve_port((held_port, spare), "ITP_TEST_PORT") == spare


def test_resolve_port_fails_when_every_candidate_is_held(held_port: int) -> None:
    with pytest.raises(OSError, match="in use"):
        ports.resolve_port((held_port,), "ITP_TEST_PORT")


def test_resolve_port_obeys_explicit_port(monkeypatch: pytest.MonkeyPatch) -> None:
    spare = free_port()
    monkeypatch.setenv("ITP_TEST_PORT", str(spare))

    assert ports.resolve_port((free_port(),), "ITP_TEST_PORT") == spare


def test_resolve_port_refuses_held_explicit_port(
    monkeypatch: pytest.MonkeyPatch,
    held_port: int,
) -> None:
    # A free candidate exists, and must not be taken instead of the named port.
    monkeypatch.setenv("ITP_TEST_PORT", str(held_port))

    with pytest.raises(OSError, match="already in use"):
        ports.resolve_port((free_port(),), "ITP_TEST_PORT")


def test_resolve_port_rejects_non_numeric_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ITP_TEST_PORT", "eighty")

    with pytest.raises(ValueError, match="not a port number"):
        ports.resolve_port((free_port(),), "ITP_TEST_PORT")


def test_make_origins_covers_both_loopback_spellings() -> None:
    assert ports.make_origins((5173, 5174)) == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    )


def test_announced_note_round_trip(tmp_path) -> None:
    note = tmp_path / ".itp-api-url"

    ports.announce_api_base_url("http://127.0.0.1:8003/", path=note)
    assert READ_ANNOUNCED(path=note) == "http://127.0.0.1:8003"

    ports.withdraw_api_base_url(path=note)
    assert not note.exists()
    assert READ_ANNOUNCED(path=note) is None

    # Withdrawing twice is harmless: shutdown may run after the file is gone.
    ports.withdraw_api_base_url(path=note)


def test_looks_like_itp_api_accepts_catalogue_only() -> None:
    catalogue, catalogue_url = serve_json({"models": []})
    other, other_url = serve_json({"status": "ok"})

    try:
        assert ports.looks_like_itp_api(catalogue_url)
        assert not ports.looks_like_itp_api(other_url)
        assert not ports.looks_like_itp_api(f"http://{HOST}:{free_port()}")
    finally:
        catalogue.shutdown()
        other.shutdown()


def test_discover_prefers_base_url_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ports.API_BASE_URL_VARIABLE, "http://example.org:9000/")
    monkeypatch.setenv(ports.API_PORT_VARIABLE, "9001")

    assert ports.discover_api_base_url() == "http://example.org:9000"


def test_discover_takes_port_variable_unprobed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ports.API_PORT_VARIABLE, "9001")

    assert ports.discover_api_base_url() == f"http://{HOST}:9001"


def test_discover_believes_note_only_when_it_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalogue, catalogue_url = serve_json({"models": []})
    fallback = free_port()

    try:
        monkeypatch.setattr(ports, "read_announced_api_base_url", lambda: catalogue_url)
        assert ports.discover_api_base_url(candidates=(fallback,)) == catalogue_url

        stale = f"http://{HOST}:{free_port()}"
        monkeypatch.setattr(ports, "read_announced_api_base_url", lambda: stale)
        assert (
            ports.discover_api_base_url(candidates=(fallback,))
            == f"http://{HOST}:{fallback}"
        )
    finally:
        catalogue.shutdown()


def test_discover_probes_candidates_and_skips_impostors() -> None:
    impostor, impostor_url = serve_json({"status": "ok"})
    catalogue, catalogue_url = serve_json({"models": []})

    impostor_port = impostor.server_address[1]
    catalogue_port = catalogue.server_address[1]

    try:
        found = ports.discover_api_base_url(
            candidates=(free_port(), impostor_port, catalogue_port),
        )
        assert found == catalogue_url
    finally:
        impostor.shutdown()
        catalogue.shutdown()


def test_discover_falls_back_to_first_candidate() -> None:
    first, second = free_port(), free_port()

    assert ports.discover_api_base_url(candidates=(first, second)) == (
        f"http://{HOST}:{first}"
    )
