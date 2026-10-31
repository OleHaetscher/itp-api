"""
Tests of model parameters chosen per agent.

A model publishes the parameters an interaction may choose, and an agent's
configuration selects the defaults, a seeded uniform draw, or explicit values.
The values used reach the model instance, the API responses and the record.
Every test runs in-process through FastAPI's test client, so no port is
involved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.API.APISpecification import APISpecification
from src.converter.ConverterRegistry import make_default_converter_registry
from src.formalmodels.LASSIFormalModel import lassi_parameter_space
from src.formalmodels.ParameterSpace import ParameterError
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


def create_lassi(client: TestClient, configuration: dict | None, **extra) -> dict:
    """
    Create a human-model interaction with a LASSI agent B.

    Args:
        client: Test client of the API.
        configuration: Configuration of agent B.
        **extra: Further fields of the creation request.

    Returns:
        Response, as status code and body.
    """

    agent_b = {"type": "model"}
    if configuration is not None:
        agent_b["configuration"] = configuration
    response = client.post(
        f"{PREFIX}/interactions",
        json={
            "modelId": "lassi",
            "numberOfTurns": 4,
            "agents": {"A": {"type": "human"}, "B": agent_b},
            **extra,
        },
    )

    return {"status": response.status_code, "body": response.json()}


def test_the_catalogue_publishes_the_lassi_parameters(api: APISpecification) -> None:
    client = TestClient(api.app)

    space = client.get(f"{PREFIX}/models/lassi").json()["parameterSpace"]

    assert [(p["group"], p["name"]) for p in space["parameters"]] == [
        ("A", "BD"),
        ("A", "IR"),
        ("C", "BD"),
        ("C", "IR"),
    ]
    assert {p["name"]: (p["minimum"], p["maximum"], p["exclusiveBounds"]) for p in space["parameters"]} == {
        "BD": (1.0, 7.0, True),
        "IR": (-1.0, 1.0, False),
    }
    assert {"tau", "lambda_relax"} <= set(space["fixed"]["A"])
    assert client.get(f"{PREFIX}/models/dummy-ipc").json()["parameterSpace"] is None


def test_without_configuration_an_agent_runs_the_configured_defaults(api: APISpecification) -> None:
    created = create_lassi(TestClient(api.app), configuration=None)

    assert created["status"] == 201
    assert created["body"]["agents"]["B"]["parameters"] == {
        "selection": "default",
        "randomSeed": None,
        "explicit": [],
        "values": lassi_parameter_space().defaults(),
    }
    assert "parameters" not in created["body"]["agents"]["A"]


def test_a_seeded_draw_repeats_and_reaches_the_model(api: APISpecification) -> None:
    client = TestClient(api.app)

    first = create_lassi(client, {"parameterSelection": "random", "randomSeed": 11})["body"]
    second = create_lassi(client, {"parameterSelection": "random", "randomSeed": 11})["body"]
    values = first["agents"]["B"]["parameters"]["values"]

    assert values == second["agents"]["B"]["parameters"]["values"]
    assert values != lassi_parameter_space().defaults()
    for axis in values.values():
        assert 1.0 < axis["BD"] < 7.0
        assert -1.0 <= axis["IR"] <= 1.0

    model = api.registry.interactions[first["sessionId"]].agents["B"].model
    for dimension, axis in model.axes.items():
        assert axis.parameters()["BD"] == pytest.approx(values[dimension]["BD"])
        assert axis.IR == pytest.approx(values[dimension]["IR"])


def test_an_unseeded_draw_names_the_seed_that_repeats_it(api: APISpecification) -> None:
    client = TestClient(api.app)

    drawn = create_lassi(client, {"parameterSelection": "random"})["body"]["agents"]["B"]["parameters"]
    repeated = create_lassi(client, {"parameterSelection": "random", "randomSeed": drawn["randomSeed"]})

    assert isinstance(drawn["randomSeed"], int)
    assert repeated["body"]["agents"]["B"]["parameters"]["values"] == drawn["values"]


def test_explicit_values_take_precedence_over_the_draw(api: APISpecification) -> None:
    configuration = {"parameterSelection": "random", "randomSeed": 11, "parameters": {"A": {"IR": -0.4}}}

    values = create_lassi(TestClient(api.app), configuration)["body"]["agents"]["B"]["parameters"]["values"]
    drawn = lassi_parameter_space().resolve({"parameterSelection": "random", "randomSeed": 11})["values"]

    assert values["A"]["IR"] == -0.4
    assert create_lassi(TestClient(api.app), configuration)["body"]["agents"]["B"]["parameters"]["explicit"] == ["A.IR"]
    assert values["A"]["BD"] == drawn["A"]["BD"]
    assert values["C"] == drawn["C"]


@pytest.mark.parametrize(
    "configuration, message",
    [
        ({"parameters": {"A": {"BD": 7}}}, "A.BD must lie in"),
        ({"parameters": {"A": {"IR": 1.5}}}, "A.IR must lie in"),
        ({"parameters": {"X": {"BD": 3}}}, "no parameter X.BD"),
        ({"parameters": {"A": {"BD": "high"}}}, "must be a number"),
        ({"parameterSelection": "grid"}, "parameterSelection must be one of"),
        ({"randomSeed": 3}, "randomSeed applies only"),
        ({"strategy": "adaptive"}, "Unknown configuration keys: strategy"),
    ],
)
def test_a_configuration_outside_the_space_is_refused(
    api: APISpecification,
    configuration: dict,
    message: str,
) -> None:
    created = create_lassi(TestClient(api.app), configuration)

    assert created["status"] == 422
    assert message in created["body"]["detail"]


def test_a_human_or_a_model_without_parameters_takes_no_configuration(api: APISpecification) -> None:
    client = TestClient(api.app)

    human = client.post(
        f"{PREFIX}/interactions",
        json={
            "modelId": "lassi",
            "numberOfTurns": 2,
            "agents": {"A": {"type": "human", "configuration": {"parameterSelection": "random"}}, "B": {"type": "model"}},
        },
    )
    dummy = client.post(
        f"{PREFIX}/interactions",
        json={
            "modelId": "dummy-ipc",
            "numberOfTurns": 2,
            "agents": {"A": {"type": "model", "configuration": {"parameterSelection": "random"}}, "B": {"type": "model"}},
        },
    )

    assert human.status_code == 422
    assert "only a model agent takes a configuration" in human.json()["detail"]
    assert dummy.status_code == 422
    assert "has no parameters to configure" in dummy.json()["detail"]


def test_two_lassi_agents_with_different_parameters_are_recorded(api: APISpecification, tmp_path: Path) -> None:
    response = TestClient(api.app).post(
        f"{PREFIX}/interactions",
        json={
            "modelId": "lassi",
            "numberOfTurns": 6,
            "persistence": {"enabled": True},
            "clientRequestId": "pertrain-session-1",
            "agents": {
                "A": {"type": "model", "configuration": {"parameters": {"A": {"BD": 2.5, "IR": 0.9}}}},
                "B": {"type": "model", "configuration": {"parameterSelection": "random", "randomSeed": 3}},
            },
        },
    )
    body = response.json()
    record = json.loads(next((tmp_path / "results").iterdir()).joinpath("interaction.json").read_text())

    assert response.status_code == 201
    assert body["status"] == "completed"
    assert record["clientRequestId"] == "pertrain-session-1"
    assert record["agents"]["A"]["parameters"]["values"]["A"] == {"BD": 2.5, "IR": 0.9}
    assert record["agents"]["B"]["parameters"] == body["agents"]["B"]["parameters"]


def test_parameters_must_be_keyed_by_group_then_name() -> None:
    space = lassi_parameter_space()

    with pytest.raises(ParameterError, match="must be an object"):
        space.resolve({"parameters": {"A": 3}})
