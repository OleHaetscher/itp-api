from __future__ import annotations

import json
from copy import deepcopy
from numbers import Real
from pathlib import Path
from typing import Any


class ITPSpecification:
    """
    Specification for numerical messages exchanged between formal models.

    Args:

    Returns:
    """

    def __init__(
        self,
        schema_version: str = "0.1",
        allowed_dimensions: tuple[str, ...] = ("agency", "communion"),
    ) -> None:
        """
        Initialize the ITP communication specification.

        Args:
            schema_version: Version of the message schema.
            allowed_dimensions: Circumplex dimensions allowed in numerical messages.

        Returns:
        """

        self.schema_version = schema_version
        self.allowed_dimensions = allowed_dimensions

    def make_message(
        self,
        source_agent: str,
        target_agent: str,
        timecode: dict[str, Any],
        values: dict[str, float],
        context: str,
        metadata: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        Create a valid numerical ITP message.

        Args:
            source_agent: Identifier of the model producing the message.
            target_agent: Identifier of the model receiving the message.
            timecode: Sequential turn in the interaction.
            values: Numerical values carried by the message.
            context: String describing the interaction context.
            metadata: Optional additional information.

        Returns:
            Numerical ITP message.
        """

        message = {
            "schema_version": self.schema_version,
            "source_agent": source_agent,
            "target_agent": target_agent,
            "timecode": timecode,
            "values": deepcopy(values),
            "context": context,
        }

        if metadata is not None:
            message["metadata"] = deepcopy(metadata)

        self.validate_message(message)

        return message

    def validate_message(
        self,
        message: dict[str, Any],
        allowed_dimensions: tuple[str, ...] | None = None,
    ) -> None:
        """
        Validate a numerical ITP message.

        Args:
            message: Message to validate.
            allowed_dimensions: Optional dimension restriction for a specific model.

        Returns:
        """

        required_keys = (
            "schema_version",
            "source_agent",
            "target_agent",
            "timecode",
            "values",
            "context",
        )

        missing_keys = [key for key in required_keys if key not in message]

        if missing_keys:
            raise ValueError(f"Missing message keys: {missing_keys}")

        if message["schema_version"] != self.schema_version:
            raise ValueError(f"Unsupported schema version: {message['schema_version']}")

        if not isinstance(message["source_agent"], str):
            raise TypeError("source_agent must be a string.")

        if not isinstance(message["target_agent"], str):
            raise TypeError("target_agent must be a string.")

        if not isinstance(message["timecode"], dict):
            raise TypeError("timecode must be a dictionary.")

        if not message["timecode"]:
            raise ValueError("timecode must not be empty.")

        if not isinstance(message["values"], dict):
            raise TypeError("values must be a dictionary.")

        if not message["values"]:
            raise ValueError("values must contain at least one numerical value.")

        dimensions = allowed_dimensions or self.allowed_dimensions
        unknown_dimensions = set(message["values"]) - set(dimensions)

        if unknown_dimensions:
            raise ValueError(f"Unknown or unsupported dimensions: {unknown_dimensions}")

        for dimension, value in message["values"].items():
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"Value for {dimension} must be numeric.")

        if not isinstance(message["context"], str):
            raise TypeError("context must be a string.")

        if not message["context"]:
            raise ValueError("context must not be empty.")

        if "metadata" in message and not isinstance(message["metadata"], dict):
            raise TypeError("metadata must be a dictionary.")

        json.dumps(message)

    def from_json(self, source: str | Path) -> dict[str, Any]:
        """
        Load a numerical ITP message from a JSON string or JSON file.

        Args:
            source: JSON string or path to a JSON file.

        Returns:
            Numerical ITP message.
        """

        if isinstance(source, Path):
            message = json.loads(source.read_text(encoding="utf-8"))
            self.validate_message(message)
            return message

        stripped_source = source.lstrip()

        if stripped_source.startswith("{"):
            message = json.loads(source)
            self.validate_message(message)
            return message

        path = Path(source)
        message = json.loads(path.read_text(encoding="utf-8"))

        self.validate_message(message)

        return message

    def to_json(
        self,
        message: dict[str, Any],
        indent: int = 4,
    ) -> str:
        """
        Convert a numerical ITP message to JSON.

        Args:
            message: Numerical ITP message.
            indent: Number of spaces used for JSON indentation.

        Returns:
            JSON representation of the numerical ITP message.
        """

        self.validate_message(message)

        return json.dumps(message, indent=indent)

    def save_json(
        self,
        message: dict[str, Any],
        path: str | Path,
        indent: int = 4,
    ) -> None:
        """
        Save a numerical ITP message to a JSON file.

        Args:
            message: Numerical ITP message.
            path: Path to the JSON file.
            indent: Number of spaces used for JSON indentation.

        Returns:
        """

        path = Path(path)
        json_text = self.to_json(message, indent=indent)

        path.write_text(json_text, encoding="utf-8")