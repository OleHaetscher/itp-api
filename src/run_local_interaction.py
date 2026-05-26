from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from src.FormalModels.BaseFormalModel import BaseFormalModel
from src.FormalModels.DummyFormalModel import DummyFormalModel


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
        Dictionary mapping model identifiers to instantiated formal models.
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


def save_protocol_message(
    message: dict[str, Any],
    output_dir: str | Path,
    file_name: str,
) -> Path:
    """
    Save one interaction protocol message as a JSON file.

    Args:
        message: Numerical ITP message.
        output_dir: Directory in which the message should be stored.
        file_name: Name of the JSON file.

    Returns:
        Path to the saved JSON file.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    path = output_dir / file_name
    BaseFormalModel.specification.save_json(message=message, path=path)

    return path


def run_interaction(
    models: dict[str, BaseFormalModel],
    n_interaction_turns: int = 10,
    first_model: Literal["model_a", "model_b"] = "model_a",
    context: str = "workplace_colleague_conversation",
    protocol_output_dir: str | Path | None = "results/interaction_protocol_example",
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """
    Run a sequential interaction between two formal models.

    Args:
        models: Dictionary containing the instantiated formal models.
        n_interaction_turns: Number of interaction turns.
        first_model: Model that starts each interaction turn.
        context: String describing the interaction context.
        protocol_output_dir: Optional directory for storing protocol messages as JSON files.
        verbose: Whether to print the interaction history.

    Returns:
        Interaction history containing states and exchanged messages.
    """

    if n_interaction_turns < 1:
        raise ValueError("n_interaction_turns must be at least 1.")

    if first_model not in models:
        raise ValueError(f"Unknown first model: {first_model}")

    if len(models) != 2:
        raise ValueError("This reference interaction currently expects exactly two models.")

    model_ids = list(models)

    second_model = next(
        model_id for model_id in model_ids if model_id != first_model
    )

    history = []

    initial_state = {
        "interaction_turn": 0,
        "first_model": first_model,
        "second_model": second_model,
        "states": {
            model_id: model.generate_numerical_output(context=context)
            for model_id, model in models.items()
        },
        "messages": {},
        "message_files": {},
    }

    history.append(initial_state)

    if verbose:
        print("Initial state")
        print(initial_state)

    for interaction_turn in range(1, n_interaction_turns + 1):
        first_actor = models[first_model]
        second_actor = models[second_model]

        first_message = first_actor.to_message(
            target_model_id=second_model,
            interaction_turn=interaction_turn,
            context=context,
        )

        first_message_file = None

        if protocol_output_dir is not None:
            first_message_file = save_protocol_message(
                message=first_message,
                output_dir=protocol_output_dir,
                file_name=f"turn_{interaction_turn:03d}_{first_model}_to_{second_model}.json",
            )

        second_actor.from_message(first_message)

        second_message = second_actor.to_message(
            target_model_id=first_model,
            interaction_turn=interaction_turn,
            context=context,
        )

        second_message_file = None

        if protocol_output_dir is not None:
            second_message_file = save_protocol_message(
                message=second_message,
                output_dir=protocol_output_dir,
                file_name=f"turn_{interaction_turn:03d}_{second_model}_to_{first_model}.json",
            )

        first_actor.from_message(second_message)

        turn_state = {
            "interaction_turn": interaction_turn,
            "first_model": first_model,
            "second_model": second_model,
            "states": {
                model_id: model.generate_numerical_output(context=context)
                for model_id, model in models.items()
            },
            "messages": {
                first_model: first_message,
                second_model: second_message,
            },
            "message_files": {
                first_model: str(first_message_file) if first_message_file else None,
                second_model: str(second_message_file) if second_message_file else None,
            },
        }

        history.append(turn_state)

        if verbose:
            print(f"\nState after interaction turn {interaction_turn}")
            print(turn_state)

    return history


if __name__ == "__main__":
    instantiated_models = instantiate_models(
        model_a_seed=1,
        model_b_seed=2,
    )

    run_interaction(
        models=instantiated_models,
        n_interaction_turns=10,
        first_model="model_a",
        context="workplace_colleague_conversation",
        protocol_output_dir="../results/interaction_protocol",
        verbose=True,
    )