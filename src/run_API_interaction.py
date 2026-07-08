from __future__ import annotations

from typing import Any

from src.API.APIClient import APIClient
from src.communication.Communication import Communication
from src.converter.ConverterRegistry import make_default_converter_registry
from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.formalmodels.DummyFormalModels import DummyIPCFormalModel
from src.utils.utilfuncs import *


def store_and_prepare_message(
    communication: Communication,
    message: dict[str, Any],
    converter=None,
) -> dict[str, Any]:
    """
    Store an original message and, if needed, store its converted version.

    Args:
        communication: ITP communication session.
        message: Numerical ITP message.
        converter: Optional converter used to align message values.

    Returns:
        Numerical ITP message ready for the target agent.
    """

    communication.receive_message(message)

    delivered_message = prepare_message_for_target(
        message=message,
        converter=converter,
    )

    if delivered_message is not message:
        communication.receive_message(delivered_message)

    return delivered_message


def run_remote_interaction(
    n_interaction_turns: int = 10,
    context: str = "workplace_colleague_conversation",
    converter=None,
) -> Communication:
    """
    Run an interaction between one local and one remote formal model.

    Args:
        n_interaction_turns: Number of interaction turns.
        context: String describing the interaction context.
        converter: Optional converter used to align message values.

    Returns:
        Communication session containing the exchanged ITP messages.
    """

    communication = Communication(context=context)

    remote_model = APIClient("http://127.0.0.1:8001")
    remote_agent = remote_model.get_info()["agent"]

    local_model: BaseFormalModel = DummyIPCFormalModel(
        model_id="model_b",
        random_seed=2,
    )

    local_agent = local_model.to_agent()

    for interaction_turn in range(1, n_interaction_turns + 1):
        remote_message = remote_model.generate_message(
            target_agent=local_agent,
            timecode=make_timecode(
                interaction_turn=interaction_turn,
                message_index=1,
            ),
            context=communication.context_name,
        )

        remote_message_for_local = store_and_prepare_message(
            communication=communication,
            message=remote_message,
            converter=converter,
        )

        local_model.from_message(remote_message_for_local)

        local_message = local_model.to_message(
            target_agent=remote_agent,
            timecode=make_timecode(
                interaction_turn=interaction_turn,
                message_index=2,
            ),
            context=communication.context_name,
        )

        local_message_for_remote = store_and_prepare_message(
            communication=communication,
            message=local_message,
            converter=converter,
        )

        remote_response = remote_model.step(local_message_for_remote)

        remote_response_for_local = store_and_prepare_message(
            communication=communication,
            message=remote_response,
            converter=converter,
        )

        local_model.from_message(remote_response_for_local)

        print(f"\nInteraction turn {interaction_turn}")
        print("Remote model output:")
        print(remote_message)
        print("Local model output:")
        print(local_message)
        print("Remote model response:")
        print(remote_response)

    return communication


if __name__ == "__main__":
    converter = make_default_converter_registry()
    run_remote_interaction(converter=converter)