"""
The parameters a formal model lets an interaction choose.

A model publishes a ParameterSpace: which of its parameters may vary between
agents, the range each may take, and its default. The API passes an agent's
``configuration`` through ``resolve``, which returns the values the model is
built with: the defaults, a uniform draw from the published ranges, and any
values the request fixes explicitly, applied in that order. The values used,
the selection, the seed and which values were set explicitly are returned with the agent and written to the
record, so a random draw can be repeated and reported.

Parameters that are part of the model but not of the space (for LASSI the
repertoire width and the relaxation rate) stay at their configured values and
are described as fixed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

PARAMETER_SELECTIONS = ("default", "random")
CONFIGURATION_KEYS = ("parameterSelection", "randomSeed", "parameters")

# Drawn values are rounded, so that a record reads as numbers a person would
# choose. An excluded bound is kept one step away for the same reason.
DRAW_DECIMALS = 2
DRAW_STEP = 10 ** -DRAW_DECIMALS


class ParameterError(ValueError):
    """
    A configuration that asks for parameters the space does not offer.

    Args:

    Returns:
    """


@dataclass(frozen=True)
class Parameter:
    """
    One parameter a model lets an interaction choose.

    Args:
        group: Part of the model the parameter belongs to, such as an axis.
        name: Name of the parameter within its group.
        label: Readable name.
        minimum: Lower bound.
        maximum: Upper bound.
        default: Value used unless the configuration selects another.
        exclusive: Whether the bounds themselves are excluded.
        description: What the parameter does.

    Returns:
    """

    group: str
    name: str
    label: str
    minimum: float
    maximum: float
    default: float
    exclusive: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        """
        Check that the default is a value the parameter may take.

        Args:

        Returns:
        """

        if not self.admits(self.default):
            raise ValueError(f"The default of {self.group}.{self.name} lies outside its range.")

    def admits(
        self,
        value: float,
    ) -> bool:
        """
        Return whether a value lies in the parameter's range.

        Args:
            value: Candidate value.

        Returns:
            Whether the value is admitted.
        """

        if self.exclusive:
            return self.minimum < value < self.maximum

        return self.minimum <= value <= self.maximum

    def draw(
        self,
        generator: random.Random,
    ) -> float:
        """
        Draw a value uniformly from the range.

        Args:
            generator: Random number generator.

        Returns:
            Drawn value, rounded to DRAW_DECIMALS.
        """

        margin = DRAW_STEP if self.exclusive else 0.0

        return round(generator.uniform(self.minimum + margin, self.maximum - margin), DRAW_DECIMALS)

    def describe(
        self,
    ) -> dict[str, Any]:
        """
        Describe the parameter for the model endpoint.

        Args:

        Returns:
            Parameter in the API representation.
        """

        return {
            "group": self.group,
            "name": self.name,
            "label": self.label,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "exclusiveBounds": self.exclusive,
            "default": self.default,
            "description": self.description,
        }


@dataclass
class ParameterSpace:
    """
    The parameters of one model that may vary between agents.

    Args:
        parameters: Parameters an interaction may choose.
        fixed: Further parameters of the model and the values every agent
            runs with, for the description only.

    Returns:
    """

    parameters: list[Parameter]
    fixed: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Index the parameters by group and name.

        Args:

        Returns:
        """

        self.index = {(parameter.group, parameter.name): parameter for parameter in self.parameters}

        if len(self.index) != len(self.parameters):
            raise ValueError("A parameter space names one parameter twice.")

    def defaults(
        self,
    ) -> dict[str, dict[str, float]]:
        """
        Return the default value of every parameter.

        Args:

        Returns:
            Values keyed by group, then by name.
        """

        values: dict[str, dict[str, float]] = {}

        for parameter in self.parameters:
            values.setdefault(parameter.group, {})[parameter.name] = parameter.default

        return values

    def resolve(
        self,
        configuration: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Turn an agent's configuration into the parameter values it runs with.

        Args:
            configuration: The agent's configuration from the creation request:
                optional ``parameterSelection`` ("default" or "random"),
                ``randomSeed`` and ``parameters`` (values keyed by group, then
                by name, which take precedence over the selection).

        Returns:
            Dictionary with the ``selection``, the ``randomSeed`` (null unless
            drawn), the parameters set ``explicit``ly as "group.name", and the
            ``values`` of every parameter.
        """

        configuration = configuration or {}
        unknown = sorted(set(configuration) - set(CONFIGURATION_KEYS))

        if unknown:
            raise ParameterError(
                f"Unknown configuration keys: {', '.join(unknown)}. "
                f"Known: {', '.join(CONFIGURATION_KEYS)}."
            )

        selection = configuration.get("parameterSelection", "default")

        if selection not in PARAMETER_SELECTIONS:
            raise ParameterError(
                f"parameterSelection must be one of {', '.join(PARAMETER_SELECTIONS)}, got {selection!r}."
            )

        values = self.defaults()
        seed = None

        if selection == "random":
            seed = configuration.get("randomSeed")
            if seed is None:
                # Drawn here rather than left to the generator, so the record
                # names a seed that repeats the draw.
                seed = random.SystemRandom().randrange(2**31)
            if not isinstance(seed, int) or isinstance(seed, bool):
                raise ParameterError(f"randomSeed must be an integer, got {seed!r}.")
            generator = random.Random(seed)
            for parameter in self.parameters:
                values[parameter.group][parameter.name] = parameter.draw(generator)
        elif "randomSeed" in configuration:
            raise ParameterError("randomSeed applies only to parameterSelection random.")

        explicit = configuration.get("parameters") or {}
        set_explicitly = []

        if not isinstance(explicit, dict):
            raise ParameterError("parameters must be an object keyed by group, then by name.")

        for group, group_values in explicit.items():
            if not isinstance(group_values, dict):
                raise ParameterError(f"parameters.{group} must be an object keyed by parameter name.")
            for name, value in group_values.items():
                parameter = self.index.get((group, name))
                if parameter is None:
                    known = ", ".join(f"{g}.{n}" for g, n in self.index)
                    raise ParameterError(f"The model has no parameter {group}.{name}. Known: {known}.")
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ParameterError(f"{group}.{name} must be a number, got {value!r}.")
                if not parameter.admits(float(value)):
                    bounds = "(" if parameter.exclusive else "["
                    closing = ")" if parameter.exclusive else "]"
                    raise ParameterError(
                        f"{group}.{name} must lie in {bounds}{parameter.minimum}, "
                        f"{parameter.maximum}{closing}, got {value}."
                    )
                values[group][name] = float(value)
                set_explicitly.append(f"{group}.{name}")

        return {"selection": selection, "randomSeed": seed, "explicit": set_explicitly, "values": values}

    def describe(
        self,
    ) -> dict[str, Any]:
        """
        Describe the space for the model endpoint.

        Args:

        Returns:
            Parameter space in the API representation.
        """

        return {
            "parameters": [parameter.describe() for parameter in self.parameters],
            "fixed": self.fixed,
            "selections": list(PARAMETER_SELECTIONS),
        }
