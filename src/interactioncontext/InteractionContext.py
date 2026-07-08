from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class InteractionContext:
    """
    Interaction context with a context name and context attributes.

    Args:
        context_name: Name of the interaction context.
        attributes: Attributes describing the interaction context.

    Returns:
    """

    context_name: str
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def diamonds(self) -> dict[str, float]:
        """
        Return DIAMONDS values for the context.
        # TODO: Automate this? In case new contexts are added?

        Args:

        Returns:
            DIAMONDS values.
        """

        return self.attributes.get("diamonds", {})

    @classmethod
    def from_config_entry(
        cls,
        config_entry: dict[str, Any],
    ) -> InteractionContext:
        """
        Create an interaction context from one config entry.

        Args:
            config_entry: Config entry describing one interaction context.

        Returns:
            Interaction context.
        """

        context_name, attributes = next(iter(config_entry.items()))

        if attributes is None:
            attributes = {}

        return cls(
            context_name=context_name,
            attributes=attributes,
        )

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
    ) -> list[InteractionContext]:
        """
        Create interaction contexts from a config.

        Args:
            config: Config containing interaction contexts.

        Returns:
            Interaction contexts.
        """

        return [
            cls.from_config_entry(config_entry)
            for config_entry in config["context"]
        ]