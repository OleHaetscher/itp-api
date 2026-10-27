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


def serve_json(
    payload: object,
    bind_host: str = HOST,
) -> tuple[ThreadingHTTPServer, str]:
    """
    Start a throwaway HTTP server answering every GET with one JSON body.

    Args:
        payload: Body to answer with.
        bind_host: Address the server binds. The returned URL always names
            the loopback address, the way a client reaches it.

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

    server = ThreadingHTTPServer((bind_host, 0), Handler)
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


def listen_on(host: str) -> socket.socket:
    """
    Open a listening socket on an OS-assigned port, the way the servers do.

    Args:
        host: Address to bind.

    Returns:
        The listening socket, to be closed by the caller.
    """

    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    holder = socket.socket(family, socket.SOCK_STREAM)
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind((host, 0))
    holder.listen()

    return holder


def has_ipv6_loopback() -> bool:
    """
    Report whether ::1 can be bound on this machine.

    Args:

    Returns:
        Whether IPv6 loopback is available.
    """

    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(("::1", 0))
    except OSError:
        return False

    return True


@pytest.mark.parametrize(
    ("listen_host", "probe_host"),
    [
        # The API binds 0.0.0.0; clients and the mock client ask 127.0.0.1.
        ("0.0.0.0", "127.0.0.1"),
        # Something on loopback only, asked about by the API's wildcard bind.
        ("127.0.0.1", "0.0.0.0"),
        ("0.0.0.0", "0.0.0.0"),
        ("127.0.0.1", "127.0.0.1"),
    ],
)
def test_is_port_free_sees_listener_across_bind_addresses(
    listen_host: str,
    probe_host: str,
) -> None:
    # SO_REUSEADDR lets the mixed pairs bind on macOS; the port is held anyway.
    holder = listen_on(listen_host)

    try:
        assert not ports.is_port_free(holder.getsockname()[1], host=probe_host)
    finally:
        holder.close()


@pytest.mark.skipif(not has_ipv6_loopback(), reason="no IPv6 loopback")
@pytest.mark.parametrize("probe_host", ["127.0.0.1", "0.0.0.0"])
def test_is_port_free_sees_ipv6_loopback_listener(probe_host: str) -> None:
    # A dev server bound to "localhost" may hold ::1 only.
    holder = listen_on("::1")

    try:
        assert not ports.is_port_free(holder.getsockname()[1], host=probe_host)
    finally:
        holder.close()


def test_is_port_free_after_listener_closes_with_time_wait() -> None:
    # The server closes its side first, so its port is left in TIME_WAIT. The
    # servers set SO_REUSEADDR and can rebind it, so it must count as free.
    holder = listen_on(HOST)
    port = holder.getsockname()[1]

    client = socket.create_connection((HOST, port))
    accepted, _ = holder.accept()
    accepted.close()
    client.recv(1)
    client.close()
    holder.close()

    assert ports.is_port_free(port, host=HOST)
    assert ports.is_port_free(port, host="0.0.0.0")


def test_is_port_listening_tells_listener_from_nothing(held_port: int) -> None:
    assert ports.is_port_listening(held_port)
    assert not ports.is_port_listening(free_port())


def test_is_port_listening_survives_missing_address_family() -> None:
    # An address nobody listens on, of either family, is simply "not listening".
    assert not ports.is_port_listening(free_port(), host="::1")


def test_make_client_base_url_maps_wildcards_to_loopback() -> None:
    assert ports.make_client_base_url("0.0.0.0", 8002) == "http://127.0.0.1:8002"
    assert ports.make_client_base_url("::", 8002) == "http://127.0.0.1:8002"
    assert ports.make_client_base_url("", 8002) == "http://127.0.0.1:8002"
    assert ports.make_client_base_url("127.0.0.1", 8002) == "http://127.0.0.1:8002"
    assert ports.make_client_base_url("::1", 8002) == "http://[::1]:8002"


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


def test_resolve_port_skips_wildcard_listener_for_loopback_server() -> None:
    # The mock client binds 127.0.0.1; a service on 0.0.0.0 must push it on.
    holder = listen_on("0.0.0.0")
    spare = free_port()

    try:
        assert (
            ports.resolve_port((holder.getsockname()[1], spare), "ITP_TEST_PORT")
            == spare
        )
    finally:
        holder.close()


def test_resolve_port_skips_loopback_listener_for_wildcard_server() -> None:
    # The API binds 0.0.0.0; a service on 127.0.0.1 must push it on.
    holder = listen_on("127.0.0.1")
    spare = free_port()

    try:
        found = ports.resolve_port(
            (holder.getsockname()[1], spare),
            "ITP_TEST_PORT",
            host="0.0.0.0",
        )
        assert found == spare
    finally:
        holder.close()


def test_discover_finds_api_bound_to_all_interfaces() -> None:
    # The way run_model_api binds. Without a note, only the probe can find it.
    catalogue, catalogue_url = serve_json({"models": []}, bind_host="0.0.0.0")
    catalogue_port = catalogue.server_address[1]

    try:
        found = ports.discover_api_base_url(candidates=(free_port(), catalogue_port))
        assert found == catalogue_url == f"http://{HOST}:{catalogue_port}"
    finally:
        catalogue.shutdown()


def test_run_api_announces_loopback_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # run_api is driven up to uvicorn.run, which is stubbed out.
    from src import run_model_api

    spare = free_port()
    announced: list[str] = []
    served: dict[str, object] = {}

    monkeypatch.setenv(ports.API_PORT_VARIABLE, str(spare))
    monkeypatch.setattr(run_model_api, "announce_api_base_url", announced.append)
    monkeypatch.setattr(
        run_model_api.uvicorn,
        "run",
        lambda app, host, port: served.update(host=host, port=port),
    )

    run_model_api.run_api()

    assert announced == [f"http://{HOST}:{spare}"]
    assert served == {"host": "0.0.0.0", "port": spare}


def test_discover_falls_back_to_first_candidate() -> None:
    first, second = free_port(), free_port()

    assert ports.discover_api_base_url(candidates=(first, second)) == (
        f"http://{HOST}:{first}"
    )
