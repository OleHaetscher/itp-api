"""
Choosing the ports the development servers bind to, and finding the API again.

Every runner in this repository used to hard-code its port. A leftover process
from an earlier session, a second copy of the API, or an unrelated service on
8001 or 5173 then stopped the runner with ``Address already in use``, and the
only way forward was to kill whatever held the port. That is the wrong trade
when the occupant belongs to somebody else's work.

Two rules replace it:

* An explicit port is obeyed exactly. ``ITP_API_PORT=9001`` means 9001, and if
  9001 is taken the runner says so and stops, because quietly binding somewhere
  else would defeat the point of naming a port.
* Without one, the runner walks a short candidate range and takes the first
  free port in it. The ranges are fixed rather than arbitrary high ports for a
  reason: the API has to allow the mock client's origin through CORS before
  either process starts, so it can only allow a range it knows in advance.

The mock client is deliberately served from a different origin than the API, so
the two processes cannot learn each other's port by being the same process.
They find each other with :func:`discover_api_base_url`. A running API leaves
its base URL in ``.itp-api-url`` at the repository root, which is the first
thing a client reads; the file is never trusted on its own, only used as a
first guess that still has to answer like the ITP catalogue. Without a usable
file the candidate range is searched instead.

The note file exists for one case that probing alone gets wrong. Two ITP APIs
on two candidate ports both answer the probe, so a search returns whichever
sits lower, which is the older process, not the one just started. The note is
written last and so names the newest.

Checking a port by binding it and letting go is inherently a moment out of date:
another process can take it between the check and the real bind. For local
development servers that race is not worth designing around, and the runner
that loses it still fails loudly.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
import urllib.error
import urllib.request

DEFAULT_HOST = "127.0.0.1"

# Both loopback addresses, because a local service may listen on either: a
# development server bound to "localhost" often holds ::1 only.
LOOPBACK_HOSTS: tuple[str, ...] = ("127.0.0.1", "::1")

# Bind addresses meaning "every interface". A client cannot connect to one of
# them; it reaches a server bound there through the loopback address.
WILDCARD_HOSTS: tuple[str, ...] = ("0.0.0.0", "::", "")

# Where a running API leaves its base URL for clients in other processes. Kept
# at the repository root and out of version control: it describes one machine
# at one moment, and is meaningless to anybody else.
API_URL_FILE = Path(__file__).resolve().parents[2] / ".itp-api-url"

# Candidate ranges. The first entry of each is the historical default, so the
# common case still binds the port the README, the CORS list, and every
# screenshot name.
API_PORT_CANDIDATES: tuple[int, ...] = tuple(range(8001, 8011))
UI_PORT_CANDIDATES: tuple[int, ...] = tuple(range(5173, 5183))

# The dashboards answer to nobody but a browser tab, so their range is a
# convenience rather than a contract: nothing has to agree with it in advance.
VISUALIZATION_PORT_CANDIDATES: tuple[int, ...] = tuple(range(8050, 8060))

API_PORT_VARIABLE = "ITP_API_PORT"
UI_PORT_VARIABLE = "ITP_UI_PORT"
VISUALIZATION_PORT_VARIABLE = "ITP_VISUALIZATION_PORT"
API_BASE_URL_VARIABLE = "ITP_API_BASE_URL"

# Seconds a single probe of one candidate port may take. Only ports that are
# already bound are probed at all, and the API answers from memory, so this is
# generous rather than tight.
PROBE_TIMEOUT_SECONDS = 1.0

# Seconds a connection attempt to a local port may take. A port nobody listens
# on refuses at once; the timeout only matters for a listener that hangs.
CONNECT_TIMEOUT_SECONDS = 0.5


def is_port_listening(
    port: int,
    host: str = DEFAULT_HOST,
    timeout: float = CONNECT_TIMEOUT_SECONDS,
) -> bool:
    """
    Report whether something accepts connections on a port.

    Args:
        port: Port to test.
        host: Address to connect to. Must be one a client can reach, not a
            wildcard bind address.
        timeout: Seconds the connection attempt may take.

    Returns:
        True when a connection is accepted, False otherwise, including on a
        machine without the address family of the host.
    """

    family = socket.AF_INET6 if ":" in host else socket.AF_INET

    try:
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.settimeout(timeout)

            return probe.connect_ex((host, port)) == 0
    except OSError:
        return False


def is_port_free(
    port: int,
    host: str = DEFAULT_HOST,
) -> bool:
    """
    Report whether a server can take a port on a host without sharing it.

    Binding alone does not answer this. The probe socket sets ``SO_REUSEADDR``
    because both servers do, so that a port left in ``TIME_WAIT`` by a
    previous run counts as free. On macOS the same option also lets a wildcard
    bind and a loopback bind of one port coexist: with the API listening on
    ``0.0.0.0:8001``, a bind to ``127.0.0.1:8001`` succeeds, and the reverse.
    A port that binds is therefore also tried with a connection, on the
    loopback addresses for a loopback or wildcard host, and is free only if
    nothing answers. A port in ``TIME_WAIT`` accepts no connection, so it
    stays free.

    Args:
        port: Port to test.
        host: Host the port would be bound on.

    Returns:
        True when the port is free, False when something holds it.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            probe.bind((host, port))
        except OSError:
            return False

    if host in WILDCARD_HOSTS or host in LOOPBACK_HOSTS or host == "localhost":
        reachable_hosts = LOOPBACK_HOSTS
    else:
        reachable_hosts = (host,)

    return not any(
        is_port_listening(port, host=reachable_host)
        for reachable_host in reachable_hosts
    )


