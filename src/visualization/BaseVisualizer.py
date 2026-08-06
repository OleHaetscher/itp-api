from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import plotly.graph_objects as go
from dash import Dash, dcc, html


class BaseVisualizer(ABC):
    """
    Base class for ITP dashboards.

    A visualizer takes one input source and renders it as a Dash dashboard.
    The source is either a formal model without any interaction data, or a
    sequence of ITP messages describing an interaction trajectory.

    This class owns everything shared between dashboards: the unified style,
    the page scaffolding and the Dash hosting. Subclasses declare what their
    source is (validate_source), what the page shows (build_body) and how it
    reacts to input (register_callbacks).

    Args:

    Returns:
    """

    BACKGROUND = "#0E1A2B"
    PANEL = "#15263B"
    GRID = "#2A3F59"
    ACCENT = "#1ABC9C"
    TEXT = "#FFFFFF"
    MUTED = "#9FB3C8"

    PRIOR = "#5B7794"
    POSTERIOR = "#1ABC9C"
    PARTNER = "#C0568A"
    DEFAULT = "#E8A33D"
    SHADED = "rgba(26,188,156,0.08)"
    COLORSCALE = "Viridis"

    FONT = "Georgia, 'Times New Roman', serif"

    def __init__(
        self,
        source: Any,
        title: str,
        subtitle: str = "",
        description: str = "",
        host: str = "127.0.0.1",
        port: int = 8050,
    ) -> None:
        """
        Initialize a visualizer and build its dashboard.

        Args:
            source: Input rendered by the dashboard.
            title: Title of the dashboard.
            subtitle: Optional line shown above the title.
            description: Optional line shown below the title.
            host: Host the dashboard is served on.
            port: Port the dashboard is served on.

        Returns:
        """

        self.source = self.validate_source(source=source)

        self.title = title
        self.subtitle = subtitle
        self.description = description
        self.host = host
        self.port = port

        self.app = Dash(__name__)
        self.app.title = title
        self.app.layout = self.build_page()

        self.register_callbacks()

    @abstractmethod
    def validate_source(
        self,
        source: Any,
    ) -> Any:
        """
        Validate the input source of the dashboard.

        Args:
            source: Input rendered by the dashboard.

        Returns:
            Validated input source.
        """

        pass

    @abstractmethod
    def build_body(
        self,
    ) -> Any:
        """
        Build the dashboard content shown below the page header.

        Args:

        Returns:
            Dash component holding the dashboard content.
        """

        pass

    def register_callbacks(
        self,
    ) -> None:
        """
        Register the Dash callbacks of the dashboard.

        Static dashboards need no callbacks, so this does nothing by default.

        Args:

        Returns:
        """

        pass

    def build_page(
        self,
    ) -> html.Div:
        """
        Build the full page, consisting of a header and the dashboard content.

        Args:

        Returns:
            Dash component holding the page.
        """

        header = [
            html.Div(
                self.subtitle,
                style={
                    "color": self.MUTED,
                    "fontStyle": "italic",
                    "fontSize": "22px",
                },
            ),
            html.Div(
                self.title,
                style={
                    "color": self.TEXT,
                    "fontSize": "42px",
                    "fontWeight": "bold",
                    "marginBottom": "6px",
                },
            ),
            html.Div(
                self.description,
                style={"color": self.MUTED, "fontSize": "16px"},
            ),
        ]

        return html.Div(
            [
                html.Div(header, style={"marginBottom": "18px"}),
                self.build_body(),
            ],
            style={
                "backgroundColor": self.BACKGROUND,
                "minHeight": "100vh",
                "padding": "26px 32px",
                "fontFamily": self.FONT,
            },
        )

    def style_figure(
        self,
        figure: go.Figure,
        title: str,
        height: int | None = None,
    ) -> go.Figure:
        """
        Apply the shared dashboard style to a figure.

        Args:
            figure: Figure to style.
            title: Title of the figure.
            height: Optional fixed figure height in pixels.

        Returns:
            Styled figure.
        """

        figure.update_layout(
            title=dict(
                text=title,
                font=dict(color=self.TEXT, size=20, family=self.FONT),
                x=0.02,
            ),
            paper_bgcolor=self.BACKGROUND,
            plot_bgcolor=self.PANEL,
            font=dict(color=self.MUTED, family=self.FONT, size=16),
            margin=dict(l=58, r=18, t=46, b=52),
        )

        if height:
            figure.update_layout(height=height)

        axis_style = dict(
            gridcolor=self.GRID,
            zerolinecolor=self.GRID,
            linecolor=self.GRID,
            color=self.MUTED,
            title_font=dict(size=16),
            tickfont=dict(size=14),
        )

        figure.update_xaxes(**axis_style)
        figure.update_yaxes(**axis_style)

        return figure

    def panel(
        self,
        children: Any,
    ) -> html.Div:
        """
        Wrap components in a styled panel.

        Args:
            children: Components shown inside the panel.

        Returns:
            Dash component holding the panel.
        """

        return html.Div(
            children,
            style={
                "backgroundColor": self.PANEL,
                "padding": "22px",
                "borderRadius": "10px",
                "border": f"1px solid {self.GRID}",
            },
        )

    def graph(
        self,
        graph_id: str,
        style: dict[str, str] | None = None,
    ) -> dcc.Graph:
        """
        Create a graph without the plotly mode bar.

        Args:
            graph_id: Identifier of the graph.
            style: Optional CSS style of the graph.

        Returns:
            Dash graph component.
        """

        return dcc.Graph(
            id=graph_id,
            config={"displayModeBar": False},
            style=style or {},
        )

    def slider(
        self,
        label: str,
        slider_id: str,
        minimum: float,
        maximum: float,
        step: float,
        value: float,
        marks: dict[float, str] | None = None,
    ) -> html.Div:
        """
        Create a labeled slider.

        Args:
            label: Label shown above the slider.
            slider_id: Identifier of the slider.
            minimum: Smallest slider value.
            maximum: Largest slider value.
            step: Step between slider values.
            value: Initial slider value.
            marks: Optional marks shown below the slider.

        Returns:
            Dash component holding the labeled slider.
        """

        return html.Div(
            [
                html.Label(
                    label,
                    style={
                        "color": self.TEXT,
                        "fontSize": "16px",
                        "fontWeight": "bold",
                        "display": "block",
                        "marginBottom": "4px",
                    },
                ),
                dcc.Slider(
                    id=slider_id,
                    min=minimum,
                    max=maximum,
                    step=step,
                    value=value,
                    marks=marks or {},
                    tooltip={"placement": "bottom", "always_visible": True},
                ),
            ],
            style={"marginBottom": "24px"},
        )

    def heading(
        self,
        text: str,
    ) -> html.Div:
        """
        Create a section heading.

        Args:
            text: Text of the heading.

        Returns:
            Dash component holding the heading.
        """

        return html.Div(
            text,
            style={
                "color": self.ACCENT,
                "fontSize": "22px",
                "fontWeight": "bold",
                "marginBottom": "16px",
            },
        )

    def caption(
        self,
        entries: dict[str, str],
    ) -> html.Div:
        """
        Create a block of muted label and value pairs.

        Args:
            entries: Mapping of labels to values.

        Returns:
            Dash component holding the label and value pairs.
        """

        lines = []

        for label, value in entries.items():
            lines.append(html.Span(f"{label}: ", style={"color": self.MUTED}))
            lines.append(html.Span(value, style={"color": self.TEXT}))
            lines.append(html.Br())

        return html.Div(
            lines,
            style={"fontSize": "14px", "lineHeight": "1.9"},
        )

    def run(
        self,
        debug: bool = False,
    ) -> None:
        """
        Serve the dashboard.

        Args:
            debug: Whether to run the Dash app in debug mode.

        Returns:
        """

        print(f"\n  {self.title}  ->  http://{self.host}:{self.port}\n")

        self.app.run(host=self.host, port=self.port, debug=debug)
