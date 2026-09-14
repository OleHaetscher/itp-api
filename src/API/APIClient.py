"""
Python client for the ITP API.

The JavaScript application is the primary client of this API. This client
mirrors it, so an interaction can be driven from Python for testing, for
demonstrations, and for the runner in ``src/run_API_interaction.py``.

Errors are raised as ``APIError``, which carries the parsed problem document
rather than a bare status code.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import requests

API_PREFIX = "/api/v1"


class APIError(RuntimeError):
    """
    Error returned by the ITP API as a problem document.

    Args:

    Returns:
    """

    def __init__(
        self,
        status_code: int,
        problem: dict[str, Any],
    ) -> None:
        """
        Initialize an API error.

        Args:
            status_code: HTTP status code of the response.
            problem: Problem document returned by the API.

        Returns:
        """

        self.status_code = status_code
        self.problem = problem

        super().__init__(
            f"{status_code} {problem.get('title', 'Error')}: "
            f"{problem.get('detail', '')}"
        )


class APIClient:
    """
    Client for one ITP API process.

    Args:

    Returns:
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 40.0,
        interaction_token: str | None = None,
    ) -> None:
        """
        Initialize the API client.

        Args:
            base_url: Base URL of the API, without the /api/v1 prefix.
            timeout: Request timeout in seconds.
            interaction_token: Optional token of an interaction already joined.

        Returns:
        """

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.interaction_token = interaction_token

    def list_models(
        self,
    ) -> list[dict[str, Any]]:
        """
        List the models the API offers.

        Args:

        Returns:
            Model summaries.
        """

        return self._request(
            method="GET",
            endpoint="/models",
            authenticated=False,
        )["models"]

    def get_model(
        self,
        model_id: str,
    ) -> dict[str, Any]:
        """
        Get the definition and state space schema of one model.

        Args:
            model_id: Identifier of the model.

        Returns:
            Model definition.
        """

        return self._request(
            method="GET",
            endpoint=f"/models/{model_id}",
            authenticated=False,
        )

    def create_interaction(
        self,
        model_id: str,
        number_of_turns: int,
        agents: dict[str, dict[str, Any]],
        model_version: str | None = None,
        persistence: bool = False,
        context: str | None = None,
        starting_agent_role: str = "A",
        client_request_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create an interaction and store the interaction token.

        Args:
            model_id: Identifier of the model the interaction is bound to.
            number_of_turns: Maximum number of interaction turns.
            agents: Agents of the interaction, keyed by role.
            model_version: Optional exact model version.
            persistence: Whether interaction data is kept after the end.
            context: Optional name of the interaction context.
            starting_agent_role: Role of the agent that acts in turn 1.
            client_request_id: Optional idempotency identifier.

        Returns:
            Created interaction, including the interaction token.
        """

        payload: dict[str, Any] = {
            "modelId": model_id,
            "numberOfTurns": number_of_turns,
            "agents": agents,
            "persistence": {"enabled": persistence},
            "startingAgentRole": starting_agent_role,
            "clientRequestId": client_request_id or f"create-{uuid4().hex[:8]}",
        }

        if model_version is not None:
            payload["modelVersion"] = model_version

        if context is not None:
            payload["context"] = context

        interaction = self._request(
            method="POST",
            endpoint="/interactions",
            payload=payload,
            authenticated=False,
        )

        self.interaction_token = interaction["interactionToken"]

        return interaction

    def join_interaction(
        self,
        invitation_code: str,
        participant: dict[str, Any] | None = None,
        client: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Join an interaction with a six-digit invitation code.

        Args:
            invitation_code: Six-digit invitation code.
            participant: Optional participant registered for the agent.
            client: Optional client registered for the agent.

        Returns:
            Join result, including the interaction token.
        """

        payload: dict[str, Any] = {"invitationCode": invitation_code}

        if participant is not None:
            payload["participant"] = participant

        if client is not None:
            payload["client"] = client

        joined = self._request(
            method="POST",
            endpoint="/interactions/join",
            payload=payload,
            authenticated=False,
        )

        self.interaction_token = joined["interactionToken"]

        return joined

    def get_interaction(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """
        Get the current status of an interaction.

        Args:
            session_id: Identifier of the interaction.

        Returns:
            Interaction status.
        """

        return self._request(
            method="GET",
            endpoint=f"/interactions/{session_id}",
        )

    def register_agent(
        self,
        session_id: str,
        agent_id: str,
        participant: dict[str, Any] | None = None,
        client: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Register a human participant that already holds the interaction token.

        Args:
            session_id: Identifier of the interaction.
            agent_id: Identifier of the agent.
            participant: Optional participant registered for the agent.
            client: Optional client registered for the agent.

        Returns:
            Registration result.
        """

        payload: dict[str, Any] = {}

        if participant is not None:
            payload["participant"] = participant

        if client is not None:
            payload["client"] = client

        return self._request(
            method="POST",
            endpoint=f"/interactions/{session_id}/agents/{agent_id}/register",
            payload=payload,
        )

    def poll_perception(
        self,
        session_id: str,
        agent_id: str,
        after: str | None = None,
        wait: float | None = None,
    ) -> dict[str, Any]:
        """
        Poll for the current perception of one agent.

        Args:
            session_id: Identifier of the interaction.
            agent_id: Identifier of the perceiving agent.
            after: Cursor of the last perception the client processed.
            wait: Seconds the server may keep the request open.

        Returns:
            Perception state.
        """

        parameters: dict[str, Any] = {}

        if after is not None:
            parameters["after"] = after

        if wait is not None:
            parameters["wait"] = wait

        return self._request(
            method="GET",
            endpoint=f"/interactions/{session_id}/agents/{agent_id}/perception",
            parameters=parameters,
        )

    def submit_action(
        self,
        session_id: str,
        agent_id: str,
        turn: int,
        behavior: dict[str, float],
        action_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Submit the behavior of one agent for one turn.

        Args:
            session_id: Identifier of the interaction.
            agent_id: Identifier of the acting agent.
            turn: Turn the action belongs to.
            behavior: Behavior vector in the agent's state space.
            action_id: Optional client-generated idempotency identifier.

        Returns:
            Acceptance response.
        """

        return self._request(
            method="POST",
            endpoint=f"/interactions/{session_id}/agents/{agent_id}/actions",
            payload={
                "actionId": action_id or str(uuid4()),
                "turn": turn,
                "behavior": behavior,
            },
        )

    def end_interaction(
        self,
        session_id: str,
        reason: str = "terminatedByClient",
    ) -> dict[str, Any]:
        """
        Terminate an interaction before its normal completion.

        Args:
            session_id: Identifier of the interaction.
            reason: Reason the interaction ended.

        Returns:
            Termination result.
        """

        return self._request(
            method="POST",
            endpoint=f"/interactions/{session_id}/end",
            payload={"reason": reason},
        )

    def get_results(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """
        Get the recorded results of an interaction.

        Args:
            session_id: Identifier of the interaction.

        Returns:
            Interaction results.
        """

        return self._request(
            method="GET",
            endpoint=f"/interactions/{session_id}/results",
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        parameters: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        """
        Send one request to the API and parse its response.

        Args:
            method: HTTP method.
            endpoint: Endpoint below the /api/v1 prefix.
            payload: Optional JSON payload.
            parameters: Optional query parameters.
            authenticated: Whether to send the interaction token.

        Returns:
            Parsed JSON response.
        """

        headers: dict[str, str] = {}

        if authenticated:
            if self.interaction_token is None:
                raise APIError(
                    status_code=401,
                    problem={
                        "title": "Missing interaction token",
                        "detail": (
                            "The client has no interaction token. Create or "
                            "join an interaction first."
                        ),
                    },
                )

            headers["Authorization"] = f"Bearer {self.interaction_token}"

        response = requests.request(
            method=method,
            url=f"{self.base_url}{API_PREFIX}{endpoint}",
            json=payload,
            params=parameters,
            headers=headers,
            timeout=self.timeout,
        )

        try:
            body = response.json()
        except ValueError:
            body = {"title": "Unparseable response", "detail": response.text}

        if response.status_code >= 400:
            raise APIError(
                status_code=response.status_code,
                problem=body,
            )

        return body
