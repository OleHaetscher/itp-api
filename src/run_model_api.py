from __future__ import annotations

from pathlib import Path

import uvicorn

from src.API.APISpecification import APISpecification
from src.API.ModelCatalogue import ModelCatalogue, ModelConstraints, ModelEntry
from src.converter.ConverterRegistry import make_default_converter_registry
from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.formalmodels.DummyFormalModels import DummyIPCFormalModel, DummySASBFormalModel
from src.formalmodels.LASSIFormalModel import LASSIFormalModel

# Interaction records are written to results/ below this directory.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def make_dummy_ipc_model(
    agent_id: str,
) -> BaseFormalModel:
    """
    Create a dummy IPC model instance for one agent.

    The agent identifier becomes the model identifier, because ITP messages are
    addressed to a model identifier and every agent runs its own instance.

    Args:
        agent_id: Identifier of the agent the instance belongs to.

    Returns:
        Formal model instance.
    """

    return DummyIPCFormalModel(model_id=agent_id)


def make_dummy_sasb_model(
    agent_id: str,
) -> BaseFormalModel:
    """
    Create a dummy SASB model instance for one agent.

    Args:
        agent_id: Identifier of the agent the instance belongs to.

    Returns:
        Formal model instance.
    """

    return DummySASBFormalModel(model_id=agent_id)


def make_lassi_model(
    agent_id: str,
) -> BaseFormalModel:
    """
    Create a LASSI agency-communion model instance for one agent.

    Args:
        agent_id: Identifier of the agent the instance belongs to.

    Returns:
        Formal model instance.
    """

    return LASSIFormalModel(model_id=agent_id)


def make_catalogue() -> ModelCatalogue:
    """
    Create the catalogue of models this API process offers.

    Args:

    Returns:
        Model catalogue.
    """

    return ModelCatalogue(
        entries=[
            ModelEntry(
                model_id="dummy-ipc",
                version="0.2.0",
                name="Dummy interpersonal circumplex model",
                description=(
                    "Averaging reference model in the interpersonal circumplex, "
                    "used to exercise the protocol rather than to model behavior."
                ),
                model_factory=make_dummy_ipc_model,
                state_space="ipc",
                constraints=ModelConstraints(
                    minimum_turns=1,
                    maximum_turns=1000,
                    supports_persistence=True,
                ),
            ),
            ModelEntry(
                model_id="dummy-sasb",
                version="0.2.0",
                name="Dummy SASB model",
                description=(
                    "Averaging reference model on the transitive SASB diamond, "
                    "used to exercise the protocol rather than to model behavior."
                ),
                model_factory=make_dummy_sasb_model,
                state_space="sasb",
                constraints=ModelConstraints(
                    minimum_turns=1,
                    maximum_turns=1000,
                    supports_persistence=True,
                ),
            ),
            ModelEntry(
                model_id="lassi",
                version="0.2.0",
                name="LASSI agency-communion model",
                description=(
                    "Discrete agency-communion model with a behavioral default, "
                    "complementarity, and interpersonal reactivity per axis."
                ),
                model_factory=make_lassi_model,
                state_space="ac",
                constraints=ModelConstraints(
                    minimum_turns=1,
                    maximum_turns=500,
                    supports_persistence=True,
                ),
            ),
        ]
    )


def make_api() -> APISpecification:
    """
    Create the ITP API serving the model catalogue.

    Every interaction with persistence enabled writes its record to
    results/ below the repository root when it ends: the ITP messages as the
    numbered files src/run_local_interaction.py also produces, and an
    interaction.json holding what only the API knows. Pass results_root=None
    to keep the process from writing anything to disk.

    Args:

    Returns:
        ITP API.
    """

    return APISpecification(
        catalogue=make_catalogue(),
        converter=make_default_converter_registry(),
        results_root=REPOSITORY_ROOT,
    )


def run_api() -> None:
    """
    Run the ITP API.

    Args:

    Returns:
    """

    uvicorn.run(
        make_api().app,
        host="127.0.0.1",
        port=8001,
    )


if __name__ == "__main__":
    run_api()
