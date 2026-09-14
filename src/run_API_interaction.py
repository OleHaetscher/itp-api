"""
Drive the ITP API from Python.

The primary client of the API is the JavaScript application. This runner does
the same thing from Python, so the endpoints can be exercised without a
browser: it creates interactions, registers participants, redeems an invitation
code, polls for perceptions, and submits behaviors.

Where a human participant would sit, a local formal model stands in. It takes
the experience vector out of a perception, integrates it, and submits its own
output as a behavior, which is exactly the loop the JavaScript application runs
around a human.

Start the API first, in another terminal::

    python -m src.run_model_api
"""

from __future__ import annotations

import threading
from typing import Any

from src.API.APIClient import APIClient, APIError
from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.formalmodels.DummyFormalModels import DummyIPCFormalModel

BASE_URL = "http://127.0.0.1:8001"
CONTEXT = "workplace_colleague_conversation"
POLL_WAIT_SECONDS = 10.0


def print_heading(
    heading: str,
) -> None:
    """
    Print a section heading.

    Args:
        heading: Text of the heading.

    Returns:
    """

    print(f"\n{heading}")
    print("-" * len(heading))


def run_participant_turns(
    client: APIClient,
    session_id: str,
    agent_id: str,
    model: BaseFormalModel,
    label: str,
) -> None:
    """
    Play one agent slot until the interaction ends.

    Args:
        client: API client holding the interaction token of that agent.
        session_id: Identifier of the interaction.
        agent_id: Identifier of the agent being played.
        model: Local model producing the behaviors of that agent.
        label: Name used when printing what the agent does.

    Returns:
    """

    cursor: str | None = None

    while True:
        perception = client.poll_perception(
            session_id=session_id,
            agent_id=agent_id,
            after=cursor,
            wait=POLL_WAIT_SECONDS,
        )

        state = perception["state"]

        if state == "interactionEnded":
            print(f"{label}: interaction ended ({perception['endReason']})")
            return

        if state == "pending":
            continue

        cursor = perception["cursor"]

        if perception.get("experience") is not None:
            print(f"{label}: perceives {perception['experience']}")
            model.integrate_numerical_input(
                numerical_input=perception["experience"],
                context=CONTEXT,
            )

        if not perception.get("actionRequired"):
            continue

        behavior = model.generate_numerical_output(context=CONTEXT)

        client.submit_action(
            session_id=session_id,
            agent_id=agent_id,
            turn=perception["turn"],
            behavior=behavior,
        )

        print(f"{label}: acts in turn {perception['turn']} with {behavior}")


def run_model_interaction(
    model_id: str = "dummy-ipc",
    number_of_turns: int = 6,
) -> dict[str, Any]:
    """
    Run an interaction in which both agents are formal models.

    The server plays both agents, so the client only creates the interaction
    and reads the result.

    Args:
        model_id: Identifier of the model both agents use.
        number_of_turns: Number of interaction turns.

    Returns:
        Results of the interaction.
    """

    print_heading("Model to model")

    client = APIClient(base_url=BASE_URL)

    interaction = client.create_interaction(
        model_id=model_id,
        number_of_turns=number_of_turns,
        agents={"A": {"type": "model"}, "B": {"type": "model"}},
        persistence=True,
        context=CONTEXT,
    )

    print(f"created {interaction['sessionId']}, status {interaction['status']}")

    results = client.get_results(session_id=interaction["sessionId"])

    for turn in results["turns"]:
        print(f"turn {turn['turn']}: {turn['actorAgentId'][:8]} {turn['behavior']}")

    print(f"ITP messages recorded: {len(results['itpMessages'])}")

    return results


