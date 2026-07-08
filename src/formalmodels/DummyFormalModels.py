from __future__ import annotations

import random

from src.formalmodels.BaseFormalModel import BaseFormalModel


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

        Args:
            numerical_input: Numerical input containing Theta and R.
            context: Optional string describing the interaction context.

        Returns:
        """

        old_theta = self.state["Theta"]
        other_theta = numerical_input["Theta"]
        theta_difference = (other_theta - old_theta + 180) % 360 - 180

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

        Args:
            numerical_input: Numerical input containing Aff and Int.
            context: Optional string describing the interaction context.

        Returns:
        """

        self.state["Aff"] = (self.state["Aff"] + numerical_input["Aff"]) / 2
        self.state["Int"] = (self.state["Int"] + numerical_input["Int"]) / 2

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