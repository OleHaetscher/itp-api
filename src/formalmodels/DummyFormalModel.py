from __future__ import annotations

import random

from src.formalmodels.BaseFormalModel import BaseFormalModel


class DummyFormalModel(BaseFormalModel):
    """
    Simple communion-only formal model used for testing.
    """

    def __init__(
        self,
        model_id: str,
        random_seed: int | None = None,
    ) -> None:
        """
        Initialize a dummy communion-only formal model.

        Args:
            model_id: Identifier of the formal model.
            random_seed: Optional random seed for reproducible initialization.

        Returns:
        """

        rng = random.Random(random_seed)

        self.model_id = model_id
        self.dimensions = ("communion",)
        self.state = {"communion": rng.uniform(1, 5)}

        self.validate_model_interface()

    def integrate_numerical_input(
        self,
        numerical_input: dict[str, float],
        context: str | None = None,
    ) -> None:
        """
        Update the communion state using another model's communion value.

        Args:
            numerical_input: Numerical input containing communion.
            context: Optional string describing the interaction context.

        Returns:
        """

        old_state = self.state["communion"]
        other_state = numerical_input["communion"]

        self.state["communion"] = (old_state + other_state) / 2

    def generate_numerical_output(
        self,
        context: str | None = None,
    ) -> dict[str, float]:
        """
        Generate the current communion state as numerical output.

        Args:
            context: Optional string describing the interaction context.

        Returns:
            Current communion state as numerical output.
        """

        return self.state.copy()