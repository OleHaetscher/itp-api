"""
Tests of the seed of each model agent's own random draws.

A model's own randomness (LASSI's draw of the expressed state, the dummy
models' starting state) runs on a seed the API draws per model agent. The seed
is reported for every model agent, with or without a parameter space, and it
repeats the model's draws. Every test runs in-process, so no port is involved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.API.APISpecification import APISpecification
from src.converter.ConverterRegistry import make_default_converter_registry
from src.formalmodels.DummyFormalModels import DummyIPCFormalModel
from src.formalmodels.LASSIFormalModel import LASSIFormalModel
from src.run_model_api import make_catalogue

PREFIX = "/api/v1"


@pytest.fixture
def api(tmp_path: Path) -> APISpecification:
    """
    Serve a fresh API that writes its records below a temporary directory.

    Args:
        tmp_path: Temporary directory from pytest.

    Returns:
        API specification.
    """

    return APISpecification(
        catalogue=make_catalogue(),
        converter=make_default_converter_registry(),
        results_root=tmp_path,
    )


def lassi_draws(seed: int | None, steps: int = 12) -> list[dict[str, float]]:
    """
    Run LASSI against a fixed partner and collect the expressed states.

    Args:
        seed: Seed of the model's draws.
        steps: Number of exchanges.

    Returns:
        Expressed state after every exchange.
    """

    model = LASSIFormalModel(model_id="lassi-agent", random_seed=seed)
    states = []
    for _ in range(steps):
        model.integrate_numerical_input({"A": 6.0, "C": 2.0})
        states.append(dict(model.generate_numerical_output()))
    return states


def test_the_same_seed_repeats_lassis_draws() -> None:
    assert lassi_draws(41) == lassi_draws(41)


def test_different_seeds_give_different_lassi_draws() -> None:
    assert any(lassi_draws(41) != lassi_draws(seed) for seed in range(42, 47))


def test_the_same_seed_repeats_the_dummy_models_start() -> None:
    first = DummyIPCFormalModel(model_id="a", random_seed=7).state
    second = DummyIPCFormalModel(model_id="b", random_seed=7).state

    assert first == second


def test_every_model_agent_reports_its_seed_in_the_response_and_the_record(
    api: APISpecification,
    tmp_path: Path,
) -> None:
    response = TestClient(api.app).post(
        f"{PREFIX}/interactions",
        json={
            "modelId": "lassi",
            "numberOfTurns": 4,
            "persistence": {"enabled": True},
            "agents": {
                "A": {"type": "model", "modelId": "dummy-ipc"},
                "B": {"type": "model", "configuration": {"parameterSelection": "random", "randomSeed": 3}},
            },
        },
    )
    body = response.json()
    record = json.loads(next((tmp_path / "results").iterdir()).joinpath("interaction.json").read_text())

    assert response.status_code == 201
    for role in ("A", "B"):
        seed = body["agents"][role]["modelSeed"]
        assert isinstance(seed, int) and 0 <= seed < 2**31
        assert record["agents"][role]["modelSeed"] == seed
    # The parameter draw keeps its own seed, apart from the model's draws.
    assert body["agents"]["B"]["parameters"]["randomSeed"] == 3


def test_a_human_agent_has_no_model_seed(api: APISpecification) -> None:
    response = TestClient(api.app).post(
        f"{PREFIX}/interactions",
        json={"modelId": "lassi", "numberOfTurns": 4, "agents": {"A": {"type": "human"}, "B": {"type": "model"}}},
    )
    agents = response.json()["agents"]

    assert "modelSeed" not in agents["A"]
    assert "modelSeed" in agents["B"]
