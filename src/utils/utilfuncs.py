from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"


def load_config(
    name: str,
) -> dict[str, Any]:
    """
    Load a YAML config file from the configs directory.

    Args:
        name: File name of the config, for example "formal_model_parameters.yaml".

    Returns:
        Config content.
    """

    path = CONFIG_DIR / name

    with open(path, encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


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

def make_iso_timestamp() -> str:
    """
    Create an ISO 8601 timestamp in UTC.

    The ITP API specification requires all API timestamps in this format.

    Args:

    Returns:
        Timestamp, for example "2026-07-31T08:45:00Z".
    """

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
