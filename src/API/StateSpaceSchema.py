"""
Compilation of IBSSS state space descriptions into validating JSON Schemas.

The files in ``schema/interpersonal-behavior-state-space/`` follow the
Interpersonal Behavior State Space Schema (IBSSS). They *describe* a state
space, they do not *validate* a state vector: nothing in ``ipc.json`` rejects
``{"Theta": 400.0}``.

The ITP API specification requires one shared ``stateSpaceSchema`` per model
that validates both the experience vectors returned by the perception endpoint
and the behavior vectors submitted to the action endpoint. This module derives
that schema from the IBSSS description, so the two cannot drift apart.

Geometry constraints (diamond, circle, simplex) cannot be expressed in JSON
Schema. They are compiled into a separate list of checks that runs after schema
validation, and they are recorded in the schema under ``x-itp-geometry`` so a
client can see them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

STATE_SPACE_DIR = (
    Path(__file__).resolve().parents[2]
    / "schema"
    / "interpersonal-behavior-state-space"
)

# ITP state space identifier -> (IBSSS file, state space abbreviation).
STATE_SPACE_SOURCES: dict[str, tuple[str, str]] = {
    "ipc": ("ipc.json", "IPC"),
    "sasb": ("sasb.json", "SASBT"),
    "sasb_intransitive": ("sasb.json", "SASBI"),
    "ac": ("haetscher-et-al-preprint.json", "AC"),
    "fds": ("westermann-banisch-2025.json", "FDS"),
}

# Full turn of the circle, per angular unit.
ANGULAR_PERIODS: dict[str, float] = {
    "degree": 360.0,
    "radian": 2.0 * 3.141592653589793,
}

GEOMETRY_TOLERANCE = 1e-9


def load_state_space_document(
    file_name: str,
) -> dict[str, Any]:
    """
    Load one IBSSS document from the schema directory.

    Args:
        file_name: File name of the IBSSS document.

    Returns:
        IBSSS document.
    """

    path = STATE_SPACE_DIR / file_name

    if not path.is_file():
        raise FileNotFoundError(f"Unknown state space document: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


class StateSpaceSchema:
    """
    Validating JSON Schema derived from one IBSSS state space description.

    Args:

    Returns:
    """

    def __init__(
        self,
        state_space: str,
        description: dict[str, Any],
        document: dict[str, Any],
    ) -> None:
        """
        Initialize a state space schema.

        Args:
            state_space: ITP state space identifier, for example "ipc".
            description: IBSSS description of one state space.
            document: Complete IBSSS document the description was taken from.

        Returns:
        """

        self.state_space = state_space
        self.description = description
        self.document = document

        self.dimensions = self._collect_dimensions()
        self.geometry_checks = self._compile_geometry_checks()
        self.json_schema = self._compile_json_schema()

        self.validator = Draft202012Validator(self.json_schema)

    @classmethod
    def from_state_space(
        cls,
        state_space: str,
    ) -> StateSpaceSchema:
        """
        Build the schema for a known ITP state space identifier.

        Args:
            state_space: ITP state space identifier, for example "ipc".

        Returns:
            State space schema.
        """

        if state_space not in STATE_SPACE_SOURCES:
            raise ValueError(f"No IBSSS description known for: {state_space}")

        file_name, abbreviation = STATE_SPACE_SOURCES[state_space]
        document = load_state_space_document(file_name)

        descriptions = [
            candidate
            for candidate in document["stateSpaces"]
            if candidate.get("abbreviation") == abbreviation
        ]

        if not descriptions:
            raise ValueError(
                f"State space {abbreviation} is not described in {file_name}."
            )

        return cls(
            state_space=state_space,
            description=descriptions[0],
            document=document,
        )

    @property
    def dimension_names(self) -> tuple[str, ...]:
        """
        Return the dimension abbreviations of the state space.

        Args:

        Returns:
            Dimension abbreviations.
        """

        return tuple(self.dimensions)

    def validate_vector(
        self,
        vector: dict[str, Any],
    ) -> list[dict[str, str]]:
        """
        Validate a state vector against the compiled schema and its geometry.

        Args:
            vector: State vector keyed by dimension abbreviation.

        Returns:
            Validation errors in the problem-details error format. Empty if the
            vector is valid.
        """

        errors = [
            {
                "path": "/" + "/".join(str(part) for part in error.absolute_path),
                "code": error.validator,
                "message": error.message,
            }
            for error in sorted(
                self.validator.iter_errors(vector),
                key=lambda error: list(error.absolute_path),
            )
        ]

        if errors:
            return errors

        return self._check_geometry(vector=vector)

    def describe(
        self,
    ) -> dict[str, Any]:
        """
        Describe the state space for the model endpoint.

        Args:

        Returns:
            State space description including the compiled JSON Schema.
        """

        return {
            "stateSpace": self.state_space,
            "abbreviation": self.description.get("abbreviation"),
            "caption": self.description.get("caption"),
            "type": self.description.get("type"),
            "dimensions": list(self.dimension_names),
            "stateSpaceSchema": self.json_schema,
            "stateSpaceDescription": self.description,
            "stateSpaceDescriptionSource": {
                "caption": self.document.get("caption"),
                "author": self.document.get("author"),
                "version": self.document.get("version"),
            },
        }

    def _collect_dimensions(
        self,
    ) -> dict[str, dict[str, Any]]:
        """
        Collect the dimensions of the state space, keyed by abbreviation.

        Args:

        Returns:
            Dimensions of the state space.
        """

        coordinates = self.description["coordinates"]
        system = coordinates["system"]

        if system == "polar":
            dimensions = [coordinates["angle"]]

            if "radius" in coordinates:
                dimensions.append(coordinates["radius"])

            return {dimension["abbreviation"]: dimension for dimension in dimensions}

        if system in ("cartesian", "angular"):
            return {
                dimension["abbreviation"]: dimension
                for dimension in coordinates["dimensions"]
            }

        raise ValueError(f"Unsupported coordinate system: {system}")

    def _compile_json_schema(
        self,
    ) -> dict[str, Any]:
        """
        Compile the state space description into a validating JSON Schema.

        Args:

        Returns:
            JSON Schema for one state vector of this state space.
        """

        is_discrete = self.description["type"] == "discrete"

        properties = {
            abbreviation: self._compile_dimension_schema(
                dimension=dimension,
                is_discrete=is_discrete,
            )
            for abbreviation, dimension in self.dimensions.items()
        }

        schema: dict[str, Any] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": self.description.get("caption", self.state_space),
            "description": self.description.get("description", ""),
            "type": "object",
            "required": list(self.dimensions),
            "additionalProperties": False,
            "properties": properties,
        }

        if self.geometry_checks:
            schema["x-itp-geometry"] = self.description.get("geometry")

        return schema

    def _compile_dimension_schema(
        self,
        dimension: dict[str, Any],
        is_discrete: bool,
    ) -> dict[str, Any]:
        """
        Compile one IBSSS dimension into a JSON Schema property.

        Args:
            dimension: IBSSS dimension description.
            is_discrete: Whether the state space is discrete.

        Returns:
            JSON Schema for one dimension.
        """

        schema: dict[str, Any] = {
            "title": dimension.get("caption", dimension["abbreviation"]),
        }

        if "description" in dimension:
            schema["description"] = dimension["description"]

        if "unit" in dimension:
            return {
                **schema,
                **self._compile_angular_bounds(dimension=dimension),
            }

        schema["type"] = "integer" if is_discrete else "number"
        schema.update(self._compile_numeric_bounds(value_range=dimension["range"]))

        return schema

    def _compile_angular_bounds(
        self,
        dimension: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Compile the bounds of an angular dimension.

        An angular dimension is periodic, so the upper bound is exclusive: for
        degrees, 360 is the same state as 0 and only one of them may be valid.

        Args:
            dimension: IBSSS angular dimension description.

        Returns:
            JSON Schema fragment bounding the angular dimension.
        """

        unit = dimension["unit"]

        if unit not in ANGULAR_PERIODS:
            raise ValueError(f"Unsupported angular unit: {unit}")

        return {
            "type": "number",
            "minimum": 0,
            "exclusiveMaximum": ANGULAR_PERIODS[unit],
            "x-itp-unit": unit,
        }

    def _compile_numeric_bounds(
        self,
        value_range: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Compile an IBSSS range into JSON Schema bounds.

        Args:
            value_range: IBSSS numeric or integer range.

        Returns:
            JSON Schema fragment bounding one dimension.
        """

        bounds: dict[str, Any] = {}

        minimum = value_range["minimum"]
        maximum = value_range["maximum"]

        if minimum != "-infinity":
            key = (
                "minimum"
                if value_range.get("minimumInclusive", True)
                else "exclusiveMinimum"
            )
            bounds[key] = minimum

        if maximum != "infinity":
            key = (
                "maximum"
                if value_range.get("maximumInclusive", True)
                else "exclusiveMaximum"
            )
            bounds[key] = maximum

        return bounds

    def _compile_geometry_checks(
        self,
    ) -> list[dict[str, Any]]:
        """
        Compile the IBSSS geometry into checks that run after schema validation.

        Args:

        Returns:
            Geometry checks. Empty if the geometry restricts nothing.
        """

        geometry = self.description.get("geometry")

        if geometry is None:
            return []

        shape = geometry["shape"]

        if shape == "box":
            return []

        if shape == "diamond":
            return [
                {
                    "type": "manhattanDistance",
                    "center": geometry["center"],
                    "operator": "<=",
                    "value": geometry["radius"],
                }
            ]

        if shape in ("circle", "disk"):
            return [
                {
                    "type": "euclideanDistance",
                    "center": geometry["center"],
                    "operator": "=" if shape == "circle" else "<=",
                    "value": geometry["radius"],
                }
            ]

        if shape == "constrained":
            return list(geometry["constraints"])

        raise ValueError(f"Unsupported geometry shape: {shape}")

    def _check_geometry(
        self,
        vector: dict[str, Any],
    ) -> list[dict[str, str]]:
        """
        Check a state vector against the geometry constraints of the space.

        Args:
            vector: State vector keyed by dimension abbreviation.

        Returns:
            Geometry errors in the problem-details error format.
        """

        errors: list[dict[str, str]] = []

        for constraint in self.geometry_checks:
            message = self._check_constraint(
                constraint=constraint,
                vector=vector,
            )

            if message is not None:
                errors.append(
                    {
                        "path": "/",
                        "code": constraint["type"],
                        "message": message,
                    }
                )

        return errors

    def _check_constraint(
        self,
        constraint: dict[str, Any],
        vector: dict[str, Any],
    ) -> str | None:
        """
        Check one geometry constraint.

        Args:
            constraint: Geometry constraint.
            vector: State vector keyed by dimension abbreviation.

        Returns:
            Error message, or None if the constraint holds.
        """

        constraint_type = constraint["type"]

        if constraint_type == "sumEquals":
            total = sum(vector[name] for name in constraint["dimensions"])

            return self._compare(
                left=total,
                operator="=",
                right=constraint["value"],
                label=f"Sum over {list(constraint['dimensions'])}",
            )

        if constraint_type == "weightedSum":
            total = sum(
                term["weight"] * vector[term["dimension"]]
                for term in constraint["terms"]
            )

            return self._compare(
                left=total,
                operator=constraint["operator"],
                right=constraint["value"],
                label="Weighted sum over the state vector",
            )

        if constraint_type == "manhattanDistance":
            distance = sum(
                abs(vector[name] - center)
                for name, center in constraint["center"].items()
            )

            return self._compare(
                left=distance,
                operator=constraint["operator"],
                right=constraint["value"],
                label="Manhattan distance from the center of the state space",
            )

        if constraint_type == "euclideanDistance":
            distance = (
                sum(
                    (vector[name] - center) ** 2
                    for name, center in constraint["center"].items()
                )
                ** 0.5
            )

            return self._compare(
                left=distance,
                operator=constraint["operator"],
                right=constraint["value"],
                label="Euclidean distance from the center of the state space",
            )

        raise ValueError(f"Unsupported geometry constraint: {constraint_type}")

    def _compare(
        self,
        left: float,
        operator: str,
        right: float,
        label: str,
    ) -> str | None:
        """
        Compare two values using an IBSSS constraint operator.

        Args:
            left: Value computed from the state vector.
            operator: IBSSS comparison operator.
            right: Value required by the constraint.
            label: Readable name of the computed value.

        Returns:
            Error message, or None if the comparison holds.
        """

        comparisons = {
            "=": lambda: abs(left - right) <= GEOMETRY_TOLERANCE,
            "<": lambda: left < right - GEOMETRY_TOLERANCE,
            "<=": lambda: left <= right + GEOMETRY_TOLERANCE,
            ">": lambda: left > right + GEOMETRY_TOLERANCE,
            ">=": lambda: left >= right - GEOMETRY_TOLERANCE,
        }

        if operator not in comparisons:
            raise ValueError(f"Unsupported constraint operator: {operator}")

        if comparisons[operator]():
            return None

        return f"{label} is {left}, but the state space requires {operator} {right}."
