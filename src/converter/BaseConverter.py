from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseConverter(ABC):
    """
    Base class for converters between different interpersonal formal models.

    A converter translates a representation produced by one formal model into a
    representation that another formal model, or a shared neutral representation,
    can consume. Two kinds of conversion are anticipated:

    1. Framework-level mapping: relating the dimensions of two interpersonal
       frameworks (e.g. mapping affiliative approach and avoidance motives onto
       the positive and negative pole of communion).
    2. Model-level mapping: relating two whole formal models whose state spaces
       differ in structure (e.g. mapping a monadic, per-agent representation onto
       a dyadic, shared relational state space).

    Subclasses implement the actual conversion in `convert`. The base class only
    fixes the shared interface and light provenance, namely which framework or
    model a converter maps from (`source`) and to (`target`).

    Args:

    Returns:
    """

    @abstractmethod
    def __init__(self) -> None:
        """
        Initialize the converter.

        Subclasses are expected to set `source` and `target` to short strings
        identifying the framework or model they convert from and to.

        Args:

        Returns:
        """

        pass

    @abstractmethod
    def convert(
        self,
        source_input: Any,
        context: str | None = None,
    ) -> Any:
        """
        Convert a source representation into the target representation. Must be implemented by the subclass.

        Args:
            source_input: Representation produced by the source model.
            context: Optional string describing the interaction context.

        Returns:
            Representation consumable by the target model.
        """

        pass

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