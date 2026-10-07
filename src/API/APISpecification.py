"""
HTTP layer of the ITP API.

This module owns routing, authentication, and error rendering, and nothing
else. The interaction lifecycle lives in ``Interaction``, the cross-interaction
state in ``InteractionRegistry``, the model catalogue in ``ModelCatalogue``, and
the state vector validation in ``StateSpaceSchema``.

The endpoints follow ``docs/ITP_API_Specification.pdf``::

    GET    /api/v1/models
    GET    /api/v1/models/{modelId}
    POST   /api/v1/interactions
    POST   /api/v1/interactions/join
    GET    /api/v1/interactions/{sessionId}
    POST   /api/v1/interactions/{sessionId}/agents/{agentId}/register
    GET    /api/v1/interactions/{sessionId}/agents/{agentId}/perception
    POST   /api/v1/interactions/{sessionId}/agents/{agentId}/actions
    POST   /api/v1/interactions/{sessionId}/end
    GET    /api/v1/interactions/{sessionId}/results

All communication is expected to happen over HTTPS in deployment. This process
serves plain HTTP and must therefore sit behind a terminating proxy, or stay on
a trusted network.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.API.APIModels import (
    ActionAcceptedResponse,
    CreateInteractionRequest,
    CreateInteractionResponse,
    EndInteractionRequest,
    EndInteractionResponse,
    InteractionStatusResponse,
    JoinInteractionRequest,
    JoinInteractionResponse,
    ModelDefinitionResponse,
    ModelListResponse,
    PerceptionResponse,
    ProblemDocument,
    RegisterAgentRequest,
    RegistrationResponse,
    ResultsResponse,
    SubmitActionRequest,
)
from src.API.APIProblem import (
    DEFAULT_PROBLEM_BASE_URI,
    ProblemDetail,
    make_problem_response,
    make_request_id,
)
from src.API.Interaction import Interaction
from src.API.InteractionRegistry import InteractionRegistry, TokenScope
from src.API.ModelCatalogue import ModelCatalogue
from src.utils.ports import UI_PORT_CANDIDATES, UI_PORT_VARIABLE, make_origins

API_PREFIX = "/api/v1"


def make_default_allowed_origins() -> tuple[str, ...]:
    """
    Build the browser origins the mock client may be served from.

    The client is served by a separate process, on a separate origin, which is
    the only way the CORS configuration gets exercised at all. That leaves the
    API having to allow an origin whose port it cannot observe, so it allows
    the whole range ``run_mock_ui`` picks from rather than the single port the
    client usually lands on. An explicit ``ITP_UI_PORT`` outside that range is
    added too, because the same variable is read by both processes.

    Allowing ten loopback ports is not a weakening worth worrying about: an
    origin is trusted here only to the extent that a browser tab on this
    machine is, and the API is a development server either way.

    Args:

    Returns:
        Allowed origins.
    """

    ports = list(UI_PORT_CANDIDATES)

    requested = os.environ.get(UI_PORT_VARIABLE, "").strip()

    if requested.isdigit() and int(requested) not in ports:
        ports.append(int(requested))

    return make_origins(tuple(ports))


DEFAULT_ALLOWED_ORIGINS = make_default_allowed_origins()

# Upper bound on how long a long-polling request is kept open, in seconds.
MAX_LONG_POLL_SECONDS = 30.0
LONG_POLL_INTERVAL_SECONDS = 0.1

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ProblemDocument, "description": description}
    for status, description in (
        (400, "The request is malformed"),
        (401, "The interaction token is missing or invalid"),
        (403, "The requested operation is not permitted"),
        (404, "The model, interaction, agent, or invitation does not exist"),
        (409, "The request conflicts with the interaction, registration, or turn state"),
        (410, "The interaction or invitation has expired"),
        (422, "The state vector or configuration violates the applicable schema"),
        (429, "The client exceeded the polling, action, or invitation attempt limit"),
        (500, "An unexpected server error occurred"),
    )
}

bearer_scheme = HTTPBearer(auto_error=False)


class APISpecification:
    """
    FastAPI application implementing the ITP API specification.

    Args:

    Returns:
    """

    def __init__(
        self,
        catalogue: ModelCatalogue,
        converter=None,
        allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS,
        problem_base_uri: str = DEFAULT_PROBLEM_BASE_URI,
        registry: InteractionRegistry | None = None,
        results_root: str | Path | None = None,
    ) -> None:
        """
        Initialize the ITP API.

        Args:
            catalogue: Catalogue of the models the API offers.
            converter: Optional converter aligning values with the target agent.
            allowed_origins: Origins allowed to call the API from a browser.
            problem_base_uri: Base URI error types are resolved against.
            registry: Optional pre-built interaction registry.
            results_root: Optional directory below which every interaction with
                persistence enabled writes its record when it ends. Nothing is
                written to disk without it.

        Returns:
        """

        self.catalogue = catalogue
        self.problem_base_uri = problem_base_uri

        self.registry = registry or InteractionRegistry(
            catalogue=catalogue,
            converter=converter,
            results_root=results_root,
        )

        self.app = FastAPI(
            title="ITP API",
            version="1.0.0",
            description=(
                "Interpersonal Transaction Protocol API. Lets a JavaScript "
                "application run interactions between human participants and "
                "formal models of interpersonal behavior."
            ),
        )

        self._register_middleware(allowed_origins=allowed_origins)
        self._register_error_handlers()
        self._register_routes()

    def _register_middleware(
        self,
        allowed_origins: tuple[str, ...],
    ) -> None:
        """
        Register CORS and the request identifier middleware.

        Args:
            allowed_origins: Origins allowed to call the API from a browser.

        Returns:
        """

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            # X-API-Key is what the gateway in front of the deployed API checks.
            # This process ignores it, but a browser client sending it is
            # preflighted here whenever the gateway passes CORS through.
            allow_headers=["Content-Type", "Authorization", "X-API-Key"],
        )

        @self.app.middleware("http")
        async def attach_request_id(
            request: Request,
            call_next,
        ):
            request.state.request_id = make_request_id()
            response = await call_next(request)
            response.headers["X-Request-Id"] = request.state.request_id

            return response

    def _register_error_handlers(
        self,
    ) -> None:
        """
        Render every error as an RFC 9457 problem document.

        Args:

        Returns:
        """

        @self.app.exception_handler(ProblemDetail)
        async def handle_problem(
            request: Request,
            problem: ProblemDetail,
        ):
            return make_problem_response(
                problem=problem,
                request=request,
                base_uri=self.problem_base_uri,
            )

        @self.app.exception_handler(RequestValidationError)
        async def handle_validation_error(
            request: Request,
            error: RequestValidationError,
        ):
            problem = ProblemDetail(
                problem_type="malformed-request",
                detail="The request body or its parameters are malformed.",
                errors=[
                    {
                        "path": "/" + "/".join(str(part) for part in entry["loc"][1:]),
                        "code": entry["type"],
                        "message": entry["msg"],
                    }
                    for entry in error.errors()
                ],
            )

            return make_problem_response(
                problem=problem,
                request=request,
                base_uri=self.problem_base_uri,
            )

        @self.app.exception_handler(StarletteHTTPException)
        async def handle_http_exception(
            request: Request,
            error: StarletteHTTPException,
        ):
            problem_types = {
                401: "missing-token",
                403: "forbidden-agent",
                404: "interaction-not-found",
                405: "malformed-request",
            }

            problem = ProblemDetail(
                problem_type=problem_types.get(error.status_code, "internal-error"),
                detail=str(error.detail),
            )

            return make_problem_response(
                problem=problem,
                request=request,
                base_uri=self.problem_base_uri,
            )

        @self.app.exception_handler(Exception)
        async def handle_unexpected_error(
            request: Request,
            error: Exception,
        ):
            problem = ProblemDetail(
                problem_type="internal-error",
                detail="An unexpected server error occurred.",
            )

            return make_problem_response(
                problem=problem,
                request=request,
                base_uri=self.problem_base_uri,
            )

    def _register_routes(
        self,
    ) -> None:
        """
        Register the endpoints of the ITP API specification.

        Args:

        Returns:
        """

        app = self.app

        @app.get(
            f"{API_PREFIX}/models",
            response_model=None,
            responses={200: {"model": ModelListResponse}, **PROBLEM_RESPONSES},
            tags=["models"],
            summary="List available simulation models",
        )
        def list_models() -> dict[str, Any]:
            return self._call(self.catalogue.list_models)

        @app.get(
            f"{API_PREFIX}/models/{{model_id}}",
            response_model=None,
            responses={200: {"model": ModelDefinitionResponse}, **PROBLEM_RESPONSES},
            tags=["models"],
            summary="Retrieve model metadata and the shared state-space schema",
        )
        def get_model(model_id: str) -> dict[str, Any]:
            return self._call(lambda: self.describe_model(model_id=model_id))

        @app.post(
            f"{API_PREFIX}/interactions",
            status_code=201,
            response_model=None,
            responses={201: {"model": CreateInteractionResponse}, **PROBLEM_RESPONSES},
            tags=["interactions"],
            summary="Create an interaction and, where required, an invitation code",
        )
        def create_interaction(
            request: CreateInteractionRequest,
            http_request: Request,
        ) -> dict[str, Any]:
            return self._call(
                lambda: self.registry.create_interaction(
                    request=request.model_dump(by_alias=True, exclude_none=True),
                    source_ip=self._source_ip(request=http_request),
                )
            )

        @app.post(
            f"{API_PREFIX}/interactions/join",
            response_model=None,
            responses={200: {"model": JoinInteractionResponse}, **PROBLEM_RESPONSES},
            tags=["interactions"],
            summary="Join an interaction and register the invited human participant",
        )
        def join_interaction(
            request: JoinInteractionRequest,
            http_request: Request,
        ) -> dict[str, Any]:
            return self._call(
                lambda: self.registry.join_interaction(
                    request=request.model_dump(by_alias=True, exclude_none=True),
                    source_ip=self._source_ip(request=http_request),
                )
            )

        @app.get(
            f"{API_PREFIX}/interactions/{{session_id}}",
            response_model=None,
            responses={200: {"model": InteractionStatusResponse}, **PROBLEM_RESPONSES},
            tags=["interactions"],
            summary="Retrieve the current interaction status",
        )
        def get_interaction(
            session_id: str,
            scope: TokenScope = Depends(self.authenticate),
        ) -> dict[str, Any]:
            return self._call(
                lambda: self.describe_interaction(
                    session_id=session_id,
                    scope=scope,
                )
            )

        @app.post(
            f"{API_PREFIX}/interactions/{{session_id}}/agents/{{agent_id}}/register",
            response_model=None,
            responses={200: {"model": RegistrationResponse}, **PROBLEM_RESPONSES},
            tags=["agents"],
            summary="Register a human participant who already has the token",
        )
        def register_agent(
            session_id: str,
            agent_id: str,
            request: RegisterAgentRequest,
            scope: TokenScope = Depends(self.authenticate),
        ) -> dict[str, Any]:
            payload = request.model_dump(by_alias=True, exclude_none=True)

            return self._call(
                lambda: self.register_agent(
                    session_id=session_id,
                    agent_id=agent_id,
                    scope=scope,
                    participant=payload.get("participant"),
                    client=payload.get("client"),
                )
            )

        @app.get(
            f"{API_PREFIX}/interactions/{{session_id}}/agents/{{agent_id}}/perception",
            response_model=None,
            responses={200: {"model": PerceptionResponse}, **PROBLEM_RESPONSES},
            tags=["agents"],
            summary="Poll for an agent's perception",
        )
        async def get_perception(
            session_id: str,
            agent_id: str,
            after: str | None = Query(default=None),
            wait: float | None = Query(default=None, ge=0),
            scope: TokenScope = Depends(self.authenticate),
        ) -> dict[str, Any]:
            return await self.poll_perception(
                session_id=session_id,
                agent_id=agent_id,
                after=after,
                wait=wait,
                scope=scope,
            )

        @app.post(
            f"{API_PREFIX}/interactions/{{session_id}}/agents/{{agent_id}}/actions",
            status_code=202,
            response_model=None,
            responses={202: {"model": ActionAcceptedResponse}, **PROBLEM_RESPONSES},
            tags=["agents"],
            summary="Submit an agent's behavior",
        )
        def submit_action(
            session_id: str,
            agent_id: str,
            request: SubmitActionRequest,
            scope: TokenScope = Depends(self.authenticate),
        ) -> dict[str, Any]:
            return self._call(
                lambda: self.resolve_agent_interaction(
                    session_id=session_id,
                    agent_id=agent_id,
                    scope=scope,
                ).submit_action(
                    agent_id=agent_id,
                    action_id=request.action_id,
                    turn=request.turn,
                    behavior=request.behavior,
                )
            )

        @app.post(
            f"{API_PREFIX}/interactions/{{session_id}}/end",
            response_model=None,
            responses={200: {"model": EndInteractionResponse}, **PROBLEM_RESPONSES},
            tags=["interactions"],
            summary="Terminate the interaction",
        )
        def end_interaction(
            session_id: str,
            request: EndInteractionRequest | None = None,
            scope: TokenScope = Depends(self.authenticate),
        ) -> dict[str, Any]:
            reason = request.reason if request is not None else "terminatedByClient"

            return self._call(
                lambda: self.resolve_interaction(
                    session_id=session_id,
                    scope=scope,
                ).end(reason=reason)
            )

        @app.get(
            f"{API_PREFIX}/interactions/{{session_id}}/results",
            response_model=None,
            responses={200: {"model": ResultsResponse}, **PROBLEM_RESPONSES},
            tags=["interactions"],
            summary="Retrieve persisted interaction results",
        )
        def get_results(
            session_id: str,
            scope: TokenScope = Depends(self.authenticate),
        ) -> dict[str, Any]:
            return self._call(
                lambda: self.resolve_interaction(
                    session_id=session_id,
                    scope=scope,
                ).describe_results()
            )

    def authenticate(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> TokenScope:
        """
        Resolve the interaction token of a request into what it may address.

        Args:
            request: Incoming request, whose path names the interaction.
            credentials: Bearer credentials sent with the request.

        Returns:
            Scope of the token.
        """

        token = credentials.credentials if credentials is not None else None

        return self.registry.resolve_token(
            token=token,
            session_id=request.path_params.get("session_id"),
        )

    def resolve_interaction(
        self,
        session_id: str,
        scope: TokenScope,
    ) -> Interaction:
        """
        Check that a token addresses the interaction named in the path.

        Args:
            session_id: Identifier from the request path.
            scope: Scope of the token sent with the request.

        Returns:
            Requested interaction.
        """

        return self.registry.require_interaction(
            session_id=session_id,
            interaction=scope.interaction,
        )

    def resolve_agent_interaction(
        self,
        session_id: str,
        agent_id: str,
        scope: TokenScope,
    ) -> Interaction:
        """
        Check that a token may act for the agent named in the path.

        A token bound to an agent may only address that agent, so one
        participant cannot read the other's perceptions or submit behavior in
        the other's name. The token issued at creation is unbound until it
        registers a participant, because an interaction between two formal
        models has no agent to bind it to.

        Args:
            session_id: Identifier from the request path.
            agent_id: Identifier of the agent from the request path.
            scope: Scope of the token sent with the request.

        Returns:
            Requested interaction.
        """

        interaction = self.resolve_interaction(
            session_id=session_id,
            scope=scope,
        )

        if scope.agent_id is not None and scope.agent_id != agent_id:
            raise ProblemDetail(
                problem_type="forbidden-agent",
                detail=(
                    "This interaction token is issued for a different agent of "
                    "the interaction."
                ),
            )

        return interaction

    def describe_model(
        self,
        model_id: str,
    ) -> dict[str, Any]:
        """
        Describe one model of the catalogue.

        Args:
            model_id: Identifier of the model.

        Returns:
            Model definition in the API representation.
        """

        entry = self.catalogue.get(model_id=model_id)

        if entry is None:
            raise ProblemDetail(
                problem_type="model-not-found",
                detail=f"There is no model {model_id}.",
            )

        return entry.describe()

    def describe_interaction(
        self,
        session_id: str,
        scope: TokenScope,
    ) -> dict[str, Any]:
        """
        Describe one interaction, including its invitation status.

        Args:
            session_id: Identifier from the request path.
            scope: Scope of the token sent with the request.

        Returns:
            Interaction status in the API representation.
        """

        interaction = self.resolve_interaction(
            session_id=session_id,
            scope=scope,
        )

        return interaction.describe(
            invitation=self.registry.get_invitation_status(session_id=session_id)
        )

    def register_agent(
        self,
        session_id: str,
        agent_id: str,
        scope: TokenScope,
        participant: dict[str, Any] | None,
        client: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Register a participant and bind the token to the agent it registered.

        Args:
            session_id: Identifier from the request path.
            agent_id: Identifier of the agent from the request path.
            scope: Scope of the token sent with the request.
            participant: Participant registered for the agent.
            client: Client registered for the agent.

        Returns:
            Registration result in the API representation.
        """

        interaction = self.resolve_agent_interaction(
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
        )

        registration = interaction.register_agent(
            agent_id=agent_id,
            participant=participant,
            client=client,
        )

        self.registry.bind_token_to_agent(
            token_hash=scope.token_hash,
            agent_id=agent_id,
        )

        return registration

    async def poll_perception(
        self,
        session_id: str,
        agent_id: str,
        after: str | None,
        wait: float | None,
        scope: TokenScope,
    ) -> dict[str, Any]:
        """
        Return the current perception of one agent, optionally long polling.

        The request is kept open for at most ``wait`` seconds, capped by the
        server, and returns as soon as a perception or an end state appears.

        Every step that touches the interaction runs in a worker thread. The
        interaction is guarded by a threading lock that a model step can hold
        for as long as that step takes, and taking it on the event loop would
        stall every other request in the process, not only this one.

        Args:
            session_id: Identifier from the request path.
            agent_id: Identifier of the perceiving agent.
            after: Cursor of the last perception the client processed.
            wait: Seconds the server may keep the request open.
            scope: Scope of the token sent with the request.

        Returns:
            Perception state in the API representation.
        """

        def read() -> dict[str, Any]:
            return self.resolve_agent_interaction(
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
            ).poll_perception(
                agent_id=agent_id,
                after=after,
            )

        def available() -> bool:
            return self.resolve_agent_interaction(
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
            ).has_perception_after(
                agent_id=agent_id,
                after=after,
            )

        if not wait:
            return await run_in_threadpool(self._call, read)

        deadline = asyncio.get_running_loop().time() + min(
            float(wait),
            MAX_LONG_POLL_SECONDS,
        )

        while True:
            if await run_in_threadpool(self._call, available):
                break

            if asyncio.get_running_loop().time() >= deadline:
                break

            await asyncio.sleep(LONG_POLL_INTERVAL_SECONDS)

        return await run_in_threadpool(self._call, read)

    def _call(
        self,
        endpoint_function: Callable[[], Any],
    ) -> Any:
        """
        Run endpoint logic and turn plain errors into problem documents.

        ``ProblemDetail`` passes through untouched; anything the domain layer
        raises as a plain error becomes a 400 or a 500.

        Args:
            endpoint_function: Function implementing the endpoint logic.

        Returns:
            Endpoint response.
        """

        try:
            return endpoint_function()
        except ProblemDetail:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise ProblemDetail(
                problem_type="malformed-request",
                detail=str(error),
            ) from error

    def _source_ip(
        self,
        request: Request,
    ) -> str | None:
        """
        Return the source address of a request for rate limiting.

        Args:
            request: Incoming request.

        Returns:
            Source address, or None if it cannot be determined.
        """

        return request.client.host if request.client else None
