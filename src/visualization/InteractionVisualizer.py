from __future__ import annotations

from typing import Any

from src.ITPSpecification import ITPSpecification
from src.visualization.BaseVisualizer import BaseVisualizer

# TODO OH: Build the trajectory dashboard on top of trajectories().


class InteractionVisualizer(BaseVisualizer):
    """
    Base class for dashboards that visualize an interaction trajectory.

    The dashboard is built from a sequence of ITP messages, for example the
    messages stored in a Communication session, and shows how the exchanged
    values develop over the interaction.

    Args:

    Returns:
    """

    specification = ITPSpecification()

    def validate_source(
        self,
        source: Any,
    ) -> list[dict[str, Any]]:
        """
        Validate the ITP messages rendered by the dashboard.

        Args:
            source: ITP messages rendered by the dashboard.

        Returns:
            Validated ITP messages.
        """

        messages = list(source)

        if not messages:
            raise ValueError("InteractionVisualizer requires at least one message.")

        for message in messages:
            self.specification.validate_message(message=message)

        return messages

    @property
    def messages(
        self,
    ) -> list[dict[str, Any]]:
        """
        Return the visualized ITP messages.

        Args:

        Returns:
            Visualized ITP messages.
        """

        return self.source

    def trajectories(
        self,
        agent_id: str | None = None,
    ) -> dict[str, list[float]]:
        """
        Collect the value trajectory of every dimension.

        Args:
            agent_id: Optional identifier restricting the trajectory to one
                sending agent.

        Returns:
            Dictionary mapping dimensions to their values over the interaction.
        """

        trajectories: dict[str, list[float]] = {}

        for message in self.messages:
            if agent_id is not None and message["source_agent"]["id"] != agent_id:
                continue

            for dimension, value in message["values"]["data"].items():
                trajectories.setdefault(dimension, []).append(value)

        return trajectories

    def build_body(
        self,
    ) -> Any:
        """
        Build the dashboard content shown below the page header.

        Args:

        Returns:
            Dash component holding the dashboard content.
        """

        raise NotImplementedError("The interaction dashboard is not implemented yet.")
