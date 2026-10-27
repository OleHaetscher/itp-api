from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from src.ITPSpecification import ITPSpecification
from src.interactioncontext.InteractionContext import InteractionContext


class Communication:
    """
    ITP communication session between named agents.

    The Communication class is agnostic regarding the ITP message sender.
    This may be a local formal model, a remote formal model, or a human user.

    Args:

    Returns:
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
        source_agent: dict[str, str],
        target_agent: dict[str, str],
        timecode: dict[str, Any],
        values: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a numerical ITP message.

        Args:
            source_agent: Agent producing the message.
            target_agent: Agent receiving the message.
            timecode: Time information for the message.
            values: Values carried by the message.
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
        source_agent: dict[str, str],
        target_agent: dict[str, str],
        timecode: dict[str, Any],
        values: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create, validate, and store a numerical ITP message.

        Args:
            source_agent: Agent producing the message.
            target_agent: Agent receiving the message.
            timecode: Time information for the message.
            values: Values carried by the message.
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

    def save_messages(
        self,
        root: str | Path = ".",
        folder: str | None = None,
    ) -> Path:
        """
        Save all stored ITP messages to a results folder.

        Args:
            root: Project root directory.
            folder: Name of the folder below results/. Defaults to a timestamp,
                which collides when two sessions end within the same second, so
                a caller that can have several in flight passes its own name.

        Returns:
            Path to the directory containing the saved messages.
        """

        if folder is None:
            folder = datetime.now().strftime("%Y%m%d_%H%M%S")

        output_dir = Path(root) / "results" / folder
        output_dir.mkdir(parents=True, exist_ok=True)

        for message_index, message in enumerate(self.messages, start=1):
            self.save_message(
                message=message,
                message_index=message_index,
                output_dir=output_dir,
            )

        return output_dir

    def save_message(
        self,
        message: dict[str, Any],
        message_index: int,
        output_dir: str | Path,
    ) -> Path:
        """
        Save one stored ITP message under the name save_messages gives it.

        Lets a caller write each message as it arrives, so a record survives a
        process that dies before the session ends.

        Args:
            message: Numerical ITP message.
            message_index: Position of the message in the session, from 1.
            output_dir: Existing directory the file is written to.

        Returns:
            Path of the written file.
        """

        path = Path(output_dir) / self._make_message_file_name(
            message=message,
            message_index=message_index,
        )

        self.specification.save_json(
            message=message,
            path=path,
        )

        return path

    def _make_message_file_name(
        self,
        message: dict[str, Any],
        message_index: int,
    ) -> str:
        """
        Create a file name for one stored ITP message.

        Args:
            message: Numerical ITP message.
            message_index: Sequential message index.

        Returns:
            File name.
        """

        source_agent = message["source_agent"]["id"]
        target_agent = message["target_agent"]["id"]
        message_type = message.get("metadata", {}).get("message_type", "original")

        return (
            f"message_{message_index:03d}_"
            f"{source_agent}_to_{target_agent}_"
            f"{message_type}.json"
        )