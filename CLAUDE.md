# CLAUDE.md

## What this is

Reference implementation of the **Interpersonal Transaction Protocol (ITP)** — a standardized numerical message format letting formal models of interpersonal interaction communicate. Intentionally minimal and transparent; not production-ready. See `README.md` for the full design writeup.

## Architecture

Three layers, deliberately decoupled:

1. **Formal models** (`src/formalmodels/`) — produce and integrate numerical ITP values. `BaseFormalModel` is the abstract base; `DummyFormalModel` is the reference stub.
2. **ITP messages** — standardized dicts (source, target, timecode, values, context). Spec/validation lives in `src/ITPSpecification.py`.
3. **Communication sessions** (`src/communication/Communication.py`) — a stateful ITP message session that stores and validates messages. It does **not** hold model objects, so it also works with external-only messages.

Other modules: `src/API/` (FastAPI wrapper + client for remote models), `src/paradigms/` and `src/converter/` and `src/interactioncontext/` (mostly not yet implemented). `src/deprecated/` is dead code. `schema/` holds JSON Schemas for state spaces and ITP; `configs/interaction_contexts.yaml` holds context config.

## Setup & run

Run everything from the **repo root** (imports are `from src....`).

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt

# local interaction between two dummy models
python src/run_local_interaction.py

# API-based interaction (two terminals)
python src/run_model_api.py        # serves a model at http://127.0.0.1:8001
python src/run_API_interaction.py  # client talks to it
```

## Conventions

- Python 3.13, `from __future__ import annotations`, type hints throughout.
- Pydantic for validation; FastAPI + uvicorn for the API.
- Docstrings use `Args:` / `Returns:` sections — match this style.
- No test suite or linter is configured yet.
