from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.visualization.BaseVisualizer import BaseVisualizer
from src.visualization.InteractionRecord import InteractionRecord

TEMPLATE_PATH = Path(__file__).parent / "templates" / "interaction_report.html"
DATA_PLACEHOLDER = "/*__ITP_REPORT_DATA__*/null"

# Panels the report can draw, in the order they are laid out.
PANELS = ("dialogue", "planes", "dimensions")

# Print widths in inches: a portrait page and a landscape page with 1 in
# margins. The figure is laid out for the width it is printed at.
PRINT_WIDTHS = {"portrait": 6.2, "landscape": 9.0}


class InteractionReport:
    """
    A self-contained HTML page that steps through one recorded interaction.

    The page is one file with no dependencies and nothing fetched, so it can be
    opened from disk, mailed, or attached to a paper as supplementary material.
    It draws the figure as SVG and exports what it shows at the selected turn
    as SVG or PNG, which makes the printed figure a frame of the supplement
    rather than a second rendering of the same data.

    Panels are independent: the dialogue (only when a dialogue file was
    attached), one plane per agent in its own state space with the partner's
    behavior as converted into it, and each dimension over turns. Colors come
    from BaseVisualizer, so the report matches the dashboards.

    Args:

    Returns:
    """

    def __init__(
        self,
        record: InteractionRecord,
        panels: tuple[str, ...] = PANELS,
        title: str = "",
        initial_turn: int | None = None,
        time_space: str | None = None,
        labels: dict[str, str] | None = None,
        print_width: float = PRINT_WIDTHS["portrait"],
    ) -> None:
        """
        Prepare a report of one interaction.

        Args:
            record: Recorded interaction.
            panels: Panels shown when the page opens; the reader can toggle
                them.
            title: Heading of the page.
            initial_turn: Turn shown when the page opens, the last by default.
            time_space: State space whose dimensions are drawn over turns,
                the agency-communion space if an agent speaks it.
            labels: Optional names of the agents by role, such as
                {"A": "IPC model"}; the model name, or "Human participant",
                otherwise.
            print_width: Width the figure is printed at, in inches; 6.2 for
                a portrait page, 9 for a landscape one. Font sizes stay the
                same in print, so a wider figure holds more per line.

        Returns:
        """

        unknown = [panel for panel in panels if panel not in PANELS]
        if unknown:
            raise ValueError(f"Unknown panels: {', '.join(unknown)}. Known: {', '.join(PANELS)}.")

        spaces = [agent["stateSpace"]["id"] for agent in record.agents.values()]
        if time_space is not None and time_space not in spaces:
            raise ValueError(f"No agent speaks {time_space}; the record has {', '.join(spaces)}.")

        labels = labels or {}
        unknown_roles = [role for role in labels if role not in record.agents]
        if unknown_roles:
            raise ValueError(f"No agent has the role {', '.join(unknown_roles)}.")

        last_turn = record.turns[-1]["turn"]
        if initial_turn is not None and not 1 <= initial_turn <= last_turn:
            raise ValueError(f"The record has turns 1 to {last_turn}, not {initial_turn}.")

        if not 4.0 <= print_width <= 12.0:
            raise ValueError(f"A print width of {print_width} in is not a page; use 4 to 12.")

        self.record = record
        self.print_width = print_width
        self.panels = tuple(panel for panel in PANELS if panel in panels)
        self.title = title or "ITP interaction report"
        self.initial_turn = initial_turn or last_turn
        self.time_space = time_space or ("ac" if "ac" in spaces else spaces[0])
        self.labels = {
            role: labels.get(role) or agent["model"] or "Human participant"
            for role, agent in record.agents.items()
        }

    def palette(
        self,
    ) -> dict[str, str]:
        """
        Collect the colors the page uses.

        The two agents take blue and amber, a pair that stays apart under the
        common color vision deficiencies. The agency and communion colors are
        not used for agents, because they are reserved for the axes.

        Args:

        Returns:
            Dictionary mapping roles of a color to hex values.
        """

        return {
            "background": BaseVisualizer.BACKGROUND,
            "panel": BaseVisualizer.PANEL,
            "subtle": BaseVisualizer.SUBTLE,
            "grid": BaseVisualizer.GRID,
            "text": BaseVisualizer.TEXT,
            "body": BaseVisualizer.BODY,
            "muted": BaseVisualizer.MUTED,
            "primary": BaseVisualizer.PRIMARY,
            "agentA": BaseVisualizer.PRIMARY,
            "agentB": BaseVisualizer.CROSS,
            "agency": BaseVisualizer.AGENCY,
            "communion": BaseVisualizer.COMMUNION,
        }

    def data(
        self,
    ) -> dict[str, Any]:
        """
        Collect the data embedded in the page.

        Args:

        Returns:
            Report data.
        """

        data = self.record.to_report_data()

        for role, agent in data["agents"].items():
            agent["label"] = self.labels[role]
        data.update(
            {
                "title": self.title,
                "panels": list(self.panels),
                "initialTurn": self.initial_turn,
                "timeSpace": self.time_space,
                "printWidth": self.print_width,
                "palette": self.palette(),
            }
        )

        return data

    def render(
        self,
    ) -> str:
        """
        Render the page.

        Args:

        Returns:
            HTML of the page.
        """

        template = TEMPLATE_PATH.read_text(encoding="utf-8")

        if template.count(DATA_PLACEHOLDER) != 1:
            raise ValueError(f"{TEMPLATE_PATH} must hold {DATA_PLACEHOLDER} exactly once.")

        # "</" would end the script element early if a text contained it.
        payload = json.dumps(self.data(), ensure_ascii=False).replace("</", "<\\/")

        return template.replace(DATA_PLACEHOLDER, payload)

    def write(
        self,
        path: str | Path,
    ) -> Path:
        """
        Write the page to disk.

        Args:
            path: Path of the HTML file.

        Returns:
            Path of the written file.
        """

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(), encoding="utf-8")

        return path
