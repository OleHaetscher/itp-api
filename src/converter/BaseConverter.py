from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any


class BaseConverter(ABC):
    """
    Base class for converters between interpersonal state spaces.

    Args:

    Returns:
    """

    @abstractmethod
    def __init__(self) -> None:
        """
        Initialize the converter.

        Args:

        Returns:
        """

        pass

    @abstractmethod
    def convert(
        self,
        source_input: dict[str, float],
        context: str | None = None,
    ) -> dict[str, float]:
        """
        Convert source values into target values.

        Args:
            source_input: Numerical values in the source state space.
            context: Optional string describing the interaction context.

        Returns:
            Numerical values in the target state space.
        """

        pass

    def convert_message(
        self,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Convert the values block of an ITP message.

        Args:
            message: Numerical ITP message.

        Returns:
            Numerical ITP message with converted values.
        """

        self.validate_converter_interface()

        if message["values"]["state_space"] != self.source:
            raise ValueError("Message values do not match converter source.")

        if message["target_agent"]["state_space"] != self.target:
            raise ValueError("Message target does not match converter target.")

        if message["values"]["analysis_unit"] != message["target_agent"]["analysis_unit"]:
            raise ValueError("Analysis unit conversion is not implemented yet.")

        converted_message = deepcopy(message)

        converted_message["values"]["state_space"] = self.target
        converted_message["values"]["analysis_unit"] = message["target_agent"][
            "analysis_unit"
        ]
        converted_message["values"]["data"] = self.convert(
            source_input=message["values"]["data"],
            context=message["context"],
        )

        metadata = converted_message.get("metadata", {})
        metadata["message_type"] = "converted"
        metadata["conversion"] = {
            "converter": self.__class__.__name__,
            "from_state_space": self.source,
            "to_state_space": self.target,
            "from_analysis_unit": message["values"]["analysis_unit"],
            "to_analysis_unit": message["target_agent"]["analysis_unit"],
        }
        converted_message["metadata"] = metadata

        return converted_message

    def describe(self) -> str:
        """
        Return a short human-readable description of the conversion direction.

        Args:

        Returns:
            Description of the form "source -> target".
        """

        self.validate_converter_interface()

        return f"{self.source} -> {self.target}"

    def validate_converter_interface(self) -> None:
        """
        Validate that the converter exposes required shared attributes.

        Args:

        Returns:
        """

        required_attributes = ("source", "target")

        for attribute in required_attributes:
            if not hasattr(self, attribute):
                raise AttributeError(
                    f"Missing required converter attribute: {attribute}"
                )

        if not isinstance(self.source, str):
            raise TypeError("source must be a string.")

        if not isinstance(self.target, str):
            raise TypeError("target must be a string.")

        if not self.source:
            raise ValueError("source must not be empty.")

        if not self.target:
            raise ValueError("target must not be empty.")