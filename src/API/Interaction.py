"""
One ITP interaction: lifecycle, turns, perceptions, and actions.

This is the stateful core of the API. The ITP API specification makes the
server authoritative for interaction states and turn numbers, so all of that
logic lives here rather than in the HTTP layer.

Turn model
----------
Interactions are alternating and turn-based: one turn is one action slot with
exactly one acting agent, which is what the specification's ``activeAgentIds``
array and its ``results`` representation (one ``actorAgentId`` per turn)
describe. ``numberOfTurns`` therefore counts single actions, not exchanges.

One API turn maps onto the ITP timecode as::

    interaction_turn = (turn + 1) // 2
    message_index    = 2 - (turn % 2)

so API turns 1 and 2 are the two messages of ITP interaction turn 1.

Perceptions
-----------
After an agent acts, the partner receives a perception carrying the experience
the action produced, converted into the partner's state space. Its ``turn`` is
the turn in which the perceiving agent is expected to act, so a client can read
``turn`` from a perception and submit it back unchanged with its action.

A fourth perception state, ``actionRequired``, extends the three states of the
specification. It is returned when an agent must act but nothing has happened
yet that it could perceive, which is the case for the agent that opens the
interaction. The alternative would be to invent an opening state vector, and
the ITP codebase does not fabricate values.

Everything that happens is also recorded as ITP messages in a ``Communication``
object, so an interaction driven through the API produces the same record as
one driven by the local runner.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.API.APIProblem import ProblemDetail
from src.API.ModelCatalogue import ModelEntry
from src.API.StateSpaceSchema import StateSpaceSchema
from src.communication.Communication import Communication
from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.utils.utilfuncs import make_iso_timestamp, make_timecode

INTERACTION_STATUSES = (
    "waitingForRegistration",
    "ready",
    "running",
    "completed",
    "terminated",
    "expired",
    "failed",
)

END_REASONS = (
    "numberOfTurnsReached",
    "terminatedByClient",
    "participantDisconnected",
    "registrationTimeout",
    "interactionExpired",
    "modelFailure",
    "serverError",
)

AGENT_ROLES = ("A", "B")

DEFAULT_ANALYSIS_UNIT = "monadic"


def hash_content(
    content: dict[str, Any],
) -> str:
    """
    Hash the content of an action for idempotency checks.

    Args:
        content: Content to hash.

    Returns:
        Hexadecimal digest of the content.
    """

    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class AgentSlot:
    """
    One of the two agents of an interaction.

    Args:
        agent_id: Identifier of the agent.
        role: Role of the agent, "A" or "B".
        agent_type: Type of the agent, "human" or "model".
        state_space: Interpersonal state space the agent works in.
        analysis_unit: Analysis unit the agent works in.
        display_name: Optional readable name.
        configuration: Optional model-specific configuration.
        model: Formal model instance, for agents of type "model".
        registration_status: Whether the agent is registered.
        participant: Participant registered for the agent.
        client: Client registered for the agent.
        registered_at: Time of registration.

    Returns:
    """

    agent_id: str
    role: str
    agent_type: str
    state_space: str
    analysis_unit: str = DEFAULT_ANALYSIS_UNIT
    display_name: str | None = None
    configuration: dict[str, Any] | None = None
    model: BaseFormalModel | None = None
    registration_status: str = "pending"
    participant: dict[str, Any] | None = None
    client: dict[str, Any] | None = None
    registered_at: str | None = None

    @property
    def is_human(self) -> bool:
        """
        Return whether the agent is a human participant.

        Args:

        Returns:
            Whether the agent is a human participant.
        """

        return self.agent_type == "human"

    def to_itp_agent(
        self,
    ) -> dict[str, str]:
        """
        Describe the agent as an ITP agent.

        Args:

        Returns:
            ITP agent description.
        """

        return {
            "id": self.agent_id,
            "state_space": self.state_space,
            "analysis_unit": self.analysis_unit,
        }

    def describe(
        self,
    ) -> dict[str, Any]:
        """
        Describe the agent for an API response.

        Args:

        Returns:
            Agent description in the API representation.
        """

        description: dict[str, Any] = {
            "agentId": self.agent_id,
            "role": self.role,
            "type": self.agent_type,
            "registrationStatus": self.registration_status,
        }

        if self.display_name is not None:
            description["displayName"] = self.display_name

        if self.state_space is not None:
            description["stateSpace"] = self.state_space

        return description


@dataclass
class Perception:
    """
    One perception produced for one agent.

    Args:
        perception_id: Identifier of the perception.
        cursor: Monotonic position of the perception in the agent's stream.
        turn: Turn in which the perceiving agent is expected to act.
        agent_id: Agent the perception belongs to.
        experience: Experience vector in the agent's state space.
        action_required: Whether the agent is expected to act.
        created_at: Time the perception was created.
        source_agent_id: Agent whose behavior produced the perception.

    Returns:
    """

    perception_id: str
    cursor: int
    turn: int
    agent_id: str
    experience: dict[str, float] | None
    action_required: bool
    created_at: str
    source_agent_id: str | None = None

    def describe(
        self,
        session_status: str,
    ) -> dict[str, Any]:
        """
        Describe the perception for the perception endpoint.

        Args:
            session_status: Current status of the interaction.

        Returns:
            Perception in the API representation.
        """

        state = "perceivable" if self.experience is not None else "actionRequired"

        # An interaction that has ended accepts no further behavior, so a
        # perception issued before it ended must not still ask for one.
        has_ended = session_status in ("completed", "terminated", "expired", "failed")
        action_required = self.action_required and not has_ended

        description: dict[str, Any] = {
            "state": state,
            "sessionStatus": session_status,
            "perceptionId": self.perception_id,
            "cursor": str(self.cursor),
            "turn": self.turn,
            "agentId": self.agent_id,
            "actionRequired": action_required,
            "createdAt": self.created_at,
        }

        if self.experience is not None:
            description["experience"] = self.experience
            description["sourceAgentId"] = self.source_agent_id

        return description


@dataclass
class Action:
    """
    One accepted behavior submission.

    Args:
        action_id: Client-generated idempotency identifier.
        agent_id: Agent that acted.
        turn: Turn the action belongs to.
        behavior: Behavior vector in the acting agent's state space.
        content_hash: Hash used to detect a reused action id.
        accepted_at: Time the action was accepted.
        response: Acceptance response returned for the action.

    Returns:
    """

    action_id: str
    agent_id: str
    turn: int
    behavior: dict[str, float]
    content_hash: str
    accepted_at: str
    response: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnRecord:
    """
    One completed turn, kept for the results endpoint.

    Args:
        turn: Number of the turn.
        actor_agent_id: Agent that acted in the turn.
        behavior: Behavior vector submitted or generated for the turn.
        perceptions: Perceptions the behavior produced.
        created_at: Time the turn was recorded.

    Returns:
    """

    turn: int
    actor_agent_id: str
    behavior: dict[str, float]
    perceptions: list[dict[str, Any]]
    created_at: str

    def describe(
        self,
    ) -> dict[str, Any]:
        """
        Describe the turn for the results endpoint.

        Args:

        Returns:
            Turn in the API representation.
        """

        return {
            "turn": self.turn,
            "actorAgentId": self.actor_agent_id,
            "behavior": self.behavior,
            "perceptions": self.perceptions,
            "createdAt": self.created_at,
        }


class Interaction:
    """
    One ITP interaction between two agents.

    Args:

    Returns:
    """

    def __init__(
        self,
        session_id: str,
        model_entry: ModelEntry,
        number_of_turns: int,
        agents: dict[str, AgentSlot],
        context: str,
        persistence_enabled: bool = False,
        starting_role: str = "A",
        converter=None,
        results_root: str | Path | None = None,
    ) -> None:
        """
        Initialize an interaction.

        Args:
            session_id: Identifier of the interaction.
            model_entry: Catalogue entry of the model the interaction is bound to.
            number_of_turns: Maximum number of interaction turns.
            agents: Agents of the interaction, keyed by role.
            context: String describing the interaction context.
            persistence_enabled: Whether interaction data is kept after the end.
            starting_role: Role of the agent that acts in turn 1.
            converter: Optional converter aligning values with the target agent.
            results_root: Optional directory below which the record is written
                when the interaction ends. Nothing is written without it.

        Returns:
        """

        self.lock = threading.RLock()

        self.session_id = session_id
        self.model_entry = model_entry
        self.number_of_turns = number_of_turns
        self.agents = agents
        self.context = context
        self.persistence_enabled = persistence_enabled
        self.starting_role = starting_role
        self.converter = converter
        self.results_root = results_root

        self.communication = Communication(context=context)

        self.status = "waitingForRegistration"
        self.current_turn = 0
        self.active_agent_ids: list[str] = []
        self.end_reason: str | None = None

        self.created_at = make_iso_timestamp()
        self.started_at: str | None = None
        self.ended_at: str | None = None

        self.perceptions: dict[str, list[Perception]] = {
            agent.agent_id: [] for agent in agents.values()
        }
        self.actions: dict[tuple[str, str], Action] = {}
        self.turns: list[TurnRecord] = []
        self.results_discarded = False
        self.results_folder: str | None = None
        self.schemas: dict[str, StateSpaceSchema] = {}

        self.cursor = 0

    def schema_for(
        self,
        state_space: str,
    ):
        """
        Return the compiled schema of one state space, building it on demand.

        Agents normally work in the state space of the interaction model, but a
        human agent may declare another one, and then its perceptions and
        behaviors are validated against that space instead.

        Args:
            state_space: ITP state space identifier.

        Returns:
            State space schema.
        """

        if state_space == self.model_entry.state_space:
            return self.model_entry.state_space_schema

        if state_space not in self.schemas:
            try:
                self.schemas[state_space] = StateSpaceSchema.from_state_space(
                    state_space=state_space
                )
            except (FileNotFoundError, ValueError) as error:
                raise ProblemDetail(
                    problem_type="invalid-configuration",
                    detail=f"No state space description is available: {error}",
                ) from error

        return self.schemas[state_space]

    @property
    def state_space_schema(self):
        """
        Return the shared state space schema of the interaction model.

        Args:

        Returns:
            State space schema of the model.
        """

        return self.model_entry.state_space_schema

    @property
    def is_running(self) -> bool:
        """
        Return whether the interaction is currently running.

        Args:

        Returns:
            Whether the interaction is running.
        """

        return self.status == "running"

    @property
    def has_ended(self) -> bool:
        """
        Return whether the interaction has ended.

        Args:

        Returns:
            Whether the interaction has ended.
        """

        return self.status in ("completed", "terminated", "expired", "failed")

    def get_agent(
        self,
        agent_id: str,
    ) -> AgentSlot:
        """
        Return one agent of the interaction.

        Args:
            agent_id: Identifier of the agent.

        Returns:
            Agent of the interaction.
        """

        for agent in self.agents.values():
            if agent.agent_id == agent_id:
                return agent

        raise ProblemDetail(
            problem_type="agent-not-found",
            detail=f"The interaction has no agent {agent_id}.",
        )

    def get_partner(
        self,
        agent: AgentSlot,
    ) -> AgentSlot:
        """
        Return the other agent of the interaction.

        Args:
            agent: Agent whose partner is requested.

        Returns:
            Partner of the agent.
        """

        return next(
            candidate
            for candidate in self.agents.values()
            if candidate.agent_id != agent.agent_id
        )

    def register_agent(
        self,
        agent_id: str,
        participant: dict[str, Any] | None,
        client: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Register a human participant for one agent.

        Registration is idempotent for the same agent and participant.

        Args:
            agent_id: Identifier of the agent.
            participant: Participant registered for the agent.
            client: Client registered for the agent.

        Returns:
            Registration result in the API representation.
        """

        with self.lock:
            agent = self.get_agent(agent_id=agent_id)

            if not agent.is_human:
                raise ProblemDetail(
                    problem_type="forbidden-agent",
                    detail=(
                        "Formal model agents are registered by the server and "
                        "must not be registered through the API."
                    ),
                )

            if self.has_ended:
                raise ProblemDetail(
                    problem_type="registration-conflict",
                    detail=f"The interaction has already ended: {self.status}.",
                )

            if agent.registration_status == "registered":
                self._require_same_participant(
                    agent=agent,
                    participant=participant,
                )
            else:
                agent.participant = participant
                agent.client = client
                agent.registration_status = "registered"
                agent.registered_at = make_iso_timestamp()

                if participant is not None and participant.get("displayName"):
                    agent.display_name = participant["displayName"]

                self.start_if_ready()

            return {
                "sessionId": self.session_id,
                "agentId": agent.agent_id,
                "agentRole": agent.role,
                "registrationStatus": agent.registration_status,
                "sessionStatus": self.status,
                "registeredAt": agent.registered_at,
            }

    def start_if_ready(
        self,
    ) -> None:
        """
        Start the interaction once every human agent has registered.

        Args:

        Returns:
        """

        with self.lock:
            if self.status != "waitingForRegistration":
                return

            pending = [
                agent
                for agent in self.agents.values()
                if agent.is_human and agent.registration_status != "registered"
            ]

            if pending:
                return

            self.status = "running"
            self.started_at = make_iso_timestamp()
            self.current_turn = 1
            self.active_agent_ids = [self.agents[self.starting_role].agent_id]

            self._announce_action_required()
            self._run_model_agents()

    def submit_action(
        self,
        agent_id: str,
        action_id: str,
        turn: int,
        behavior: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Accept the behavior of one agent for one turn.

        Args:
            agent_id: Identifier of the acting agent.
            action_id: Client-generated idempotency identifier.
            turn: Turn the action belongs to.
            behavior: Behavior vector in the agent's state space.

        Returns:
            Acceptance response in the API representation.
        """

        with self.lock:
            agent = self.get_agent(agent_id=agent_id)

            content_hash = hash_content(
                content={
                    "agentId": agent_id,
                    "turn": turn,
                    "behavior": behavior,
                }
            )

            replayed = self._replay_action(
                agent_id=agent_id,
                action_id=action_id,
                content_hash=content_hash,
            )

            if replayed is not None:
                return replayed

            self._require_agent_may_act(
                agent=agent,
                turn=turn,
            )
            self._validate_behavior(
                behavior=behavior,
                agent=agent,
            )

            action = Action(
                action_id=action_id,
                agent_id=agent_id,
                turn=turn,
                behavior=dict(behavior),
                content_hash=content_hash,
                accepted_at=make_iso_timestamp(),
            )

            self.actions[(agent_id, action_id)] = action

            try:
                self._apply_behavior(
                    agent=agent,
                    behavior=dict(behavior),
                )
            except Exception:
                # The action was recorded before it was applied. Applying it is
                # what advances the interaction, so an action that failed to
                # apply must not be replayable as an accepted one.
                self.actions.pop((agent_id, action_id), None)
                raise

            action.response = {
                "status": "accepted",
                "sessionId": self.session_id,
                "agentId": agent_id,
                "actionId": action_id,
                "turn": turn,
                "sessionStatus": self.status,
                "acceptedAt": action.accepted_at,
            }

            return action.response

    def poll_perception(
        self,
        agent_id: str,
        after: str | None = None,
    ) -> dict[str, Any]:
        """
        Return the current perception state of one agent.

        Polling never consumes a perception: the same request repeated returns
        the same perception until the client advances its cursor.

        Args:
            agent_id: Identifier of the perceiving agent.
            after: Cursor of the last perception the client processed.

        Returns:
            Perception state in the API representation.
        """

        with self.lock:
            agent = self.get_agent(agent_id=agent_id)
            after_cursor = self._parse_cursor(after=after)

            perception = next(
                (
                    candidate
                    for candidate in self.perceptions[agent.agent_id]
                    if candidate.cursor > after_cursor
                ),
                None,
            )

            if perception is not None:
                return perception.describe(session_status=self.status)

            if self.has_ended:
                return {
                    "state": "interactionEnded",
                    "sessionStatus": self.status,
                    "finalTurn": self.current_turn,
                    "endReason": self.end_reason,
                    "endedAt": self.ended_at,
                }

            return {
                "state": "pending",
                "sessionStatus": self.status,
                "currentTurn": self.current_turn,
                "cursor": str(self._last_cursor(agent_id=agent.agent_id)),
                "retryAfterMilliseconds": 1000,
            }

    def has_perception_after(
        self,
        agent_id: str,
        after: str | None,
    ) -> bool:
        """
        Check whether a poll would return something other than "pending".

        Args:
            agent_id: Identifier of the perceiving agent.
            after: Cursor of the last perception the client processed.

        Returns:
            Whether a new perception or an end state is available.
        """

        with self.lock:
            if self.has_ended:
                return True

            after_cursor = self._parse_cursor(after=after)

            return any(
                candidate.cursor > after_cursor
                for candidate in self.perceptions[agent_id]
            )

    def end(
        self,
        reason: str = "terminatedByClient",
    ) -> dict[str, Any]:
        """
        Terminate the interaction before its normal completion.

        The operation is idempotent: terminating an interaction that has
        already ended returns the existing termination result.

        Args:
            reason: Reason the interaction ended.

        Returns:
            Termination result in the API representation.
        """

        with self.lock:
            if reason not in END_REASONS:
                raise ProblemDetail(
                    problem_type="malformed-request",
                    detail=f"Unknown end reason: {reason}",
                )

            if not self.has_ended:
                self._finish(
                    status="terminated",
                    reason=reason,
                )

            return {
                "sessionId": self.session_id,
                "status": self.status,
                "endReason": self.end_reason,
                "finalTurn": self.current_turn,
                "endedAt": self.ended_at,
            }

    def describe(
        self,
        invitation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Describe the interaction for the status endpoint.

        Args:
            invitation: Optional invitation status, without the code.

        Returns:
            Interaction status in the API representation.
        """

        with self.lock:
            description: dict[str, Any] = {
                "sessionId": self.session_id,
                "status": self.status,
                "model": {
                    "id": self.model_entry.model_id,
                    "version": self.model_entry.version,
                },
                "numberOfTurns": self.number_of_turns,
                "currentTurn": self.current_turn,
                "activeAgentIds": list(self.active_agent_ids),
                "agents": {
                    role: agent.describe() for role, agent in self.agents.items()
                },
                "context": self.context,
                "persistence": {"enabled": self.persistence_enabled},
                "createdAt": self.created_at,
                "startedAt": self.started_at,
            }

            if invitation is not None:
                description["invitation"] = invitation

            if self.has_ended:
                description["endReason"] = self.end_reason
                description["endedAt"] = self.ended_at

            return description

    def describe_results(
        self,
    ) -> dict[str, Any]:
        """
        Describe the recorded interaction for the results endpoint.

        Args:

        Returns:
            Interaction results in the API representation.
        """

        with self.lock:
            if self.results_discarded:
                raise ProblemDetail(
                    problem_type="results-gone",
                    detail=(
                        "Persistence was disabled for this interaction, so its "
                        "data was discarded when the interaction ended."
                    ),
                )

            return {
                "sessionId": self.session_id,
                "status": self.status,
                "model": {
                    "id": self.model_entry.model_id,
                    "version": self.model_entry.version,
                },
                "numberOfTurns": self.number_of_turns,
                "context": self.context,
                "agents": {
                    role: agent.describe() for role, agent in self.agents.items()
                },
                "turns": [turn.describe() for turn in self.turns],
                "itpMessages": self.communication.get_messages(),
                "completedAt": self.ended_at,
                "resultsFolder": self.results_folder,
            }

    def save_results(
        self,
        root: str | Path,
    ) -> Path | None:
        """
        Write the record of the interaction to the results folder.

        The ITP messages are written as the numbered files the local runner
        produces, so an interaction driven through the API leaves the same
        record behind as one driven by src/run_local_interaction.py. Beside
        them, interaction.json holds what only the API knows: which agent was
        human and which was a model, how the interaction ended, and the bare
        behavior vector of every turn as it came off the wire.

        The folder name carries the session id as well as the timestamp,
        because two interactions can end within the same second.

        A failed write is reported and swallowed. This runs inside the action
        that ends an interaction, and the record is a convenience: a full disk
        should not turn a completed interaction into a server error after its
        status has already been set.

        Args:
            root: Directory below which the results folder is written.

        Returns:
            Path the record was written to, or None if it could not be written.
        """

        folder = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.session_id[:8]}"

        record = {
            "sessionId": self.session_id,
            "status": self.status,
            "endReason": self.end_reason,
            "model": {
                "id": self.model_entry.model_id,
                "version": self.model_entry.version,
            },
            "numberOfTurns": self.number_of_turns,
            "context": self.context,
            "agents": {
                role: agent.describe() for role, agent in self.agents.items()
            },
            "turns": [turn.describe() for turn in self.turns],
            "itpMessageCount": len(self.communication.messages),
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
        }

        try:
            directory = self.communication.save_messages(root=root, folder=folder)

            (directory / "interaction.json").write_text(
                json.dumps(record, indent=4, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            print(f"  could not write the results of {self.session_id}: {error}")
            return None

        self.results_folder = folder

        print(f"  results written to {directory}")

        return directory

    def _apply_behavior(
        self,
        agent: AgentSlot,
        behavior: dict[str, float],
    ) -> None:
        """
        Turn one behavior into ITP messages, perceptions, and the next turn.

        Args:
            agent: Agent that acted.
            behavior: Behavior vector in the agent's state space.

        Returns:
        """

        partner = self.get_partner(agent=agent)
        turn = self.current_turn

        message = self._make_itp_message(
            agent=agent,
            partner=partner,
            behavior=behavior,
            turn=turn,
        )

        self.communication.receive_message(message)

        delivered = self._convert_for_target(message=message)

        if delivered is not message:
            self.communication.receive_message(delivered)

        self._validate_experience(
            experience=delivered["values"]["data"],
            agent=partner,
            source_agent=agent,
        )

        if partner.model is not None:
            partner.model.from_message(delivered)

        next_turn = turn + 1
        is_final_turn = turn >= self.number_of_turns

        perception = self._make_perception(
            agent=partner,
            experience=delivered["values"]["data"],
            turn=turn if is_final_turn else next_turn,
            action_required=not is_final_turn,
            source_agent_id=agent.agent_id,
        )

        self.turns.append(
            TurnRecord(
                turn=turn,
                actor_agent_id=agent.agent_id,
                behavior=dict(behavior),
                perceptions=[
                    {
                        "agentId": perception.agent_id,
                        "perceptionId": perception.perception_id,
                        "experience": perception.experience,
                    }
                ],
                created_at=perception.created_at,
            )
        )

        if is_final_turn:
            self._finish(
                status="completed",
                reason="numberOfTurnsReached",
            )
            return

        self.current_turn = next_turn
        self.active_agent_ids = [partner.agent_id]

        self._run_model_agents()

    def _run_model_agents(
        self,
    ) -> None:
        """
        Let formal model agents act while it is their turn.

        Args:

        Returns:
        """

        while self.is_running:
            agent = self._active_agent()

            if agent is None or agent.model is None:
                return

            behavior = self._generate_model_behavior(agent=agent)

            server_action_id = f"server-turn-{self.current_turn}"

            self.actions[(agent.agent_id, server_action_id)] = Action(
                action_id=server_action_id,
                agent_id=agent.agent_id,
                turn=self.current_turn,
                behavior=behavior,
                content_hash=hash_content(content=behavior),
                accepted_at=make_iso_timestamp(),
            )

            self._apply_behavior(
                agent=agent,
                behavior=behavior,
            )

    def _generate_model_behavior(
        self,
        agent: AgentSlot,
    ) -> dict[str, float]:
        """
        Generate and validate the behavior of one formal model agent.

        Args:
            agent: Agent whose model generates the behavior.

        Returns:
            Behavior vector in the agent's state space.
        """

        try:
            behavior = agent.model.generate_numerical_output(context=self.context)
        except Exception as error:
            self._finish(
                status="failed",
                reason="modelFailure",
            )

            raise ProblemDetail(
                problem_type="model-failure",
                detail=f"The formal model of agent {agent.agent_id} failed.",
            ) from error

        errors = self.schema_for(state_space=agent.state_space).validate_vector(
            vector=behavior
        )

        if errors:
            self._finish(
                status="failed",
                reason="modelFailure",
            )

            raise ProblemDetail(
                problem_type="model-failure",
                detail=(
                    f"The formal model of agent {agent.agent_id} produced a state "
                    "vector outside its own state space."
                ),
                errors=errors,
            )

        return behavior

    def _make_perception(
        self,
        agent: AgentSlot,
        experience: dict[str, float] | None,
        turn: int,
        action_required: bool,
        source_agent_id: str | None = None,
    ) -> Perception:
        """
        Create and store one perception for an agent.

        Args:
            agent: Agent the perception belongs to.
            experience: Experience vector in the agent's state space.
            turn: Turn in which the agent is expected to act.
            action_required: Whether the agent is expected to act.
            source_agent_id: Agent whose behavior produced the perception.

        Returns:
            Created perception.
        """

        self.cursor += 1

        perception = Perception(
            perception_id=str(uuid4()),
            cursor=self.cursor,
            turn=turn,
            agent_id=agent.agent_id,
            experience=dict(experience) if experience is not None else None,
            action_required=action_required,
            created_at=make_iso_timestamp(),
            source_agent_id=source_agent_id,
        )

        self.perceptions[agent.agent_id].append(perception)

        return perception

    def _announce_action_required(
        self,
    ) -> None:
        """
        Tell the opening agent to act when it has nothing to perceive yet.

        Args:

        Returns:
        """

        agent = self._active_agent()

        if agent is None or agent.model is not None:
            return

        self._make_perception(
            agent=agent,
            experience=None,
            turn=self.current_turn,
            action_required=True,
        )

    def _make_itp_message(
        self,
        agent: AgentSlot,
        partner: AgentSlot,
        behavior: dict[str, float],
        turn: int,
    ) -> dict[str, Any]:
        """
        Wrap one behavior into an ITP message.

        Args:
            agent: Agent that acted.
            partner: Agent receiving the message.
            behavior: Behavior vector in the acting agent's state space.
            turn: Turn the behavior belongs to.

        Returns:
            Numerical ITP message.
        """

        timecode = make_timecode(
            interaction_turn=(turn + 1) // 2,
            message_index=2 - (turn % 2),
        )
        timecode["api_turn"] = turn
        timecode["iso_timestamp"] = make_iso_timestamp()

        values = self.communication.specification.make_values(
            state_space=agent.state_space,
            analysis_unit=agent.analysis_unit,
            data=behavior,
        )

        return self.communication.make_message(
            source_agent=agent.to_itp_agent(),
            target_agent=partner.to_itp_agent(),
            timecode=timecode,
            values=values,
            metadata={
                "session_id": self.session_id,
                "agent_role": agent.role,
                "agent_type": agent.agent_type,
            },
        )

    def _convert_for_target(
        self,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Convert a message into the state space of its target agent if needed.

        Args:
            message: Numerical ITP message.

        Returns:
            Numerical ITP message ready for the target agent.
        """

        matches_target = (
            message["values"]["state_space"] == message["target_agent"]["state_space"]
            and message["values"]["analysis_unit"]
            == message["target_agent"]["analysis_unit"]
        )

        if matches_target:
            return message

        if self.converter is None:
            raise ProblemDetail(
                problem_type="internal-error",
                detail=(
                    "The message requires state space conversion, but the API "
                    "was started without a converter."
                ),
            )

        try:
            return self.converter.convert_message(message)
        except ValueError as error:
            raise ProblemDetail(
                problem_type="invalid-configuration",
                detail=str(error),
            ) from error

    def _replay_action(
        self,
        agent_id: str,
        action_id: str,
        content_hash: str,
    ) -> dict[str, Any] | None:
        """
        Replay the response of an action that was already accepted.

        Action ids are scoped to the agent that submitted them. The two clients
        of an interaction generate their ids independently, so a counter-style
        id such as "action-1" would otherwise collide between them and the
        second client would be told its own first action conflicts.

        Args:
            agent_id: Agent that submitted the action.
            action_id: Client-generated idempotency identifier.
            content_hash: Hash of the submitted action content.

        Returns:
            Original acceptance response, or None if the action is new.
        """

        action = self.actions.get((agent_id, action_id))

        if action is None:
            return None

        if action.content_hash != content_hash:
            raise ProblemDetail(
                problem_type="action-conflict",
                detail=(
                    f"Action {action_id} was already submitted with different "
                    "content."
                ),
            )

        return action.response

    def _require_agent_may_act(
        self,
        agent: AgentSlot,
        turn: int,
    ) -> None:
        """
        Check that an agent may submit a behavior for one turn.

        Args:
            agent: Agent that wants to act.
            turn: Turn the action is submitted for.

        Returns:
        """

        if not agent.is_human:
            raise ProblemDetail(
                problem_type="forbidden-agent",
                detail=(
                    "Formal model agents are executed by the server and cannot "
                    "have behaviors submitted for them."
                ),
            )

        if self.has_ended:
            raise ProblemDetail(
                problem_type="action-conflict",
                detail="The interaction has already ended.",
            )

        if not self.is_running:
            raise ProblemDetail(
                problem_type="action-conflict",
                detail=f"The interaction is not running: {self.status}.",
            )

        if turn != self.current_turn:
            raise ProblemDetail(
                problem_type="action-conflict",
                detail=(
                    f"Turn {turn} is not the current turn "
                    f"({self.current_turn})."
                ),
            )

        if agent.agent_id not in self.active_agent_ids:
            raise ProblemDetail(
                problem_type="action-conflict",
                detail=f"Agent {agent.agent_id} is not expected to act in turn {turn}.",
            )

        already_acted = any(
            action.agent_id == agent.agent_id and action.turn == turn
            for action in self.actions.values()
        )

        if already_acted:
            raise ProblemDetail(
                problem_type="action-conflict",
                detail=(
                    f"Agent {agent.agent_id} has already acted in turn {turn}."
                ),
            )

    def _require_same_participant(
        self,
        agent: AgentSlot,
        participant: dict[str, Any] | None,
    ) -> None:
        """
        Check that a repeated registration carries the same participant.

        Args:
            agent: Agent that is already registered.
            participant: Participant of the repeated registration.

        Returns:
        """

        registered_id = (agent.participant or {}).get("participantId")
        submitted_id = (participant or {}).get("participantId")

        if registered_id != submitted_id:
            raise ProblemDetail(
                problem_type="registration-conflict",
                detail=(
                    f"Agent {agent.agent_id} is already registered for a "
                    "different participant."
                ),
            )

    def _validate_behavior(
        self,
        behavior: dict[str, Any],
        agent: AgentSlot,
    ) -> None:
        """
        Validate a submitted behavior against the agent's state space schema.

        Args:
            behavior: Behavior vector.
            agent: Agent that submitted the behavior.

        Returns:
        """

        errors = self.schema_for(state_space=agent.state_space).validate_vector(
            vector=behavior
        )

        if errors:
            raise ProblemDetail(
                problem_type="invalid-state-vector",
                detail=(
                    "The submitted behavior does not conform to the model's "
                    "state-space schema."
                ),
                errors=errors,
            )

    def _validate_experience(
        self,
        experience: dict[str, Any],
        agent: AgentSlot,
        source_agent: AgentSlot,
    ) -> None:
        """
        Validate an experience against the perceiving agent's state space.

        The specification requires that every returned experience vector is
        valid according to the shared schema. When the two agents work in
        different state spaces, the vector has passed through a converter, and
        a converter can leave the target space: the interpersonal circumplex,
        for instance, excludes its own neutral center, which every other space
        contains. Rather than hand a client a vector its schema rejects, the
        interaction fails here and names the conversion that produced it.

        Args:
            experience: Experience vector delivered to the agent.
            agent: Agent that would perceive the experience.
            source_agent: Agent whose behavior produced the experience.

        Returns:
        """

        errors = self.schema_for(state_space=agent.state_space).validate_vector(
            vector=experience
        )

        if not errors:
            return

        self._finish(
            status="failed",
            reason="serverError",
        )

        if agent.state_space == source_agent.state_space:
            raise ProblemDetail(
                problem_type="invalid-state-vector",
                detail=(
                    f"The experience produced for agent {agent.agent_id} is "
                    f"outside the state space {agent.state_space}."
                ),
                errors=errors,
            )

        raise ProblemDetail(
            problem_type="invalid-state-vector",
            detail=(
                f"Converting a state from {source_agent.state_space} to "
                f"{agent.state_space} produced a vector outside "
                f"{agent.state_space}. The two state spaces do not cover the "
                "same region, and the ITP converters do not yet enforce "
                "geometry constraints."
            ),
            errors=errors,
        )

    def _active_agent(
        self,
    ) -> AgentSlot | None:
        """
        Return the agent that is currently expected to act.

        Args:

        Returns:
            Active agent, or None if no agent is expected to act.
        """

        if not self.active_agent_ids:
            return None

        return self.get_agent(agent_id=self.active_agent_ids[0])

    def _last_cursor(
        self,
        agent_id: str,
    ) -> int:
        """
        Return the cursor of the last perception of one agent.

        Args:
            agent_id: Identifier of the agent.

        Returns:
            Cursor of the last perception, or 0 if the agent has none.
        """

        perceptions = self.perceptions[agent_id]

        return perceptions[-1].cursor if perceptions else 0

    def _parse_cursor(
        self,
        after: str | None,
    ) -> int:
        """
        Parse the cursor a client sends with a perception poll.

        Args:
            after: Cursor of the last perception the client processed.

        Returns:
            Parsed cursor.
        """

        if after is None or after == "":
            return 0

        try:
            return int(after)
        except (TypeError, ValueError) as error:
            raise ProblemDetail(
                problem_type="malformed-request",
                detail=f"The cursor is not a valid perception cursor: {after}",
            ) from error

    def _finish(
        self,
        status: str,
        reason: str,
    ) -> None:
        """
        Move the interaction into an end state.

        Args:
            status: End status of the interaction.
            reason: Reason the interaction ended.

        Returns:
        """

        self.status = status
        self.end_reason = reason
        self.ended_at = make_iso_timestamp()
        self.active_agent_ids = []

        if self.persistence_enabled and self.results_root is not None:
            self.save_results(root=self.results_root)

        if not self.persistence_enabled:
            self.turns = []
            self.communication.messages = []
            self.results_discarded = True
