# CLAUDE.md

## What this is

Reference implementation of the **Interpersonal Transaction Protocol (ITP)** — a standardized numerical message format letting formal models of interpersonal interaction communicate. Intentionally minimal and transparent; not production-ready. See `README.md` for the full design writeup.

## Architecture

Three layers, deliberately decoupled:

1. **Formal models** (`src/formalmodels/`) — produce and integrate numerical ITP values. `BaseFormalModel` is the abstract base; `DummyFormalModels.py` holds `DummyIPCFormalModel` / `DummySASBFormalModel`; `LASSIFormalModel.py` is the agency-communion (`ac`) model, a reimplementation of the reference in the `lassi_simulations` repository (`handoff/formal-model-spec.md` there). One exchange moves the mean of a per-axis state distribution to a convex mixture of the previous mean (`mu_prev`), the behavioral default (`BD`) and the partner-implied target (`partner_target`), then makes the distribution the agent's `repertoire` exponentially tilted onto that mean: the realised mean equals `mu_t` exactly, and clipping is structurally impossible — a clip in this model hides a broken invariant. The spec's notation and this module's names differ; the mapping is in the module docstring. Reactivity `IR` is **signed** in `[-1, +1]`: magnitude is the weight on the partner, sign is the response direction. `m` (`complementarity_direction`) belongs to the axis, not the person. Its per-axis parameters live in `configs/formal_model_parameters.yaml` and are stated on the **ITP 1-based scale** `1 … N`, matching `lassi_simulations`; the internal grid is symmetric and zero-centred, and conversion happens in `to_itp_state` / `to_internal_state`. `step_record()` exposes every intermediate of the last update, under the field names the handoff vectors use, for the visualization and the conformance test.
2. **ITP messages** — nested dicts: `source_agent`/`target_agent` = `{id, state_space, analysis_unit}`, `values` = `{state_space, analysis_unit, data}`, plus `schema_version`, `timecode`, `context`, optional `metadata`. Spec/validation lives in `src/ITPSpecification.py` (`schema_version = "0.2"`).
3. **Communication sessions** (`src/communication/Communication.py`) — a stateful ITP message session that stores and validates messages (original and converted). It does **not** hold model objects, clients, or users.

Cross-state-space delivery: whoever delivers a message converts its `values` to the target's state space first, using `src/converter/` (`BaseConverter`, `ConverterRegistry`, `BehavioralStateSpaceConverters`) — the **runner** locally, `APISpecification` for messages crossing the API. Converters live outside `Communication`. They do not enforce geometry constraints in general; the API validates every converted vector against the target state space and fails the interaction if one leaves it. The IPC neutral center is settled: the circumplex **includes** it, marked by `R = 0`, where `Theta` is undefined and reported as `NEUTRAL_CENTER_ANGLE` — never interpret `Theta` unless `R > 0`.

**Visualization** (`src/visualization/`) — Dash dashboards, decoupled from the models. `BaseVisualizer` owns the shared style, page scaffolding and Dash hosting; subclasses implement `validate_source` / `build_body` / `register_callbacks`. `FormalModelVisualizer` takes a formal model, `InteractionVisualizer` takes ITP messages (trajectory dashboard not implemented yet), `LASSIFormalModelVisualizer` is the LASSI update walk-through (mean rule, response direction, tilt, repeated exchanges). Dashboards recompute on throwaway objects and never mutate the model they render. Style is the PerTRAIN design system, defined once as class attributes on `BaseVisualizer` (light neutrals, `#2C6BB5` primary, system sans, no font binaries) — take colours from there rather than writing a hex into a figure. `AGENCY = #315A7D` and `COMMUNION = #B84650` are the agreed pair for agency-communion figures and are reserved for the axes: the current state of an axis is drawn in its axis colour, everything else keeps a role colour that does not change with the axis. The two flow diagrams at the repo root use the same palette as CSS variables.

