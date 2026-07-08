from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.ITPSpecification import ITPSpecification
from src.interactioncontext import InteractionContext


class Communication:
    """
    ITP communication session between named agents.
    Note: The Communication class is agnostid regarding the ITP's message sender. This may be
    - a local formal model agent
    - a remote formal model agent
    - a human user

    Attributes:
        specification: ITPSpecification (class attribute)

    """

    specification = ITPSpecification()

    def __init__(
        self,
        context: InteractionContext | str,
    ) -> None:
        """
        Initialize an ITP communication session.

        Args:
            context: Interaction context of the communication.

        Returns:
        """

        self.context = context
        self.behavior_state_space = None
        self.messages: list[dict[str, Any]] = []

    @property
    def context_name(self) -> str:
        """
        Return the name of the interaction context.

        Args:

        Returns:
            Name of the interaction context.
        """

        if isinstance(self.context, str):
            return self.context

        return self.context.context_name

    @property
    def last_message(self) -> dict[str, Any] | None:
        """
        Return the last message in the communication.

        Args:

        Returns:
            Last message in the communication.
        """

        if not self.messages:
            return None

        return self.messages[-1]

    @property
    def n_messages(self) -> int:
        """
        Return the number of stored messages.

        Args:

        Returns:
            Number of stored messages.
        """

        return len(self.messages)

    def make_message(
        self,
        source_agent: str,
        target_agent: str,
        timecode: dict[str, Any],
        values: dict[str, float],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a numerical ITP message.

        Args:
            source_agent: Identifier of the sending agent.
            target_agent: Identifier of the receiving agent.
            timecode: Time information for the message.
            values: Numerical values carried by the message.
            metadata: Optional additional information.

        Returns:
            Numerical ITP message.
        """

        message = self.specification.make_message(
            source_agent=source_agent,
            target_agent=target_agent,
            timecode=timecode,
            values=values,
            context=self.context_name,
            metadata=metadata,
        )

        return message

    def receive_message(
        self,
        message: dict[str, Any],
    ) -> None:
        """
        Receive and store a numerical ITP message.

        Args:
            message: Numerical ITP message.

        Returns:
        """

        self.specification.validate_message(message)
        self.messages.append(deepcopy(message))

    def create_and_receive_message(
        self,
        source_agent: str,
        target_agent: str,
        timecode: dict[str, Any],
        values: dict[str, float],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create, validate, and store a numerical ITP message.

        Args:
            source_agent: Identifier of the sending agent.
            target_agent: Identifier of the receiving agent.
            timecode: Time information for the message.
            values: Numerical values carried by the message.
            metadata: Optional additional information.

        Returns:
            Numerical ITP message.
        """

        message = self.make_message(
            source_agent=source_agent,
            target_agent=target_agent,
            timecode=timecode,
            values=values,
            metadata=metadata,
        )

        self.receive_message(message)

        return message

    def make_next_timecode(
        self,
        timestamp: str,
    ) -> dict[str, Any]:
        """
        Create a timecode for the next message.

        Args:
            timestamp: Timestamp of the message.

        Returns:
            Timecode for the next message.
        """

        return {
            "timestamp": timestamp,
            "interaction_turn": self.n_messages + 1,
        }

    def get_messages(
        self,
    ) -> list[dict[str, Any]]:
        """
        Return stored messages.

        Args:

        Returns:
            Stored messages.
        """

        return deepcopy(self.messages)