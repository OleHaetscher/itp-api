"""
LASSI-style agency-communion formal model.

Each interpersonal axis carries a discrete probability distribution p over an
integer state grid 0 ... num_states - 1. One update step is:

    delta_BD = w_BD * (BD - E[S_t-1])                 behavioral-default pull
    delta_C  = w_C * m * (partner_state - midpoint)   complementarity
    delta_IR = IR * delta_C                           reactivity-moderated

    E[S_t] = clip(E[S_t-1] + delta_BD + delta_IR, state_min, state_max)
    drift  = E[S_t] - E[S_t-1]

    p_t = p_t-1 @ K(drift)

with m = -1 for agency and m = +1 for communion, and K a row-stochastic
Gaussian transport kernel. Complementarity enters only through delta_IR, so an
axis with IR = 0 ignores the partner entirely.

Scale convention: all parameters and states in this module are on the internal
0-based grid, including BD. Conversion to and from the ITP 1-based "ac" scale
happens only in to_itp_state and to_internal_state.

Parameters are read from configs/formal_model_parameters.yaml.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.utils.utilfuncs import load_config

LASSI_CONFIG_NAME = "formal_model_parameters.yaml"
LASSI_CONFIG_KEY = "lassi_formal_model"

# Config settings that are shared by all axes and flattened into each axis.
LASSI_SHARED_PARAMETERS = (
    "num_states",
    "sigma_floor_steps",
    "boundary_stickiness",
)


def load_lassi_parameters() -> dict[str, dict[str, Any]]:
    """
    Load the LASSI axis parameters from the formal model config.

    Args:

    Returns:
        Dictionary mapping axis abbreviations to axis parameters.
    """

    config = load_config(LASSI_CONFIG_NAME)[LASSI_CONFIG_KEY]

    shared = {
        parameter: config[parameter]
        for parameter in LASSI_SHARED_PARAMETERS
    }

    return {
        dimension: {**shared, **axis_parameters}
        for dimension, axis_parameters in config["axes"].items()
    }


def _normalize(
    probabilities: np.ndarray,
    epsilon: float = 1e-12,
) -> np.ndarray:
    """
    Normalize a probability vector.

    Args:
        probabilities: Probability vector.
        epsilon: Lower bound below which the total is treated as zero.

    Returns:
        Normalized probability vector.
    """

    total = probabilities.sum()

    if total < epsilon:
        return probabilities

    return probabilities / total


def _expectation(
    grid: np.ndarray,
    probabilities: np.ndarray,
) -> float:
    """
    Compute the expectation of a discrete distribution.

    Args:
        grid: Discrete state grid.
        probabilities: Probability vector over the state grid.

    Returns:
        Expected state.
    """

    return float(np.dot(grid, probabilities))


def _bell_curve(
    grid: np.ndarray,
    mean: float,
    sigma: float,
) -> np.ndarray:
    """
    Create a bell-shaped probability vector over a grid.

    Args:
        grid: Discrete state grid.
        mean: Mean of the bell curve.
        sigma: Width of the bell curve.

    Returns:
        Bell-shaped probability vector.
    """

    values = np.exp(-((grid - mean) ** 2) / (2 * sigma**2))

    return _normalize(values)


def _reflect(
    value: float,
    lower: float,
    upper: float,
) -> float:
    """
    Reflect a value back into an interval.

    Args:
        value: Value to reflect.
        lower: Lower bound of the interval.
        upper: Upper bound of the interval.

    Returns:
        Reflected value inside the interval.
    """

    if lower == upper:
        return lower

    span = upper - lower
    remainder = (value - lower) % (2 * span)

    if remainder <= span:
        return lower + remainder

    return upper - (remainder - span)


def _kernel_sigma(
    grid: np.ndarray,
    sigma: float,
    sigma_floor_steps: float,
) -> float:
    """
    Compute the effective kernel width for a grid.

    The floor keeps the kernel wide enough to spread mass across neighboring
    states, so that a narrow sigma cannot collapse the distribution onto a
    single state.

    Args:
        grid: Discrete state grid.
        sigma: Requested kernel width.
        sigma_floor_steps: Lower bound on the kernel width, in grid steps.

    Returns:
        Effective kernel width.
    """

    step = float(np.median(np.diff(grid))) if len(grid) > 1 else 1.0

    return max(float(sigma), sigma_floor_steps * step)


def _gaussian_transport_kernel(
    grid: np.ndarray,
    drift: float,
    sigma: float,
    boundary_stickiness: float,
) -> np.ndarray:
    """
    Create a row-stochastic Gaussian transition kernel over a discrete grid.

    Each source state is shifted by the drift. Because the shifted target can
    fall outside the grid, every row blends a Gaussian centered on the clipped
    target with a Gaussian centered on the reflected target. Clipping piles
    mass up at the boundary, reflection pushes it back inward, and
    boundary_stickiness weights the two.

    Args:
        grid: Discrete state grid.
        drift: Mean shift applied to each source state.
        sigma: Effective width of the Gaussian transition.
        boundary_stickiness: Weight of the clipped Gaussian, between 0 and 1.

    Returns:
        Transition matrix whose rows sum to 1.
    """

    n_states = len(grid)
    transition_matrix = np.empty((n_states, n_states), dtype=float)

    state_min = float(grid[0])
    state_max = float(grid[-1])
    stickiness = float(np.clip(boundary_stickiness, 0.0, 1.0))

    for source_index in range(n_states):
        target_mean = float(grid[source_index]) + drift

        clipped_mean = float(np.clip(target_mean, state_min, state_max))
        reflected_mean = _reflect(
            value=target_mean,
            lower=state_min,
            upper=state_max,
        )

        row = stickiness * np.exp(
            -((grid - clipped_mean) ** 2) / (2 * sigma**2)
        ) + (1.0 - stickiness) * np.exp(
            -((grid - reflected_mean) ** 2) / (2 * sigma**2)
        )

        if row.sum() > 0:
            transition_matrix[source_index, :] = _normalize(row)
        else:
            transition_matrix[source_index, :] = np.full(n_states, 1.0 / n_states)

    return transition_matrix


class LASSIAxis:
    """
    Single discrete LASSI interpersonal axis.

    Args:

    Returns:
    """

    def __init__(
        self,
        dimension: str,
        parameters: dict[str, Any],
    ) -> None:
        """
        Initialize a LASSI interpersonal axis.

        Args:
            dimension: Axis abbreviation.
            parameters: Axis parameters, as returned by load_lassi_parameters.

        Returns:
        """

        self.dimension = dimension
        self.name = parameters["name"]

        self.num_states = int(parameters["num_states"])
        self.state_min = 0.0
        self.state_max = float(self.num_states - 1)
        self.state_grid = np.arange(self.num_states, dtype=float)
        self.midpoint = (self.state_min + self.state_max) / 2

        self.BD = float(parameters["BD"])
        self.w_BD = float(parameters["w_BD"])
        self.w_C = float(parameters["w_C"])
        self.IR = float(parameters["IR"])
        self.sigma = float(parameters["sigma"])
        self.complementarity_direction = float(parameters["complementarity_direction"])
        self.deterministic = bool(parameters["deterministic"])

        self.sigma_floor_steps = float(parameters["sigma_floor_steps"])
        self.boundary_stickiness = float(parameters["boundary_stickiness"])

        self.sigma_eff = _kernel_sigma(
            grid=self.state_grid,
            sigma=self.sigma,
            sigma_floor_steps=self.sigma_floor_steps,
        )

        self.prior_state_dist = None
        self.transition_matrix = None
        self.drift_components = {}

        self.set_state_dist_from_mean(mean=self.BD)

    @classmethod
    def from_config(
        cls,
        dimension: str,
    ) -> LASSIAxis:
        """
        Create a LASSI interpersonal axis from the formal model config.

        Args:
            dimension: Axis abbreviation.

        Returns:
            LASSI interpersonal axis.
        """

        parameters = load_lassi_parameters()

        if dimension not in parameters:
            raise ValueError(f"No LASSI parameters configured for axis: {dimension}")

        return cls(
            dimension=dimension,
            parameters=parameters[dimension],
        )

    def parameters(
        self,
    ) -> dict[str, Any]:
        """
        Return the axis parameters.

        The result can be passed back into LASSIAxis, which makes it a
        convenient starting point for parameter variations.

        Args:

        Returns:
            Axis parameters.
        """

        return {
            "name": self.name,
            "num_states": self.num_states,
            "BD": self.BD,
            "w_BD": self.w_BD,
            "w_C": self.w_C,
            "IR": self.IR,
            "sigma": self.sigma,
            "complementarity_direction": self.complementarity_direction,
            "deterministic": self.deterministic,
            "sigma_floor_steps": self.sigma_floor_steps,
            "boundary_stickiness": self.boundary_stickiness,
        }

    def set_state_dist_from_mean(
        self,
        mean: float,
    ) -> None:
        """
        Set the state distribution to a bell curve centered on a mean.

        Args:
            mean: Mean of the bell curve, on the internal grid.

        Returns:
        """

        self.state_dist = _bell_curve(
            grid=self.state_grid,
            mean=float(np.clip(mean, self.state_min, self.state_max)),
            sigma=self.sigma,
        )

        self.state = self.next_state()

    def update_from_partner_state(
        self,
        partner_state: float,
    ) -> None:
        """
        Update the axis from an incoming partner state.

        Args:
            partner_state: Partner state on the internal grid.

        Returns:
        """

        self.update_probabilities(partner_state=partner_state)
        self.state = self.next_state()

    def update_probabilities(
        self,
        partner_state: float,
    ) -> None:
        """
        Update the state distribution from an incoming partner state.

        Args:
            partner_state: Partner state on the internal grid.

        Returns:
        """

        state_dist_t_minus_1 = _normalize(self.state_dist.astype(float))
        mean_t_minus_1 = _expectation(
            grid=self.state_grid,
            probabilities=state_dist_t_minus_1,
        )

        delta_BD = self._delta_BD(
            expected_state=mean_t_minus_1,
        )

        delta_C = self._delta_C(
            partner_state=partner_state,
        )

        delta_IR = self.IR * delta_C

        unclipped_mean_t = mean_t_minus_1 + delta_BD + delta_IR
        mean_t = float(np.clip(unclipped_mean_t, self.state_min, self.state_max))

        drift = mean_t - mean_t_minus_1

        transition_matrix = _gaussian_transport_kernel(
            grid=self.state_grid,
            drift=drift,
            sigma=self.sigma_eff,
            boundary_stickiness=self.boundary_stickiness,
        )

        state_dist_t = state_dist_t_minus_1 @ transition_matrix

        self.prior_state_dist = state_dist_t_minus_1
        self.state_dist = _normalize(state_dist_t)
        self.transition_matrix = transition_matrix
        self.drift_components = {
            "partner_state": float(partner_state),
            "prior_mean_state_dist": mean_t_minus_1,
            "BD_pull_comp": delta_BD,
            "C_comp": delta_C,
            "IR_comp": delta_IR,
            "unclipped_mean_state_dist": unclipped_mean_t,
            "updated_mean_state_dist": mean_t,
            "drift": drift,
        }

    def next_state(
        self,
    ) -> int:
        """
        Update and return the current discrete state.

        Args:

        Returns:
            Current discrete state on the internal grid.
        """

        if self.deterministic:
            return int(np.argmax(self.state_dist))

        return int(np.random.choice(len(self.state_dist), p=self.state_dist))

    def step_record(
        self,
    ) -> dict[str, Any]:
        """
        Return every quantity of the most recent update step.

        Args:

        Returns:
            Distributions, transition matrix and drift components of the step.
        """

        return {
            "dimension": self.dimension,
            "name": self.name,
            "state_grid": self.state_grid,
            "prior_state_dist": self.prior_state_dist,
            "state_dist": self.state_dist,
            "transition_matrix": self.transition_matrix,
            "state": self.state,
            "midpoint": self.midpoint,
            "sigma_eff": self.sigma_eff,
            **self.drift_components,
        }

    def _delta_BD(
        self,
        expected_state: float,
    ) -> float:
        """
        Compute the behavioral-default pull.

        Args:
            expected_state: Expected state at the previous time point.

        Returns:
            Behavioral-default increment.
        """

        return self.w_BD * (self.BD - expected_state)

    def _delta_C(
        self,
        partner_state: float,
    ) -> float:
        """
        Compute the complementarity increment.

        Args:
            partner_state: Partner state on the internal grid.

        Returns:
            Complementarity increment.
        """

        centered_partner_state = partner_state - self.midpoint

        return self.w_C * self.complementarity_direction * centered_partner_state

    def to_itp_state(
        self,
    ) -> int:
        """
        Return the current state on the ITP scale.

        Args:

        Returns:
            Current state on the ITP 1-based scale.
        """

        return self.state + 1

    def to_internal_state(
        self,
        itp_state: float,
    ) -> int:
        """
        Convert an ITP state to the internal grid.

        Args:
            itp_state: State on the ITP 1-based scale.

        Returns:
            State on the internal 0-based grid.
        """

        if int(itp_state) != itp_state:
            raise ValueError("LASSIFormalModel only accepts discrete states.")

        if itp_state < 1 or itp_state > self.num_states:
            raise ValueError(
                f"LASSIFormalModel states must be between 1 and {self.num_states}."
            )

        return int(itp_state) - 1


class LASSIFormalModel(BaseFormalModel):
    """
    LASSI-style agency-communion formal model.

    Args:

    Returns:
    """

    def __init__(
        self,
        model_id: str,
        dimensions: tuple[str, ...] = ("A", "C"),
        parameters: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """
        Initialize a LASSI formal model.

        Args:
            model_id: Identifier of the formal model.
            dimensions: Interpersonal dimensions used by the model.
            parameters: Optional axis parameters, overriding the config.

        Returns:
        """

        self.model_id = model_id
        self.state_space = "ac"
        self.analysis_unit = "monadic"
        self.dimensions = dimensions

        if parameters is None:
            parameters = load_lassi_parameters()

        missing_dimensions = set(dimensions) - set(parameters)

        if missing_dimensions:
            raise ValueError(
                f"No LASSI parameters configured for axes: {missing_dimensions}"
            )

        self.axes = {
            dimension: LASSIAxis(
                dimension=dimension,
                parameters=parameters[dimension],
            )
            for dimension in self.dimensions
        }

        self.state = self.generate_numerical_output()

        self.validate_model_interface()

    def integrate_numerical_input(
        self,
        numerical_input: dict[str, float],
        context: str | None = None,
    ) -> None:
        """
        Integrate numerical input into the model state.

        Args:
            numerical_input: Numerical input received by the model.
            context: Optional string describing the interaction context.

        Returns:
        """

        for dimension in self.dimensions:
            if dimension not in numerical_input:
                raise ValueError(f"Missing input dimension: {dimension}")

            partner_state = self.axes[dimension].to_internal_state(
                itp_state=numerical_input[dimension],
            )

            self.axes[dimension].update_from_partner_state(
                partner_state=partner_state,
            )

        self.state = self.generate_numerical_output(context=context)

    def generate_numerical_output(
        self,
        context: str | None = None,
    ) -> dict[str, float]:
        """
        Generate numerical output from the current model state.

        Args:
            context: Optional string describing the interaction context.

        Returns:
            Current discrete agency-communion state.
        """

        return {
            dimension: self.axes[dimension].to_itp_state()
            for dimension in self.dimensions
        }

    def step_records(
        self,
    ) -> dict[str, dict[str, Any]]:
        """
        Return the most recent update step of every axis.

        Args:

        Returns:
            Dictionary mapping axis abbreviations to step records.
        """

        return {
            dimension: self.axes[dimension].step_record()
            for dimension in self.dimensions
        }
