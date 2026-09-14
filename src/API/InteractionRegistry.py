"""
In-memory store of interactions, tokens, and invitations.

The registry owns everything that spans more than one interaction: the
interaction objects themselves, the hashed interaction tokens used for bearer
authentication, the hashed invitation codes, the idempotency map for
``clientRequestId``, and the join rate limiter.

Interaction creation and invitation-code generation happen inside one lock, as
does invitation redemption together with participant registration, so the
atomicity the ITP API specification requires holds under the thread pool
FastAPI runs synchronous endpoints in.

Nothing is written to disk and nothing survives the process. Persistence beyond
the process lifetime is out of scope for this reference implementation; the
``persistence.enabled`` flag controls whether an interaction keeps its record
after it ends.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.API.APIProblem import ProblemDetail
from src.API.Interaction import AGENT_ROLES, AgentSlot, Interaction
from src.API.Invitation import (
    DEFAULT_CODE_GENERATION_ATTEMPTS,
    DEFAULT_INVITATION_LIFETIME_SECONDS,
    Invitation,
    JoinRateLimiter,
    hash_secret,
    make_interaction_token,
    make_invitation_code,
)
from src.API.ModelCatalogue import ModelCatalogue, ModelEntry
from src.utils.utilfuncs import make_iso_timestamp

DEFAULT_CONTEXT = "workplace_colleague_conversation"


@dataclass
class TokenScope:
    """
    What one interaction token is allowed to address.

    Args:
        interaction: Interaction the token is scoped to.
        agent_id: Agent the token was issued for, if it is bound to one.
        token_hash: Hash under which the token is stored.

    Returns:
    """

    interaction: Interaction
    agent_id: str | None
    token_hash: str


class InteractionRegistry:
    """
    Store of all interactions served by one API process.

    Args:

    Returns:
    """

    def __init__(
        self,
        catalogue: ModelCatalogue,
        converter=None,
        invitation_lifetime_seconds: int = DEFAULT_INVITATION_LIFETIME_SECONDS,
        rate_limiter: JoinRateLimiter | None = None,
        results_root: str | Path | None = None,
    ) -> None:
        """
        Initialize the interaction registry.

        Args:
            catalogue: Catalogue of the models the API offers.
            converter: Optional converter aligning values with the target agent.
            invitation_lifetime_seconds: Lifetime of an invitation code.
            rate_limiter: Optional rate limiter for the join endpoint.
            results_root: Optional directory below which every interaction
                writes its record when it ends.

        Returns:
        """

        self.catalogue = catalogue
        self.converter = converter
        self.invitation_lifetime_seconds = invitation_lifetime_seconds
        self.rate_limiter = rate_limiter or JoinRateLimiter()
        self.results_root = results_root

        self.lock = threading.RLock()

        self.interactions: dict[str, Interaction] = {}
        self.invitations: dict[str, Invitation] = {}
        self.invitations_by_session: dict[str, Invitation] = {}
        self.tokens: dict[str, str] = {}
        self.token_agents: dict[str, str] = {}
        self.client_requests: dict[str, dict[str, Any]] = {}

    def create_interaction(
        self,
        request: dict[str, Any],
        source_ip: str | None = None,
    ) -> dict[str, Any]:
        """
        Create an interaction and, where required, an invitation code.

        Args:
            request: Validated creation request.
            source_ip: Source address of the request, used to scope the
                clientRequestId idempotency record.

        Returns:
            Creation response in the API representation.
        """

        with self.lock:
            client_request_id = request.get("clientRequestId")
            request_fingerprint = hash_secret(
                json.dumps(request, sort_keys=True, separators=(",", ":"))
            )

            if client_request_id is not None:
                stored = self.client_requests.get(client_request_id)

                if stored is not None:
                    return self._replay_creation(
                        stored=stored,
                        request_fingerprint=request_fingerprint,
                        source_ip=source_ip,
                        client_request_id=client_request_id,
                    )

            model_entry = self._resolve_model(request=request)
            number_of_turns = self._resolve_number_of_turns(
                request=request,
                model_entry=model_entry,
            )
            persistence_enabled = self._resolve_persistence(
                request=request,
                model_entry=model_entry,
            )

            session_id = str(uuid4())

            agents = self._build_agents(
                request=request,
                model_entry=model_entry,
            )

            interaction = Interaction(
                session_id=session_id,
                model_entry=model_entry,
                number_of_turns=number_of_turns,
                agents=agents,
                context=request.get("context") or DEFAULT_CONTEXT,
                persistence_enabled=persistence_enabled,
                starting_role=request.get("startingAgentRole", "A"),
                converter=self.converter,
                results_root=self.results_root,
            )

            token = make_interaction_token()

            self.interactions[session_id] = interaction
            self.tokens[hash_secret(token)] = session_id

            invitation_code = self._create_invitation(
                interaction=interaction,
            )

            interaction.start_if_ready()

            response = self._describe_creation(
                interaction=interaction,
                token=token,
                invitation_code=invitation_code,
            )

            if client_request_id is not None:
                self.client_requests[client_request_id] = {
                    "response": response,
                    "request_fingerprint": request_fingerprint,
                    "source_ip": source_ip,
                }

            return response

    def join_interaction(
        self,
        request: dict[str, Any],
        source_ip: str | None = None,
    ) -> dict[str, Any]:
        """
        Redeem an invitation code and register the invited participant.

        Resolution, registration, and invalidation happen inside one lock, so a
        concurrent second join cannot register a second participant for the
        same agent.

        Args:
            request: Validated join request.
            source_ip: Source address of the request, used for rate limiting.

        Returns:
            Join response in the API representation.
        """

        code = request.get("invitationCode")
        client_id = (request.get("client") or {}).get("clientId")

        retry_after = self.rate_limiter.check(
            source_ip=source_ip,
            client_id=client_id,
            code=code,
        )

        if retry_after is not None:
            raise ProblemDetail(
                problem_type="invitation-rate-limit",
                detail="Too many unsuccessful invitation attempts were submitted.",
                extra={"retryAfterSeconds": retry_after},
            )

        with self.lock:
            try:
                invitation = self._resolve_invitation(code=code)
                interaction = self.interactions[invitation.session_id]

                registration = interaction.register_agent(
                    agent_id=invitation.agent_id,
                    participant=request.get("participant"),
                    client=request.get("client"),
                )
            except ProblemDetail:
                self.rate_limiter.record_failure(
                    source_ip=source_ip,
                    client_id=client_id,
                    code=code,
                )
                raise

            invitation.status = "used"

            token = make_interaction_token()
            token_hash = hash_secret(token)

            self.tokens[token_hash] = interaction.session_id
            self.token_agents[token_hash] = invitation.agent_id

            agent = interaction.get_agent(agent_id=invitation.agent_id)

            return {
                "sessionId": interaction.session_id,
                "interactionToken": token,
                "sessionStatus": interaction.status,
                "agent": agent.describe(),
                "model": {
                    "id": interaction.model_entry.model_id,
                    "version": interaction.model_entry.version,
                },
                "numberOfTurns": interaction.number_of_turns,
                "currentTurn": interaction.current_turn,
                "registeredAt": registration["registeredAt"],
            }

    def resolve_token(
        self,
        token: str | None,
    ) -> TokenScope:
        """
        Resolve an interaction token into what it is allowed to address.

        Args:
            token: Bearer token sent with the request.

        Returns:
            Scope of the token.
        """

        if not token:
            raise ProblemDetail(
                problem_type="missing-token",
                detail="The request carries no interaction token.",
            )

        with self.lock:
            token_hash = hash_secret(token)
            session_id = self.tokens.get(token_hash)

            if session_id is None or session_id not in self.interactions:
                raise ProblemDetail(
                    problem_type="invalid-token",
                    detail="The interaction token is invalid.",
                )

            return TokenScope(
                interaction=self.interactions[session_id],
                agent_id=self.token_agents.get(token_hash),
                token_hash=token_hash,
            )

    def bind_token_to_agent(
        self,
        token_hash: str,
        agent_id: str,
    ) -> None:
        """
        Bind a token to the agent it was used to register.

        A bound token may only address its own agent, which is what the
        specification requires of a client. The token issued at creation stays
        unbound until it registers a participant, because an interaction
        between two formal models has no agent to bind it to.

        Args:
            token_hash: Hash of the token to bind.
            agent_id: Agent the token belongs to.

        Returns:
        """

        with self.lock:
            self.token_agents.setdefault(token_hash, agent_id)

    def _replay_creation(
        self,
        stored: dict[str, Any],
        request_fingerprint: str,
        source_ip: str | None,
        client_request_id: str,
    ) -> dict[str, Any]:
        """
        Replay a creation response for a repeated clientRequestId.

        The stored response carries an interaction token, so it may only be
        handed back to a repeat of the same request from the same source.
        Without that check, any client could obtain another client's token by
        guessing its clientRequestId, and the identifier in the specification's
        own example is a fixed string.

        Args:
            stored: Stored creation record.
            request_fingerprint: Hash of the repeated request.
            source_ip: Source address of the repeated request.
            client_request_id: Identifier the client sent.

        Returns:
            Original creation response.
        """

        matches = (
            stored["request_fingerprint"] == request_fingerprint
            and stored["source_ip"] == source_ip
        )

        if not matches:
            raise ProblemDetail(
                problem_type="registration-conflict",
                detail=(
                    f"The clientRequestId {client_request_id} was already used "
                    "for a different request. Use an identifier unique to this "
                    "client."
                ),
            )

        return stored["response"]

    def get_interaction(
        self,
        session_id: str,
    ) -> Interaction:
        """
        Return one interaction.

        Args:
            session_id: Identifier of the interaction.

        Returns:
            Interaction stored under the identifier.
        """

        with self.lock:
            interaction = self.interactions.get(session_id)

            if interaction is None:
                raise ProblemDetail(
                    problem_type="interaction-not-found",
                    detail=f"There is no interaction {session_id}.",
                )

            return interaction

    def require_interaction(
        self,
        session_id: str,
        interaction: Interaction,
    ) -> Interaction:
        """
        Check that a token-resolved interaction matches the requested path.

        Args:
            session_id: Identifier from the request path.
            interaction: Interaction the token is scoped to.

        Returns:
            Requested interaction.
        """

        if interaction.session_id != session_id:
            raise ProblemDetail(
                problem_type="forbidden-agent",
                detail="The interaction token is scoped to a different interaction.",
            )

        return interaction

    def get_invitation_status(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """
        Return the invitation status of one interaction, without the code.

        Args:
            session_id: Identifier of the interaction.

        Returns:
            Invitation status, or None if the interaction has no invitation.
        """

        with self.lock:
            invitation = self.invitations_by_session.get(session_id)

            return invitation.describe() if invitation is not None else None

    def _resolve_invitation(
        self,
        code: str | None,
    ) -> Invitation:
        """
        Resolve an invitation code into a usable invitation.

        Args:
            code: Invitation code submitted with the request.

        Returns:
            Usable invitation.
        """

        invitation = self.invitations.get(hash_secret(code)) if code else None

        if invitation is None or invitation.session_id not in self.interactions:
            raise ProblemDetail(
                problem_type="invalid-invitation",
                detail="The invitation code is invalid or no longer available.",
            )

        status = invitation.current_status()

        if status == "expired":
            invitation.status = "expired"

            raise ProblemDetail(
                problem_type="invitation-expired",
                detail="The invitation code has expired.",
            )

        if status == "used":
            raise ProblemDetail(
                problem_type="invitation-already-used",
                detail=(
                    "The human agent associated with this invitation has "
                    "already been registered."
                ),
            )

        if status == "revoked":
            raise ProblemDetail(
                problem_type="invalid-invitation",
                detail="The invitation code is invalid or no longer available.",
            )

        return invitation

    def _create_invitation(
        self,
        interaction: Interaction,
    ) -> str | None:
        """
        Create an invitation code if a second human participant must join.

        The invitation is bound to the highest-lettered unregistered human
        agent, which is agent B in a two-agent interaction.

        Args:
            interaction: Interaction the invitation belongs to.

        Returns:
            Invitation code, or None if no invitation is required.
        """

        invited = [
            agent
            for role, agent in sorted(interaction.agents.items())
            if agent.is_human
        ][1:]

        if not invited:
            return None

        agent = invited[0]
        code = self._make_unique_code()

        expires_at_monotonic = time.monotonic() + self.invitation_lifetime_seconds
        expires_at = (
            (
                datetime.now(timezone.utc)
                + timedelta(seconds=self.invitation_lifetime_seconds)
            )
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        invitation = Invitation(
            code_hash=hash_secret(code),
            session_id=interaction.session_id,
            agent_id=agent.agent_id,
            agent_role=agent.role,
            expires_at_monotonic=expires_at_monotonic,
            expires_at=expires_at,
        )

        self.invitations[invitation.code_hash] = invitation
        self.invitations_by_session[interaction.session_id] = invitation

        return code

    def _make_unique_code(
        self,
    ) -> str:
        """
        Create an invitation code that is unique among active invitations.

        Args:

        Returns:
            Invitation code.
        """

        for _ in range(DEFAULT_CODE_GENERATION_ATTEMPTS):
            code = make_invitation_code()
            code_hash = hash_secret(code)

            existing = self.invitations.get(code_hash)

            if existing is None or existing.current_status() != "pending":
                return code

        raise ProblemDetail(
            problem_type="internal-error",
            detail="No unused invitation code could be generated.",
        )

    def _resolve_model(
        self,
        request: dict[str, Any],
    ) -> ModelEntry:
        """
        Resolve the model an interaction is bound to.

        Args:
            request: Validated creation request.

        Returns:
            Catalogue entry of the model.
        """

        model_id = request["modelId"]
        model_entry = self.catalogue.get(model_id=model_id)

        if model_entry is None:
            raise ProblemDetail(
                problem_type="model-not-found",
                detail=f"There is no model {model_id}.",
            )

        if not model_entry.is_available:
            raise ProblemDetail(
                problem_type="invalid-configuration",
                detail=(
                    f"Model {model_id} has status {model_entry.status} and cannot "
                    "be used for new interactions."
                ),
            )

        model_version = request.get("modelVersion")

        if model_version is not None and model_version != model_entry.version:
            raise ProblemDetail(
                problem_type="invalid-configuration",
                detail=(
                    f"Model {model_id} is available in version "
                    f"{model_entry.version}, not {model_version}."
                ),
            )

        return model_entry

    def _resolve_number_of_turns(
        self,
        request: dict[str, Any],
        model_entry: ModelEntry,
    ) -> int:
        """
        Resolve and check the number of turns against the model constraints.

        Args:
            request: Validated creation request.
            model_entry: Catalogue entry of the model.

        Returns:
            Number of interaction turns.
        """

        number_of_turns = request["numberOfTurns"]
        constraints = model_entry.constraints

        if not constraints.minimum_turns <= number_of_turns <= constraints.maximum_turns:
            raise ProblemDetail(
                problem_type="invalid-configuration",
                detail=(
                    f"Model {model_entry.model_id} allows between "
                    f"{constraints.minimum_turns} and {constraints.maximum_turns} "
                    f"turns, not {number_of_turns}."
                ),
                errors=[
                    {
                        "path": "/numberOfTurns",
                        "code": "modelConstraint",
                        "message": "The number of turns violates the model constraints.",
                    }
                ],
            )

        return number_of_turns

    def _resolve_persistence(
        self,
        request: dict[str, Any],
        model_entry: ModelEntry,
    ) -> bool:
        """
        Resolve whether interaction data is kept after the interaction ends.

        Args:
            request: Validated creation request.
            model_entry: Catalogue entry of the model.

        Returns:
            Whether persistence is enabled.
        """

        persistence_enabled = bool(
            (request.get("persistence") or {}).get("enabled", False)
        )

        if persistence_enabled and not model_entry.constraints.supports_persistence:
            raise ProblemDetail(
                problem_type="invalid-configuration",
                detail=f"Model {model_entry.model_id} does not support persistence.",
            )

        return persistence_enabled

    def _build_agents(
        self,
        request: dict[str, Any],
        model_entry: ModelEntry,
    ) -> dict[str, AgentSlot]:
        """
        Build the agent slots of an interaction.

        Formal model agents are registered and instantiated by the server;
        human agents start out pending.

        Args:
            request: Validated creation request.
            model_entry: Catalogue entry of the model.

        Returns:
            Agents of the interaction, keyed by role.
        """

        requested = request["agents"]
        missing_roles = [role for role in AGENT_ROLES if role not in requested]

        if missing_roles:
            raise ProblemDetail(
                problem_type="invalid-configuration",
                detail=f"The interaction is missing agents: {missing_roles}",
            )

        agents: dict[str, AgentSlot] = {}

        for role in AGENT_ROLES:
            specification = requested[role]
            agent_type = specification["type"]

            if agent_type not in model_entry.supported_agent_types:
                raise ProblemDetail(
                    problem_type="invalid-configuration",
                    detail=(
                        f"Model {model_entry.model_id} does not support agents of "
                        f"type {agent_type}."
                    ),
                )

            agent = AgentSlot(
                agent_id=str(uuid4()),
                role=role,
                agent_type=agent_type,
                state_space=specification.get("stateSpace")
                or model_entry.state_space,
                display_name=specification.get("displayName"),
                configuration=specification.get("configuration"),
            )

            if agent_type == "model":
                agent.model = self._instantiate_model(
                    model_entry=model_entry,
                    agent=agent,
                )
                agent.analysis_unit = agent.model.analysis_unit
                agent.registration_status = "registered"
                agent.registered_at = make_iso_timestamp()

            agents[role] = agent

        return agents

    def _instantiate_model(
        self,
        model_entry: ModelEntry,
        agent: AgentSlot,
    ):
        """
        Instantiate the formal model backing one agent.

        Args:
            model_entry: Catalogue entry of the model.
            agent: Agent the model instance belongs to.

        Returns:
            Formal model instance.
        """

        if agent.state_space != model_entry.state_space:
            raise ProblemDetail(
                problem_type="invalid-configuration",
                detail=(
                    "A formal model agent cannot be given a state space other "
                    f"than {model_entry.state_space}."
                ),
            )

        try:
            return model_entry.create_model(agent_id=agent.agent_id)
        except (TypeError, ValueError) as error:
            raise ProblemDetail(
                problem_type="invalid-configuration",
                detail=f"The formal model could not be created: {error}",
            ) from error

    def _describe_creation(
        self,
        interaction: Interaction,
        token: str,
        invitation_code: str | None,
    ) -> dict[str, Any]:
        """
        Describe a newly created interaction.

        This is the only place the invitation code is disclosed.

        Args:
            interaction: Created interaction.
            token: Interaction token issued for the creating client.
            invitation_code: Invitation code, if one was created.

        Returns:
            Creation response in the API representation.
        """

        response = interaction.describe()
        response["interactionToken"] = token

        if invitation_code is not None:
            invitation = self.invitations_by_session[interaction.session_id]
            response["invitation"] = {
                "code": invitation_code,
                **invitation.describe(),
            }

        return response