def run_participant_interaction(
    model_id: str = "dummy-ipc",
    number_of_turns: int = 6,
) -> dict[str, Any]:
    """
    Run an interaction between a participant slot and a formal model.

    Args:
        model_id: Identifier of the model the model agent uses.
        number_of_turns: Number of interaction turns.

    Returns:
        Results of the interaction.
    """

    print_heading("Participant to model")

    client = APIClient(base_url=BASE_URL)

    interaction = client.create_interaction(
        model_id=model_id,
        number_of_turns=number_of_turns,
        agents={
            "A": {"type": "human", "displayName": "Participant A"},
            "B": {"type": "model"},
        },
        persistence=True,
        context=CONTEXT,
    )

    session_id = interaction["sessionId"]
    agent_id = interaction["agents"]["A"]["agentId"]

    client.register_agent(
        session_id=session_id,
        agent_id=agent_id,
        participant={"participantId": "participant-1042", "displayName": "Participant A"},
        client={"clientId": "python-runner"},
    )

    run_participant_turns(
        client=client,
        session_id=session_id,
        agent_id=agent_id,
        model=DummyIPCFormalModel(model_id=agent_id),
        label="A",
    )

    return client.get_results(session_id=session_id)


def run_two_participant_interaction(
    model_id: str = "dummy-ipc",
    number_of_turns: int = 6,
) -> dict[str, Any]:
    """
    Run an interaction between two participant slots joined by invitation code.

    Two independent clients are used, as two browser instances would be.

    Args:
        model_id: Identifier of the model defining the state space.
        number_of_turns: Number of interaction turns.

    Returns:
        Results of the interaction.
    """

    print_heading("Participant to participant")

    client_a = APIClient(base_url=BASE_URL)

    interaction = client_a.create_interaction(
        model_id=model_id,
        number_of_turns=number_of_turns,
        agents={
            "A": {"type": "human", "displayName": "Participant A"},
            "B": {"type": "human", "displayName": "Participant B"},
        },
        persistence=True,
        context=CONTEXT,
    )

    session_id = interaction["sessionId"]
    agent_a = interaction["agents"]["A"]["agentId"]
    invitation_code = interaction["invitation"]["code"]

    print(f"invitation code for the second participant: {invitation_code}")

    client_a.register_agent(
        session_id=session_id,
        agent_id=agent_a,
        participant={"participantId": "participant-1042"},
    )

    client_b = APIClient(base_url=BASE_URL)

    joined = client_b.join_interaction(
        invitation_code=invitation_code,
        participant={"participantId": "participant-2048"},
        client={"clientId": "python-runner-b"},
    )

    agent_b = joined["agent"]["agentId"]
    print(f"second participant joined as agent {agent_b[:8]}, status {joined['sessionStatus']}")

    thread_b = threading.Thread(
        target=run_participant_turns,
        kwargs={
            "client": client_b,
            "session_id": session_id,
            "agent_id": agent_b,
            "model": DummyIPCFormalModel(model_id=agent_b),
            "label": "B",
        },
        daemon=True,
    )
    thread_b.start()

    run_participant_turns(
        client=client_a,
        session_id=session_id,
        agent_id=agent_a,
        model=DummyIPCFormalModel(model_id=agent_a),
        label="A",
    )

    thread_b.join(timeout=POLL_WAIT_SECONDS)

    return client_a.get_results(session_id=session_id)


def main() -> None:
    """
    Run one interaction of each supported dyad configuration.

    Args:

    Returns:
    """

    client = APIClient(base_url=BASE_URL)

    try:
        models = client.list_models()
    except Exception as error:
        print(f"The API is not reachable at {BASE_URL}: {error}")
        print("Start it with: python -m src.run_model_api")
        return

    print_heading("Available models")

    for model in models:
        print(f"{model['id']} {model['version']} ({model['status']}): {model['name']}")

    try:
        run_model_interaction()
        run_participant_interaction()
        run_two_participant_interaction()
    except APIError as error:
        print(f"\nThe API rejected a request: {error}")
        print(f"Problem document: {error.problem}")


if __name__ == "__main__":
    main()
