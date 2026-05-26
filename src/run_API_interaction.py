from __future__ import annotations

from src.API.APIClient import APIClient
from src.FormalModels.DummyFormalModel import DummyFormalModel


def run_remote_interaction(
    n_interaction_turns: int = 10,
    context: str = "workplace_colleague_conversation",
) -> None:
    """
    Run an interaction between one local and one remote formal model.

    Args:
        n_interaction_turns: Number of interaction turns.
        context: String describing the interaction context.

    Returns:
    """

    remote_model_a = APIClient("http://127.0.0.1:8001")

    model_b = DummyFormalModel(
        model_id="model_b",
        random_seed=2,
    )

    for interaction_turn in range(1, n_interaction_turns + 1):
        message_a = remote_model_a.generate_message(
            target_model_id="model_b",
            interaction_turn=interaction_turn,
            context=context,
        )

        model_b.from_message(message_a)

        message_b = model_b.to_message(
            target_model_id="model_a",
            interaction_turn=interaction_turn,
            context=context,
        )

        message_a_response = remote_model_a.step(message_b)

        print(f"\nInteraction turn {interaction_turn}")
        print("Remote model A output:")
        print(message_a_response)
        print("Local model B output:")
        print(message_b)


if __name__ == "__main__":
    run_remote_interaction()