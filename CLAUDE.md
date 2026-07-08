# CLAUDE.md

## What this is

Reference implementation of the **Interpersonal Transaction Protocol (ITP)** — a standardized numerical message format letting formal models of interpersonal interaction communicate. Intentionally minimal and transparent; not production-ready. See `README.md` for the full design writeup.

## Architecture

Three layers, deliberately decoupled:

1. **Formal models** (`src/formalmodels/`) — produce and integrate numerical ITP values. `BaseFormalModel` is the abstract base; `DummyFormalModels.py` holds `DummyIPCFormalModel` / `DummySASBFormalModel`; `LASSIFormalModel.py` is the agency-communion (`ac`) model.
2. **ITP messages** — nested dicts: `source_agent`/`target_agent` = `{id, state_space, analysis_unit}`, `values` = `{state_space, analysis_unit, data}`, plus `schema_version`, `timecode`, `context`, optional `metadata`. Spec/validation lives in `src/ITPSpecification.py` (`schema_version = "0.2"`).
3. **Communication sessions** (`src/communication/Communication.py`) — a stateful ITP message session that stores and validates messages (original and converted). It does **not** hold model objects, clients, or users.

Cross-state-space delivery: the **runner** converts a message's `values` to the target's state space before delivery, using `src/converter/` (`BaseConverter`, `ConverterRegistry`, `StateSpaceConverters`). Converters live outside `Communication`. Geometry constraints are not enforced yet.

Other modules: `src/API/` (FastAPI wrapper + client for remote models), `src/interactioncontext/`, `src/utils/utilfuncs.py` (timecode + conversion helpers). `src/deprecated/` is dead code. `schema/` holds JSON Schemas and example ITP messages; `configs/interaction_contexts.yaml` holds context config.

## Setup & run

Run everything from the **repo root as modules** (imports are `from src....`, and there are no `__init__.py` files, so `python src/foo.py` fails — use `-m`).

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt

# local interaction between two dummy models
python -m src.run_local_interaction

# API-based interaction (two terminals)
python -m src.run_model_api        # serves a model at http://127.0.0.1:8001
python -m src.run_API_interaction  # client talks to it
```

## Conventions

- Python 3.13, `from __future__ import annotations`, type hints throughout.
- Pydantic for validation; FastAPI + uvicorn for the API.
- Docstrings use `Args:` / `Returns:` sections — match this style.
- No test suite or linter is configured yet.
