from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html

from src.formalmodels.LASSIFormalModel import LASSIAxis
from src.visualization.FormalModelVisualizer import FormalModelVisualizer

# Identifiers of the parameter controls, in the order the callback expects them.
CONTROL_IDS = (
    "dimension",
    "num_states",
    "BD",
    "prior_mean",
    "w_BD",
    "IR",
    "w_C",
    "partner_state",
    "sigma",
)

# Controls that hold a state on the ITP scale, so their range follows N.
STATE_CONTROL_IDS = (
    "BD",
    "prior_mean",
    "partner_state",
)


def to_itp_scale(
    values: Any,
) -> np.ndarray:
    """
    Map internal 0-based grid values to the ITP 1-based scale.

    Args:
        values: Values on the internal grid.

    Returns:
        Values on the ITP scale.
    """

    return np.asarray(values, dtype=float) + 1.0


class LASSIFormalModelVisualizer(FormalModelVisualizer):
    """
    Interactive walk-through of one LASSI state distribution update.

    The dashboard shows the three steps of LASSIAxis.update_probabilities for a
    single axis: the drift computed from the behavioral default, the partner
    state and the reactivity, the transport kernel built from that drift, and
    the resulting update of the state distribution.

    The visualized model supplies the axes and their configured parameters,
    which become the initial slider values. Every callback then builds a
    throwaway axis from the current slider values, so the dashboard explores
    parameter variations without changing the model it was given.

    All sliders use the ITP 1-based scale, while the model works on the
    internal 0-based grid.

    Args:

    Returns:
    """

    # Poles of the ITP scale, used for the axis labels of the drift figure.
    AXIS_POLES = {
        "A": ("extreme submissive", "extreme dominant"),
        "C": ("extreme cold", "extreme warm"),
    }

    NUM_STATES_MIN = 3
    NUM_STATES_MAX = 15

    def __init__(
        self,
        model: Any,
        host: str = "127.0.0.1",
        port: int = 8050,
    ) -> None:
        """
        Initialize the LASSI dashboard.

        Args:
            model: LASSI formal model supplying axes and parameters.
            host: Host the dashboard is served on.
            port: Port the dashboard is served on.

        Returns:
        """

        super().__init__(
            source=model,
            title="State Distribution Updating",
            subtitle="Formale Modellierung",
            description=(
                "Interactive walk-through of  pₜ = p₍ₜ₋₁₎ · Kₜ  on one interpersonal "
                "axis. Drift is computed from BD, IR, w_BD, w_C and the partner's "
                "state, as in the model code."
            ),
            host=host,
            port=port,
        )

    def build_body(
        self,
    ) -> html.Div:
        """
        Build the three-column dashboard body.

        Args:

        Returns:
            Dash component holding the controls and the three figures.
        """

        return html.Div(
            [
                html.Div(
                    self.panel(self.build_controls()),
                    style={"flex": "0 0 340px"},
                ),
                html.Div(
                    [
                        html.Div(
                            self.graph("figure_drift"),
                            style={"marginBottom": "10px"},
                        ),
                        html.Div(self.graph("figure_kernel")),
                    ],
                    style={"flex": "1 1 0", "minWidth": "0"},
                ),
                html.Div(
                    self.graph("figure_update", style={"height": "100%"}),
                    style={
                        "flex": "1 1 0",
                        "minWidth": "0",
                        "display": "flex",
                        "alignItems": "stretch",
                    },
                ),
            ],
            style={"display": "flex", "gap": "18px", "alignItems": "flex-start"},
        )

    def build_controls(
        self,
    ) -> list[Any]:
        """
        Build the parameter controls, initialized from the model parameters.

        Args:

        Returns:
            Dash components holding the parameter controls.
        """

        dimension = self.model.dimensions[0]
        axis = self.model.axes[dimension]
        state_marks = self.state_marks(num_states=axis.num_states)

        return [
            self.heading("Parameters"),
            html.Div(
                [
                    html.Label(
                        "Axis",
                        style={
                            "color": self.TEXT,
                            "fontSize": "16px",
                            "fontWeight": "bold",
                            "display": "block",
                            "marginBottom": "6px",
                        },
                    ),
                    dcc.RadioItems(
                        id="dimension",
                        options=[
                            {
                                "label": f" {self.model.axes[name].name} ",
                                "value": name,
                            }
                            for name in self.model.dimensions
                        ],
                        value=dimension,
                        inline=True,
                        style={"color": self.TEXT, "fontSize": "16px"},
                    ),
                ],
                style={"marginBottom": "24px"},
            ),
            self.slider(
                label="BD — behavioral default",
                slider_id="BD",
                minimum=1,
                maximum=axis.num_states,
                step=1,
                value=float(to_itp_scale(axis.BD)),
                marks=state_marks,
            ),
            self.slider(
                label="E[S₍ₜ₋₁₎] — prior mean state",
                slider_id="prior_mean",
                minimum=1,
                maximum=axis.num_states,
                step=1,
                value=float(to_itp_scale(axis.midpoint)),
                marks=state_marks,
            ),
            self.slider(
                label="w_BD — behavioral-default weight",
                slider_id="w_BD",
                minimum=0.0,
                maximum=1.0,
                step=0.05,
                value=axis.w_BD,
            ),
            self.slider(
                label="IR — interpersonal reactivity",
                slider_id="IR",
                minimum=-1.0,
                maximum=2.0,
                step=0.1,
                value=axis.IR,
                marks={-1: "-1", 0: "0", 1: "1", 2: "2"},
            ),
            self.slider(
                label="w_C — complementarity weight",
                slider_id="w_C",
                minimum=0.0,
                maximum=1.0,
                step=0.05,
                value=axis.w_C,
            ),
            self.slider(
                label="s_other — partner's assessed state",
                slider_id="partner_state",
                minimum=1,
                maximum=axis.num_states,
                step=1,
                value=axis.num_states,
                marks=state_marks,
            ),
            self.slider(
                label="σ — kernel width",
                slider_id="sigma",
                minimum=0.1,
                maximum=2.0,
                step=0.1,
                value=axis.sigma,
            ),
            self.slider(
                label="N — number of discrete states (odd)",
                slider_id="num_states",
                minimum=self.NUM_STATES_MIN,
                maximum=self.NUM_STATES_MAX,
                step=2,
                value=axis.num_states,
                marks={3: "3", 7: "7", 11: "11", 15: "15"},
            ),
            html.Hr(style={"borderColor": self.GRID}),
            self.model_caption(),
            self.caption(
                {
                    "states shown": "1 … N on the ITP scale",
                    "clip bounds": "[1, N], locked to the grid",
                }
            ),
        ]

    def register_callbacks(
        self,
    ) -> None:
        """
        Register the callback that redraws the three figures.

        Args:

        Returns:
        """

        @self.app.callback(
            Output("figure_drift", "figure"),
            Output("figure_kernel", "figure"),
            Output("figure_update", "figure"),
            *[Input(control_id, "value") for control_id in CONTROL_IDS],
        )
        def update_figures(*control_values: Any) -> tuple[go.Figure, ...]:
            """
            Recompute one update step and redraw the figures.

            Args:
                control_values: Current values of the parameter controls.

            Returns:
                Drift, kernel and update figure.
            """

            record = self.compute_step(**dict(zip(CONTROL_IDS, control_values)))

            return (
                self.figure_drift(record=record),
                self.figure_kernel(record=record),
                self.figure_update(record=record),
            )

        @self.app.callback(
            *[
                Output(control_id, control_property)
                for control_id in STATE_CONTROL_IDS
                for control_property in ("max", "marks", "value")
            ],
            Input("num_states", "value"),
            *[State(control_id, "value") for control_id in STATE_CONTROL_IDS],
        )
        def update_state_controls(
            num_states: int,
            *state_values: float,
        ) -> tuple[Any, ...]:
            """
            Keep the state sliders inside the grid when N changes.

            Args:
                num_states: Current number of discrete states.
                state_values: Current values of the state sliders.

            Returns:
                Maximum, marks and value of every state slider.
            """

            num_states = int(num_states)
            marks = self.state_marks(num_states=num_states)

            updated_controls = []

            for value in state_values:
                updated_controls += [num_states, marks, min(value, num_states)]

            return tuple(updated_controls)

    def compute_step(
        self,
        dimension: str,
        num_states: int,
        BD: float,
        prior_mean: float,
        w_BD: float,
        IR: float,
        w_C: float,
        partner_state: float,
        sigma: float,
    ) -> dict[str, Any]:
        """
        Run one update step on a throwaway axis built from the control values.

        Args:
            dimension: Axis abbreviation.
            num_states: Number of discrete states.
            BD: Behavioral default on the ITP scale.
            prior_mean: Prior mean state on the ITP scale.
            w_BD: Weight of the behavioral-default pull.
            IR: Interpersonal reactivity.
            w_C: Weight of the complementarity increment.
            partner_state: Partner state on the ITP scale.
            sigma: Width of the bell prior and of the transport kernel.

        Returns:
            Step record of the update.
        """

        num_states = int(num_states)
        state_max = num_states - 1

        parameters = self.model.axes[dimension].parameters()
        parameters.update(
            num_states=num_states,
            BD=np.clip(BD - 1.0, 0.0, state_max),
            w_BD=w_BD,
            w_C=w_C,
            IR=IR,
            sigma=sigma,
        )

        axis = LASSIAxis(dimension=dimension, parameters=parameters)
        axis.set_state_dist_from_mean(mean=prior_mean - 1.0)
        axis.update_probabilities(
            partner_state=float(np.clip(partner_state - 1.0, 0.0, state_max)),
        )

        return axis.step_record()

    def figure_drift(
        self,
        record: dict[str, Any],
    ) -> go.Figure:
        """
        Draw the drift on the interpersonal axis.

        Args:
            record: Step record of the update.

        Returns:
            Drift figure.
        """

        grid = to_itp_scale(record["state_grid"])
        prior_mean = to_itp_scale(record["prior_mean_state_dist"])
        updated_mean = to_itp_scale(record["updated_mean_state_dist"])

        figure = go.Figure()

        figure.add_vrect(
            x0=grid[0],
            x1=grid[-1],
            fillcolor=self.SHADED,
            line_width=0,
            layer="below",
        )
        figure.add_trace(
            go.Scatter(
                x=[grid[0], grid[-1]],
                y=[0, 0],
                mode="lines",
                line=dict(color=self.GRID, width=2),
                showlegend=False,
                hoverinfo="skip",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=grid,
                y=np.zeros_like(grid),
                mode="markers",
                marker=dict(color=self.GRID, size=10, symbol="line-ns-open"),
                showlegend=False,
                hoverinfo="skip",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[to_itp_scale(record["midpoint"])],
                y=[0.55],
                mode="markers+text",
                marker=dict(color=self.MUTED, size=11, symbol="diamond"),
                text=["s̄"],
                textposition="top center",
                textfont=dict(color=self.MUTED, size=15),
                showlegend=False,
                hoverinfo="skip",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[to_itp_scale(record["partner_state"])],
                y=[0.55],
                mode="markers+text",
                marker=dict(color=self.PARTNER, size=14),
                text=["s_other"],
                textposition="top center",
                textfont=dict(color=self.PARTNER, size=15),
                showlegend=False,
                hovertemplate="s_other=%{x:.0f}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[prior_mean],
                y=[0],
                mode="markers+text",
                marker=dict(color=self.PRIOR, size=17, line=dict(color=self.TEXT, width=1)),
                text=["E[S₍ₜ₋₁₎]"],
                textposition="bottom center",
                textfont=dict(color=self.PRIOR, size=16),
                showlegend=False,
                hovertemplate="E[S_{t-1}]=%{x:.3f}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=[updated_mean],
                y=[0],
                mode="markers+text",
                marker=dict(
                    color=self.POSTERIOR,
                    size=17,
                    line=dict(color=self.TEXT, width=1),
                ),
                text=["E[Sₜ]"],
                textposition="bottom center",
                textfont=dict(color=self.POSTERIOR, size=16),
                showlegend=False,
                hovertemplate="E[S_t]=%{x:.3f}<extra></extra>",
            )
        )

        figure.add_annotation(
            x=updated_mean,
            y=0,
            ax=prior_mean,
            ay=0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            showarrow=True,
            arrowhead=3,
            arrowsize=1.4,
            arrowwidth=3,
            arrowcolor=self.ACCENT,
        )
        figure.add_annotation(
            x=(prior_mean + updated_mean) / 2,
            y=0.32,
            text=f"drift = {record['drift']:+.3f}",
            showarrow=False,
            font=dict(color=self.ACCENT, size=18, family=self.FONT),
        )

        if not np.isclose(
            record["unclipped_mean_state_dist"],
            record["updated_mean_state_dist"],
        ):
            figure.add_annotation(
                x=updated_mean,
                y=-0.6,
                text="clipped to grid bound",
                showarrow=False,
                font=dict(color=self.MUTED, size=13),
            )

        figure.update_yaxes(
            range=[-1, 1.1],
            showticklabels=False,
            showgrid=False,
            zeroline=False,
        )
        figure.update_xaxes(
            title=self.state_axis_title(record=record),
            dtick=1,
            range=[grid[0] - 0.4, grid[-1] + 0.4],
        )

        return self.style_figure(
            figure=figure,
            title="①  Drift  =  E[Sₜ] − E[S₍ₜ₋₁₎]",
            height=255,
        )

    def figure_kernel(
        self,
        record: dict[str, Any],
    ) -> go.Figure:
        """
        Draw the transport kernel as a heatmap.

        Args:
            record: Step record of the update.

        Returns:
            Kernel figure.
        """

        grid = to_itp_scale(record["state_grid"])

        figure = go.Figure(
            go.Heatmap(
                z=record["transition_matrix"],
                x=grid,
                y=grid,
                colorscale=self.COLORSCALE,
                colorbar=dict(
                    title=dict(text="K", font=dict(color=self.MUTED, size=16)),
                    tickfont=dict(color=self.MUTED, size=14),
                    outlinewidth=0,
                ),
                hovertemplate=(
                    "from xⱼ=%{y:.0f}<br>to xᵢ=%{x:.0f}<br>K=%{z:.3f}<extra></extra>"
                ),
            )
        )

        figure.update_xaxes(
            title="destination state  xᵢ  (t)",
            dtick=1,
            scaleanchor="y",
            constrain="domain",
        )
        figure.update_yaxes(
            title="source state  xⱼ  (t−1)",
            dtick=1,
            autorange="reversed",
        )

        return self.style_figure(
            figure=figure,
            title="②  Transport kernel  K   (rows = source, each row sums to 1)",
            height=430,
        )

    def figure_update(
        self,
        record: dict[str, Any],
    ) -> go.Figure:
        """
        Draw the prior and the updated state distribution.

        Args:
            record: Step record of the update.

        Returns:
            Update figure.
        """

        grid = to_itp_scale(record["state_grid"])

        figure = go.Figure()

        figure.add_trace(
            go.Bar(
                x=grid,
                y=record["prior_state_dist"],
                name="p₍ₜ₋₁₎ (prior)",
                marker_color=self.PRIOR,
                opacity=0.55,
                hovertemplate="x=%{x:.0f}<br>p_{t-1}=%{y:.3f}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Bar(
                x=grid,
                y=record["state_dist"],
                name="pₜ (updated)",
                marker_color=self.POSTERIOR,
                hovertemplate="x=%{x:.0f}<br>p_t=%{y:.3f}<extra></extra>",
            )
        )

        figure.add_vline(
            x=to_itp_scale(record["prior_mean_state_dist"]),
            line=dict(color=self.PRIOR, width=1.5, dash="dot"),
        )
        figure.add_vline(
            x=to_itp_scale(record["updated_mean_state_dist"]),
            line=dict(color=self.POSTERIOR, width=1.5, dash="dot"),
        )

        figure.update_xaxes(title=f"{record['name']} state  (1 → N)", dtick=1)
        figure.update_yaxes(title="probability mass")

        figure = self.style_figure(
            figure=figure,
            title="③  Apply:  pₜ = p₍ₜ₋₁₎ · K",
            height=695,
        )

        figure.update_layout(
            barmode="overlay",
            legend=dict(
                font=dict(color=self.MUTED, size=16),
                bgcolor="rgba(0,0,0,0)",
                orientation="h",
                y=1.08,
                x=0.5,
                xanchor="center",
            ),
        )

        return figure

    def state_axis_title(
        self,
        record: dict[str, Any],
    ) -> str:
        """
        Create the axis title describing the poles of the ITP scale.

        Args:
            record: Step record of the update.

        Returns:
            Axis title.
        """

        num_states = len(record["state_grid"])
        low_pole, high_pole = self.AXIS_POLES.get(record["dimension"], ("low", "high"))

        return (
            f"{record['name']} state  "
            f"(1 = {low_pole}  →  {num_states} = {high_pole})"
        )

    def state_marks(
        self,
        num_states: int,
    ) -> dict[int, str]:
        """
        Create slider marks for every state on the ITP scale.

        Args:
            num_states: Number of discrete states.

        Returns:
            Slider marks.
        """

        return {state: str(state) for state in range(1, num_states + 1)}
