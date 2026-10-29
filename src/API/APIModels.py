"""
Request and response models for the ITP API.

The ITP API specification uses camelCase for JSON property names and status
values. These Pydantic models pin that contract down, so the generated OpenAPI
document at ``/docs`` carries payload schemas a JavaScript client can be typed
against, rather than the bare ``dict[str, Any]`` the previous API exposed.

Request models forbid unknown properties: a client that misspells a key gets a
400 rather than a silently ignored field. Response models are attached to the
routes for documentation only, so a response never has fields filtered out by
a model that has drifted from the implementation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AgentRole = Literal["A", "B"]
AgentType = Literal["human", "model"]


class StrictModel(BaseModel):
    """
    Base model rejecting unknown properties.

    Args:

    Returns:
    """

    model_config = ConfigDict(extra="forbid")


class ParticipantSpecification(StrictModel):
    """
    Participant registered for a human agent.

    Args:

    Returns:
    """

    participant_id: str | None = Field(default=None, alias="participantId")
    display_name: str | None = Field(default=None, alias="displayName")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ClientSpecification(StrictModel):
    """
    Client instance acting for a human agent.

    Args:

    Returns:
    """

    client_id: str | None = Field(default=None, alias="clientId")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AgentSpecification(StrictModel):
    """
    One agent of a new interaction.

    Args:

    Returns:
    """

    type: AgentType
    display_name: str | None = Field(default=None, alias="displayName")
    configuration: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Model-specific configuration of a model agent. For a model with a "
            "parameterSpace: parameterSelection ('default' or 'random'), "
            "randomSeed (random only) and parameters keyed by group, then by "
            "name, which take precedence. A model without a parameterSpace "
            "and a human agent take none."
        ),
    )
    model_id: str | None = Field(
        default=None,
        alias="modelId",
        description=(
            "ITP extension. Model this formal model agent runs, if it differs "
            "from the interaction's modelId. Only valid for agents of type "
            "model."
        ),
    )
    model_version: str | None = Field(
        default=None,
        alias="modelVersion",
        description="ITP extension. Exact version of the agent's modelId.",
    )
    state_space: str | None = Field(
        default=None,
        alias="stateSpace",
        description=(
            "ITP extension. State space a human agent works in, if it differs "
            "from the state space of the model. Perceptions are converted into "
            "it. Formal model agents must use the state space of their model."
        ),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PersistenceSpecification(StrictModel):
    """
    Whether interaction data remains available after the interaction ends.

    Args:

    Returns:
    """

    enabled: bool = False


class CreateInteractionRequest(StrictModel):
    """
    Request creating a new interaction.

    Args:

    Returns:
    """

    model_id: str = Field(alias="modelId")
    model_version: str | None = Field(default=None, alias="modelVersion")
    number_of_turns: int = Field(alias="numberOfTurns", ge=1)
    persistence: PersistenceSpecification | None = None
    agents: dict[AgentRole, AgentSpecification]
    client_request_id: str | None = Field(default=None, alias="clientRequestId")
    context: str | None = Field(
        default=None,
        description=(
            "ITP extension. Name of the interaction context the models are "
            "given. Defaults to the context configured for the API."
        ),
    )
    starting_agent_role: AgentRole = Field(
        default="A",
        alias="startingAgentRole",
        description="ITP extension. Role of the agent that acts in turn 1.",
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RegisterAgentRequest(StrictModel):
    """
    Request registering a human participant that already holds the token.

    Args:

    Returns:
    """

    participant: ParticipantSpecification | None = None
    client: ClientSpecification | None = None


class JoinInteractionRequest(StrictModel):
    """
    Request joining an interaction with a six-digit invitation code.

    Args:

    Returns:
    """

    invitation_code: str = Field(alias="invitationCode", pattern=r"^[0-9]{6}$")
    participant: ParticipantSpecification | None = None
    client: ClientSpecification | None = None

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SubmitActionRequest(StrictModel):
    """
    Request submitting the behavior of one agent for one turn.

    Args:

    Returns:
    """

    action_id: str = Field(alias="actionId", min_length=1)
    # Optional: without it the server takes the current turn. A client that
    # re-sends a behavior after a failure can still pin it to a turn.
    turn: int | None = Field(default=None, ge=1)
    behavior: dict[str, float]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class EndInteractionRequest(StrictModel):
    """
    Request terminating an interaction before its normal completion.

    Args:

    Returns:
    """

    reason: str = "terminatedByClient"


class ModelSummary(BaseModel):
    """
    One model in the model list.

    Args:

    Returns:
    """

    id: str
    version: str
    name: str
    description: str
    status: str
    supportedAgentTypes: list[str]
    links: dict[str, str]


class ModelListResponse(BaseModel):
    """
    Response of the model list endpoint.

    Args:

    Returns:
    """

    models: list[ModelSummary]


class ModelDefinitionResponse(BaseModel):
    """
    Response of the model definition endpoint.

    Args:

    Returns:
    """

    id: str
    version: str
    name: str
    description: str
    status: str
    supportedAgentTypes: list[str]
    interactionMode: str
    stateSpaceSchema: dict[str, Any]
    stateSpace: dict[str, Any]
    constraints: dict[str, Any]
    parameterSpace: dict[str, Any] | None = None


class AgentModelDescription(BaseModel):
    """
    The formal model a model agent runs.

    Args:

    Returns:
    """

    id: str
    version: str
    name: str


class AgentDescription(BaseModel):
    """
    One agent in an interaction response.

    Args:

    Returns:
    """

    agentId: str
    role: str
    type: str
    registrationStatus: str
    displayName: str | None = None
    stateSpace: str | None = None
    model: AgentModelDescription | None = Field(
        default=None,
        description=(
            "ITP extension. The formal model the agent runs, or null for a "
            "human agent."
        ),
    )
    parameters: dict[str, Any] | None = Field(
        default=None,
        description=(
            "ITP extension. For a model with a parameterSpace: how the "
            "parameters were chosen (selection, randomSeed) and the values the "
            "agent runs with."
        ),
    )


class InvitationDescription(BaseModel):
    """
    Invitation status. The code is present only in the creation response.

    Args:

    Returns:
    """

    agentId: str
    agentRole: str
    status: str
    expiresAt: str
    code: str | None = None


class InteractionStatusResponse(BaseModel):
    """
    Response of the interaction status endpoint.

    Args:

    Returns:
    """

    sessionId: str
    status: str
    model: dict[str, str]
    numberOfTurns: int
    currentTurn: int
    activeAgentIds: list[str]
    agents: dict[str, AgentDescription]
    context: str
    persistence: dict[str, bool]
    createdAt: str
    startedAt: str | None = None
    endedAt: str | None = None
    endReason: str | None = None
    invitation: InvitationDescription | None = None


class CreateInteractionResponse(InteractionStatusResponse):
    """
    Response of the interaction creation endpoint.

    Args:

    Returns:
    """

    interactionToken: str


class RegistrationResponse(BaseModel):
    """
    Response of the participant registration endpoint.

    Args:

    Returns:
    """

    sessionId: str
    agentId: str
    agentRole: str
    registrationStatus: str
    sessionStatus: str
    registeredAt: str | None = None


class JoinInteractionResponse(BaseModel):
    """
    Response of the join endpoint.

    Args:

    Returns:
    """

    sessionId: str
    interactionToken: str
    sessionStatus: str
    agent: AgentDescription
    model: dict[str, str]
    numberOfTurns: int
    currentTurn: int
    registeredAt: str | None = None


class PerceptionResponse(BaseModel):
    """
    Response of the perception endpoint.

    The endpoint returns one of four states. ``pending`` and
    ``interactionEnded`` come from the specification, ``perceivable`` carries
    an experience, and ``actionRequired`` marks a turn in which the agent must
    act without having anything new to perceive.

    Args:

    Returns:
    """

    state: Literal["pending", "perceivable", "actionRequired", "interactionEnded"]
    sessionStatus: str
    currentTurn: int | None = None
    cursor: str | None = None
    retryAfterMilliseconds: int | None = None
    perceptionId: str | None = None
    turn: int | None = None
    agentId: str | None = None
    actionRequired: bool | None = None
    experience: dict[str, float] | None = None
    sourceAgentId: str | None = None
    createdAt: str | None = None
    finalTurn: int | None = None
    endReason: str | None = None
    endedAt: str | None = None


class ActionAcceptedResponse(BaseModel):
    """
    Response of the action endpoint.

    Args:

    Returns:
    """

    status: str
    sessionId: str
    agentId: str
    actionId: str
    turn: int
    cursor: str
    sessionStatus: str
    acceptedAt: str


class EndInteractionResponse(BaseModel):
    """
    Response of the end endpoint.

    Args:

    Returns:
    """

    sessionId: str
    status: str
    endReason: str | None = None
    finalTurn: int
    endedAt: str | None = None


class TurnResult(BaseModel):
    """
    One recorded turn in the results response.

    Args:

    Returns:
    """

    turn: int
    actorAgentId: str
    behavior: dict[str, float]
    perceptions: list[dict[str, Any]]
    createdAt: str


class ResultsResponse(BaseModel):
    """
    Response of the results endpoint.

    Args:

    Returns:
    """

    sessionId: str
    status: str
    model: dict[str, str]
    numberOfTurns: int
    context: str
    agents: dict[str, AgentDescription]
    turns: list[TurnResult]
    itpMessages: list[dict[str, Any]]
    completedAt: str | None = None
    resultsFolder: str | None = None


class ProblemDocument(BaseModel):
    """
    RFC 9457 problem document returned for every error.

    Args:

    Returns:
    """

    type: str
    title: str
    status: int
    detail: str
    instance: str | None = None
    errors: list[dict[str, str]] | None = None
    retryAfterSeconds: int | None = None
    requestId: str | None = None
