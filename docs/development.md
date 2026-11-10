# Notes for development

What someone changing this repository needs beyond the README: decisions the code relies on, how
the runners find each other, what the tests protect, and what is planned. The API's own design is
in `api_design.md`, the deployment in `deployment.md`.

## Layout

```text
configs/        formal model parameters, interaction contexts
docs/           API specification (PDF), design notes, these notes
schema/         JSON Schemas of ITP messages and of the state spaces (IBSSS descriptions)
src/
  ITPSpecification.py   message format and validation
  communication/        Communication, the message session
  formalmodels/         BaseFormalModel, dummy models, LASSIFormalModel, ParameterSpace
  converter/            conversion between state spaces
  API/                  the web API (FastAPI)
  visualization/        Dash dashboards, the interaction report and its HTML template
  interactioncontext/   placeholder for interaction contexts
  utils/                ports and discovery, helpers
  deprecated/           the previous /sessions API, unmounted
  run_*.py              runners, started as modules (python -m src.run_...)
ui/             the mock client, one HTML file
examples/       the run behind Figure 2, and a participant-facing web client
tests/          pytest suite and the LASSI conformance vectors
itp-api-flow.html, itp-communication-flow.html   flow diagrams; section 00 of the first is Figure 1
```

There are no `__init__.py` files. Imports are `from src....`, so every runner is started from the
repository root with `python -m`.

## LASSIFormalModel

The normative description of the model is `handoff/formal-model-spec.md` in the
`lassi_simulations` repository. The docstring of `src/formalmodels/LASSIFormalModel.py` states the
update rule as implemented and maps the spec's notation onto the module's names. This repository
holds a reimplementation, not a copy (see *Tests*).

Each axis carries a probability distribution over a symmetric, zero-centred grid. One exchange
moves the mean of that distribution to a convex mixture of where the agent was, its behavioral
default, and the state the partner's behavior implies. The distribution is then the agent's
habitual repertoire, minimally deformed to have exactly that mean. The realised mean therefore
equals the intended mean to solver precision, and the mean cannot leave the grid. Nothing is ever
clipped, and a clip in this model would hide a bug. Reactivity `IR` is signed: its magnitude is the
weight on the partner, its sign the direction of the response.

Three things this repository decides for itself:

- **Scale.** Axis parameters in `configs/formal_model_parameters.yaml` are on the ITP 1-based
  scale, the scale ITP messages carry and the one `lassi_simulations` states its behavioral
  defaults on. `to_itp_state` and `to_internal_state` convert at the message boundary.
- **Diagnostics.** `step_record()` per axis and `step_records()` per model expose every
  intermediate of the last update, under the field names the conformance vectors use. The
  dashboard and the test both read them.
- **Parameters per agent.** `lassi_parameter_space()` publishes `BD` (strictly inside 1 to 7) and
  `IR` (−1 to +1) per axis, with the configured values as defaults. `tau`, `lambda_relax`, the axis
  signs and the number of states stay as configured. `lassi_parameters_with` merges an agent's
  choice into the configuration. A new model with parameters declares a `ParameterSpace` in its
  catalogue entry and accepts `parameters` in its factory, which takes `(agent_id, parameters)`.

## Converters and new state spaces

Converters change a values block from one state space to another. `ConverterRegistry` picks a
registered converter and raises when none exists. The defaults cover `ac <-> ipc` and
`sasb <-> ipc`, and converters are not chained. Converters do not keep vectors inside the target
space in general. The API validates every converted vector and fails the interaction when one
leaves it.

A client joins in the state space its own scale speaks, and the API converts to and from the
model's space. The PerTRAIN backend (`ITPGenerator`) registers its human agent in `ac`, because its
agency and communion axes have seven states, which is the `ac` grid (1 to 7, `AC_NUM_STATES`). An
`ac` client therefore reaches `lassi` directly and `dummy-ipc` through `ac <-> ipc`, but not
`dummy-sasb`.

A client with a different number of states (say, five per axis) needs a new state space, never a
change to `ac`. The `ac` range is tied to LASSI's seven states, and changing it silently rescales
every converted message. The new space needs:

1. an IBSSS description with the new range in `schema/interpersonal-behavior-state-space/`;
2. an entry in `STATE_SPACE_SOURCES` in `src/API/StateSpaceSchema.py`, under its own identifier
   (e.g., `ac5`);
3. converters to every space it should reach, registered in `make_default_converter_registry`
   (to talk to `lassi`, that includes a converter to `ac`);
4. a new release of the API (`deployment.md`).

## Ports and discovery

No runner hard-codes a port; `src/utils/ports.py` owns the policy. The API takes the first free
port in 8001 to 8010, the mock client 5173 to 5182, and the LASSI dashboard 8050 to 8059.
`ITP_API_PORT`, `ITP_UI_PORT` and `ITP_VISUALIZATION_PORT` name a port instead, which is then
obeyed exactly or refused. "Free" means that binding succeeds and nothing answers on `127.0.0.1` or
`::1`, because macOS lets a wildcard and a loopback bind of one port coexist.

