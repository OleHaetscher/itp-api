from __future__ import annotations

from typing import Any

from src.API.APIClient import APIClient
from src.communication.Communication import Communication
from src.formalmodels.DummyFormalModel import DummyFormalModel


def make_timecode(
    interaction_turn: int,
    message_index: int,
) -> dict[str, Any]:
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


def run_remote_interaction(
    n_interaction_turns: int = 10,
    context: str = "workplace_colleague_conversation",
) -> Communication:
    """
    Run an interaction between one local and one remote formal model.

    Args:
        n_interaction_turns: Number of interaction turns.
        context: String describing the interaction context.

    Returns:
        Communication session containing the exchanged ITP messages.
    """

    communication = Communication(context=context)

    remote_model_a = APIClient("http://127.0.0.1:8001")

    model_b = DummyFormalModel(
        model_id="model_b",
        random_seed=2,
    )

    for interaction_turn in range(1, n_interaction_turns + 1):
        message_a = remote_model_a.generate_message(
            target_agent="model_b",
            timecode=make_timecode(
                interaction_turn=interaction_turn,
                message_index=1,
            ),
            context=communication.context_name,
        )

        communication.receive_message(message_a)
        model_b.from_message(message_a)

        message_b = model_b.to_message(
            target_agent="model_a",
            timecode=make_timecode(
                interaction_turn=interaction_turn,
                message_index=2,
            ),
            context=communication.context_name,
        )

        communication.receive_message(message_b)

        message_a_response = remote_model_a.step(message_b)

        communication.receive_message(message_a_response)
        model_b.from_message(message_a_response)

        print(f"\nInteraction turn {interaction_turn}")
        print("Remote model A output:")
        print(message_a)
        print("Local model B output:")
        print(message_b)
        print("Remote model A response:")
        print(message_a_response)

    return communication


if __name__ == "__main__":
    run_remote_interaction()