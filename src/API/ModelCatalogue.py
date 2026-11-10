"""
Catalogue of the formal models an ITP API process offers.

The ITP API specification binds every interaction to an exact model id and
model version, and exposes the available models through ``GET /models``. This
module holds that catalogue: one entry per model, each carrying the factory
that produces a fresh model instance per agent and the state space schema used
to validate perceptions and behaviors. A model that lets agents differ in its
parameters also carries the ParameterSpace an agent's ``configuration`` is
resolved against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.API.StateSpaceSchema import StateSpaceSchema
from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.formalmodels.ParameterSpace import ParameterError, ParameterSpace

MODEL_STATUSES = ("available", "maintenance", "deprecated", "unavailable")
AGENT_TYPES = ("human", "model")
INTERACTION_MODES = ("turnBased",)


@dataclass
class ModelConstraints:
    """
    Constraints an interaction using this model must satisfy.

    Args:
        minimum_turns: Smallest permitted number of interaction turns.
        maximum_turns: Largest permitted number of interaction turns.
        supports_persistence: Whether interaction data may be persisted.

    Returns:
    """

    minimum_turns: int = 1
    maximum_turns: int = 1000
    supports_persistence: bool = True

    def describe(
        self,
    ) -> dict[str, Any]:
        """
        Describe the constraints for the model endpoint.

        Args:

        Returns:
            Constraints in the API representation.
        """

        return {
            "minimumTurns": self.minimum_turns,
            "maximumTurns": self.maximum_turns,
            "supportsPersistence": self.supports_persistence,
        }


@dataclass
class ModelEntry:
    """
    One formal model offered by the API.

    Args:
        model_id: Stable identifier of the model.
        version: Exact model version an interaction is bound to.
        name: Readable model name.
        description: Readable model description.
        model_factory: Callable producing a fresh model instance per agent,
            from the agent id, the parameter values the agent runs with (None
            for a model without a parameter space), and the seed of the
            model's own random draws.
        state_space: ITP state space identifier the model works in.
        status: Availability of the model for new interactions.
        supported_agent_types: Agent types the model can be paired with.
        interaction_mode: Turn mode of interactions using this model.
        constraints: Constraints on interactions using this model.
        parameter_space: Parameters an agent's configuration may choose, or
            None if every agent runs the same model.

    Returns:
    """

    model_id: str
    version: str
    name: str
    description: str
    model_factory: Callable[[str, dict[str, dict[str, float]] | None, int | None], BaseFormalModel]
    state_space: str
    status: str = "available"
    supported_agent_types: tuple[str, ...] = AGENT_TYPES
    interaction_mode: str = "turnBased"
    constraints: ModelConstraints = field(default_factory=ModelConstraints)
    parameter_space: ParameterSpace | None = None

    def __post_init__(self) -> None:
        """
        Validate the catalogue entry and compile its state space schema.

        Args:

        Returns:
        """

        if self.status not in MODEL_STATUSES:
            raise ValueError(f"Unknown model status: {self.status}")

        if self.interaction_mode not in INTERACTION_MODES:
            raise ValueError(f"Unknown interaction mode: {self.interaction_mode}")

        unknown_agent_types = set(self.supported_agent_types) - set(AGENT_TYPES)

        if unknown_agent_types:
            raise ValueError(f"Unknown agent types: {sorted(unknown_agent_types)}")

        self.state_space_schema = StateSpaceSchema.from_state_space(self.state_space)

    @property
    def is_available(self) -> bool:
        """
        Return whether the model can be used for new interactions.

        Args:

        Returns:
            Whether the model is available.
        """

        return self.status == "available"

    def resolve_configuration(
        self,
        configuration: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """
        Resolve an agent's configuration into the parameters it runs with.

        Args:
            configuration: The agent's configuration from the creation request.

        Returns:
            Selection, seed and values from ParameterSpace.resolve, or None for
            a model without a parameter space.
        """

        if self.parameter_space is None:
            if configuration:
                raise ParameterError(
                    f"Model {self.model_id} has no parameters to configure; "
                    "leave out configuration."
                )
            return None

        return self.parameter_space.resolve(configuration)

    def create_model(
        self,
        agent_id: str,
        parameters: dict[str, dict[str, float]] | None = None,
        random_seed: int | None = None,
    ) -> BaseFormalModel:
        """
        Create a fresh model instance for one agent.

        Args:
            agent_id: Identifier of the agent the instance belongs to.
            parameters: Parameter values the agent runs with, keyed by group,
                then by name; None for the model's defaults.
            random_seed: Seed of the model's own random draws (a starting
                state, a sampled expressed state); None for unseeded draws.

        Returns:
            Formal model instance.
        """

        model = self.model_factory(agent_id, parameters, random_seed)
        model.validate_model_interface()

        if model.state_space != self.state_space:
            raise ValueError(
                f"Model {self.model_id} declares state space {self.state_space}, "
                f"but its instances use {model.state_space}."
            )

        return model

    def describe_summary(
        self,
    ) -> dict[str, Any]:
        """
        Describe the model for the model list endpoint.

        Args:

        Returns:
            Model summary in the API representation.
        """

        return {
            "id": self.model_id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "supportedAgentTypes": list(self.supported_agent_types),
            "links": {"self": f"/api/v1/models/{self.model_id}"},
        }

    def describe(
        self,
    ) -> dict[str, Any]:
        """
        Describe the model and its state space for the model detail endpoint.

        Args:

        Returns:
            Model definition in the API representation.
        """

        state_space = self.state_space_schema.describe()

        return {
            "id": self.model_id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "supportedAgentTypes": list(self.supported_agent_types),
            "interactionMode": self.interaction_mode,
            "stateSpaceSchema": state_space["stateSpaceSchema"],
            "stateSpace": {
                key: value
                for key, value in state_space.items()
                if key != "stateSpaceSchema"
            },
            "constraints": self.constraints.describe(),
            "parameterSpace": (
                self.parameter_space.describe()
                if self.parameter_space is not None
                else None
            ),
        }


class ModelCatalogue:
    """
    Registry of the formal models an API process offers.

    Args:

    Returns:
    """

    def __init__(
        self,
        entries: list[ModelEntry] | None = None,
    ) -> None:
        """
        Initialize the model catalogue.

        Args:
            entries: Model entries to register.

        Returns:
        """

        self.entries: dict[str, ModelEntry] = {}

        for entry in entries or []:
            self.register(entry)

    def register(
        self,
        entry: ModelEntry,
    ) -> None:
        """
        Register one model.

        Args:
            entry: Model entry to register.

        Returns:
        """

        if entry.model_id in self.entries:
            raise ValueError(f"Model is already registered: {entry.model_id}")

        self.entries[entry.model_id] = entry

    def get(
        self,
        model_id: str,
    ) -> ModelEntry | None:
        """
        Return one registered model.

        Args:
            model_id: Identifier of the model.

        Returns:
            Model entry, or None if the model is not registered.
        """

        return self.entries.get(model_id)

    def list_models(
        self,
    ) -> dict[str, Any]:
        """
        Describe every registered model for the model list endpoint.

        Args:

        Returns:
            Model summaries in the API representation.
        """

        return {
            "models": [entry.describe_summary() for entry in self.entries.values()]
        }