While the API runs, it writes its base URL to `.itp-api-url` at the repository root (untracked).
`run_API_interaction` and the mock client find the API through `ITP_API_BASE_URL`, then
`ITP_API_PORT`, then that note (believed only when it answers like the catalogue), then a probe of
8001 to 8010. The API binds all interfaces, so a container can be reached from outside, but
announces itself under `127.0.0.1`, because browsers have started to block requests to `0.0.0.0`.

The mock client is served on a port of its own, never from the API process. Same-origin serving
would hide the CORS check, which is what a mock client should exercise. The API therefore allows
`localhost` and `127.0.0.1` on 5173 to 5182. `ITP_UI_PORT` outside that range has to be set for the
API process too, where the origin list is built.

## The mock client

`ui/index.html` walks the whole workflow in collapsible cards: connect (catalogue and API key),
set up (who is in the interaction, each agent's model, the state space you act in, and the model
parameters), create and register, perceive (long polling), act (one input per dimension;
out-of-range values are submitted, so the server's `422` is visible), and read the record. Every
request and response is logged on the right. The API key is sent as `X-API-Key` and never appears
in the log.

The interaction context is deliberately not a control: it reaches the ITP messages but modulates
nothing in any model yet. State lives in the tab, and a reload starts over. The page is due to
leave this repository (`client_split.md`); until then, nothing in it may depend on `src/`.

## Visualization style

The dashboards, the report and the flow diagrams follow the PerTRAIN design system: neutral light
surfaces, blue (`#2C6BB5`) for primary elements, green and amber for the remaining roles, and the
system sans stack, so no font binaries live in this repository. The colours are defined once, as
class attributes on `BaseVisualizer`.

Two colours are reserved for the agency-communion axes: agency `#315A7D` (dark, muted blue) and
communion `#B84650` (muted red-pink). Whatever state an agent is in now is drawn in the colour of
its axis. Everything else keeps a role colour, which is why the two agents in the interaction
report are blue and amber.

## Tests

`python -m pytest tests` runs everything in-process, on ports the OS hands out, so a running API
does not affect it.

The suite that matters most is the LASSI conformance test. `LASSIFormalModel` is one of three
implementations of the model (`lassi_simulations`, this repository, and the PerTRAIN production
repository), which feed the same published claims, and nothing detects drift between them
automatically. `tests/data/lassi_test_vectors.json` is a copy of `handoff/test_vectors.json` from
`lassi_simulations`, generated there from the reference implementation: 23 cases across both axes,
`IR = 0` at and away from the default, `IR = ±1`, the degenerate corner at `|IR| = 1` and
`lambda = 1`, endpoint targets, narrow and wide repertoires, grids of 5, 7, 9 and 11, and defaults
near the admissible edge. `tests/test_lassi_formal_model.py` asserts every expected value to 1e-9,
plus the invariants. When the model changes there, the vectors are regenerated
(`python -m handoff.generate_test_vectors`) and replace this copy. A mismatch is a release blocker,
not a rounding question.

The other files cover the API (`test_api_interactions.py`: two models in one interaction, ending
early, the record, the restart answer, actions without a turn, the cursor, recovery by
`clientRequestId`), model parameters (`test_model_parameters.py`), the interaction report
(`test_interaction_report.py`), and the port policy (`test_ports.py`).

## Planned work

Roughly in the order of what blocks what:

1. **The deployment's gaps**: interaction expiry, the client address behind the proxy, and state
   beyond the process (`deployment.md`).
2. **Interfaces and paradigms.** PerTRAIN is the only interface connected so far; MovES is next.
   Paradigms could also run on the platform itself (LASSI, MovES, Direct). A paradigm enacts the model's output (as an
   utterance, a movement, a rendered scene) and codes what the partner perceives back into
   numbers. The wire format already draws the boundary there: `behavior` goes in, `experience`
   comes out. The seam is `_apply_behavior` in `src/API/Interaction.py`, where a behavior becomes
   the partner's perception and today only a state space conversion happens. Three things are
   missing: a way to declare which paradigm an interaction runs under, a place for what a paradigm
   produced beside the numbers (ITP `metadata` is the obvious candidate), and per-agent paradigm
   settings (`ParameterSpace.resolve` refuses keys it does not know).
3. **Smaller items, each marked in the code**: the trajectory dashboard
   (`InteractionVisualizer.build_body` raises `NotImplementedError`, and its `trajectories()`
   mixes original and converted messages, so it should read through `InteractionRecord`),
   analysis-unit conversion (monadic to transitive, which raises and surfaces as a `422`),
   geometry constraints inside the converters, and chained conversion (`ac` to `sasb` through
   `ipc`).
4. **Interactions between two humans.** The API runs them (invitation codes, `run_API_interaction`
   with stand-ins), but they have not been tested with participants and are left out of the paper.
5. **Interaction contexts** beyond a string, for example as dimensions such as status difference,
   familiarity, or sociality.
6. **Visualizations on the deployed platform.** The LASSI dashboard (`run_lassi_visualization`)
   runs only locally; the container holds the API alone. The paper therefore says the codebase
   includes a visualization of the LASSI model, not that the platform serves one. Deploying the
   dashboards next to the API would make them reachable for anyone with the link.
7. **Setting the model seed from a request.** Every model agent now runs on a seed the server
   draws and reports as `modelSeed` (`api_design.md`, *Model seeds*), so the model side of a
   recorded run can be repeated in Python. Repeating it through the API needs a request field for
   the seed.
