"""
Six-digit invitation codes for human-to-human interactions.

An invitation code lets a second instance of the JavaScript application join an
interaction and register the second human agent. It is not authentication: it
is exchanged once for the interaction token and then invalidated.

The ITP API specification requires that codes are generated with a
cryptographically secure random-number generator, are unique among all active
invitations, are bound to exactly one interaction and one human agent, can be
used only once, expire, and are not stored in plaintext when avoidable. Only
the hash is kept here; the plaintext code is returned once, at creation.

Because the code carries only six decimal digits, the join endpoint must be
rate-limited. ``JoinRateLimiter`` implements that with fixed windows over the
source address, the client identifier, and the individual code.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

INVITATION_CODE_PATTERN = r"^[0-9]{6}$"
INVITATION_STATUSES = ("pending", "used", "expired", "revoked")

DEFAULT_INVITATION_LIFETIME_SECONDS = 30 * 60
DEFAULT_CODE_GENERATION_ATTEMPTS = 64

DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_MAX_FAILED_ATTEMPTS_PER_SOURCE = 10
DEFAULT_MAX_FAILED_ATTEMPTS_PER_CODE = 5
DEFAULT_MAX_FAILED_ATTEMPTS_GLOBAL = 200


def hash_secret(
    secret: str,
) -> str:
    """
    Hash an invitation code or an interaction token for storage.

    Args:
        secret: Secret to hash.

    Returns:
        Hexadecimal digest of the secret.
    """

    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def make_invitation_code() -> str:
    """
    Create a six-digit invitation code.

    Args:

    Returns:
        Invitation code.
    """

    return f"{secrets.randbelow(1_000_000):06d}"


def make_interaction_token() -> str:
    """
    Create an interaction-scoped access token.

    Args:

    Returns:
        Interaction token.
    """

    return secrets.token_urlsafe(32)


@dataclass
class Invitation:
    """
    One invitation bound to one interaction and one human agent.

    Args:
        code_hash: Hash of the invitation code.
        session_id: Interaction the invitation belongs to.
        agent_id: Human agent the invitation registers.
        agent_role: Role of that agent.
        expires_at_monotonic: Monotonic deadline of the invitation.
        expires_at: Readable ISO 8601 deadline of the invitation.
        status: Current status of the invitation.

    Returns:
    """

    code_hash: str
    session_id: str
    agent_id: str
    agent_role: str
    expires_at_monotonic: float
    expires_at: str
    status: str = "pending"

    @property
    def is_expired(self) -> bool:
        """
        Return whether the invitation has passed its deadline.

        Args:

        Returns:
            Whether the invitation has expired.
        """

        return time.monotonic() > self.expires_at_monotonic

    def current_status(
        self,
    ) -> str:
        """
        Return the status of the invitation, accounting for expiry.

        Args:

        Returns:
            Current status of the invitation.
        """

        if self.status == "pending" and self.is_expired:
            return "expired"

        return self.status

    def describe(
        self,
    ) -> dict[str, Any]:
        """
        Describe the invitation without disclosing the code.

        Args:

        Returns:
            Invitation status in the API representation.
        """

        return {
            "agentId": self.agent_id,
            "agentRole": self.agent_role,
            "status": self.current_status(),
            "expiresAt": self.expires_at,
        }


class JoinRateLimiter:
    """
    Fixed-window rate limiter for failed invitation attempts.

    Args:

    Returns:
    """

    def __init__(
        self,
        window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        max_per_source: int = DEFAULT_MAX_FAILED_ATTEMPTS_PER_SOURCE,
        max_per_code: int = DEFAULT_MAX_FAILED_ATTEMPTS_PER_CODE,
        max_global: int = DEFAULT_MAX_FAILED_ATTEMPTS_GLOBAL,
    ) -> None:
        """
        Initialize the rate limiter.

        Args:
            window_seconds: Length of the counting window.
            max_per_source: Failed attempts allowed per source address or client.
            max_per_code: Failed attempts allowed per invitation code.
            max_global: Failed attempts allowed across all invitation codes.

        Returns:
        """

        self.window_seconds = window_seconds
        self.max_per_source = max_per_source
        self.max_per_code = max_per_code
        self.max_global = max_global

        self.lock = threading.RLock()
        self.failures: dict[str, list[float]] = {}

    def check(
        self,
        source_ip: str | None,
        client_id: str | None,
        code: str | None,
    ) -> int | None:
        """
        Check whether a join attempt may proceed.

        Args:
            source_ip: Source address of the request.
            client_id: Client identifier, where available.
            code: Invitation code submitted with the request.

        Returns:
            Seconds to wait before retrying, or None if the attempt may proceed.
        """

        with self.lock:
            now = time.monotonic()

            limits = [
                (self._source_key(source_ip), self.max_per_source),
                (self._client_key(client_id), self.max_per_source),
                (self._code_key(code), self.max_per_code),
                ("global", self.max_global),
            ]

            for key, limit in limits:
                if key is None:
                    continue

                attempts = self._recent(
                    key=key,
                    now=now,
                )

                if len(attempts) >= limit:
                    return max(
                        1,
                        int(self.window_seconds - (now - attempts[0])) + 1,
                    )

            return None

    def record_failure(
        self,
        source_ip: str | None,
        client_id: str | None,
        code: str | None,
    ) -> None:
        """
        Record one failed join attempt.

        Args:
            source_ip: Source address of the request.
            client_id: Client identifier, where available.
            code: Invitation code submitted with the request.

        Returns:
        """

        with self.lock:
            now = time.monotonic()

            keys = [
                self._source_key(source_ip),
                self._client_key(client_id),
                self._code_key(code),
                "global",
            ]

            for key in keys:
                if key is None:
                    continue

                attempts = self._recent(
                    key=key,
                    now=now,
                )
                attempts.append(now)
                self.failures[key] = attempts

    def _recent(
        self,
        key: str,
        now: float,
    ) -> list[float]:
        """
        Return the failed attempts of one key inside the current window.

        Args:
            key: Rate limiting key.
            now: Current monotonic time.

        Returns:
            Timestamps of recent failed attempts.
        """

        return [
            timestamp
            for timestamp in self.failures.get(key, [])
            if now - timestamp < self.window_seconds
        ]

    def _source_key(
        self,
        source_ip: str | None,
    ) -> str | None:
        """
        Return the rate limiting key for a source address.

        Args:
            source_ip: Source address of the request.

        Returns:
            Rate limiting key, or None if the address is unknown.
        """

        return f"ip:{source_ip}" if source_ip else None

    def _client_key(
        self,
        client_id: str | None,
    ) -> str | None:
        """
        Return the rate limiting key for a client identifier.

        Args:
            client_id: Client identifier, where available.

        Returns:
            Rate limiting key, or None if the client is unknown.
        """

        return f"client:{client_id}" if client_id else None

    def _code_key(
        self,
        code: str | None,
    ) -> str | None:
        """
        Return the rate limiting key for an invitation code.

        The code itself is never used as a key, only its hash.

        Args:
            code: Invitation code submitted with the request.

        Returns:
            Rate limiting key, or None if no code was submitted.
        """

        return f"code:{hash_secret(code)}" if code else None
