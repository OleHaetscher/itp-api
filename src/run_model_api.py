"""
Serve the ITP API.

The port is not fixed. 8001 is tried first, because that is what the README,
the mock client, and ``run_API_interaction`` expect to find, but a leftover
process or an unrelated service holding it is no reason to stop: the next free
port in 8001-8010 is taken instead, and the clients discover it. Set
``ITP_API_PORT`` to name a port, which is then obeyed exactly::

    ITP_API_PORT=9001 python -m src.run_model_api

Whichever port is taken is written to ``.itp-api-url`` at the repository root
while the process runs, because the clients are separate processes that cannot
observe it. The file is removed on shutdown, and a leftover one is checked
before it is believed.
"""

from __future__ import annotations

from pathlib import Path

import uvicorn

from src.API.APISpecification import APISpecification
from src.API.ModelCatalogue import ModelCatalogue, ModelConstraints, ModelEntry
from src.converter.ConverterRegistry import make_default_converter_registry
from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.formalmodels.DummyFormalModels import DummyIPCFormalModel, DummySASBFormalModel
from src.formalmodels.LASSIFormalModel import LASSIFormalModel
from src.utils.ports import (
    API_PORT_CANDIDATES,
    API_PORT_VARIABLE,
    announce_api_base_url,
    resolve_port,
    withdraw_api_base_url,
)

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

    host = "127.0.0.1"
    port = resolve_port(API_PORT_CANDIDATES, API_PORT_VARIABLE, host=host)

    if port != API_PORT_CANDIDATES[0]:
        print(
            f"\n  Port {API_PORT_CANDIDATES[0]} is in use, serving on {port} instead."
            f"\n  The mock client and run_API_interaction find this automatically."
        )

    base_url = f"http://{host}:{port}"

    print(f"\n  ITP API  ->  {base_url}/api/v1\n")

    app = make_api().app

    # Clients run in other processes and cannot see which port was taken. The
    # note is written last, so when two APIs are up the newest one is the one
    # a client finds.
    announce_api_base_url(base_url)

    # Withdrawing it hangs off the application shutdown rather than a finally
    # around uvicorn.run: uvicorn re-raises the signal it caught once it has
    # shut down, so control never comes back here when the process is stopped
    # the normal way. A note that outlives its process is survivable either
    # way, because a client checks that it answers before believing it.
    app.router.on_shutdown.append(withdraw_api_base_url)

    uvicorn.run(
        app,
        host=host,
        port=port,
    )


if __name__ == "__main__":
    run_api()
