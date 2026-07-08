from __future__ import annotations

from typing import Any

from src.converter.BaseConverter import BaseConverter
from src.converter.StateSpaceConverters import (
    ACToIPCConverter,
    IPCToACConverter,
    IPCToSASBConverter,
    SASBToIPCConverter,
)


class ConverterRegistry:
    """
    Registry for converters between interpersonal state spaces.

    Args:

    Returns:
    """

    def __init__(
        self,
    ) -> None:
        """
        Initialize the converter registry.

        Args:

        Returns:
        """

        self.converters: dict[tuple[str, str], BaseConverter] = {}

    def register(
        self,
        converter: BaseConverter,
    ) -> None:
        """
        Register a converter.

        Args:
            converter: Converter to register.

        Returns:
        """

        converter.validate_converter_interface()

        self.converters[(converter.source, converter.target)] = converter

    def get_converter(
        self,
        source: str,
        target: str,
    ) -> BaseConverter:
        """
        Return a registered converter.

        Args:
            source: Source state space.
            target: Target state space.

        Returns:
            Registered converter.
        """

        key = (source, target)

        if key not in self.converters:
            raise ValueError(f"No converter registered for {source} -> {target}.")

        return self.converters[key]

    def needs_conversion(
        self,
        message: dict[str, Any],
    ) -> bool:
        """
        Check whether an ITP message requires conversion.

        Args:
            message: Numerical ITP message.

        Returns:
            Whether the message requires conversion.
        """

        return (
            message["values"]["state_space"] != message["target_agent"]["state_space"]
            or message["values"]["analysis_unit"]
            != message["target_agent"]["analysis_unit"]
        )

    def convert_message(
        self,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Convert an ITP message if needed.

        Args:
            message: Numerical ITP message.

        Returns:
            Converted numerical ITP message.
        """

        if not self.needs_conversion(message):
            return message

        if message["values"]["analysis_unit"] != message["target_agent"]["analysis_unit"]:
            raise ValueError("Analysis unit conversion is not implemented yet.")

        source = message["values"]["state_space"]
        target = message["target_agent"]["state_space"]

        converter = self.get_converter(
            source=source,
            target=target,
        )

        return converter.convert_message(message)


def make_default_converter_registry() -> ConverterRegistry:
    """
    Create a converter registry with default converters.

    Args:

    Returns:
        Converter registry.
    """

    registry = ConverterRegistry()

    registry.register(ACToIPCConverter())
    registry.register(IPCToACConverter())
    registry.register(SASBToIPCConverter())
    registry.register(IPCToSASBConverter())

    return registry