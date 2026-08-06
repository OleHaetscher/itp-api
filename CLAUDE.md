# CLAUDE.md

## What this is

Reference implementation of the **Interpersonal Transaction Protocol (ITP)** — a standardized numerical message format letting formal models of interpersonal interaction communicate. Intentionally minimal and transparent; not production-ready. See `README.md` for the full design writeup.

## Architecture

Three layers, deliberately decoupled:

1. **Formal models** (`src/formalmodels/`) — produce and integrate numerical ITP values. `BaseFormalModel` is the abstract base; `DummyFormalModels.py` holds `DummyIPCFormalModel` / `DummySASBFormalModel`; `LASSIFormalModel.py` is the agency-communion (`ac`) model. Its per-axis parameters live in `configs/formal_model_parameters.yaml` and are all on the internal 0-based grid (including `BD`) — the ITP 1-based scale is entered only in `to_itp_state` / `to_internal_state`. `step_record()` exposes every intermediate of the last update for the visualization.
2. **ITP messages** — nested dicts: `source_agent`/`target_agent` = `{id, state_space, analysis_unit}`, `values` = `{state_space, analysis_unit, data}`, plus `schema_version`, `timecode`, `context`, optional `metadata`. Spec/validation lives in `src/ITPSpecification.py` (`schema_version = "0.2"`).
3. **Communication sessions** (`src/communication/Communication.py`) — a stateful ITP message session that stores and validates messages (original and converted). It does **not** hold model objects, clients, or users.

Cross-state-space delivery: whoever delivers a message converts its `values` to the target's state space first, using `src/converter/` (`BaseConverter`, `ConverterRegistry`, `BehavioralStateSpaceConverters`) — the **runner** locally, `APISpecification` for messages crossing the API. Converters live outside `Communication`. Geometry constraints are not enforced yet.

**Visualization** (`src/visualization/`) — Dash dashboards, decoupled from the models. `BaseVisualizer` owns the shared style, page scaffolding and Dash hosting; subclasses implement `validate_source` / `build_body` / `register_callbacks`. `FormalModelVisualizer` takes a formal model, `InteractionVisualizer` takes ITP messages (trajectory dashboard not implemented yet), `LASSIFormalModelVisualizer` is the LASSI update walk-through. Dashboards recompute on throwaway objects and never mutate the model they render.

Other modules: `src/API/` (FastAPI wrapper + client for remote models; state lives in per-session model instances, see `docs/api_design.md`), `src/interactioncontext/`, `src/utils/utilfuncs.py` (timecode + conversion helpers, `load_config`). `src/deprecated/` is dead code. `schema/` holds JSON Schemas and example ITP messages; `configs/` holds the context and formal model parameter configs.

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

# LASSI state distribution dashboard at http://127.0.0.1:8050
python -m src.run_lassi_visualization
```

## Conventions

- Python 3.13, `from __future__ import annotations`, type hints throughout.
- Pydantic for validation; FastAPI + uvicorn for the API; Dash + plotly for visualization.
- Docstrings use `Args:` / `Returns:` sections — match this style.
- No test suite or linter is configured yet.
