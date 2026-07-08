from __future__ import annotations

from src.communication.Communication import Communication
from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.formalmodels.DummyFormalModel import DummyFormalModel


def instantiate_models(
    model_a_seed: int | None = 1,
    model_b_seed: int | None = 2,
) -> dict[str, BaseFormalModel]:
    """
    Instantiate the formal models used in the interaction.

    Args:
        model_a_seed: Random seed used to initialize the first model.
        model_b_seed: Random seed used to initialize the second model.

    Returns:
        Dictionary mapping agent identifiers to instantiated formal models.
    """

    model_a = DummyFormalModel(
        model_id="model_a",
        random_seed=model_a_seed,
    )

    model_b = DummyFormalModel(
        model_id="model_b",
        random_seed=model_b_seed,
    )

    return {
        "model_a": model_a,
        "model_b": model_b,
    }


def make_timecode(
    interaction_turn: int,
    message_index: int,
) -> dict[str, int | str]:
    """
    Create a timecode for an ITP message.

    Args:
        interaction_turn: Sequential interaction turn.
        message_index: Sequential message within the interaction turn.

    Returns:
        Timecode.
    """

    return {
        "timestamp": f"{interaction_turn}:{message_index:02d}",
        "interaction_turn": interaction_turn,
    }


def exchange_message(
    communication: Communication,
    models: dict[str, BaseFormalModel],
    source_agent: str,
    target_agent: str,
    timecode: dict[str, int | str],
) -> dict:
    """
    Exchange one ITP message between two formal models.

    Args:
        communication: ITP communication session.
        models: Dictionary mapping agent identifiers to formal models.
        source_agent: Identifier of the sending agent.
        target_agent: Identifier of the receiving agent.
        timecode: Time information for the message.

    Returns:
        Numerical ITP message.
    """

    message = models[source_agent].to_message(
        target_agent=target_agent,
        timecode=timecode,
        context=communication.context_name,
    )

    communication.receive_message(message)
    models[target_agent].from_message(message)

    return message


def run_interaction(
    models: dict[str, BaseFormalModel],
    n_interaction_turns: int = 10,
    first_agent: str = "model_a",
    context: str = "workplace_colleague_conversation",
    verbose: bool = True,
) -> Communication:
    """
    Run a sequential ITP interaction between two formal models.

    Args:
        models: Dictionary containing the instantiated formal models.
        n_interaction_turns: Number of interaction turns.
        first_agent: Agent that sends the first message in each interaction turn.
        context: String describing the interaction context.
        verbose: Whether to print the exchanged messages.

    Returns:
        Communication session containing the exchanged ITP messages.
    """

    agent_ids = list(models)
    second_agent = next(agent_id for agent_id in agent_ids if agent_id != first_agent)

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
        )

        if verbose:
            print(f"\nInteraction turn {interaction_turn}")
            print(first_message)
            print(second_message)

    return communication


if __name__ == "__main__":
    models = instantiate_models(
        model_a_seed=1,
        model_b_seed=2,
    )

    communication = run_interaction(
        models=models,
        n_interaction_turns=10,
        first_agent="model_a",
        context="workplace_colleague_conversation",
        verbose=True,
    )