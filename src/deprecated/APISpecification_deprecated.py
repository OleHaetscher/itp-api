from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.communication.Communication import Communication
from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.utils.utilfuncs import make_timecode, prepare_message_for_target

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


class APISpecification:
    """
    REST API for exposing a formal model through the ITP framework.

    The API serves one formal model in sessions. Each session holds its own
    model instance and its own communication, so several clients can talk to
    the same API without sharing model state.

    Args:

    Returns:
    """

    def __init__(
        self,
        model_factory: Callable[[], BaseFormalModel],
        converter=None,
        allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS,
    ) -> None:
        """
        Initialize the API for one formal model.

        Args:
            model_factory: Callable creating a new instance of the exposed formal model.
            converter: Optional converter used to align message values.
            allowed_origins: Origins allowed to call the API from a browser.

        Returns:
        """

        self.model_factory = model_factory
        self.converter = converter
        self.sessions: dict[str, dict[str, Any]] = {}

        self.template_model = model_factory()
        self.template_model.validate_model_interface()

        self.app = FastAPI(
            title=f"ITP Formal Model API: {self.template_model.model_id}"
        )

        self._register_cors(allowed_origins=allowed_origins)
        self._register_routes()

    def _register_cors(
        self,
        allowed_origins: tuple[str, ...],
    ) -> None:
        """
        Allow browser clients from the given origins to call the API.

        Args:
            allowed_origins: Origins allowed to call the API from a browser.

        Returns:
        """

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

    def _register_routes(
        self,
    ) -> None:
        """
        Register REST endpoints for the formal model API.

        Args:

        Returns:
        """

        @self.app.get("/info")
        def get_info() -> dict[str, Any]:
            return self._handle_endpoint_call(self.get_info)

        @self.app.post("/sessions")
        def create_session(request: dict[str, Any]) -> dict[str, Any]:
            return self._handle_endpoint_call(
                lambda: self.create_session(request=request)
            )

        @self.app.get("/sessions")
        def list_sessions() -> dict[str, Any]:
            return self._handle_endpoint_call(self.list_sessions)

        @self.app.get("/sessions/{session_id}")
        def get_session_info(session_id: str) -> dict[str, Any]:
            return self._handle_endpoint_call(
                lambda: self.get_session_info(session_id=session_id)
            )

        @self.app.delete("/sessions/{session_id}")
        def delete_session(session_id: str) -> dict[str, Any]:
            return self._handle_endpoint_call(
                lambda: self.delete_session(session_id=session_id)
            )

        @self.app.get("/sessions/{session_id}/messages")
        def get_messages(session_id: str) -> dict[str, Any]:
            return self._handle_endpoint_call(
                lambda: self.get_messages(session_id=session_id)
            )

        @self.app.post("/sessions/{session_id}/generate")
        def generate_message(
            session_id: str,
            request: dict[str, Any],
        ) -> dict[str, Any]:
            return self._handle_endpoint_call(
                lambda: self.generate_message(
                    session_id=session_id,
                    request=request,
                )
            )

        @self.app.post("/sessions/{session_id}/step")
        def step(
            session_id: str,
            message: dict[str, Any],
        ) -> dict[str, Any]:
            return self._handle_endpoint_call(
                lambda: self.step(
                    session_id=session_id,
                    message=message,
                )
            )

    def get_info(
        self,
    ) -> dict[str, Any]:
        """
        Return basic information about the exposed formal model.

        Args:

        Returns:
            Basic model information.
        """

        return {
            "agent": self.template_model.to_agent(),
            "dimensions": list(self.template_model.dimensions),
            "schema_version": self.template_model.specification.schema_version,
        }

    def create_session(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Create a session with its own model instance and communication.

        Args:
            request: Request containing the interaction context.

        Returns:
            Description of the created session.
        """

        context = self._get_required_value(
            request=request,
            key="context",
        )

        model = self.model_factory()
        session_id = str(uuid4())

        self.sessions[session_id] = {
            "model": model,
            "communication": Communication(context=context),
            "interaction_turn": 0,
        }

        return self.get_session_info(session_id=session_id)

    def list_sessions(
        self,
    ) -> dict[str, Any]:
        """
        Return the identifiers of all open sessions.

        Args:

        Returns:
            Identifiers of all open sessions.
        """

        return {"session_ids": list(self.sessions)}

    def get_session_info(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """
        Return a description of one session.

        Args:
            session_id: Identifier of the session.

        Returns:
            Description of the session.
        """

        session = self._get_session(session_id=session_id)

        return {
            "session_id": session_id,
            "agent": session["model"].to_agent(),
            "context": session["communication"].context_name,
            "n_messages": session["communication"].n_messages,
        }

    def delete_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """
        Delete one session and its stored messages.

        Args:
            session_id: Identifier of the session.

        Returns:
            Identifier of the deleted session.
        """

        self._get_session(session_id=session_id)
        del self.sessions[session_id]

        return {"session_id": session_id, "deleted": True}

    def get_messages(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """
        Return all ITP messages stored in one session.

        Args:
            session_id: Identifier of the session.

        Returns:
            Stored ITP messages.
        """

        session = self._get_session(session_id=session_id)

        return {
            "session_id": session_id,
            "messages": session["communication"].get_messages(),
        }

    def generate_message(
        self,
        session_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate an ITP message without integrating an incoming message first.

        Args:
            session_id: Identifier of the session.
            request: Request containing the target agent and optional timecode.

        Returns:
            ITP message generated by the formal model.
        """

        session = self._get_session(session_id=session_id)

        target_agent = self._get_required_value(
            request=request,
            key="target_agent",
        )

        message = session["model"].to_message(
            target_agent=target_agent,
            timecode=self._make_session_timecode(
                session=session,
                timecode=request.get("timecode"),
            ),
            context=session["communication"].context_name,
            metadata=request.get("metadata"),
        )

        return self._store_and_prepare_message(
            session=session,
            message=message,
        )

    def step(
        self,
        session_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Integrate an incoming ITP message and generate a response message.

        Incoming and outgoing values are converted on the server if they do not
        match the state space of their target agent.

        Args:
            session_id: Identifier of the session.
            message: Incoming ITP message targeting the exposed formal model.

        Returns:
            ITP response message generated by the formal model.
        """

        session = self._get_session(session_id=session_id)
        model = session["model"]

        self._validate_message_target(
            message=message,
            model=model,
        )

        message_for_model = self._store_and_prepare_message(
            session=session,
            message=message,
        )

        model.from_message(message_for_model)

        response = model.to_message(
            target_agent=message["source_agent"],
            timecode=self._make_response_timecode(
                session=session,
                message=message,
            ),
            context=session["communication"].context_name,
        )

        return self._store_and_prepare_message(
            session=session,
            message=response,
        )

    def _store_and_prepare_message(
        self,
        session: dict[str, Any],
        message: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Store an ITP message and convert it for its target agent if needed.

        Args:
            session: Session storing the message.
            message: Numerical ITP message.

        Returns:
            Numerical ITP message ready for the target agent.
        """

        session["communication"].receive_message(message)

        delivered_message = prepare_message_for_target(
            message=message,
            converter=self.converter,
        )

        if delivered_message is not message:
            session["communication"].receive_message(delivered_message)

        return delivered_message

    def _make_session_timecode(
        self,
        session: dict[str, Any],
        timecode: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Return the requested timecode or start the next interaction turn.

        Args:
            session: Session the message belongs to.
            timecode: Optional timecode provided by the client.

        Returns:
            Timecode for the message.
        """

        if timecode is not None:
            return timecode

        session["interaction_turn"] += 1

        return make_timecode(
            interaction_turn=session["interaction_turn"],
            message_index=1,
        )

    def _make_response_timecode(
        self,
        session: dict[str, Any],
        message: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Derive a timecode for the response to an incoming message.

        The response stays in the interaction turn of the message it answers.

        Args:
            session: Session the message belongs to.
            message: Incoming ITP message.

        Returns:
            Timecode for the response message.
        """

        interaction_turn = message["timecode"].get("interaction_turn")

        if interaction_turn is None:
            session["interaction_turn"] += 1
            interaction_turn = session["interaction_turn"]

        return make_timecode(
            interaction_turn=interaction_turn,
            message_index=2,
        )

    def _get_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        """
        Return one session.

        Args:
            session_id: Identifier of the session.

        Returns:
            Session stored under the identifier.
        """

        if session_id not in self.sessions:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown session: {session_id}",
            )

        return self.sessions[session_id]

    def _validate_message_target(
        self,
        message: dict[str, Any],
        model: BaseFormalModel,
    ) -> None:
        """
        Validate that an incoming message targets the exposed formal model.

        Args:
            message: Incoming ITP message.
            model: Formal model of the session.

        Returns:
        """

        target_agent = message["target_agent"]

        if target_agent["id"] != model.model_id:
            raise ValueError(
                f"Message targets {target_agent['id']}, "
                f"but this API exposes {model.model_id}."
            )

    def _get_required_value(
        self,
        request: dict[str, Any],
        key: str,
    ) -> Any:
        """
        Extract a required value from an API request.

        Args:
            request: API request.
            key: Required key.

        Returns:
            Value stored under the required key.
        """

        if key not in request:
            raise ValueError(f"Missing required request key: {key}")

        if request[key] is None:
            raise ValueError(f"Request key must not be None: {key}")

        return request[key]

    def _handle_endpoint_call(
        self,
        endpoint_function,
    ) -> dict[str, Any]:
        """
        Run an endpoint function and convert errors to HTTP errors.

        Args:
            endpoint_function: Function implementing the endpoint logic.

        Returns:
            Endpoint response.
        """

        try:
            return endpoint_function()
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
