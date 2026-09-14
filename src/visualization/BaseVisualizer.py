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

    Style follows the PerTRAIN design system, so a screenshot from a dashboard
    sits beside the homepage, the mock client and a slide without looking like
    a different project: neutral light surfaces, one blue for primary elements,
    green and amber for the remaining roles, and the two axis colours agreed
    for agency-communion figures. Type is the system sans stack rather than the
    brand's Sofia Sans and Inter, so that no font binaries have to live in this
    repository and nothing is fetched from a third party.

    Args:

    Returns:
    """

    # Neutral surfaces and text.
    BACKGROUND = "#FAFAFA"
    PANEL = "#FFFFFF"
    SUBTLE = "#F3F4F6"
    GRID = "#E5E7EB"
    TEXT = "#1F2937"
    BODY = "#374151"
    MUTED = "#6B7280"

    # The brand palette. Blue is research and anything primary, green is
    # application, amber is what belongs to neither. The values are the
    # text-safe variants where the raw brand tone does not reach AA as type.
    PRIMARY = "#2C6BB5"
    SCIENCE = "#3B82D6"
    APPLICATION = "#159570"
    CROSS = "#D68A1F"

    # The agreed agency-communion pair for scientific figures: a different hue
    # each, agency deliberately the darker of the two, both used as solid
    # areas. See docs/img.png.
    AGENCY = "#315A7D"
    COMMUNION = "#B84650"

    # Roles inside one update figure, named after what they mean rather than
    # what they look like, and pointed at the palette above so that a colour
    # has one home. The state an axis is in *now* is not here: it takes the
    # colour of its own axis, which the figure sets.
    PRIOR = MUTED
    DEFAULT = CROSS
    PARTNER = APPLICATION
    ACCENT = PRIMARY

    # Sequential scale for any dashboard that draws a matrix or a density.
    COLORSCALE = "Blues"

    FONT = (
        "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, system-ui, "
        "sans-serif"
    )
    MONO = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"

    RADIUS = "10px"
    SHADOW = "0 1px 2px 0 rgba(31, 41, 55, 0.05)"

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
                    "color": self.SCIENCE,
                    "fontSize": "13px",
                    "fontWeight": "600",
                    "letterSpacing": "0.08em",
                    "textTransform": "uppercase",
                },
            ),
            html.Div(
                self.title,
                style={
                    "color": self.TEXT,
                    "fontSize": "34px",
                    "fontWeight": "700",
                    "letterSpacing": "-0.02em",
                    "lineHeight": "1.15",
                    "margin": "6px 0 8px",
                },
            ),
            html.Div(
                self.description,
                style={
                    "color": self.MUTED,
                    "fontSize": "15px",
                    "maxWidth": "88ch",
                    "lineHeight": "1.55",
                },
            ),
        ]

        return html.Div(
            [
                html.Div(header, style={"marginBottom": "24px"}),
                self.build_body(),
            ],
            style={
                "backgroundColor": self.BACKGROUND,
                "minHeight": "100vh",
                "padding": "34px 28px 56px",
                "fontFamily": self.FONT,
                "color": self.BODY,
                "WebkitFontSmoothing": "antialiased",
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
                font=dict(color=self.TEXT, size=17, family=self.FONT, weight=600),
                x=0.01,
                y=0.97,
            ),
            paper_bgcolor=self.PANEL,
            plot_bgcolor=self.PANEL,
            font=dict(color=self.BODY, family=self.FONT, size=14),
            margin=dict(l=56, r=20, t=52, b=50),
        )

        if height:
            figure.update_layout(height=height)

        axis_style = dict(
            gridcolor=self.GRID,
            zerolinecolor=self.GRID,
            linecolor=self.GRID,
            color=self.MUTED,
            title_font=dict(size=13, color=self.MUTED),
            tickfont=dict(size=13, color=self.MUTED),
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
                "padding": "20px 22px 24px",
                "borderRadius": self.RADIUS,
                "border": f"1px solid {self.GRID}",
                "boxShadow": self.SHADOW,
            },
        )

    def graph(
        self,
        graph_id: str,
        style: dict[str, str] | None = None,
    ) -> dcc.Graph:
        """
        Create a graph without the plotly mode bar, inside a styled panel.

        Args:
            graph_id: Identifier of the graph.
            style: Optional CSS style of the graph.

        Returns:
            Dash component holding the graph.
        """

        return html.Div(
            dcc.Graph(
                id=graph_id,
                config={"displayModeBar": False},
                style=style or {},
            ),
            style={
                "backgroundColor": self.PANEL,
                "borderRadius": self.RADIUS,
                "border": f"1px solid {self.GRID}",
                "boxShadow": self.SHADOW,
                "padding": "6px 8px",
                "overflow": "hidden",
            },
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
                        "fontSize": "13px",
                        "fontWeight": "600",
                        "display": "block",
                        "marginBottom": "2px",
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
            style={"marginBottom": "26px"},
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
                "color": self.TEXT,
                "fontSize": "16px",
                "fontWeight": "600",
                "letterSpacing": "-0.01em",
                "marginBottom": "16px",
                "paddingBottom": "10px",
                "borderBottom": f"1px solid {self.GRID}",
            },
        )

    def caption(
        self,
        entries: dict[str, str],
    ) -> html.Div:
        """
        Create a block of label and value pairs.

        Args:
            entries: Mapping of labels to values.

        Returns:
            Dash component holding the label and value pairs.
        """

        rows = []

        for label, value in entries.items():
            rows.append(
                html.Div(
                    [
                        html.Span(
                            label,
                            style={"color": self.MUTED, "fontSize": "13px"},
                        ),
                        html.Span(
                            value,
                            style={
                                "color": self.TEXT,
                                "fontSize": "13px",
                                "fontFamily": self.MONO,
                                "textAlign": "right",
                            },
                        ),
                    ],
                    style={
                        "display": "flex",
                        "justifyContent": "space-between",
                        "gap": "14px",
                        "padding": "3px 0",
                    },
                )
            )

        return html.Div(rows, style={"lineHeight": "1.5"})

    def tint(
        self,
        color: str,
        opacity: float,
    ) -> str:
        """
        Turn a hex color into a translucent fill of the same hue.

        Used where a trace should stay recognizably in the colour of its axis
        without competing with the solid mark of the same colour.

        Args:
            color: Color as a six-digit hex string.
            opacity: Opacity between 0 and 1.

        Returns:
            Color as an rgba string.
        """

        hex_digits = color.lstrip("#")

        red, green, blue = (
            int(hex_digits[position : position + 2], 16) for position in (0, 2, 4)
        )

        return f"rgba({red}, {green}, {blue}, {opacity})"

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
