from __future__ import annotations

import math

from src.converter.BaseConverter import BaseConverter

# NOTE: These converters map values numerically between state spaces but do NOT
# enforce geometry constraints (e.g. valid regions, radius bounds, or lattice
# structure of the target space). Geometry constraints are not implemented yet.


def _clip(
    value: float,
    lower: float,
    upper: float,
) -> float:
    """
    Clip a value to a closed interval.

    Args:
        value: Value to clip.
        lower: Lower bound.
        upper: Upper bound.

    Returns:
        Clipped value.
    """

    return max(lower, min(upper, value))


def _round_int(
    value: float,
) -> int:
    """
    Round a value to the nearest integer.

    Args:
        value: Value to round.

    Returns:
        Rounded integer.
    """

    return int(round(value))


def _cartesian_to_ipc(
    agency: float,
    communion: float,
) -> dict[str, float]:
    """
    Convert normalized agency-communion coordinates to IPC polar coordinates.

    Args:
        agency: Normalized agency value.
        communion: Normalized communion value.

    Returns:
        IPC values.
    """

    theta = math.degrees(math.atan2(agency, communion)) % 360
    radius = math.sqrt(agency**2 + communion**2)
    radius = _clip(radius, 0.0, 1.0)

    return {
        "Theta": float(theta),
        "R": float(radius),
    }


def _ipc_to_cartesian(
    theta: float,
    radius: float,
) -> dict[str, float]:
    """
    Convert IPC polar coordinates to normalized agency-communion coordinates.

    Args:
        theta: IPC angle in degrees.
        radius: IPC radius.

    Returns:
        Normalized agency-communion coordinates.
    """

    theta_radian = math.radians(theta)
    radius = _clip(radius, 0.0, 1.0)

    communion = radius * math.cos(theta_radian)
    agency = radius * math.sin(theta_radian)

    return {
        "agency": agency,
        "communion": communion,
    }


class ACToIPCConverter(BaseConverter):
    """
    Converter from discrete agency-communion states to IPC polar states.

    Args:

    Returns:
    """

    def __init__(self) -> None:
        """
        Initialize the converter.

        Args:

        Returns:
        """

        self.source = "ac"
        self.target = "ipc"

    def convert(
        self,
        source_input: dict[str, float],
        context: str | None = None,
    ) -> dict[str, float]:
        """
        Convert AC values to IPC values.

        Args:
            source_input: AC values with A and C on a 1-5 scale.
            context: Optional string describing the interaction context.

        Returns:
            IPC values with Theta and R.
        """

        agency = (source_input["A"] - 3) / 2
        communion = (source_input["C"] - 3) / 2

        return _cartesian_to_ipc(
            agency=agency,
            communion=communion,
        )


class IPCToACConverter(BaseConverter):
    """
    Converter from IPC polar states to discrete agency-communion states.

    Args:

    Returns:
    """

    def __init__(self) -> None:
        """
        Initialize the converter.

        Args:

        Returns:
        """

        self.source = "ipc"
        self.target = "ac"

    def convert(
        self,
        source_input: dict[str, float],
        context: str | None = None,
    ) -> dict[str, float]:
        """
        Convert IPC values to AC values.

        Args:
            source_input: IPC values with Theta and R.
            context: Optional string describing the interaction context.

        Returns:
            AC values with A and C on a 1-5 scale.
        """

        coordinates = _ipc_to_cartesian(
            theta=source_input["Theta"],
            radius=source_input["R"],
        )

        agency = 3 + 2 * coordinates["agency"]
        communion = 3 + 2 * coordinates["communion"]

        return {
            "A": _round_int(_clip(agency, 1, 5)),
            "C": _round_int(_clip(communion, 1, 5)),
        }


class SASBToIPCConverter(BaseConverter):
    """
    Converter from SASB states to IPC polar states.

    Args:

    Returns:
    """

    def __init__(self) -> None:
        """
        Initialize the converter.

        Args:

        Returns:
        """

        self.source = "sasb"
        self.target = "ipc"

    def convert(
        self,
        source_input: dict[str, float],
        context: str | None = None,
    ) -> dict[str, float]:
        """
        Convert SASB values to IPC values.

        Args:
            source_input: SASB values with Aff and Int.
            context: Optional string describing the interaction context.

        Returns:
            IPC values with Theta and R.
        """

        communion = source_input["Aff"] / 2
        agency = -source_input["Int"] / 2

        return _cartesian_to_ipc(
            agency=agency,
            communion=communion,
        )


class IPCToSASBConverter(BaseConverter):
    """
    Converter from IPC polar states to SASB states.

    Args:

    Returns:
    """

    def __init__(self) -> None:
        """
        Initialize the converter.

        Args:

        Returns:
        """

        self.source = "ipc"
        self.target = "sasb"

    def convert(
        self,
        source_input: dict[str, float],
        context: str | None = None,
    ) -> dict[str, float]:
        """
        Convert IPC values to SASB values.

        Args:
            source_input: IPC values with Theta and R.
            context: Optional string describing the interaction context.

        Returns:
            SASB values with Aff and Int.
        """

        coordinates = _ipc_to_cartesian(
            theta=source_input["Theta"],
            radius=source_input["R"],
        )

        affiliation = 2 * coordinates["communion"]
        interdependence = -2 * coordinates["agency"]

        return {
            "Aff": _round_int(_clip(affiliation, -2, 2)),
            "Int": _round_int(_clip(interdependence, -2, 2)),
        }