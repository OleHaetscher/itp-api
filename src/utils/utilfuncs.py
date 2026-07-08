from typing import Any


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


def needs_conversion(
    message: dict[str, Any],
) -> bool:
    """
    Check whether a message needs conversion before delivery.

    Args:
        message: Numerical ITP message.

    Returns:
        Whether the message needs conversion.
    """

    return (
        message["values"]["state_space"] != message["target_agent"]["state_space"]
        or message["values"]["analysis_unit"] != message["target_agent"]["analysis_unit"]
    )


def prepare_message_for_target(
    message: dict[str, Any],
    converter=None,
) -> dict[str, Any]:
    """
    Convert a message if needed before it is delivered to the target model.

    Args:
        message: Numerical ITP message.
        converter: Optional converter used to align message values with the target model.

    Returns:
        Numerical ITP message ready for the target model.
    """

    if not needs_conversion(message):
        return message

    if converter is None:
        raise ValueError(
            "Message requires conversion, but no converter was provided."
        )

    return converter.convert_message(message)