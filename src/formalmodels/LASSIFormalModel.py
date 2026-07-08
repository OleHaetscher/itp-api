from __future__ import annotations

import numpy as np

from src.formalmodels.BaseFormalModel import BaseFormalModel

# TODO OH: Verify

LASSI_AXIS_DEFAULTS = {
    "A": {
        "name": "Agency",
        "BD": 2.0,
        "w_BD": 0.25,
        "w_C": 0.35,
        "IR": 1.0,
        "sigma": 0.8,
        "deterministic": True,
    },
    "C": {
        "name": "Communion",
        "BD": 2.0,
        "w_BD": 0.25,
        "w_C": 0.35,
        "IR": 1.0,
        "sigma": 0.8,
        "deterministic": True,
    },
}


def _normalize(
    probabilities: np.ndarray,
) -> np.ndarray:
    """
    Normalize a probability vector.

    Args:
        probabilities: Probability vector.

    Returns:
        Normalized probability vector.
    """

    total = probabilities.sum()

    if total == 0:
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


def _gaussian_transport_kernel(
    grid: np.ndarray,
    drift: float,
    sigma: float,
) -> np.ndarray:
    """
    Create a Gaussian transition kernel over a discrete grid.

    Args:
        grid: Discrete state grid.
        drift: Mean shift applied to each source state.
        sigma: Width of the Gaussian transition.

    Returns:
        Transition matrix.
    """

    n_states = len(grid)
    transition_matrix = np.empty((n_states, n_states), dtype=float)

    state_min = float(grid[0])
    state_max = float(grid[-1])

    for source_index in range(n_states):
        target_mean = grid[source_index] + drift
        target_mean = np.clip(target_mean, state_min, state_max)

        row = np.exp(-((grid - target_mean) ** 2) / (2 * sigma**2))
        transition_matrix[source_index, :] = _normalize(row)

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
    ) -> None:
        """
        Initialize a LASSI interpersonal axis.

        Args:
            dimension: Axis abbreviation.

        Returns:
        """

        params = LASSI_AXIS_DEFAULTS[dimension]

        self.dimension = dimension
        self.name = params["name"]
        self.num_states = 5
        self.state_min = 0
        self.state_max = self.num_states - 1
        self.state_grid = np.arange(self.num_states, dtype=float)

        self.BD = params["BD"]
        self.w_BD = params["w_BD"]
        self.w_C = params["w_C"]
        self.IR = params["IR"]
        self.sigma = params["sigma"]
        self.deterministic = params["deterministic"]

        self.state_dist = _bell_curve(
            grid=self.state_grid,
            mean=self.BD,
            sigma=self.sigma,
        )

        self.state = self.next_state()
        self.transition_matrix = None
        self.drift_components = {}

    def update_from_partner_state(
        self,
        partner_state: int,
    ) -> None:
        """
        Update the axis from an incoming partner state.

        Args:
            partner_state: Partner state on the internal 0-4 grid.

        Returns:
        """

        self.update_probabilities(partner_state=partner_state)
        self.state = self.next_state()

    def update_probabilities(
        self,
        partner_state: int,
    ) -> None:
        """
        Update the state distribution from an incoming partner state.

        Args:
            partner_state: Partner state on the internal 0-4 grid.

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

        mean_t = mean_t_minus_1 + delta_BD + delta_IR
        mean_t = float(np.clip(mean_t, self.state_min, self.state_max))

        drift = mean_t - mean_t_minus_1

        transition_matrix = _gaussian_transport_kernel(
            grid=self.state_grid,
            drift=drift,
            sigma=self.sigma,
        )

        state_dist_t = state_dist_t_minus_1 @ transition_matrix

        self.state_dist = _normalize(state_dist_t)
        self.transition_matrix = transition_matrix
        self.drift_components = {
            "BD_pull_comp": delta_BD,
            "C_comp": delta_C,
            "IR_comp": delta_IR,
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
            Current discrete state on the internal 0-4 grid.
        """

        if self.deterministic:
            return int(np.argmax(self.state_dist))

        return int(np.random.choice(len(self.state_dist), p=self.state_dist))

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
        partner_state: int,
    ) -> float:
        """
        Compute the complementarity increment.

        Args:
            partner_state: Partner state on the internal 0-4 grid.

        Returns:
            Complementarity increment.
        """

        midpoint = (self.state_min + self.state_max) / 2
        centered_partner_state = partner_state - midpoint

        if self.dimension == "C":
            complementarity_direction = 1.0
        else:
            complementarity_direction = -1.0

        return self.w_C * complementarity_direction * centered_partner_state

    def to_itp_state(
        self,
    ) -> int:
        """
        Return the current state on the ITP 1-5 scale.

        Args:

        Returns:
            Current state on the ITP 1-5 scale.
        """

        return self.state + 1

    def to_internal_state(
        self,
        itp_state: float,
    ) -> int:
        """
        Convert an ITP 1-5 state to the internal 0-4 grid.

        Args:
            itp_state: State on the ITP 1-5 scale.

        Returns:
            State on the internal 0-4 grid.
        """

        if int(itp_state) != itp_state:
            raise ValueError("LASSIFormalModel only accepts discrete states.")

        if itp_state < 1 or itp_state > 5:
            raise ValueError("LASSIFormalModel states must be between 1 and 5.")

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
    ) -> None:
        """
        Initialize a LASSI formal model.

        Args:
            model_id: Identifier of the formal model.
            dimensions: Interpersonal dimensions used by the model.

        Returns:
        """

        self.model_id = model_id
        self.state_space = "ac"
        self.analysis_unit = "monadic"
        self.dimensions = dimensions

        self.axes = {
            dimension: LASSIAxis(dimension=dimension)
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