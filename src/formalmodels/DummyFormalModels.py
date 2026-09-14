from __future__ import annotations

import random

from src.formalmodels.BaseFormalModel import BaseFormalModel

# Manhattan radius of the SASB diamond, from the IBSSS description in
# schema/interpersonal-behavior-state-space/sasb.json.
SASB_DIAMOND_RADIUS = 2


def project_onto_sasb_diamond(
    affiliation: float,
    interdependence: float,
) -> dict[str, int]:
    """
    Round a SASB state onto the integer lattice and into the diamond.

    The SASB state space is discrete and diamond-shaped, so a state must have
    integer coordinates with a Manhattan distance of at most two from the
    center. Averaging two valid states does not preserve either property.

    Args:
        affiliation: Affiliation value.
        interdependence: Interdependence value.

    Returns:
        SASB state on the lattice and inside the diamond.
    """

    values = {
        "Aff": int(round(affiliation)),
        "Int": int(round(interdependence)),
    }

    while sum(abs(value) for value in values.values()) > SASB_DIAMOND_RADIUS:
        dimension = max(values, key=lambda key: abs(values[key]))
        values[dimension] -= 1 if values[dimension] > 0 else -1

    return values


class DummyIPCFormalModel(BaseFormalModel):
    """
    Simple IPC formal model used for testing.

    Args:

    Returns:
    """

    def __init__(
        self,
        model_id: str,
        random_seed: int | None = None,
    ) -> None:
        """
        Initialize a dummy IPC formal model.

        Args:
            model_id: Identifier of the formal model.
            random_seed: Optional random seed for reproducible initialization.

        Returns:
        """

        rng = random.Random(random_seed)

        self.model_id = model_id
        self.state_space = "ipc"
        self.analysis_unit = "monadic"
        self.dimensions = ("Theta", "R")
        self.state = {
            "Theta": rng.uniform(0, 360),
            "R": rng.uniform(0.1, 1.0),
        }

        self.validate_model_interface()

    def integrate_numerical_input(
        self,
        numerical_input: dict[str, float],
        context: str | None = None,
    ) -> None:
        """
        Update the IPC state using another IPC state.

        The angle of the input is only read when its radius is greater than
        zero. At the neutral center the circumplex defines no angle, so moving
        toward the reported one would treat a neutral partner as if it had a
        direction. Only the radius is integrated in that case.

        Args:
            numerical_input: Numerical input containing Theta and R.
            context: Optional string describing the interaction context.

        Returns:
        """

        if numerical_input["R"] > 0:
            old_theta = self.state["Theta"]
            theta_difference = (numerical_input["Theta"] - old_theta + 180) % 360 - 180

            self.state["Theta"] = (old_theta + theta_difference / 2) % 360

        self.state["R"] = (self.state["R"] + numerical_input["R"]) / 2

    def generate_numerical_output(
        self,
        context: str | None = None,
    ) -> dict[str, float]:
        """
        Generate the current IPC state as numerical output.

        Args:
            context: Optional string describing the interaction context.

        Returns:
            Current IPC state as numerical output.
        """

        return self.state.copy()


class DummySASBFormalModel(BaseFormalModel):
    """
    Simple SASB formal model used for testing.

    Args:

    Returns:
    """

    def __init__(
        self,
        model_id: str,
        random_seed: int | None = None,
    ) -> None:
        """
        Initialize a dummy SASB formal model.

        Args:
            model_id: Identifier of the formal model.
            random_seed: Optional random seed for reproducible initialization.

        Returns:
        """

        rng = random.Random(random_seed)

        possible_states = [
            {"Aff": aff, "Int": interdependence}
            for aff in range(-2, 3)
            for interdependence in range(-2, 3)
            if abs(aff) + abs(interdependence) <= 2
        ]

        self.model_id = model_id
        self.state_space = "sasb"
        self.analysis_unit = "monadic"
        self.dimensions = ("Aff", "Int")
        self.state = rng.choice(possible_states).copy()

        self.validate_model_interface()

    def integrate_numerical_input(
        self,
        numerical_input: dict[str, float],
        context: str | None = None,
    ) -> None:
        """
        Update the SASB state using another SASB state.

        The averaged state is projected back onto the SASB lattice, because the
        SASB state space is discrete and averaging two valid states can leave
        both the lattice and the diamond.

        Args:
            numerical_input: Numerical input containing Aff and Int.
            context: Optional string describing the interaction context.

        Returns:
        """

        self.state = project_onto_sasb_diamond(
            affiliation=(self.state["Aff"] + numerical_input["Aff"]) / 2,
            interdependence=(self.state["Int"] + numerical_input["Int"]) / 2,
        )

    def generate_numerical_output(
        self,
        context: str | None = None,
    ) -> dict[str, float]:
        """
        Generate the current SASB state as numerical output.

        Args:
            context: Optional string describing the interaction context.

        Returns:
            Current SASB state as numerical output.
        """

        return self.state.copy()