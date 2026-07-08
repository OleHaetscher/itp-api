from __future__ import annotations

from typing import Any

from src.communication.Communication import Communication
from src.converter.ConverterRegistry import make_default_converter_registry
from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.formalmodels.DummyFormalModels import DummyIPCFormalModel, DummySASBFormalModel
from src.utils.utilfuncs import *

def instantiate_models(
    model_ipc_seed: int | None = 1,
    model_sasb_seed: int | None = 2,
) -> dict[str, BaseFormalModel]:
    """
    Instantiate the formal models used in the interaction.

    Args:
        model_ipc_seed: Random seed used to initialize the IPC model.
        model_sasb_seed: Random seed used to initialize the SASB model.

    Returns:
        Dictionary mapping agent identifiers to instantiated formal models.
    """

    model_ipc = DummyIPCFormalModel(
        model_id="model_ipc",
        random_seed=model_ipc_seed,
    )

    model_sasb = DummySASBFormalModel(
        model_id="model_sasb",
        random_seed=model_sasb_seed,
    )

    return {
        model_ipc.model_id: model_ipc,
        model_sasb.model_id: model_sasb,
    }


def exchange_message(
    communication: Communication,
    models: dict[str, BaseFormalModel],
    source_agent: str,
    target_agent: str,
    timecode: dict[str, Any],
    converter=None,
) -> dict[str, Any]:
    """
    Exchange one ITP message between two formal models.

    Args:
        communication: ITP communication session.
        models: Dictionary mapping agent identifiers to formal models.
        source_agent: Identifier of the sending agent.
        target_agent: Identifier of the receiving agent.
        timecode: Time information for the message.
        converter: Optional converter used to align message values.

    Returns:
        Numerical ITP message delivered to the target model.
    """

    original_message = models[source_agent].to_message(
        target_agent=models[target_agent].to_agent(),
        timecode=timecode,
        context=communication.context_name,
    )

    communication.receive_message(original_message)

    delivered_message = prepare_message_for_target(
        message=original_message,
        converter=converter,
    )

    if delivered_message is not original_message:
        communication.receive_message(delivered_message)

    models[target_agent].from_message(delivered_message)

    return delivered_message


def get_second_agent(
    models: dict[str, BaseFormalModel],
    first_agent: str,
) -> str:
    """
    Return the second agent in a two-agent interaction.

    Args:
        models: Dictionary mapping agent identifiers to formal models.
        first_agent: Identifier of the first agent.

    Returns:
        Identifier of the second agent.
    """

    agent_ids = list(models)

    if first_agent not in models:
        raise ValueError(f"Unknown first agent: {first_agent}")

    if len(agent_ids) != 2:
        raise ValueError("This runner currently expects exactly two models.")

    return next(agent_id for agent_id in agent_ids if agent_id != first_agent)


def run_interaction(
    models: dict[str, BaseFormalModel],
    n_interaction_turns: int = 10,
    first_agent: str = "model_sasb",
    context: str = "workplace_colleague_conversation",
    verbose: bool = True,
    converter=None,
) -> Communication:
    """
    Run a sequential ITP interaction between two formal models.

    Args:
        models: Dictionary containing the instantiated formal models.
        n_interaction_turns: Number of interaction turns.
        first_agent: Agent that sends the first message in each interaction turn.
        context: String describing the interaction context.
        verbose: Whether to print the exchanged messages.
        converter: Optional converter used to align message values.

    Returns:
        Communication session containing the exchanged ITP messages.
    """

    second_agent = get_second_agent(
        models=models,
        first_agent=first_agent,
    )

    communication = Communication(context=context)

    for interaction_turn in range(1, n_interaction_turns + 1):
        first_message = exchange_message(
            communication=communication,
            models=models,
            source_agent=first_agent,
            target_agent=second_agent,
            timecode=make_timecode(
                interaction_turn=interaction_turn,
                message_index=1,
            ),
            converter=converter,
        )

        second_message = exchange_message(
            communication=communication,
            models=models,
            source_agent=second_agent,
            target_agent=first_agent,
            timecode=make_timecode(
                interaction_turn=interaction_turn,
                message_index=2,
            ),
            converter=converter,
        )

        if verbose:
            print(f"\nInteraction turn {interaction_turn}")
            print(first_message)
            print(second_message)

    return communication


if __name__ == "__main__":
    models = instantiate_models(
        model_ipc_seed=1,
        model_sasb_seed=2,
    )

    converter = make_default_converter_registry()

    communication = run_interaction(
        models=models,
        n_interaction_turns=10,
        first_agent="model_sasb",
        context="workplace_colleague_conversation",
        verbose=True,
        converter=converter,
    )

    output_dir = communication.save_messages(root=".")
    print(output_dir)