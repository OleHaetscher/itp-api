"""
LASSI-style agency-communion formal model.

Each interpersonal axis carries a discrete probability distribution p over a
symmetric, zero-centered integer state grid -(N - 1)/2 ... +(N - 1)/2. One
exchange moves the mean of that distribution toward a convex mixture of three
states, and the distribution itself is then the agent's habitual repertoire,
minimally deformed to have exactly that mean:

    IR_abs = |IR|                                    reactivity magnitude
    d      = +1 if IR >= 0 else -1                   response direction
    T      = s_bar + d * m * (s_other - s_bar)       partner-implied target
    mu_t   = (1 - lam) * mu_t-1 + lam * ((1 - IR_abs) * BD + IR_abs * T)
    p_t    = argmin_p KL(p || h)  subject to  E_p[S] = mu_t

with m = -1 for agency and m = +1 for communion. The projection has the closed
form p_t = h * exp(eta * s) / Z, the exponential tilt of the repertoire with the
single eta that puts the mean at mu_t. Two properties follow, and both are
load-bearing: the realised mean equals the intended mean to solver precision,
and mu_t is a convex combination of three states that already lie on the grid,
so it can never leave it and nothing is ever clipped.

Reactivity is signed. Its magnitude is the weight on the partner, its sign is
the direction of the response: IR = +1 is full complementarity, IR = 0 the
behavioral default alone, IR = -1 full anti-complementarity. The complementarity
direction m is a property of the axis and says what complementarity *means*
there; the sign of IR is a property of the person and says which way this agent
answers. Keeping them apart is what lets one dyad hold a complementary and an
anti-complementary responder at the same time.

The rule above is written in the notation of the spec. This module is written in
names, and the two do not coincide everywhere:

    lam                 lambda_relax
    T                   partner_target
    d                   direction
    h                   repertoire
    mu_t-1              mu_prev
    p_t-1, p_t          p_prev, p_new
    s_bar               s_bar in a step record, midpoint on the axis
    m                   m in a step record, complementarity_direction on the axis

BD, tau, IR, IR_abs, mu_t and eta are spelled the same on both sides.

Scale convention: the parameters in configs/formal_model_parameters.yaml are on
the ITP 1-based scale 1 ... N, the scale ITP messages carry. They are converted
to the internal centered grid when an axis is built, and back in to_itp_state.

This module is a separate implementation of the model in the lassi_simulations
repository, not a shared package. The normative description is
handoff/formal-model-spec.md there; tests/data/lassi_test_vectors.json is a copy
of its conformance vectors, and tests/test_lassi_formal_model.py runs them
against this implementation. When the model changes there, the vectors are
regenerated and this implementation has to be checked against the new file.
Nothing detects the divergence on its own.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.utils.utilfuncs import load_config

LASSI_CONFIG_NAME = "formal_model_parameters.yaml"
LASSI_CONFIG_KEY = "lassi_formal_model"

# Config key holding the per-axis settings. Everything beside it is shared by
# all axes and flattened into each of them.
LASSI_AXES_KEY = "axes"

# Convergence tolerance of the tilt solve, in grid units. The mean is solved to
# machine precision in practice; this is where the iteration stops.
SOLVER_TOLERANCE = 1e-13

# Iteration cap of the safeguarded Newton solve. Newton on an exact derivative
# converges in three or four steps from a cold start, so this is a runaway guard
# rather than a working limit.
SOLVER_MAX_ITERATIONS = 100

# Cap on the number of doublings in the bracket search. The bound reached after
# k doublings is 2**(k+1) - 1, so this permits |eta| past 1e18. A fixed bracket
# would be a bug: the tilt needed to move a width-tau repertoire grows like
# (mu - BD) / tau**2, so any constant silently rejects legitimate interior
# targets at some repertoire width.
BRACKET_MAX_DOUBLINGS = 60

# How close to a grid endpoint a target mean has to be before it is treated as
# being *at* the endpoint, where the projection is the point mass rather than a
# finite tilt. Floating-point slack, not a modelling choice: an exact endpoint
# target arises whenever a fully reactive agent answers a partner who expressed
# an extreme state.
ENDPOINT_TOLERANCE = 1e-12


def load_lassi_parameters() -> dict[str, dict[str, Any]]:
    """
    Load the LASSI axis parameters from the formal model config.

    Args:

    Returns:
        Dictionary mapping axis abbreviations to axis parameters.
    """

    config = load_config(LASSI_CONFIG_NAME)[LASSI_CONFIG_KEY]

    shared = {
        parameter: value
        for parameter, value in config.items()
        if parameter != LASSI_AXES_KEY
    }

    return {
        dimension: {**shared, **axis_parameters}
        for dimension, axis_parameters in config[LASSI_AXES_KEY].items()
    }


def build_state_grid(
    num_states: int,
) -> np.ndarray:
    """
    Build the symmetric, zero-centered state grid of one axis.

    Args:
        num_states: Number of discrete states, expected to be odd.

    Returns:
        The grid -(num_states - 1)/2 ... +(num_states - 1)/2.
    """

    return np.arange(num_states, dtype=float) - (num_states - 1) / 2


def to_itp_scale(
    values: Any,
    num_states: int,
) -> np.ndarray:
    """
    Map internal centered grid values to the ITP 1-based scale.

    Args:
        values: Values on the internal grid.
        num_states: Number of discrete states.

    Returns:
        Values on the ITP scale.
    """

    return np.asarray(values, dtype=float) + (num_states + 1) / 2


def to_internal_scale(
    values: Any,
    num_states: int,
) -> np.ndarray:
    """
    Map ITP 1-based scale values to the internal centered grid.

    Args:
        values: Values on the ITP scale.
        num_states: Number of discrete states.

    Returns:
        Values on the internal grid.
    """

    return np.asarray(values, dtype=float) - (num_states + 1) / 2


def _normalize_log(
    log_weights: np.ndarray,
) -> np.ndarray:
    """
    Turn unnormalized log weights into a probability vector.

    Working in log space is what keeps a narrow repertoire representable: a
    width of 0.1 on a seven-point grid puts exp(-450) on the end states, which
    underflows to zero if the weights are exponentiated before the shift applied
    here.

    Args:
        log_weights: Unnormalized log weights over the state grid.

    Returns:
        Normalized probability vector.
    """

    weights = np.exp(log_weights - log_weights.max())

    return weights / weights.sum()


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


def _bracket_tilt(
    mean_at: Callable[[float], float],
    target_mean: float,
) -> tuple[float, float]:
    """
    Find a bracket around the tilt that attains a target mean.

    Searched outward from zero by doubling rather than assumed, because no fixed
    bracket is correct at every repertoire width. The search stops when the
    tilted mean stops responding, which is the floating-point signature of a
    target at a grid endpoint, where the tilt is genuinely infinite and the
    projection is the point mass instead.

    Args:
        mean_at: Tilted mean as a function of the tilt, strictly increasing.
        target_mean: Mean to bracket.

    Returns:
        Bracket (lower, upper) with mean_at(lower) <= target <= mean_at(upper).
    """

    previous = mean_at(0.0)

    if previous == target_mean:
        return 0.0, 0.0

    direction = 1.0 if previous < target_mean else -1.0
    inner, outer, step = 0.0, direction, 1.0

    for _ in range(BRACKET_MAX_DOUBLINGS):
        current = mean_at(outer)

        if (current - target_mean) * direction >= 0.0:
            return (inner, outer) if direction > 0.0 else (outer, inner)

        if current == previous:
            raise ValueError(
                f"The tilted mean saturates at {current} before reaching "
                f"{target_mean}, so no finite tilt attains it. Either the "
                "target is at a grid endpoint, where the projection is the "
                "point mass rather than a tilt, or the repertoire has "
                "underflowed to zero on the outer states, which happens below "
                "about tau = 0.08 on a unit-step grid."
            )

        inner, previous = outer, current
        step *= 2.0
        outer += direction * step

    raise ValueError(
        f"Could not bracket a tilt for target mean {target_mean} within "
        f"{BRACKET_MAX_DOUBLINGS} doublings."
    )


def _solve_tilt(
    log_weights: np.ndarray,
    grid: np.ndarray,
    target_mean: float,
) -> float:
    """
    Solve for the tilt whose tilted mean equals a target.

    Safeguarded Newton on the exponential-family identity dE[S]/d_eta = Var[S],
    which is exact. A Newton step that leaves the bracket or fails to reduce the
    error is replaced by a bisection, which keeps the solve robust where the
    family is nearly degenerate and the variance underflows.

    Every strictly interior target is reachable at a unique finite tilt: E[S] is
    continuous and strictly increasing in eta, with the grid endpoints as its
    limits, so it is a bijection onto the open grid interval.

    Args:
        log_weights: Unnormalized log weights of the repertoire.
        grid: Discrete state grid.
        target_mean: Mean to attain.

    Returns:
        Tilt attaining the target mean.
    """

    state_min, state_max = float(grid[0]), float(grid[-1])

    if not state_min < target_mean < state_max:
        raise ValueError(
            f"Target mean {target_mean} must lie strictly inside the grid "
            f"({state_min}, {state_max}); an endpoint needs an infinite tilt."
        )

    def mean_at(eta: float) -> float:
        """
        Compute the mean of the repertoire tilted by eta.

        Args:
            eta: Tilt applied to the repertoire.

        Returns:
            Mean of the tilted distribution.
        """

        return _expectation(grid, _normalize_log(log_weights + eta * grid))

    lower, upper = _bracket_tilt(mean_at=mean_at, target_mean=target_mean)
    eta = 0.0

    for _ in range(SOLVER_MAX_ITERATIONS):
        probabilities = _normalize_log(log_weights + eta * grid)
        mean = _expectation(grid, probabilities)
        error = mean - target_mean

        if abs(error) < SOLVER_TOLERANCE:
            return eta

        if error < 0.0:
            lower = eta
        else:
            upper = eta

        variance = float(np.dot(grid**2, probabilities) - mean**2)
        step = eta - error / variance if variance > 0.0 else 0.5 * (lower + upper)
        eta = step if lower < step < upper else 0.5 * (lower + upper)

    raise ValueError(
        f"Tilt solve did not converge to {SOLVER_TOLERANCE:g} for target mean "
        f"{target_mean} in {SOLVER_MAX_ITERATIONS} iterations."
    )


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

        The repertoire is built here and never rebuilt: it is a symmetric bell
        of width tau, tilted once so that its mean is exactly BD. The obvious
        formula h(s) ~ exp(-(s - BD)**2 / (2 * tau**2)) is *not* the right one,
        because on a finite grid truncation pulls its mean toward the center: on
        the -3 ... +3 grid, BD = 2 and tau = 1.5 give a mean of 1.572. Building
        it any other way breaks the IR = 0 case, where the update has to return
        the repertoire untilted.

        Args:
            dimension: Axis abbreviation.
            parameters: Axis parameters, as returned by load_lassi_parameters.

        Returns:
        """

        self.dimension = dimension
        self.name = parameters["name"]

        self.num_states = int(parameters["num_states"])
        self.state_grid = build_state_grid(num_states=self.num_states)
        self.state_min = float(self.state_grid[0])
        self.state_max = float(self.state_grid[-1])
        self.midpoint = (self.state_min + self.state_max) / 2

        self.BD = float(to_internal_scale(parameters["BD"], self.num_states))
        self.tau = float(parameters["tau"])
        self.IR = float(parameters["IR"])
        self.lambda_relax = float(parameters["lambda_relax"])
        self.complementarity_direction = float(parameters["complementarity_direction"])
        self.deterministic = bool(parameters["deterministic"])

        self.validate_parameters()

        symmetric = -0.5 * (self.state_grid / self.tau) ** 2
        self._repertoire_log_weights = symmetric + self.state_grid * _solve_tilt(
            log_weights=symmetric,
            grid=self.state_grid,
            target_mean=self.BD,
        )
        self.repertoire = _normalize_log(self._repertoire_log_weights)

        # The realised mean rather than the configured one, so that BD and the
        # repertoire cannot disagree by the solver tolerance. Everything
        # downstream reads BD from here.
        self.BD = _expectation(self.state_grid, self.repertoire)

        self.prior_state_dist = None
        self.step_components = {}

        self.state_dist = self.repertoire
        self.state = self.next_state()

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

    @property
    def IR_abs(
        self,
    ) -> float:
        """
        Return the magnitude of the signed reactivity.

        Args:

        Returns:
            Weight the update places on the partner-implied target.
        """

        return abs(self.IR)

    @property
    def direction(
        self,
    ) -> float:
        """
        Return the response direction of the signed reactivity.

        Zero is mapped to +1 rather than to 0, so that a non-reactive agent is
        the |IR| = 0 limit of the complementary branch rather than a third case.
        The direction is multiplied by a weight of zero there, so the choice
        affects only the reported partner target, never the update.

        Args:

        Returns:
            +1 for a complementary responder, -1 for an anti-complementary one.
        """

        return 1.0 if self.IR >= 0.0 else -1.0

    def validate_parameters(
        self,
    ) -> None:
        """
        Validate the axis parameters.

        The complementarity direction and the odd state count are conditions the
        reference implementation states but does not check, on the grounds that
        they are architectural facts of the scale. They are checked here because
        this axis is built from editable config and from dashboard controls, and
        because a violation surfaces far away from its cause: a complementarity
        direction other than +-1 scales the partner state off the grid, and the
        projection then reports a target it cannot reach.

        Args:

        Returns:
        """

        if self.num_states < 3 or self.num_states % 2 == 0:
            raise ValueError(
                f"num_states must be odd and at least 3, got {self.num_states}; "
                "the agency-communion scale has a neutral middle state."
            )

        if self.tau <= 0.0:
            raise ValueError(f"tau is a width and must be positive, got {self.tau}")

        if not self.state_min < self.BD < self.state_max:
            raise ValueError(
                f"BD must lie strictly inside the ITP scale "
                f"(1, {self.num_states}), got "
                f"{float(to_itp_scale(self.BD, self.num_states))}; a default at "
                "an endpoint would need an infinite tilt."
            )

        if not -1.0 <= self.IR <= 1.0:
            raise ValueError(
                f"IR is a signed convex weight and must lie in [-1, 1], got "
                f"{self.IR}"
            )

        if not 0.0 < self.lambda_relax <= 1.0:
            raise ValueError(
                f"lambda_relax is a relaxation rate and must lie in (0, 1], got "
                f"{self.lambda_relax}"
            )

        if self.complementarity_direction not in (-1.0, 1.0):
            raise ValueError(
                f"complementarity_direction must be -1 or +1, got "
                f"{self.complementarity_direction}; it is the axis sign, and an "
                "agent who answers dominance with dominance has IR < 0 instead."
            )

    def parameters(
        self,
    ) -> dict[str, Any]:
        """
        Return the axis parameters.

        The result can be passed back into LASSIAxis, which makes it a
        convenient starting point for parameter variations. BD is returned on
        the ITP scale, which is the scale it is given on.

        Args:

        Returns:
            Axis parameters.
        """

        return {
            "name": self.name,
            "num_states": self.num_states,
            "BD": float(to_itp_scale(self.BD, self.num_states)),
            "tau": self.tau,
            "IR": self.IR,
            "lambda_relax": self.lambda_relax,
            "complementarity_direction": self.complementarity_direction,
            "deterministic": self.deterministic,
        }

    def tilt(
        self,
        eta: float,
    ) -> np.ndarray:
        """
        Exponentially tilt the repertoire.

        Args:
            eta: Tilt applied to the repertoire. Zero returns the repertoire.

        Returns:
            Tilted probability vector.
        """

        return _normalize_log(self._repertoire_log_weights + eta * self.state_grid)

    def project(
        self,
        target_mean: float,
    ) -> tuple[np.ndarray, float]:
        """
        Find the distribution closest to the repertoire with a given mean.

        This is the whole content of the update. For an interior target the
        solution is the exponential tilt. At either grid endpoint the feasible
        set holds exactly one distribution, the point mass there, since no other
        distribution on the grid has a mean that extreme; that point mass is
        therefore the projection, and it is the limit of the tilt as eta runs to
        infinity. Returning it is exact rather than a fallback, and it is
        reached in normal use: at |IR| = 1 and lambda_relax = 1 the agent takes
        its partner's expressed state, mirrored or copied, as its target.

        Args:
            target_mean: Mean the result must have, inside the closed grid.

        Returns:
            Projected probability vector and the tilt that produced it, which is
            infinite at an endpoint.
        """

        if target_mean <= self.state_min + ENDPOINT_TOLERANCE:
            if target_mean < self.state_min - ENDPOINT_TOLERANCE:
                raise ValueError(
                    f"Target mean {target_mean} is below the grid at "
                    f"{self.state_min}."
                )

            return self._point_mass(index=0), -np.inf

        if target_mean >= self.state_max - ENDPOINT_TOLERANCE:
            if target_mean > self.state_max + ENDPOINT_TOLERANCE:
                raise ValueError(
                    f"Target mean {target_mean} is above the grid at "
                    f"{self.state_max}."
                )

            return self._point_mass(index=self.num_states - 1), np.inf

        eta = _solve_tilt(
            log_weights=self._repertoire_log_weights,
            grid=self.state_grid,
            target_mean=target_mean,
        )

        return self.tilt(eta=eta), eta

    def set_state_dist_from_mean(
        self,
        mean: float,
    ) -> None:
        """
        Set the state distribution to the repertoire projected onto a mean.

        Every distribution the axis ever holds is a member of the same
        exponential family, so the only thing that ever changes is the tilt.

        Args:
            mean: Mean of the state distribution, on the internal grid.

        Returns:
        """

        self.state_dist, _ = self.project(target_mean=mean)
        self.state = self.next_state()

    def partner_target(
        self,
        partner_state: float,
        direction: float | None = None,
    ) -> float:
        """
        Compute the state the partner's behavior pulls the axis toward.

        The complementary target with the response direction applied. The axis
        sign says what complementary *means* here, reflection about the midpoint
        on agency and correspondence on communion; the direction says whether
        this agent responds that way or the opposite way.

        Args:
            partner_state: Partner state on the internal grid.
            direction: Optional response direction, defaulting to the direction
                of the axis reactivity.

        Returns:
            Partner-implied target state, which lies on the grid whenever the
            partner state does, because the grid is symmetric about its
            midpoint.
        """

        if direction is None:
            direction = self.direction

        return self.midpoint + direction * self.complementarity_direction * (
            partner_state - self.midpoint
        )

    def update_mean(
        self,
        mean: float,
        target: float,
    ) -> float:
        """
        Advance the expected state by one exchange.

        Written as a displacement from the previous mean rather than as the
        weighted average of the module docstring. The two are algebraically the
        same, and this form drifts less when the mean is already close to the
        target.

        Args:
            mean: Expected state before the update.
            target: Partner-implied target from partner_target.

        Returns:
            Updated expected state, which lies in the convex hull of the
            previous mean, BD and the target, and so cannot leave the grid.
        """

        return mean + self.lambda_relax * (
            (1.0 - self.IR_abs) * (self.BD - mean) + self.IR_abs * (target - mean)
        )

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

        if not self.state_min <= partner_state <= self.state_max:
            raise ValueError(
                f"Partner state {partner_state} lies outside the grid "
                f"[{self.state_min}, {self.state_max}]."
            )

        state_dist_t_minus_1 = self.state_dist
        mean_t_minus_1 = _expectation(self.state_grid, state_dist_t_minus_1)

        target = self.partner_target(partner_state=partner_state)
        mean_t = self.update_mean(mean=mean_t_minus_1, target=target)

        state_dist_t, eta = self.project(target_mean=mean_t)

        realised_mean = _expectation(self.state_grid, state_dist_t)
        variance = float(
            np.dot(self.state_grid**2, state_dist_t) - realised_mean**2
        )

        self.prior_state_dist = state_dist_t_minus_1
        self.state_dist = state_dist_t
        self.step_components = {
            "s_other": float(partner_state),
            "IR_abs": self.IR_abs,
            "direction": self.direction,
            "m_effective": self.direction * self.complementarity_direction,
            "partner_target": target,
            "target_complementary": self.partner_target(
                partner_state=partner_state,
                direction=1.0,
            ),
            "target_anti": self.partner_target(
                partner_state=partner_state,
                direction=-1.0,
            ),
            "w_prior": 1.0 - self.lambda_relax,
            "w_BD_eff": self.lambda_relax * (1.0 - self.IR_abs),
            "w_IR_eff": self.lambda_relax * self.IR_abs,
            "mu_prev": mean_t_minus_1,
            "mu_t": mean_t,
            "eta": eta,
            "eta_is_infinite": not bool(np.isfinite(eta)),
            "mu_realised": realised_mean,
            "sd_realised": float(np.sqrt(max(variance, 0.0))),
        }

    def next_state(
        self,
    ) -> float:
        """
        Draw the current discrete state from the state distribution.

        Args:

        Returns:
            Current discrete state on the internal grid.
        """

        if self.deterministic:
            index = int(np.argmax(self.state_dist))
        else:
            index = int(np.random.choice(self.num_states, p=self.state_dist))

        return float(self.state_grid[index])

    def step_record(
        self,
    ) -> dict[str, Any]:
        """
        Return every quantity of the most recent update step.

        The field names follow the conformance vectors of the handoff, so that
        the test compares them without a translation table.

        Args:

        Returns:
            Distributions, weights and intermediate quantities of the step.
        """

        return {
            "dimension": self.dimension,
            "name": self.name,
            "num_states": self.num_states,
            "grid": self.state_grid,
            "repertoire": self.repertoire,
            "repertoire_mean": self.BD,
            "BD": self.BD,
            "tau": self.tau,
            "IR": self.IR,
            "lambda_relax": self.lambda_relax,
            "m": self.complementarity_direction,
            "s_bar": self.midpoint,
            "state_min": self.state_min,
            "state_max": self.state_max,
            "p_prev": self.prior_state_dist,
            "p_new": self.state_dist,
            "state": self.state,
            **self.step_components,
        }

    def to_itp_state(
        self,
    ) -> int:
        """
        Return the current state on the ITP scale.

        Args:

        Returns:
            Current state on the ITP 1-based scale.
        """

        return int(round(float(to_itp_scale(self.state, self.num_states))))

    def to_internal_state(
        self,
        itp_state: float,
    ) -> float:
        """
        Convert an ITP state to the internal grid.

        Args:
            itp_state: State on the ITP 1-based scale.

        Returns:
            State on the internal centered grid.
        """

        if int(itp_state) != itp_state:
            raise ValueError("LASSIFormalModel only accepts discrete states.")

        if itp_state < 1 or itp_state > self.num_states:
            raise ValueError(
                f"LASSIFormalModel states must be between 1 and {self.num_states}."
            )

        return float(to_internal_scale(itp_state, self.num_states))

    def _point_mass(
        self,
        index: int,
    ) -> np.ndarray:
        """
        Build the degenerate distribution on one grid state.

        Args:
            index: Index into the state grid.

        Returns:
            Indicator vector at that index.
        """

        probabilities = np.zeros(self.num_states, dtype=float)
        probabilities[index] = 1.0

        return probabilities


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

        Agency and communion are modelled as separate, independent axes: the
        model runs once per axis and nothing in it couples them.

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
