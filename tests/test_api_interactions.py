"""
Tests of the API behaviors added for the PerTRAIN client.

Two different formal models in one interaction, the model each agent runs,
ending an interaction early with its record kept, the record opened at
creation, and the answer a client gets after a server restart. Every test runs
in-process through FastAPI's test client, so no port is involved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.API.APISpecification import APISpecification
from src.converter.ConverterRegistry import make_default_converter_registry
from src.run_model_api import make_catalogue

PREFIX = "/api/v1"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """
    Serve a fresh API that writes its records below a temporary directory.

    Args:
        tmp_path: Temporary directory from pytest.

    Returns:
        Test client of the API.
    """

    api = APISpecification(
        catalogue=make_catalogue(),
        converter=make_default_converter_registry(),
        results_root=tmp_path,
    )

    return TestClient(api.app)


def create(client: TestClient, **request) -> dict:
    """
    Create an interaction and return the response body.

    Args:
        client: Test client of the API.
        **request: Creation request.

    Returns:
        Response body.
    """

    response = client.post(f"{PREFIX}/interactions", json=request)
    assert response.status_code == 201, response.json()

    return response.json()


def bearer(body: dict) -> dict[str, str]:
    """
    Return the authorization header for the token of a creation response.

    Args:
        body: Creation response.

    Returns:
        Request headers.
    """

    return {"Authorization": f"Bearer {body['interactionToken']}"}


def test_two_different_models_interact(client: TestClient, tmp_path: Path) -> None:
    body = create(
        client,
        modelId="lassi",
        numberOfTurns=6,
        persistence={"enabled": True},
        agents={"A": {"type": "model"}, "B": {"type": "model", "modelId": "dummy-ipc"}},
    )

    assert body["status"] == "completed"
    assert body["agents"]["A"]["model"]["id"] == "lassi"
    assert body["agents"]["A"]["stateSpace"] == "ac"
    assert body["agents"]["B"]["model"]["id"] == "dummy-ipc"
    assert body["agents"]["B"]["stateSpace"] == "ipc"

    results = client.get(
        f"{PREFIX}/interactions/{body['sessionId']}/results",
        headers=bearer(body),
    ).json()

    # Every behavior crosses state spaces, so each turn leaves an original and
    # a converted message.
    assert len(results["itpMessages"]) == 12
    assert len(list((tmp_path / "results" / results["resultsFolder"]).glob("message_*"))) == 12


def test_pair_without_converter_is_rejected(client: TestClient) -> None:
    response = client.post(
        f"{PREFIX}/interactions",
        json={
            "modelId": "lassi",
            "numberOfTurns": 4,
            "agents": {
                "A": {"type": "model"},
                "B": {"type": "model", "modelId": "dummy-sasb"},
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "noConverter"


def test_human_agent_takes_no_model(client: TestClient) -> None:
    response = client.post(
        f"{PREFIX}/interactions",
        json={
            "modelId": "lassi",
            "numberOfTurns": 4,
            "agents": {
                "A": {"type": "human", "modelId": "lassi"},
                "B": {"type": "model"},
            },
        },
    )

    assert response.status_code == 422


def test_turn_limit_of_every_model_applies(client: TestClient) -> None:
    # lassi allows at most 500 turns, dummy-ipc 1000.
    response = client.post(
        f"{PREFIX}/interactions",
        json={
            "modelId": "dummy-ipc",
            "numberOfTurns": 600,
            "agents": {
                "A": {"type": "model"},
                "B": {"type": "model", "modelId": "lassi"},
            },
        },
    )

    assert response.status_code == 422


def test_ending_early_keeps_the_record(client: TestClient, tmp_path: Path) -> None:
    body = create(
        client,
        modelId="lassi",
        numberOfTurns=10,
        persistence={"enabled": True},
        startingAgentRole="B",
        agents={"A": {"type": "human"}, "B": {"type": "model"}},
    )

    assert body["agents"]["A"]["model"] is None

    session = body["sessionId"]
    agent = body["agents"]["A"]["agentId"]
    headers = bearer(body)

    # The record exists before anything has happened.
    status = client.get(f"{PREFIX}/interactions/{session}", headers=headers).json()
    assert status["status"] == "waitingForRegistration"

    client.post(f"{PREFIX}/interactions/{session}/agents/{agent}/register", json={}, headers=headers)
    perception = client.get(
        f"{PREFIX}/interactions/{session}/agents/{agent}/perception",
        headers=headers,
    ).json()
    client.post(
        f"{PREFIX}/interactions/{session}/agents/{agent}/actions",
        json={
            "actionId": "action-1",
            "turn": perception["turn"],
            "behavior": {axis: 4 for axis in perception["experience"]},
        },
        headers=headers,
    )

    ended = client.post(f"{PREFIX}/interactions/{session}/end", headers=headers).json()
    assert ended["status"] == "terminated"

    results = client.get(f"{PREFIX}/interactions/{session}/results", headers=headers).json()
    folder = tmp_path / "results" / results["resultsFolder"]
    record = json.loads((folder / "interaction.json").read_text())

    assert record["status"] == "terminated"
    assert record["endReason"] == "terminatedByClient"
    assert record["itpMessageCount"] == 3
    assert "turns" not in record
    assert len(list(folder.glob("message_*"))) == 3


def test_record_is_opened_at_creation(client: TestClient, tmp_path: Path) -> None:
    create(
        client,
        modelId="lassi",
        numberOfTurns=4,
        persistence={"enabled": True},
        agents={"A": {"type": "human"}, "B": {"type": "model"}},
    )

    (record_file,) = (tmp_path / "results").glob("*/interaction.json")
    record = json.loads(record_file.read_text())

    assert record["status"] == "waitingForRegistration"
    assert record["endedAt"] is None
    assert record["agents"]["B"]["model"]["id"] == "lassi"


def test_nothing_is_written_without_persistence(client: TestClient, tmp_path: Path) -> None:
    create(
        client,
        modelId="lassi",
        numberOfTurns=4,
        agents={"A": {"type": "model"}, "B": {"type": "model"}},
    )

    assert not (tmp_path / "results").exists()


def test_end_without_token_says_how_to_send_it(client: TestClient) -> None:
    body = create(
        client,
        modelId="lassi",
        numberOfTurns=4,
        agents={"A": {"type": "human"}, "B": {"type": "model"}},
    )

    response = client.post(f"{PREFIX}/interactions/{body['sessionId']}/end")

    assert response.status_code == 401
    assert "Authorization: Bearer" in response.json()["detail"]


def test_unknown_interaction_after_restart(client: TestClient) -> None:
    # A second API stands in for the restarted server: it never saw the
    # interaction or its token.
    body = create(
        client,
        modelId="lassi",
        numberOfTurns=4,
        agents={"A": {"type": "human"}, "B": {"type": "model"}},
    )

    restarted = TestClient(
        APISpecification(
            catalogue=make_catalogue(),
            converter=make_default_converter_registry(),
        ).app
    )

    response = restarted.get(
        f"{PREFIX}/interactions/{body['sessionId']}",
        headers=bearer(body),
    )

    assert response.status_code == 404
    assert response.json()["type"].endswith("interaction-not-found")
    assert "restart" in response.json()["detail"]

    # A client that lost its token as well is told the same, not 401.
    response = restarted.post(f"{PREFIX}/interactions/{body['sessionId']}/end")

    assert response.status_code == 404


def test_mixed_models_check_each_agent_against_its_own_model(client: TestClient) -> None:
    body = create(
        client,
        modelId="dummy-ipc",
        numberOfTurns=4,
        agents={"A": {"type": "model"}, "B": {"type": "model", "modelId": "lassi"}},
    )

    assert body["agents"]["B"]["model"]["id"] == "lassi"

    response = client.post(
        f"{PREFIX}/interactions",
        json={
            "modelId": "lassi",
            "numberOfTurns": 4,
            "agents": {"A": {"type": "human", "modelVersion": "0.2.0"}, "B": {"type": "model"}},
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["path"] == "/agents/A/modelVersion"


def test_api_key_header_passes_preflight(client: TestClient) -> None:
    response = client.options(
        f"{PREFIX}/models",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )

    assert response.status_code == 200
    assert "X-API-Key" in response.headers["access-control-allow-headers"]
