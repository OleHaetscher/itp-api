from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html
from plotly.subplots import make_subplots

from src.formalmodels.LASSIFormalModel import LASSIAxis, to_internal_scale, to_itp_scale
from src.visualization.FormalModelVisualizer import FormalModelVisualizer

# Identifiers of the parameter controls, in the order the callback expects them.
CONTROL_IDS = (
    "dimension",
    "num_states",
    "BD",
    "prior_mean",
    "IR",
    "lambda_relax",
    "tau",
    "partner_state",
)

# Controls that hold a state on the ITP scale, so their range follows N.
STATE_CONTROL_IDS = (
    "BD",
    "prior_mean",
    "partner_state",
)

# Number of exchanges drawn in the iteration panel.
ITERATION_STEPS = 25


class LASSIFormalModelVisualizer(FormalModelVisualizer):
    """
    Interactive walk-through of one LASSI state distribution update.

    The dashboard takes one exchange apart panel by panel for a single axis:
    the mean rule that places the expected state, the partner-implied target
    that the sign of IR chooses between, the tilt that carries the distribution
    to that mean, and the trajectory the same exchange produces when it is
    repeated against an unchanged partner.

    The visualized model supplies the axes and their configured parameters,
    which become the initial slider values. Every callback then builds a
    throwaway axis from the current slider values, so the dashboard explores
    parameter variations without changing the model it was given.

    All sliders use the ITP 1-based scale, while the model works on the internal
    centered grid.

    Args:

    Returns:
    """

    # Poles of the ITP scale, used for the axis labels.
    AXIS_POLES = {
        "A": ("extreme submissive", "extreme dominant"),
        "C": ("extreme cold", "extreme warm"),
    }

    # The colour each axis is drawn in. The state the agent is in now carries
    # the colour of its axis, so the same figure reads as agency or as
    # communion without the caption having to say which. Everything that is not
    # the current state keeps its role colour, which does not change with the
    # axis. See BaseVisualizer for where the pair comes from.
    AXIS_COLORS = {
        "A": FormalModelVisualizer.AGENCY,
        "C": FormalModelVisualizer.COMMUNION,
    }

    NUM_STATES_MIN = 3
    NUM_STATES_MAX = 15

    # Smallest repertoire width the width slider offers. The model is numerically
    # sound down to about 0.08 on a unit-step grid, below which the repertoire
    # underflows to zero on the outer states; this keeps the control well clear
    # of that.
    TAU_MIN = 0.25

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
                "Interactive walk-through of one exchange on a single interpersonal "
                "axis. The expected state is a convex mixture of where the agent "
                "was, its behavioral default and the partner-implied target; the "
                "distribution is the agent's repertoire, minimally deformed to have "
                "that mean."
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
            Dash component holding the controls and the four figures.
        """

        return html.Div(
            [
                html.Div(
                    self.panel(self.build_controls()),
                    style={"flex": "0 0 360px"},
                ),
                html.Div(
                    [
                        html.Div(
                            self.graph("figure_mean_rule"),
                            style={"marginBottom": "10px"},
                        ),
                        html.Div(self.graph("figure_direction")),
                    ],
                    style={"flex": "1 1 0", "minWidth": "0"},
                ),
                html.Div(
                    [
                        html.Div(
                            self.graph("figure_tilt"),
                            style={"marginBottom": "10px"},
                        ),
                        html.Div(self.graph("figure_iterate")),
                    ],
                    style={"flex": "1 1 0", "minWidth": "0"},
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
        num_states = axis.num_states

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
                minimum=2,
                maximum=num_states - 1,
                step=0.5,
                value=float(to_itp_scale(axis.BD, num_states)),
                marks=self.state_marks(num_states=num_states, interior=True),
            ),
            self.slider(
                label="E[S₍ₜ₋₁₎] — prior mean state",
                slider_id="prior_mean",
                minimum=1,
                maximum=num_states,
                step=0.5,
                value=float(to_itp_scale(axis.midpoint, num_states)),
                marks=self.state_marks(num_states=num_states),
            ),
            self.slider(
                label="IR — signed interpersonal reactivity",
                slider_id="IR",
                minimum=-1.0,
                maximum=1.0,
                step=0.05,
                value=axis.IR,
                marks={-1: "−1 anti", 0: "0", 1: "+1 compl"},
            ),
            self.slider(
                label="λ — relaxation rate",
                slider_id="lambda_relax",
                minimum=0.05,
                maximum=1.0,
                step=0.05,
                value=axis.lambda_relax,
            ),
            self.slider(
                label="τ — repertoire width",
                slider_id="tau",
                minimum=self.TAU_MIN,
                maximum=2.5,
                step=0.05,
                value=axis.tau,
            ),
            self.slider(
                label="s_other — partner's assessed state",
                slider_id="partner_state",
                minimum=1,
                maximum=num_states,
                step=1,
                value=num_states,
                marks=self.state_marks(num_states=num_states),
            ),
            self.slider(
                label="N — number of discrete states (odd)",
                slider_id="num_states",
                minimum=self.NUM_STATES_MIN,
                maximum=self.NUM_STATES_MAX,
                step=2,
                value=num_states,
                marks={3: "3", 7: "7", 11: "11", 15: "15"},
            ),
            html.Hr(style={"borderColor": self.GRID}),
            self.heading("Readout"),
            html.Div(id="readout"),
            html.Hr(style={"borderColor": self.GRID}),
            self.model_caption(),
            self.caption(
                {
                    "states shown": "1 … N on the ITP scale",
                    "BD": "strictly inside (1, N)",
                    "clipping": "none, by construction",
                }
            ),
        ]

    def register_callbacks(
        self,
    ) -> None:
        """
        Register the callbacks of the dashboard.

        Args:

        Returns:
        """

        @self.app.callback(
            Output("figure_mean_rule", "figure"),
            Output("figure_direction", "figure"),
            Output("figure_tilt", "figure"),
            Output("figure_iterate", "figure"),
            Output("readout", "children"),
            *[Input(control_id, "value") for control_id in CONTROL_IDS],
        )
        def update_figures(*control_values: Any) -> tuple[Any, ...]:
            """
            Recompute one update step and redraw the figures.

            Args:
                control_values: Current values of the parameter controls.

            Returns:
                The four figures and the readout.
            """

            record = self.compute_step(**dict(zip(CONTROL_IDS, control_values)))

            return (
                self.figure_mean_rule(record=record),
                self.figure_direction(record=record),
                self.figure_tilt(record=record),
                self.figure_iterate(record=record),
                self.readout(record=record),
            )

        @self.app.callback(
            Output("BD", "max"),
            Output("BD", "marks"),
            Output("BD", "value"),
            Output("prior_mean", "max"),
            Output("prior_mean", "marks"),
            Output("prior_mean", "value"),
            Output("partner_state", "max"),
            Output("partner_state", "marks"),
            Output("partner_state", "value"),
            Input("num_states", "value"),
            *[State(control_id, "value") for control_id in STATE_CONTROL_IDS],
        )
        def update_state_controls(
            num_states: int,
            behavioral_default: float,
            prior_mean: float,
            partner_state: float,
        ) -> tuple[Any, ...]:
            """
            Keep the state sliders inside the grid when N changes.

            Args:
                num_states: Current number of discrete states.
                behavioral_default: Current behavioral default.
                prior_mean: Current prior mean state.
                partner_state: Current partner state.

            Returns:
                Maximum, marks and value of every state slider.
            """

            num_states = int(num_states)
            marks = self.state_marks(num_states=num_states)
            interior_marks = self.state_marks(num_states=num_states, interior=True)

            return (
                num_states - 1,
                interior_marks,
                float(np.clip(behavioral_default, 2, num_states - 1)),
                num_states,
                marks,
                min(prior_mean, num_states),
                num_states,
                marks,
                min(partner_state, num_states),
            )

    def compute_step(
        self,
        dimension: str,
        num_states: int,
        BD: float,
        prior_mean: float,
        IR: float,
        lambda_relax: float,
        tau: float,
        partner_state: float,
    ) -> dict[str, Any]:
        """
        Run one update step on a throwaway axis built from the control values.

        The distribution before the exchange is the repertoire projected onto
        the chosen prior mean rather than a separate bell of its own. That keeps
        the panels honest: every distribution the dashboard shows belongs to the
        same exponential family, so the only thing an exchange changes is the
        tilt.

        Args:
            dimension: Axis abbreviation.
            num_states: Number of discrete states.
            BD: Behavioral default on the ITP scale.
            prior_mean: Prior mean state on the ITP scale.
            IR: Signed interpersonal reactivity.
            lambda_relax: Relaxation rate.
            tau: Repertoire width.
            partner_state: Partner state on the ITP scale.

        Returns:
            Step record of the update, with the iterated trajectory.
        """

        num_states = int(num_states)

        parameters = self.model.axes[dimension].parameters()
        parameters.update(
            num_states=num_states,
            BD=float(np.clip(BD, 2, num_states - 1)),
            IR=IR,
            lambda_relax=lambda_relax,
            tau=tau,
            # The expressed state is not drawn here. The dashboard shows the
            # distribution rather than a sample from it, and a redraw on every
            # slider move should not flicker.
            deterministic=True,
        )

        axis = LASSIAxis(dimension=dimension, parameters=parameters)
        axis.set_state_dist_from_mean(
            mean=float(to_internal_scale(prior_mean, num_states)),
        )
        axis.update_probabilities(
            partner_state=float(to_internal_scale(partner_state, num_states)),
        )

        record = axis.step_record()
        record["trajectory"] = self.mean_trajectory(axis=axis, record=record)
        record["fixed_point"] = (1.0 - axis.IR_abs) * axis.BD + (
            axis.IR_abs * record["partner_target"]
        )

        return record

    def mean_trajectory(
        self,
        axis: LASSIAxis,
        record: dict[str, Any],
    ) -> np.ndarray:
        """
        Iterate the mean rule against an unchanged partner.

        Args:
            axis: Axis holding the parameters of the update.
            record: Step record of the update.

        Returns:
            Expected state before the exchange and after every iteration.
        """

        mean = record["mu_prev"]
        trajectory = [mean]

        for _ in range(ITERATION_STEPS):
            mean = axis.update_mean(mean=mean, target=record["partner_target"])
            trajectory.append(mean)

        return np.asarray(trajectory, dtype=float)

    def figure_mean_rule(
        self,
        record: dict[str, Any],
    ) -> go.Figure:
        """
        Draw the four states of the mean rule and the weights combining them.

        Args:
            record: Step record of the update.

        Returns:
            Mean rule figure.
        """

        num_states = record["num_states"]

        figure = make_subplots(
            rows=2,
            cols=1,
            row_heights=[0.72, 0.28],
            vertical_spacing=0.34,
            subplot_titles=(
                "where the expected state goes",
                "the three convex weights",
            ),
        )

        axis_color = self.axis_color(record=record)

        markers = (
            ("E[S₍ₜ₋₁₎]  before", record["mu_prev"], self.PRIOR, "circle"),
            ("BD  default", record["BD"], self.DEFAULT, "square"),
            ("T  partner target", record["partner_target"], self.PARTNER, "diamond"),
            ("E[Sₜ]  after", record["mu_t"], axis_color, "star"),
        )

        for row, (label, value, color, symbol) in enumerate(markers):
            shown = float(to_itp_scale(value, num_states))
            position, text = self.label_side(value=shown, num_states=num_states)

            figure.add_trace(
                go.Scatter(
                    x=[shown],
                    y=[len(markers) - row],
                    mode="markers+text",
                    marker=dict(size=17, color=color, symbol=symbol),
                    text=[text.format(f"{label}: {shown:.2f}")],
                    textposition=position,
                    textfont=dict(color=color, size=15),
                    showlegend=False,
                    hovertemplate=f"{label}: %{{x:.3f}}<extra></extra>",
                ),
                row=1,
                col=1,
            )

        weights = (
            ("(1−λ) on E[S₍ₜ₋₁₎]", record["w_prior"], self.PRIOR),
            ("λ(1−|IR|) on BD", record["w_BD_eff"], self.DEFAULT),
            ("λ·|IR| on T", record["w_IR_eff"], self.PARTNER),
        )

        for label, value, color in weights:
            figure.add_trace(
                go.Bar(
                    x=[value],
                    y=["weight"],
                    orientation="h",
                    marker=dict(color=color),
                    name=label,
                    text=[f"{value:.2f}" if value > 0.06 else ""],
                    textposition="inside",
                    hovertemplate=f"{label}: %{{x:.3f}}<extra></extra>",
                ),
                row=2,
                col=1,
            )

        figure.update_xaxes(
            title=self.state_axis_title(record=record),
            range=[0.5, num_states + 0.5],
            dtick=1,
            row=1,
            col=1,
        )
        # A full marker slot of padding, so the outermost labels are not clipped
        # by the row edge. No grid: the axis stacks the markers, it does not
        # measure them, and its lines read as strikethrough across the labels.
        figure.update_yaxes(
            range=[0.1, len(markers) + 0.9],
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            row=1,
            col=1,
        )
        figure.update_xaxes(range=[0, 1], row=2, col=1)
        figure.update_yaxes(showticklabels=False, row=2, col=1)

        figure = self.style_figure(
            figure=figure,
            title="①  E[Sₜ] = (1−λ)·E[S₍ₜ₋₁₎] + λ·[(1−|IR|)·BD + |IR|·T]",
            height=420,
        )

        figure.update_layout(
            barmode="stack",
            legend=dict(
                font=dict(color=self.MUTED, size=14),
                bgcolor="rgba(0,0,0,0)",
                orientation="h",
                y=-0.22,
                x=0.0,
            ),
        )

        for annotation in figure.layout.annotations:
            annotation.font.update(color=self.MUTED, size=15)

        return figure

    def figure_direction(
        self,
        record: dict[str, Any],
    ) -> go.Figure:
        """
        Draw both targets the partner's state implies, and which one is taken.

        The panel a signed reactivity needs. A partner state implies two
        targets, mirror images of each other about the scale midpoint. The sign
        of IR picks between them and its magnitude says how far along the agent
        travels. Drawing the road not taken is what makes the sign visible
        rather than merely asserted.

        Args:
            record: Step record of the update.

        Returns:
            Direction figure.
        """

        num_states = record["num_states"]
        complementary = record["direction"] > 0.0
        axis_color = self.axis_color(record=record)

        figure = go.Figure()

        figure.add_vline(
            x=float(to_itp_scale(record["s_bar"], num_states)),
            line=dict(color=self.GRID, width=1.5, dash="dot"),
            annotation_text="s̄",
            annotation_position="top",
            annotation_font=dict(color=self.MUTED, size=15),
        )

        rows = (
            ("s_other  partner", record["s_other"], self.PARTNER, "diamond", True, 3),
            (
                "T  complementary  (d = +1)",
                record["target_complementary"],
                axis_color if complementary else self.MUTED,
                "star" if complementary else "circle-open",
                complementary,
                2,
            ),
            (
                "T  anti-complementary  (d = −1)",
                record["target_anti"],
                self.MUTED if complementary else axis_color,
                "circle-open" if complementary else "star",
                not complementary,
                1,
            ),
            (
                f"E[Sₜ] at |IR| = {record['IR_abs']:.2f}",
                record["mu_t"],
                axis_color,
                "star",
                True,
                0,
            ),
        )

        for label, value, color, symbol, emphasized, row in rows:
            shown = float(to_itp_scale(value, num_states))
            position, text = self.label_side(value=shown, num_states=num_states)
            taken = "   ← taken" if emphasized and row in (1, 2) else ""

            figure.add_trace(
                go.Scatter(
                    x=[shown],
                    y=[row],
                    mode="markers+text",
                    marker=dict(
                        size=18 if emphasized else 12,
                        color=color,
                        symbol=symbol,
                    ),
                    text=[text.format(f"{label}{taken}")],
                    textposition=position,
                    textfont=dict(color=color, size=15),
                    showlegend=False,
                    hovertemplate=f"{label}: %{{x:.3f}}<extra></extra>",
                )
            )

        figure.update_xaxes(
            title=self.state_axis_title(record=record),
            range=[0.5, num_states + 0.5],
            dtick=1,
        )
        figure.update_yaxes(
            range=[-0.6, 3.8],
            showticklabels=False,
            showgrid=False,
            zeroline=False,
        )

        return self.style_figure(
            figure=figure,
            title="②  T = s̄ + d·m·(s_other − s̄),   d = sign(IR),  m = axis sign",
            height=340,
        )

    def figure_tilt(
        self,
        record: dict[str, Any],
    ) -> go.Figure:
        """
        Draw the repertoire, the distribution before the exchange, and the one
        after it.

        Args:
            record: Step record of the update.

        Returns:
            Tilt figure.
        """

        num_states = record["num_states"]
        grid = to_itp_scale(record["grid"], num_states)
        axis_color = self.axis_color(record=record)

        figure = go.Figure()

        figure.add_trace(
            go.Bar(
                x=grid,
                y=record["repertoire"],
                name="h  repertoire (mean = BD)",
                marker_color=self.tint(color=axis_color, opacity=0.3),
                hovertemplate="h(%{x:.0f}) = %{y:.4f}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=grid,
                y=record["p_prev"],
                name="p₍ₜ₋₁₎  before",
                mode="lines+markers",
                line=dict(color=self.PRIOR, width=2, dash="dot"),
                marker=dict(size=7),
                hovertemplate="p₍ₜ₋₁₎(%{x:.0f}) = %{y:.4f}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=grid,
                y=record["p_new"],
                name="pₜ  after",
                mode="lines+markers",
                line=dict(color=axis_color, width=3),
                marker=dict(size=9),
                hovertemplate="pₜ(%{x:.0f}) = %{y:.4f}<extra></extra>",
            )
        )

        for label, value, color in (
            ("BD", record["BD"], self.DEFAULT),
            ("E[Sₜ]", record["mu_t"], axis_color),
        ):
            figure.add_vline(
                x=float(to_itp_scale(value, num_states)),
                line=dict(color=color, width=1.5, dash="dash"),
                annotation_text=label,
                annotation_position="top",
                annotation_font=dict(color=color, size=15),
            )

        figure.update_xaxes(
            title=self.state_axis_title(record=record),
            range=[0.5, num_states + 0.5],
            dtick=1,
        )
        figure.update_yaxes(title="probability mass", rangemode="tozero")

        figure = self.style_figure(
            figure=figure,
            title="③  pₜ = h · exp(η·s) / Z,   with  E[pₜ] = E[Sₜ]",
            height=430,
        )

        figure.update_layout(
            barmode="overlay",
            legend=dict(
                font=dict(color=self.MUTED, size=14),
                bgcolor="rgba(0,0,0,0)",
                orientation="h",
                y=1.08,
                x=0.5,
                xanchor="center",
            ),
        )

        return figure

    def figure_iterate(
        self,
        record: dict[str, Any],
    ) -> go.Figure:
        """
        Draw the expected state over repeated exchanges against a fixed partner.

        The fixed point is (1 − |IR|)·BD + |IR|·T, which the relaxation rate
        does not move: it changes how fast the trajectory arrives, not where.

        Args:
            record: Step record of the update.

        Returns:
            Iteration figure.
        """

        num_states = record["num_states"]
        trajectory = to_itp_scale(record["trajectory"], num_states)
        axis_color = self.axis_color(record=record)

        figure = go.Figure()

        figure.add_trace(
            go.Scatter(
                x=list(range(len(trajectory))),
                y=trajectory,
                mode="lines+markers",
                line=dict(color=axis_color, width=3),
                marker=dict(size=7),
                showlegend=False,
                hovertemplate="exchange %{x}: %{y:.4f}<extra></extra>",
            )
        )

        for label, value, color in (
            ("fixed point", record["fixed_point"], self.ACCENT),
            ("BD", record["BD"], self.DEFAULT),
            ("T", record["partner_target"], self.PARTNER),
        ):
            figure.add_hline(
                y=float(to_itp_scale(value, num_states)),
                line=dict(color=color, width=1.5, dash="dash"),
                annotation_text=label,
                annotation_position="right",
                annotation_font=dict(color=color, size=15),
            )

        figure.update_xaxes(title="exchange")
        figure.update_yaxes(
            title=f"E[S]  (1 … {num_states})",
            range=[0.5, num_states + 0.5],
            dtick=1,
        )

        return self.style_figure(
            figure=figure,
            title="④  The same exchange, repeated against an unchanged partner",
            height=340,
        )

    def readout(
        self,
        record: dict[str, Any],
    ) -> html.Div:
        """
        Create the numeric readout of the update.

        The residual is shown deliberately: the exactness of the realised mean
        is the claim the formulation was written to make good, and it should
        stay at machine precision for every setting the sliders can reach.

        Args:
            record: Step record of the update.

        Returns:
            Dash component holding the readout.
        """

        num_states = record["num_states"]
        eta = record["eta"]
        residual = abs(record["mu_realised"] - record["mu_t"])

        return self.caption(
            {
                "|IR|, d": f"{record['IR_abs']:.2f}, {record['direction']:+.0f}",
                "T": f"{float(to_itp_scale(record['partner_target'], num_states)):.2f}",
                "E[S₍ₜ₋₁₎] → E[Sₜ]": (
                    f"{float(to_itp_scale(record['mu_prev'], num_states)):.3f}"
                    f"  →  {float(to_itp_scale(record['mu_t'], num_states)):.3f}"
                ),
                "η": "±∞ (point mass)" if record["eta_is_infinite"] else f"{eta:+.4f}",
                "E[pₜ]": f"{float(to_itp_scale(record['mu_realised'], num_states)):.6f}",
                "SD[pₜ]": f"{record['sd_realised']:.4f}",
                "residual |E[pₜ] − E[Sₜ]|": f"{residual:.2e}",
            }
        )

    def label_side(
        self,
        value: float,
        num_states: int,
    ) -> tuple[str, str]:
        """
        Choose which side of a marker its label sits on.

        A label pinned to the right of a marker runs off the panel once the
        marker is in the right half of the scale, which is exactly where the
        interesting states are. Flipping the side keeps every label inside the
        axes without widening the range past the grid, which would misrepresent
        the state space.

        Args:
            value: Position of the marker on the ITP scale.
            num_states: Number of discrete states.

        Returns:
            Plotly text position, and a template padding the label text.
        """

        if value > (num_states + 1) / 2:
            return "middle left", "{}  "

        return "middle right", "  {}"

    def axis_color(
        self,
        record: dict[str, Any],
    ) -> str:
        """
        Return the colour of the axis the step record belongs to.

        Args:
            record: Step record of the update.

        Returns:
            Colour of the axis.
        """

        return self.AXIS_COLORS.get(record["dimension"], self.PRIMARY)

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

        num_states = record["num_states"]
        low_pole, high_pole = self.AXIS_POLES.get(record["dimension"], ("low", "high"))

        return (
            f"{record['name']} state  "
            f"(1 = {low_pole}  →  {num_states} = {high_pole})"
        )

    def state_marks(
        self,
        num_states: int,
        interior: bool = False,
    ) -> dict[int, str]:
        """
        Create slider marks for the states of the ITP scale.

        Args:
            num_states: Number of discrete states.
            interior: Whether to leave out the two endpoints, for a control
                whose value has to lie strictly inside the scale.

        Returns:
            Slider marks.
        """

        first = 2 if interior else 1
        last = num_states - 1 if interior else num_states

        return {state: str(state) for state in range(first, last + 1)}
