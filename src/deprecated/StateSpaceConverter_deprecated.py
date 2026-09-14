from __future__ import annotations

import statistics
import warnings
from typing import Any

from src.BaseConverter import BaseConverter

# A relational state vector: probabilities over the four dyadic relations.
RelationalVector = dict[str, float]

# A window of per-turn paired communion states: [(communion_A, communion_B), ...].
PairedStates = list[tuple[float, float]]

# A LASSI communion state distribution: {state_value: probability}.
CommunionDistribution = dict[float, float]


class BehavioralStateSpaceConverter(BaseConverter):
    """
    Convert LASSI communion states onto the Westermann relational state space.

    This converter maps the *communion* dimension of the LASSI framework (a
    monadic, per-agent representation on the interpersonal circumplex) onto the
    dyadic relational state space of Westermann and Banisch (2025). It does two
    things at once, corresponding to the two conversion kinds described in
    `BaseConverter`:

    1. Framework-level mapping (dimension semantics): the positive pole of
       communion (friendly) is identified with the affiliative approach motive /
       friendly behavior (F), and the negative pole (hostile or distancing) with
       the affiliative avoidance motive / distancing behavior (D). A continuous
       or binned communion value is reduced to F or D by a threshold (see
       `threshold`). Agency is not represented in Westermann's affiliative space
       and is therefore dropped by this converter.

    2. Model-level mapping (state-space geometry): two per-agent communion
       representations are combined into a single dyadic state, a probability
       vector over the four relations FF, DF, FD, DD, mirroring the relational
       state space schema (interpersonal-state-space.schema.json). The first
       letter denotes individual A's pole, the second individual B's pole.

    Two routes are supported:

    - Empirical joint (faithful), via `from_paired_states`: tabulate the
      co-occurrence of A's and B's communion poles across a window of turns.
      Because it is measured from the actual coupled trajectory, this route can
      represent dyadic association and therefore reach the interior of the
      tetrahedron (e.g. coordination, cyclicity).
    - Product (lossy), via `from_marginals`: multiply the two agents' marginal
      friendliness probabilities. This assumes A and B are independent and
      therefore lands only on the independence surface of the tetrahedron,
      discarding dyadic association. A warning is emitted whenever it is used.

    The converter is for comparability only; it does not alter or replace the
    LASSI state distributions, which continue to evolve under their own logic.
    A typical use is to take a window of an interaction (a variable number of
    turns, but at least `min_observations`) and read off the current relational
    state.

    Args:
        scale: Lower and upper bound of the LASSI communion scale, used to derive
            the default threshold as the scale midpoint. Defaults to (1.0, 5.0).
        threshold: Communion value separating friendly (F) from distancing (D).
            A value strictly greater than the threshold counts as F, otherwise D.
            If None, the midpoint of `scale` is used. Note that treating the
            midpoint as the F/D boundary assumes the scale midpoint is the
            motivational neutral point; this can be changed or fitted from data.
        min_observations: Minimum number of paired observations required for the
            empirical-joint route. Defaults to 2.

    Returns:
    """

    # Relation keys in the order used by the relational state space schema.
    RELATION_KEYS: tuple[str, ...] = ("FF", "DF", "FD", "DD")

    # In-code reflection of the relational state space schema dimensions.
    RELATIONS: dict[str, str] = {
        "FF": "A friendly/approach and B friendly/approach (aF bF).",
        "DF": "A distancing/avoidance and B friendly/approach (aD bF).",
        "FD": "A friendly/approach and B distancing/avoidance (aF bD).",
        "DD": "A distancing/avoidance and B distancing/avoidance (aD bD).",
    }

    def __init__(
        self,
        scale: tuple[float, float] = (1.0, 5.0),
        threshold: float | None = None,
        min_observations: int = 2,
    ) -> None:
        """
        Initialize the LASSI-communion to relational-state-space converter.

        Args:
            scale: Lower and upper bound of the LASSI communion scale.
            threshold: F/D boundary on communion. Defaults to the scale midpoint.
            min_observations: Minimum paired observations for the joint route.

        Returns:
        """

        if scale[0] >= scale[1]:
            raise ValueError("scale lower bound must be below the upper bound.")

        if min_observations < 1:
            raise ValueError("min_observations must be at least 1.")

        # TODO: We need some registry to track which conversions are supported
        self.source = "LASSI:communion"
        self.target = "Westermann:relational_state_space"

        self.scale = scale
        self.threshold = self._scale_midpoint() if threshold is None else float(
            threshold
        )
        self.min_observations = min_observations

        # Whether the most recent conversion used the lossy product route.
        self.lossy = False

    def convert(
        self,
        source_input: dict[str, Any],
        context: str | None = None,
    ) -> RelationalVector:
        """
        Convert LASSI communion input into a relational state vector.

        The route is selected from the keys of `source_input`:
        - "paired_states": a window of (communion_A, communion_B) tuples, routed
          to the faithful empirical-joint computation.
        - "marginals": a mapping {"a": ..., "b": ...} of the two agents'
          friendliness, routed to the lossy product computation. Each value may
          be a friendliness probability (float in [0, 1]) or a communion
          distribution ({state_value: probability}).

        Args:
            source_input: Dict carrying exactly one of the keys above.
            context: Optional string describing the interaction context.

        Returns:
            Relational state vector over FF, DF, FD, DD.
        """

        has_pairs = "paired_states" in source_input
        has_marginals = "marginals" in source_input

        if has_pairs and has_marginals:
            raise ValueError(
                "source_input must contain either 'paired_states' or "
                "'marginals', not both."
            )

        if has_pairs:
            return self.from_paired_states(source_input["paired_states"])

        if has_marginals:
            marginals = source_input["marginals"]
            return self.from_marginals(marginals["a"], marginals["b"])

        raise ValueError(
            "source_input must contain 'paired_states' or 'marginals'."
        )

    def from_paired_states(self, window: PairedStates) -> RelationalVector:
        """
        Build a relational state vector from a window of paired communion states.

        This is the faithful route. Each item pairs individual A's and B's
        communion state at one step of the window (the caller decides how A and
        B are aligned per step, e.g. once per interaction exchange). The relation
        frequencies are the normalized co-occurrence counts of the two poles and
        therefore retain dyadic association.

        Args:
            window: List of (communion_A, communion_B) tuples.

        Returns:
            Relational state vector over FF, DF, FD, DD.
        """

        if len(window) < self.min_observations:
            raise ValueError(
                f"window needs at least {self.min_observations} paired "
                f"observations, got {len(window)}."
            )

        counts = {key: 0 for key in self.RELATION_KEYS}

        for pair in window:
            communion_a, communion_b = pair
            key = self._pole(communion_a) + self._pole(communion_b)
            counts[key] += 1

        n = len(window)
        vector = {key: counts[key] / n for key in self.RELATION_KEYS}

        self.lossy = False

        return self._format_output(self._validated(vector))

    def from_marginals(
        self,
        agent_a: float | CommunionDistribution,
        agent_b: float | CommunionDistribution,
    ) -> RelationalVector:
        """
        Build a relational state vector by multiplying per-agent marginals.

        This is the lossy route. It assumes that A's and B's communion poles are
        statistically independent, so the resulting state lies on the
        independence surface of the tetrahedron and carries no dyadic
        association. A warning is emitted on every call.

        Args:
            agent_a: Individual A's friendliness as a probability in [0, 1], or a
                communion distribution to be reduced to one.
            agent_b: Individual B's friendliness as a probability in [0, 1], or a
                communion distribution to be reduced to one.

        Returns:
            Relational state vector over FF, DF, FD, DD.
        """

        warnings.warn(
            "from_marginals multiplies per-agent marginals and assumes A and B "
            "are independent; the result lies on the independence surface of the "
            "relational space and discards dyadic association (lossy).",
            stacklevel=2,
        )

        p_a = self._as_friendly_probability(agent_a)
        p_b = self._as_friendly_probability(agent_b)

        vector = {
            "FF": p_a * p_b,
            "DF": (1.0 - p_a) * p_b,
            "FD": p_a * (1.0 - p_b),
            "DD": (1.0 - p_a) * (1.0 - p_b),
        }

        self.lossy = True

        return self._format_output(self._validated(vector))

    def communion_distribution_to_p_friendly(
        self,
        distribution: CommunionDistribution,
    ) -> float:
        """
        Reduce a LASSI communion distribution to a friendliness probability.

        The friendliness probability is the share of probability mass on states
        strictly above the threshold. The distribution is normalized defensively
        in case its mass does not sum to one.

        Args:
            distribution: Mapping {state_value: probability}.

        Returns:
            Probability of being friendly (F), in [0, 1].
        """

        if not distribution:
            raise ValueError("distribution must not be empty.")

        total = sum(distribution.values())

        if total <= 0.0:
            raise ValueError("distribution mass must be positive.")

        friendly_mass = sum(
            probability
            for value, probability in distribution.items()
            if value > self.threshold
        )

        return friendly_mass / total

    def set_threshold(self, value: float) -> None:
        """
        Set the F/D threshold on communion.

        Args:
            value: New threshold value.

        Returns:
        """

        self.threshold = float(value)

    def fit_threshold(
        self,
        values: list[float],
        strategy: str = "mean",
    ) -> float:
        """
        Set the F/D threshold from observed communion values.

        This offers a data-driven alternative to the scale midpoint, for example
        an "above versus below average" boundary. It replaces the assumption that
        the scale midpoint is the motivational neutral point with a
        sample-relative boundary, which is itself an assumption to keep in mind.

        Args:
            values: Observed communion values to derive the threshold from.
            strategy: Either "mean" or "median".

        Returns:
            The fitted threshold, which is also stored on the converter.
        """

        if not values:
            raise ValueError("values must not be empty.")

        if strategy == "mean":
            fitted = statistics.fmean(values)
        elif strategy == "median":
            fitted = statistics.median(values)
        else:
            raise ValueError("strategy must be 'mean' or 'median'.")

        self.threshold = float(fitted)

        return self.threshold

    def validate_relational_vector(self, vector: RelationalVector) -> None:
        """
        Validate a relational state vector against the schema's constraints.

        Checks that all four relation keys are present, that every probability
        lies in [0, 1], and that the probabilities sum to one (the sumEquals
        constraint of the relational state space schema).

        Args:
            vector: Relational state vector to validate.

        Returns:
        """

        missing = set(self.RELATION_KEYS) - set(vector)

        if missing:
            raise ValueError(f"relational vector missing relations: {missing}")

        for key in self.RELATION_KEYS:
            probability = vector[key]
            if not 0.0 <= probability <= 1.0:
                raise ValueError(
                    f"relation {key} probability out of range: {probability}"
                )

        total = sum(vector[key] for key in self.RELATION_KEYS)

        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"relational vector must sum to 1, got {total}.")

    def _pole(self, communion_value: float) -> str:
        """
        Map a communion value onto a friendliness pole.

        Args:
            communion_value: Communion state value.

        Returns:
            "F" if the value is strictly above the threshold, otherwise "D".
        """

        # A value exactly at the threshold is treated as D; this boundary is the
        # flagged midpoint-as-neutral assumption and can be tuned via threshold.
        return "F" if communion_value > self.threshold else "D"

    def _as_friendly_probability(
        self,
        agent: float | CommunionDistribution,
    ) -> float:
        """
        Coerce a per-agent marginal into a friendliness probability.

        Args:
            agent: Friendliness probability in [0, 1] or a communion distribution.

        Returns:
            Friendliness probability in [0, 1].
        """

        if isinstance(agent, dict):
            return self.communion_distribution_to_p_friendly(agent)

        probability = float(agent)

        if not 0.0 <= probability <= 1.0:
            raise ValueError(
                f"friendliness probability must be in [0, 1], got {probability}."
            )

        return probability

    def _scale_midpoint(self) -> float:
        """
        Return the midpoint of the communion scale.

        Args:

        Returns:
            Midpoint of the configured scale.
        """

        return (self.scale[0] + self.scale[1]) / 2.0

    def _validated(self, vector: RelationalVector) -> RelationalVector:
        """
        Validate and return a relational state vector.

        Args:
            vector: Relational state vector.

        Returns:
            The same vector, once validated.
        """

        self.validate_relational_vector(vector)

        return vector

    def _format_output(self, vector: RelationalVector) -> RelationalVector:
        """
        Shape the converter output.

        Currently returns the bare four-relation vector. This is a deliberate
        seam: later versions may attach provenance (window length, threshold,
        lossy flag, context) without changing the computation above.

        Args:
            vector: Relational state vector.

        Returns:
            The output representation.
        """

        return vector


