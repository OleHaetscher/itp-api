"""
Conformance test of LASSIFormalModel against the handoff vectors.

The LASSI formal model exists three times: in the lassi_simulations repository,
here, and in the PerTRAIN production repository. They are separate
implementations rather than a shared package, and the numbers they produce feed
the same published claims, so they must not diverge.

tests/data/lassi_test_vectors.json is a copy of handoff/test_vectors.json from
lassi_simulations, generated there from the reference implementation. This test
runs every case through LASSIAxis and asserts every expected value to the stated
tolerance, plus every invariant listed in the file. Nothing detects a change in
the reference on its own: when the model changes there, the vectors are
regenerated and the new file is copied over this one, and a mismatch is a
blocker rather than a rounding question.

Run from the repository root::

    python -m pytest tests
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.formalmodels.LASSIFormalModel import LASSIAxis, to_itp_scale

VECTOR_PATH = Path(__file__).resolve().parent / "data" / "lassi_test_vectors.json"

# Tolerances of the invariants, which are stricter than the case tolerance.
# They are stated in the vector file as text, next to the values they apply to.
PROBABILITY_TOLERANCE = 1e-12
EXACTNESS_TOLERANCE = 1e-9


def load_vectors() -> dict[str, Any]:
    """
    Load the conformance vectors.

    Args:

    Returns:
        Vector file with its tolerance, invariants and cases.
    """

    return json.loads(VECTOR_PATH.read_text(encoding="utf-8"))


VECTORS = load_vectors()
CASES = VECTORS["cases"]
CASE_LABELS = [case["label"] for case in CASES]


def run_case(
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """
    Run one vector case through the model.

    The distribution before the exchange is the agent's own untilted repertoire,
    which the vectors denote by ``p_prev = "repertoire"`` rather than an inlined
    vector: an implementation that builds the repertoire wrongly fails on the
    very first case, which is the intent.

    Args:
        inputs: Inputs of one vector case.

    Returns:
        Step record of the update.
    """

    assert inputs["p_prev"] == "repertoire"

    axis = LASSIAxis(
        dimension="A",
        parameters={
            "name": "Test axis",
            "num_states": inputs["n_states"],
            "BD": inputs["BD_display"],
            "tau": inputs["tau"],
            "IR": inputs["IR"],
            "lambda_relax": inputs["lambda_relax"],
            "complementarity_direction": inputs["m"],
            # The vectors say nothing about the expressed state, which is drawn
            # from the updated distribution. Taking the mode keeps the case
            # deterministic without seeding the generator.
            "deterministic": True,
        },
    )

    assert axis.midpoint == inputs["s_bar"]

    partner_state = axis.to_internal_state(itp_state=inputs["s_other_display"])

    assert partner_state == inputs["s_other"]

    axis.update_probabilities(partner_state=partner_state)

    return axis.step_record()


@pytest.mark.parametrize("case", CASES, ids=CASE_LABELS)
def test_expected_values(
    case: dict[str, Any],
) -> None:
    """
    Assert every expected value of one case.

    Args:
        case: One vector case.

    Returns:
    """

    record = run_case(inputs=case["inputs"])
    expected = case["expected"]
    tolerance = VECTORS["tolerance"]

    for field, expected_value in expected.items():
        if field == "eta" and expected["eta_is_infinite"]:
            # An endpoint target is reached by an infinite tilt, which the
            # vector file cannot hold and stores as null. The point mass in
            # p_new is what the case actually pins down.
            assert not np.isfinite(record["eta"])
            continue

        if isinstance(expected_value, bool):
            assert record[field] is expected_value, field
            continue

        assert np.allclose(
            record[field],
            expected_value,
            rtol=0.0,
            atol=tolerance,
        ), field


@pytest.mark.parametrize("case", CASES, ids=CASE_LABELS)
def test_invariants(
    case: dict[str, Any],
) -> None:
    """
    Assert the invariants the model must satisfy on every case.

    Args:
        case: One vector case.

    Returns:
    """

    record = run_case(inputs=case["inputs"])
    inputs = case["inputs"]

    assert abs(record["p_new"].sum() - 1.0) < PROBABILITY_TOLERANCE
    assert (record["p_new"] >= 0.0).all()

    # The central claim of the model: the realised mean is the intended mean.
    assert abs(record["mu_realised"] - record["mu_t"]) < EXACTNESS_TOLERANCE

    assert record["IR_abs"] == abs(inputs["IR"])
    assert record["direction"] == (1.0 if inputs["IR"] >= 0.0 else -1.0)

    weights = (record["w_prior"], record["w_BD_eff"], record["w_IR_eff"])

    # Convexity is the no-clipping proof. If it fails, the mean can leave the
    # grid, and a clip would hide it rather than fix it.
    assert all(weight >= 0.0 for weight in weights)
    assert abs(sum(weights) - 1.0) < PROBABILITY_TOLERANCE

    assert record["state_min"] <= record["mu_t"] <= record["state_max"]
    assert abs(record["repertoire_mean"] - inputs["BD"]) < EXACTNESS_TOLERANCE

    if inputs["IR"] == 0.0 and record["mu_prev"] == record["BD"]:
        assert np.array_equal(record["p_new"], record["repertoire"])


@pytest.mark.parametrize("case", CASES, ids=CASE_LABELS)
def test_display_scale(
    case: dict[str, Any],
) -> None:
    """
    Assert that the internal grid maps onto the ITP scale 1 ... N.

    The vectors carry both scales, so they pin down the conversion as well as
    the update. A repository that got it wrong would still reproduce every
    expected value and exchange unusable ITP messages.

    Args:
        case: One vector case.

    Returns:
    """

    record = run_case(inputs=case["inputs"])
    num_states = case["inputs"]["n_states"]

    displayed = to_itp_scale(record["grid"], num_states)

    assert displayed[0] == 1.0
    assert displayed[-1] == float(num_states)
    assert np.allclose(
        to_itp_scale(record["BD"], num_states),
        case["inputs"]["BD_display"],
        rtol=0.0,
        atol=EXACTNESS_TOLERANCE,
    )