def resolve_port(
    candidates: tuple[int, ...],
    variable: str,
    host: str = DEFAULT_HOST,
) -> int:
    """
    Decide which port a server binds.

    Args:
        candidates: Ports to try in order when no port is named.
        variable: Environment variable naming a port explicitly.
        host: Host the port is bound on.

    Returns:
        Port to bind.

    Raises:
        ValueError: The environment variable does not hold a port number.
        OSError: The named port is taken, or every candidate is.
    """

    requested = os.environ.get(variable, "").strip()

    if requested:
        try:
            port = int(requested)
        except ValueError:
            raise ValueError(
                f"{variable} is not a port number: {requested!r}"
            ) from None

        if not is_port_free(port, host=host):
            raise OSError(
                f"{variable} asks for {host}:{port}, which is already in use. "
                f"Free that port, name another one, or unset {variable} to take "
                f"the first free port in {candidates[0]}-{candidates[-1]}."
            )

        return port

    for port in candidates:
        if is_port_free(port, host=host):
            return port

    raise OSError(
        f"Every port from {candidates[0]} to {candidates[-1]} is in use on {host}. "
        f"Set {variable} to a free port."
    )


def make_origins(
    ports: tuple[int, ...],
) -> tuple[str, ...]:
    """
    Build the browser origins a set of ports is reachable under.

    Both spellings of the loopback host are separate origins to a browser, and
    the mock client is opened under either one.

    Args:
        ports: Ports the client may be served on.

    Returns:
        Origins, in the order the ports were given.
    """

    return tuple(
        f"http://{host}:{port}" for port in ports for host in ("localhost", "127.0.0.1")
    )


def make_client_base_url(
    host: str,
    port: int,
) -> str:
    """
    Build the base URL a client on this machine reaches a server under.

    A server bound to a wildcard address is reached through the loopback
    address. ``http://0.0.0.0:<port>`` works from Python, but browsers have
    started to block requests to it, so it must never reach the mock client's
    base URL field.

    Args:
        host: Host the server is bound on.
        port: Port the server is bound on.

    Returns:
        Base URL, without the version prefix.
    """

    client_host = DEFAULT_HOST if host in WILDCARD_HOSTS else host

    if ":" in client_host:
        client_host = f"[{client_host}]"

    return f"http://{client_host}:{port}"


def announce_api_base_url(
    base_url: str,
    path: Path = API_URL_FILE,
) -> None:
    """
    Leave a note saying where the API is, for clients in other processes.

    A failure to write is swallowed: a read-only checkout is a reason to fall
    back to probing, not a reason to refuse to serve.

    Args:
        base_url: Base URL the API bound, without the version prefix.
        path: File the note is written to.

    Returns:
    """

    try:
        path.write_text(f"{base_url}\n", encoding="utf-8")
    except OSError:
        pass


def withdraw_api_base_url(
    path: Path = API_URL_FILE,
) -> None:
    """
    Remove the note left by :func:`announce_api_base_url`.

    Args:
        path: File the note was written to.

    Returns:
    """

    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def read_announced_api_base_url(
    path: Path = API_URL_FILE,
) -> str | None:
    """
    Read the note a running API left, if there is one.

    Args:
        path: File the note is read from.

    Returns:
        Base URL, or None when no readable note exists.
    """

    try:
        base_url = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    return base_url.rstrip("/") or None


def looks_like_itp_api(
    base_url: str,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> bool:
    """
    Report whether something at a base URL answers like the ITP API.

    The model catalogue is the cheapest identifying endpoint: it needs no
    token, it is served from memory, and its shape is specific enough that an
    unrelated service on a candidate port is not mistaken for the API.

    Args:
        base_url: Base URL of the suspected API, without the version prefix.
        timeout: Seconds the probe may take.

    Returns:
        True when the response is an ITP model catalogue.
    """

    try:
        with urllib.request.urlopen(
            f"{base_url}/api/v1/models",
            timeout=timeout,
        ) as response:
            if response.status != 200:
                return False

            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError):
        return False

    return isinstance(payload, dict) and isinstance(payload.get("models"), list)


def discover_api_base_url(
    host: str = DEFAULT_HOST,
    candidates: tuple[int, ...] = API_PORT_CANDIDATES,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> str:
    """
    Find the base URL of a running ITP API.

    An explicit ``ITP_API_BASE_URL`` or ``ITP_API_PORT`` is taken at its word
    and not probed, so a client can be pointed at an API that is not up yet.
    Otherwise the note the most recently started API left is tried, and then
    the candidate range is searched. Only ports that accept a connection are
    probed over HTTP, which keeps the search close to instant when nothing is
    running. A bind test cannot answer this: on macOS a bind to ``127.0.0.1``
    succeeds while the API listens on ``0.0.0.0``, so the API's port would
    look unused and never be probed.

    Args:
        host: Host the API is expected on.
        candidates: Ports to search when no port is named.
        timeout: Seconds a single probe may take.

    Returns:
        Base URL of the API, without the version prefix. Falls back to the
        first candidate port when no running API is found, so the caller fails
        against the documented default rather than against a guess.
    """

    base_url = os.environ.get(API_BASE_URL_VARIABLE, "").strip()

    if base_url:
        return base_url.rstrip("/")

    requested = os.environ.get(API_PORT_VARIABLE, "").strip()

    if requested:
        return f"http://{host}:{requested}"

    announced = read_announced_api_base_url()

    if announced and looks_like_itp_api(announced, timeout=timeout):
        return announced

    for port in candidates:
        if not is_port_listening(port, host=host):
            continue

        candidate_url = f"http://{host}:{port}"

        if looks_like_itp_api(candidate_url, timeout=timeout):
            return candidate_url

    return f"http://{host}:{candidates[0]}"