**API** (`src/API/`) — implements `docs/ITP_API_Specification.pdf` under `/api/v1`: model catalogue, interaction lifecycle, server-authoritative alternating turns, participant registration, six-digit invitation codes, perception polling, idempotent action submission, RFC 9457 errors. `APISpecification` is routing/auth/errors only; `Interaction` owns the turn engine, `InteractionRegistry` owns tokens/invitations/idempotency (tokens are bound to the agent they registered; a bound token may only address its own agent), `ModelCatalogue` the model entries, `StateSpaceSchema` compiles IBSSS descriptions into validating JSON Schemas (plus geometry checks JSON Schema cannot express). The wire format is bare `experience`/`behavior` vectors; ITP messages are built server-side and stored in `Communication`. See `docs/api_design.md` for extensions to the spec and known gaps.

**Mock client** (`ui/index.html`, served by `src/run_mock_ui.py`) — stands in for the JavaScript application: catalogue, interaction creation, registration, invitation codes, long-polled perceptions, behavior inputs built from the model's `stateSpaceSchema`, and a log of every request and response. Each step is a collapsible card, auto-collapsing behind the current one. Plain HTML and JS, one file, no build step and no dependencies — keep it that way, and keep the palette on the PerTRAIN design system (neutral surfaces, `#2C6BB5` for actions, system sans, no font binaries). It must be served on port **5173**, because that is what the API's CORS list allows; serving it from the API process would make it same-origin and hide that check. The interaction context is deliberately not a control there: it modulates nothing in any model yet.

**Results on disk**: `APISpecification(results_root=...)` makes every interaction with persistence enabled write itself to `<results_root>/results/<timestamp>_<session prefix>/` when it ends — the ITP message files `Communication.save_messages` produces, plus an `interaction.json` with the API-level record. `run_model_api.py` passes the repo root; without `results_root` nothing is written. The folder name is returned as `resultsFolder` in `/results`.

Other modules: `src/interactioncontext/`, `src/utils/utilfuncs.py` (timecode + conversion helpers, `load_config`, `make_iso_timestamp`). `src/deprecated/` is dead code, including the previous `/sessions` API. `schema/` holds JSON Schemas and example ITP messages; `configs/` holds the context and formal model parameter configs.

## Setup & run

Run everything from the **repo root as modules** (imports are `from src....`, and there are no `__init__.py` files, so `python src/foo.py` fails — use `-m`).

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt

# local interaction between two dummy models
python -m src.run_local_interaction

# API-based interaction (two terminals)
python -m src.run_model_api        # serves the catalogue at http://127.0.0.1:8001
python -m src.run_API_interaction  # runs model-model, human-model, human-human

# LASSI state distribution dashboard at http://127.0.0.1:8050
python -m src.run_lassi_visualization

# browser mock client of the API, in a third terminal (open http://127.0.0.1:5173)
python -m src.run_mock_ui

# conformance test of LASSIFormalModel against the lassi_simulations vectors
python -m pytest tests
```

## Conventions

- Python 3.13, `from __future__ import annotations`, type hints throughout.
- Pydantic for validation; FastAPI + uvicorn for the API; `jsonschema` for state vector validation; Dash + plotly for visualization.
- Docstrings use `Args:` / `Returns:` sections — match this style.
- No linter is configured yet. The only tests are `tests/test_lassi_formal_model.py`, which runs the conformance vectors of `lassi_simulations` (`tests/data/lassi_test_vectors.json`, a copy of `handoff/test_vectors.json` there) against `LASSIFormalModel`. Run them with `python -m pytest tests` from the repo root. The three copies of that model — `lassi_simulations`, here, and the PerTRAIN production repo — are separate implementations feeding the same published claims, nothing detects drift between them, and these vectors are the only mitigation. When the model changes there, the file is regenerated and copied over this one; a mismatch is a release blocker, not a rounding question.
