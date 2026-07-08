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
        schema_version: str = "0.2",
        allowed_dimensions: tuple[str, ...] | None = None,
    ) -> None:
        """
        Initialize the ITP communication specification.

        Args:
            schema_version: Version of the message schema.
            allowed_dimensions: Optional dimensions allowed in numerical messages.

        Returns:
        """

        self.schema_version = schema_version
        self.allowed_dimensions = allowed_dimensions

    def make_message(
        self,
        source_agent: dict[str, str],
        target_agent: dict[str, str],
        timecode: dict[str, Any],
        values: dict[str, Any],
        context: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a valid numerical ITP message.

        Args:
            source_agent: Agent producing the message.
            target_agent: Agent receiving the message.
            timecode: Time information for the message.
            values: Numerical values carried by the message.
            context: String describing the interaction context.
            metadata: Optional additional information.

        Returns:
            Numerical ITP message.
        """

        message = {
            "schema_version": self.schema_version,
            "source_agent": deepcopy(source_agent),
            "target_agent": deepcopy(target_agent),
            "timecode": deepcopy(timecode),
            "values": deepcopy(values),
            "context": context,
        }

        if metadata is not None:
            message["metadata"] = deepcopy(metadata)

        self.validate_message(message)

        return message

    def make_agent(
        self,
        agent_id: str,
        state_space: str,
        analysis_unit: str,
    ) -> dict[str, str]:
        """
        Create an ITP agent description.

        Args:
            agent_id: Identifier of the agent.
            state_space: State space used by the agent.
            analysis_unit: Analysis unit used by the agent.

        Returns:
            ITP agent description.
        """

        return {
            "id": agent_id,
            "state_space": state_space,
            "analysis_unit": analysis_unit,
        }

    def make_values(
        self,
        state_space: str,
        analysis_unit: str,
        data: dict[str, float],
    ) -> dict[str, Any]:
        """
        Create an ITP values block.

        Args:
            state_space: State space used by the values.
            analysis_unit: Analysis unit used by the values.
            data: Numerical values.

        Returns:
            ITP values block.
        """

        return {
            "state_space": state_space,
            "analysis_unit": analysis_unit,
            "data": deepcopy(data),
        }

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

        self.validate_agent(message["source_agent"], "source_agent")
        self.validate_agent(message["target_agent"], "target_agent")
        self.validate_timecode(message["timecode"])
        self.validate_values(
            values=message["values"],
            allowed_dimensions=allowed_dimensions,
        )

        if not isinstance(message["context"], str):
            raise TypeError("context must be a string.")

        if not message["context"]:
            raise ValueError("context must not be empty.")

        if "metadata" in message and not isinstance(message["metadata"], dict):
            raise TypeError("metadata must be a dictionary.")

        json.dumps(message)

    def validate_agent(
        self,
        agent: dict[str, Any],
        field_name: str,
    ) -> None:
        """
        Validate an ITP agent description.

        Args:
            agent: Agent description.
            field_name: Name of the message field containing the agent.

        Returns:
        """

        if not isinstance(agent, dict):
            raise TypeError(f"{field_name} must be a dictionary.")

        required_keys = ("id", "state_space", "analysis_unit")
        missing_keys = [key for key in required_keys if key not in agent]

        if missing_keys:
            raise ValueError(f"Missing {field_name} keys: {missing_keys}")

        for key in required_keys:
            if not isinstance(agent[key], str):
                raise TypeError(f"{field_name}.{key} must be a string.")

            if not agent[key]:
                raise ValueError(f"{field_name}.{key} must not be empty.")

    def validate_timecode(
        self,
        timecode: dict[str, Any],
    ) -> None:
        """
        Validate an ITP timecode.

        Args:
            timecode: Time information for the message.

        Returns:
        """

        if not isinstance(timecode, dict):
            raise TypeError("timecode must be a dictionary.")

        if not timecode:
            raise ValueError("timecode must not be empty.")

    def validate_values(
        self,
        values: dict[str, Any],
        allowed_dimensions: tuple[str, ...] | None = None,
    ) -> None:
        """
        Validate an ITP values block.

        Args:
            values: Values block.
            allowed_dimensions: Optional allowed dimensions.

        Returns:
        """

        if not isinstance(values, dict):
            raise TypeError("values must be a dictionary.")

        required_keys = ("state_space", "analysis_unit", "data")
        missing_keys = [key for key in required_keys if key not in values]

        if missing_keys:
            raise ValueError(f"Missing values keys: {missing_keys}")

        if not isinstance(values["state_space"], str):
            raise TypeError("values.state_space must be a string.")

        if not values["state_space"]:
            raise ValueError("values.state_space must not be empty.")

        if not isinstance(values["analysis_unit"], str):
            raise TypeError("values.analysis_unit must be a string.")

        if not values["analysis_unit"]:
            raise ValueError("values.analysis_unit must not be empty.")

        if not isinstance(values["data"], dict):
            raise TypeError("values.data must be a dictionary.")

        if not values["data"]:
            raise ValueError("values.data must contain at least one numerical value.")

        dimensions = allowed_dimensions or self.allowed_dimensions

        if dimensions is not None:
            unknown_dimensions = set(values["data"]) - set(dimensions)

            if unknown_dimensions:
                raise ValueError(
                    f"Unknown or unsupported dimensions: {unknown_dimensions}"
                )

        for dimension, value in values["data"].items():
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"Value for {dimension} must be numeric.")

    def from_json(
        self,
        source: str | Path,
    ) -> dict[str, Any]:
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