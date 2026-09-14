from __future__ import annotations

import math

from src.converter.BaseConverter import BaseConverter

# NOTE: These converters map values numerically between state spaces but do NOT
# enforce geometry constraints (e.g. valid regions, radius bounds, or lattice
# structure of the target space). Geometry constraints are not implemented yet.
#
# The one geometric case that is handled is the neutral center. A Cartesian
# space such as SASB or the agency-communion box contains its own center, and
# converting that center into the polar IPC space yields a radius of zero, where
# the angle is undefined. IPC includes that point and marks it by R = 0; Theta
# is then reported as NEUTRAL_CENTER_ANGLE by convention and carries no
# information. See schema/interpersonal-behavior-state-space/ipc.json.

# Angle reported for the IPC neutral center, where no angle is defined.
NEUTRAL_CENTER_ANGLE = 0.0

# Number of discrete states per agency-communion axis, with the midpoint and the
# distance from it to either end derived from it. The agency-communion state
# space is defined on 1 ... AC_NUM_STATES in
# schema/interpersonal-behavior-state-space/haetscher-et-al-preprint.json, and
# LASSIFormalModel is configured to the same number of states. Changing one of
# the three without the others silently rescales every converted message.
AC_NUM_STATES = 7
AC_MIDPOINT = (AC_NUM_STATES + 1) / 2
AC_HALF_RANGE = (AC_NUM_STATES - 1) / 2


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

    At the neutral center the angle is undefined, because every angle denotes
    the same state there. It is reported as NEUTRAL_CENTER_ANGLE rather than
    left to whatever atan2 returns for the origin, so the convention is visible
    rather than incidental.

    Args:
        agency: Normalized agency value.
        communion: Normalized communion value.

    Returns:
        IPC values.
    """

    radius = _clip(math.sqrt(agency**2 + communion**2), 0.0, 1.0)

    if radius == 0.0:
        return {
            "Theta": NEUTRAL_CENTER_ANGLE,
            "R": 0.0,
        }

    theta = math.degrees(math.atan2(agency, communion)) % 360

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

    A radius of zero maps onto the origin for every angle, which is the correct
    reading of the IPC neutral center: the angle carries no information there.

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
            source_input: AC values with A and C on a 1 ... AC_NUM_STATES scale.
            context: Optional string describing the interaction context.

        Returns:
            IPC values with Theta and R.
        """

        agency = (source_input["A"] - AC_MIDPOINT) / AC_HALF_RANGE
        communion = (source_input["C"] - AC_MIDPOINT) / AC_HALF_RANGE

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
            AC values with A and C on a 1 ... AC_NUM_STATES scale.
        """

        coordinates = _ipc_to_cartesian(
            theta=source_input["Theta"],
            radius=source_input["R"],
        )

        agency = AC_MIDPOINT + AC_HALF_RANGE * coordinates["agency"]
        communion = AC_MIDPOINT + AC_HALF_RANGE * coordinates["communion"]

        return {
            "A": _round_int(_clip(agency, 1, AC_NUM_STATES)),
            "C": _round_int(_clip(communion, 1, AC_NUM_STATES)),
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