if __name__ == "__main__":
    # A little end-to-end test: take two LASSI messages, one per agent, that
    # follow the standardized monadic message protocol, pair them, and convert.
    #
    # Note on the pairing seam: two monadic messages (one communion value from
    # each agent) form a single dyadic observation (A, B). A single observation
    # can only name a pure relation, i.e. a vertex of the relational space; an
    # interior state would need a longer window. We therefore allow a single
    # paired observation here via min_observations=1.

    message_a = {
        "schema_version": "0.1",
        "source_agent": "model_a",
        "target_agent": "model_b",
        "timecode": {"timestamp": "0:00", "interaction_turn": 1},
        "values": {"communion": 3.75},
        "context": "workplace_colleague_conversation",
    }

    message_b = {
        "schema_version": "0.1",
        "source_agent": "model_b",
        "target_agent": "model_a",
        "timecode": {"timestamp": "0:30", "interaction_turn": 2},
        "values": {"communion": 2.5},
        "context": "workplace_colleague_conversation",
    }

    # Pair the two agents' communion values into one window step (A, B). The raw
    # communion values are scale positions, so the faithful paired-states route
    # is used (the marginals route would expect friendliness probabilities).
    communion_a = message_a["values"]["communion"]
    communion_b = message_b["values"]["communion"]
    window = [(communion_a, communion_b)]

    converter = BehavioralStateSpaceConverter(min_observations=1)
    relational_state = converter.convert({"paired_states": window})

    print(f"direction:        {converter.describe()}")
    print(f"threshold:        {converter.threshold}")
    print(f"communion (A, B): ({communion_a}, {communion_b})")
    print(f"relational state: {relational_state}")

    # A = 3.75 > 3.0 -> friendly (F); B = 2.5 <= 3.0 -> distancing (D).
    # The dyad is therefore in the pure relation FD (A friendly, B distancing).
    assert relational_state == {"FF": 0.0, "DF": 0.0, "FD": 1.0, "DD": 0.0}
    print("ok: single-observation snapshot resolves to relation FD")