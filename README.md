# Interpersonal Transaction Protocol (ITP)

This repository contains a minimal Python reference implementation for letting formal models of interpersonal interaction communicate through standardized numerical messages. The implementation is intentionally simple and transparent. It is not intended to be a production system yet.

## General Idea

The Interpersonal Transaction Protocol (ITP) defines a shared message format for exchanging interpersonal state information between agents. These agents can be formal models implemented inside this repository, external models exposed through an API, human users, or future interaction paradigms.

The central goal is to specify what information is passed during an interaction, for example:

- who produced a message
- who should receive it
- when it occurred
- which numerical interpersonal values were produced
- in which interaction context it occurred

For now, the repository focuses on direct message exchange between formal models. Later, the same protocol can also be used by interaction paradigms such as LASSI, movES, or Direct, where formal model outputs are enacted in simulated interactions and then converted back into numerical model inputs.

## Core Design

The implementation separates three layers:

1. **Formal models**
   - Generate numerical output.
   - Integrate numerical input.
   - Can be internal Python classes or external models accessed via API.

2. **ITP messages**
   - Standardized dictionaries containing source, target, timecode, values, context, and optional metadata.

3. **Communication sessions**
   - Implemented by `Communication`.
   - Store and validate ITP messages.
   - Do not store or manage model objects.
   - Can therefore also be used with external messages only.

`Communication` is deliberately not a dyad of Python objects. It is a stateful ITP message session.

## Current ITP Message Format

A minimal ITP message looks like this:

```json
{
    "schema_version": "0.2",
    "source_agent": {
        "id": "model_sasb",
        "state_space": "sasb",
        "analysis_unit": "monadic"
    },
    "target_agent": {
        "id": "model_ipc",
        "state_space": "ipc",
        "analysis_unit": "monadic"
    },
    "timecode": {
        "timestamp": "0:00",
        "interaction_turn": 1
    },
    "values": {
        "state_space": "sasb",
        "analysis_unit": "monadic",
        "data": {
            "Aff": 1,
            "Int": -1
        }
    },
    "context": "workplace_colleague_conversation"
}
```

### Fields

| Field | Description |
|---|---|
| `schema_version` | Version of the ITP message schema (currently `0.2`). |
| `source_agent` | Producing agent as `{"id", "state_space", "analysis_unit"}`. |
| `target_agent` | Receiving agent as `{"id", "state_space", "analysis_unit"}`. |
| `timecode` | Dictionary containing time information, currently `timestamp` and `interaction_turn`. |
| `values` | Values block as `{"state_space", "analysis_unit", "data"}`, where `data` maps dimension names to numbers. |
| `context` | String describing the interaction context. |
| `metadata` | Optional free-form metadata (e.g. `message_type`, conversion provenance). |

When two agents use different state spaces, the message `values` are converted to the target's state space before delivery. Conversion lives outside the core protocol in the `converter` module and is applied by the runner, not by `Communication`.

## Project Structure

```text
itp/
├── README.md
├── requirements.txt
├── .gitignore
├── configs/
│   ├── formal_model_parameters.yaml
│   └── interaction_contexts.yaml
│
├── docs/
│   ├── ITP_API_Specification.pdf
│   ├── api_design.md
│   ├── client_split.md
│   └── img.png
│
├── itp-api-flow.html
├── itp-communication-flow.html
│
├── schema/
│   ├── ITP extended/
│   │   ├── ITP.json
│   │   └── ITP_converted.json
│   │
│   ├── interpersonal-behavior-state-space/
│   │   ├── interpersonal-behavior-state-space.schema.json
│   │   ├── haetscher-et-al-preprint.json
│   │   ├── ipc.json
│   │   ├── sasb.json
│   │   └── westermann-banisch-2025.json
│   │
│   └── interpersonal-state-space/
│       ├── interpersonal-state-space.schema.json
│       ├── haetscher-et-al-preprint.txt
│       └── westermann-banisch-2025.json
│
├── ui/
│   └── index.html
│
├── src/
│   ├── ITPSpecification.py
│   ├── run_API_interaction.py
│   ├── run_lassi_visualization.py
│   ├── run_local_interaction.py
│   ├── run_mock_ui.py
│   ├── run_model_api.py
│   │
│   ├── API/
│   │   ├── APIClient.py
│   │   ├── APIModels.py
│   │   ├── APIProblem.py
│   │   ├── APISpecification.py
│   │   ├── Interaction.py
│   │   ├── InteractionRegistry.py
│   │   ├── Invitation.py
│   │   ├── ModelCatalogue.py
│   │   └── StateSpaceSchema.py
│   │
│   ├── communication/
│   │   └── Communication.py
│   │
│   ├── converter/
│   │   ├── BaseConverter.py
│   │   ├── ConverterRegistry.py
│   │   └── BehavioralStateSpaceConverters.py
│   │
│   ├── deprecated/
│   │   ├── APIClient_deprecated.py
│   │   ├── APISpecification_deprecated.py
│   │   └── StateSpaceConverter_deprecated.py
│   │
│   ├── formalmodels/
│   │   ├── BaseFormalModel.py
│   │   ├── DummyFormalModels.py
│   │   └── LASSIFormalModel.py
│   │
│   ├── interactioncontext/
│   │   └── InteractionContext.py
│   │
│   ├── utils/
│   │   ├── ports.py
│   │   └── utilfuncs.py
│   │
│   └── visualization/
│       ├── BaseVisualizer.py
│       ├── FormalModelVisualizer.py
│       ├── InteractionVisualizer.py
│       └── LASSIFormalModelVisualizer.py
│
├── tests/
│   ├── data/
│   │   └── lassi_test_vectors.json
│   ├── test_lassi_formal_model.py
│   └── test_ports.py
│
└── conftest.py
```

## Main Components

### `ITPSpecification`

Defines and validates the shared ITP message format.

Both internal and external models should produce and consume messages that satisfy this specification.

### `Communication`

Stores and validates ITP messages within one communication session.

The class keeps track of:

```python
communication.messages
communication.last_message
communication.n_messages
communication.context_name
```

It does not store model objects or API clients. Model orchestration happens outside the class.

### `BaseFormalModel`

Abstract base class for formal models implemented inside this repository.

Internal formal models must implement:

```python
integrate_numerical_input()
generate_numerical_output()
```

The base class also provides helper methods for converting model output to ITP messages and integrating ITP messages as input.

### Dummy formal models

Simple reference models for testing, defined in `formalmodels/DummyFormalModels.py`:

- `DummyIPCFormalModel` — state space `ipc`, dimensions `Theta` and `R`.
- `DummySASBFormalModel` — state space `sasb`, dimensions `Aff` and `Int`.

Both are `monadic` and update their state by averaging their current state with the incoming state.

### `LASSIFormalModel`

Agency-communion model (`state_space = "ac"`, dimensions `A` and `C`). Internally it works on a
symmetric, zero-centred grid −3 … +3 and exchanges discrete states on the ITP 1–7 scale.

Each axis carries a probability distribution over that grid. One exchange moves the mean of that
distribution to a convex mixture of where the agent was, its behavioral default, and the state
the partner's behavior implies; the distribution is then the agent's habitual repertoire,
minimally deformed to have exactly that mean. Two properties follow and are relied on elsewhere:
the realised mean equals the intended mean to solver precision, and the mean cannot leave the
grid, so nothing is ever clipped — a clip in this model would be a bug being hidden. Reactivity
is signed: its magnitude is the weight on the partner, its sign is the direction of the response.

The equations, the parameter contract and the invariants are deliberately not repeated here. The
normative description is `handoff/formal-model-spec.md` in the `lassi_simulations` repository;
the module docstring in `src/formalmodels/LASSIFormalModel.py` states the update rule as it is
implemented. This repository holds a reimplementation, not a copy — three implementations feed
the same published claims and nothing detects drift between them, which is what `tests/` is for.

The spec is written in mathematical notation and this module in names. The module docstring
carries the mapping between the two, so a reader can follow one beside the other.

Two things this repository decides for itself:

- **Scale.** Axis parameters in `configs/formal_model_parameters.yaml` are on the ITP 1-based
  scale — the scale ITP messages carry, and the one the sister repository states its behavioral
  defaults on. `to_itp_state` and `to_internal_state` convert at the message boundary.
- **Diagnostics.** `step_record()` per axis and `step_records()` per model expose every
  intermediate of the last update, under the field names the conformance vectors use, which is
  what the dashboard and the test both consume.

### `visualization`

Dash dashboards, decoupled from the models they render. `BaseVisualizer` owns the shared style,
the page scaffolding and the Dash hosting; subclasses declare their input source, their page
content and their callbacks.

The style follows the PerTRAIN design system, so a screenshot from a dashboard sits beside the
homepage, the mock client and a slide without looking like a different project: neutral light
surfaces, blue for primary elements, green and amber for the remaining roles, and the system sans
stack rather than the brand's Sofia Sans and Inter, so that no font binaries live in this
repository. Two colours are reserved and should not be spent on anything else:

| Axis | Colour | |
|---|---|---|
| Agency | `#315A7D` | dark, muted blue |
| Communion | `#B84650` | muted red-pink |

They are the agreed pair for agency-communion figures — a different hue each, agency deliberately
the darker of the two, both used as solid areas (`docs/img.png`). In the dashboards they mark the
axis itself: whatever state the agent is in *now* is drawn in the colour of its axis, so a figure
reads as agency or as communion without the caption having to say so. `FormalModelVisualizer` renders a single formal model without
interaction data, `InteractionVisualizer` renders a sequence of ITP messages as a trajectory
(not implemented yet), and `LASSIFormalModelVisualizer` is the interactive walk-through of one
LASSI update step.

### `API`

The API module implements `docs/ITP_API_Specification.pdf`: it lets a
JavaScript web application run interactions between human participants and
formal models. All four dyad configurations are supported — model to model,
human to model, model to human, and human to human. The two model agents of an
interaction may run different models (`agents.X.modelId`), provided a converter
connects their state spaces, and every agent reports the model it runs, `null`
for a human.

```text
GET    /api/v1/models                                               model catalogue
GET    /api/v1/models/{modelId}                                     definition + stateSpaceSchema
POST   /api/v1/interactions                                         create, issue token and invitation
POST   /api/v1/interactions/join                                    redeem an invitation code
GET    /api/v1/interactions/{sessionId}                             status
POST   /api/v1/interactions/{sessionId}/agents/{agentId}/register   register a participant
GET    /api/v1/interactions/{sessionId}/agents/{agentId}/perception poll for a perception
POST   /api/v1/interactions/{sessionId}/agents/{agentId}/actions    submit a behavior
POST   /api/v1/interactions/{sessionId}/end                         terminate
GET    /api/v1/interactions/{sessionId}/results                     persisted record
```

The server is authoritative for interaction state and turn numbers. It runs
formal model agents itself, converts every behavior into the perceiving agent's
state space, and hands clients bare `experience` and `behavior` vectors. Inside,
every behavior is still wrapped into a full ITP message and stored in a
`Communication`, so an API-driven interaction produces the same record as a
local one; `/results` returns both.

Each model exposes one shared `stateSpaceSchema`, compiled by
`StateSpaceSchema` from the IBSSS descriptions in
`schema/interpersonal-behavior-state-space/`, and used to validate every
submitted behavior and every returned experience — including the geometry
constraints JSON Schema cannot express, such as the SASB diamond.

Authentication is an interaction-scoped bearer token, issued on creation and on
join. Human-to-human interactions get a single-use six-digit invitation code,
stored hashed, with a rate-limited join endpoint. Errors are RFC 9457
`application/problem+json` documents.

Communication is stateful per interaction and lives in memory, and so do the
interactions and their tokens: a restart drops them, and a client asking about
an interaction the server no longer knows gets a `404` telling it to start a
new one. See
`docs/api_design.md` for the design, the extensions to the specification, and
the known gaps. The previous `/info` and `/sessions` API is kept unmounted in
`src/deprecated/`.

### `interactioncontext`

Placeholder module for interaction contexts.

For now, context is represented as a string in the ITP message, for example:

```text
workplace_colleague_conversation
romantic_partner_conflict
stranger_smalltalk
```

Later, contexts may be represented more richly, for example through dimensions such as status difference, familiarity, duty, positivity, negativity, or sociality.

### `converter`

Converts message `values` between state spaces. `BaseConverter` converts a values block only;
`ConverterRegistry` selects a registered converter and raises when no mapping exists.
Default converters cover `ac <-> ipc` and `sasb <-> ipc`.

Note: geometric/geometry constraints between state spaces are **not enforced yet** — conversions
are numeric approximations. Converters live outside `Communication`; the runner applies them
before delivering a message to a model with a different state space.

A client joins in the state space its own scale speaks, and the API converts to and from the
model's space. The PerTRAIN backend (`ITPGenerator`) registers its human agent in `ac`, because
its agency and communion axes have seven states, which is the `ac` grid (1 to 7, set by
`AC_NUM_STATES`). Which models a client can talk to therefore depends on the converters: an `ac`
client reaches `lassi` directly and `dummy-ipc` through `ac <-> ipc`, but not `dummy-sasb`,
because converters are not chained.

A client with a different number of states, say a PerTRAIN model with five states per axis,
needs a new state space in this repository, not a change to `ac`. `ac` is tied to LASSI's seven
states, and changing its range silently rescales every converted message. The new space needs:

1. an IBSSS description with the new range in `schema/interpersonal-behavior-state-space/`;
2. an entry in `STATE_SPACE_SOURCES` in `src/API/StateSpaceSchema.py`, under its own
   identifier (e.g. `ac5`);
3. converters to every space it should reach, registered in `make_default_converter_registry`.
   To talk to `lassi`, that includes a converter to `ac` itself;
4. a redeploy of the API.

### `configs`

`interaction_contexts.yaml` holds the interaction contexts, `formal_model_parameters.yaml` holds
the parameters of the formal models. Both are read with `load_config` from `utils/utilfuncs.py`.

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Running a Local Interaction

Run from the repository root (the modules import as `src.…`, so run them as modules):

```bash
python -m src.run_local_interaction
```

This instantiates two internal dummy models and lets them interact sequentially.

One interaction turn currently means:

1. the first model generates an ITP message
2. the communication session stores and validates it
3. the second model integrates it
4. the second model generates an ITP message
5. the communication session stores and validates it
6. the first model integrates it

## Running the LASSI Visualization

Serve the interactive walk-through of one LASSI state distribution update (from the repository
root):

```bash
python -m src.run_lassi_visualization
```

Then open the address it prints, normally http://127.0.0.1:8050 (the next free port in 8050–8059
if that one is taken; `ITP_VISUALIZATION_PORT` names one exactly). The sliders vary the axis parameters, the axis
selector switches between agency and communion — which also switches the colour every trace of
the current state is drawn in — and the four figures show the mean rule, the two
targets the partner's state implies and which one the sign of `IR` picks, the tilt that carries
the distribution to the new mean, and the trajectory the same exchange produces when it is
repeated against an unchanged partner. A readout under the sliders carries the arithmetic,
including the residual `|E[p_t] − E[S_t]|`, which is the model's exactness claim made visible.
The dashboard recomputes each step on a throwaway axis, so it never changes the model it
visualizes.

## Running an API-Based Interaction

First, start a model API in one terminal (from the repository root):

```bash
python -m src.run_model_api
```

The API should be available at:

```text
http://127.0.0.1:8001
```

Useful endpoints:

```text
http://127.0.0.1:8001/api/v1/models
http://127.0.0.1:8001/docs
```

8001 is the first choice, not a requirement. If something already holds it —
a leftover process from an earlier session, or an unrelated service — the API
takes the next free port in 8001–8010 and prints which one, rather than
refusing to start and making you evict whatever is there. `ITP_API_PORT` names
a port instead, and is then obeyed exactly:

```bash
ITP_API_PORT=9001 python -m src.run_model_api
```

Clients do not have to be told. While the API runs it writes its base URL to
`.itp-api-url` at the repository root (untracked), and `run_API_interaction`
and the mock client read it, check that it answers, and otherwise search
8001–8010 for a live catalogue. `ITP_API_BASE_URL` overrides the search
wholesale, for an API on another host.

Then, in another terminal, run (from the repository root):

```bash
python -m src.run_API_interaction
```

This runs one interaction of each dyad configuration against the API: two
formal models, a participant against a formal model, and two participants
joined by an invitation code. Where a human would sit, a local formal model
stands in, taking the experience out of each perception and submitting its own
output as a behavior — the same loop the JavaScript application runs around a
human.

## Running the Mock Client

The primary client of the API is a JavaScript application that does not exist yet.
`ui/index.html` stands in for it: one page, no build step, no dependencies, calling the API
from the browser the way that application will.

Start the API in one terminal and the page in another (both from the repository root):

```bash
python -m src.run_model_api   # http://127.0.0.1:8001
python -m src.run_mock_ui     # http://127.0.0.1:5173
```

Then open the address `run_mock_ui` prints, normally http://127.0.0.1:5173. The port matters:
serving the page from the API process would make it same-origin and hide the CORS check, which
is the opposite of what a mock client is for, so `APISpecification` has to allow the page's
origin explicitly. It allows `localhost` and `127.0.0.1` on 5173–5182, which is the range
`run_mock_ui` picks from — so a port already in use costs nothing, and a page served from
anywhere else is still refused before it reaches a route. `ITP_UI_PORT` names a port outside
that range, but it then has to be set for the API process too, since that is where the origin
list is built.

The page does not have to be told which port the API took. `run_mock_ui` finds the API the same
way `run_API_interaction` does and answers `mock-ui-config.json` with the result, which fills in
the base URL field before the first request. The field stays editable: discovery is a
convenience, not a constraint.

Each step is a collapsible card: the one you are on is open, the ones behind you fold up with a
one-line summary, and any of them can be reopened by clicking its header. The page walks the
whole workflow:

1. **Connect** — `GET /models` renders the catalogue, and `GET /models/{modelId}` is fetched for
   each model, which is where the page gets a compiled state space schema for every space this
   API knows. There is no endpoint for a state space on its own. For the deployed API, enter the
   key in the API key field: it is sent as `X-API-Key` on every request, for the gateway in front
   of the API. It stays in the field and never appears in the log.
2. **Set up** — pick who is in the interaction, the model of each agent, and the state space *you*
   act in. A human agent may work in a space the model does not use, in which case the server
   converts every perception into it and validates your behavior against it. The catalogue
   above only lists the models; here the *Agent A* and *Agent B* fields pick the model each agent
   runs, from the available ones, and show *You* or *Second participant* where a human sits.
   With two participants, a third field picks the model the interaction is bound to, which
   neither of you runs: the API requires one, and it sets the default state space and the turn
   limits.
3. **Create** — `POST /interactions`, then `POST .../register` for your agent. With two humans
   the six-digit invitation code appears; open the page in a second tab and redeem it in the
   *Join with a code* panel. With two models the server plays both and the page goes straight
   to the record.
4. **Perceive** — the page long-polls `GET .../perception` and renders the state machine:
   `pending`, `perceivable`, `actionRequired`, `interactionEnded`.
5. **Act** — one input per dimension, with the bounds the schema declares. Out-of-range values
   are submitted rather than blocked, so the server's `422` and its `errors` array are visible
   instead of being pre-empted by the page.
6. **Read the record** — `GET .../results` shows the turns and the ITP messages the server built
   from the bare wire vectors, and names the folder under `results/` the server wrote them to.

Every request and response is listed on the right, newest first, with problem documents
rendered in full. That panel is the point of the page: it is how the protocol is inspected
rather than inferred.

The interaction context is deliberately not a control on this page. It reaches the ITP messages
but modulates nothing in any model yet, so the API's default stands rather than a field that
suggests a choice with no consequence.

State lives in the tab. Reloading the page starts over, and the interaction it left behind
stays on the server until the process is restarted.

### Where the runs are written

Every interaction created with persistence enabled records itself in `results/`, one folder per
interaction named `<creation timestamp>_<session prefix>`:

```text
results/20260914_155820_9aa18034/
├── interaction.json
├── message_001_<source>_to_<target>_original.json
├── message_002_<source>_to_<target>_converted.json
└── …
```

The message files are the same ones a local interaction produces, `_converted` copies included
whenever the two agents work in different state spaces. `interaction.json` holds what only the
API knows: which agent was human and which was a model, which model each ran, the state space
each worked in, and how and when the interaction ended.

The folder and `interaction.json` are written when the interaction is created, each message as
it arrives, and `interaction.json` again when the interaction starts and when it ends. An
interaction ended early with *End interaction* (`POST .../end`) keeps every message up to that
point. With persistence off, nothing is written.

This is a property of the API process, not of the page: `src/run_model_api.py` passes the
repository root as `results_root`, and an `APISpecification` built without one writes nothing to
disk. See `docs/api_design.md` under *Persistence*.

## Tests

```bash
python -m pytest tests
```

The suite that matters most exists for one reason. `LASSIFormalModel` is a reimplementation
of the model in the `lassi_simulations` repository, which also lives a third time in the
PerTRAIN production repository. The three are separate implementations feeding the same
published claims, and nothing detects drift between them automatically.

`tests/data/lassi_test_vectors.json` is a copy of `handoff/test_vectors.json` from
`lassi_simulations`, generated there from the reference implementation. It holds 23 cases
covering both axes, `IR = 0` at and away from the default, `IR = ±1`, the degenerate corner at
`|IR| = 1` and `lambda = 1`, endpoint targets, narrow and wide repertoires, grids of 5, 7, 9 and
11, and defaults near the admissible edge. `tests/test_lassi_formal_model.py` runs every case and
asserts every expected value to 1e-9, plus the invariants the file lists — the distribution sums
to one, the realised mean equals the intended mean, the three weights are convex, no clipping is
ever needed.

When the model changes in `lassi_simulations`, the vectors are regenerated there
(`python -m handoff.generate_test_vectors`) and the new file replaces this copy. A mismatch is a
release blocker, not a rounding question.

`tests/test_api_interactions.py` drives the API in-process: two different models in one
interaction, a pair without a converter refused, ending early with the record kept, the record
written at creation, and the `404` a client gets after a restart.

`tests/test_ports.py` covers the port policy in `src/utils/ports.py`: an explicit port is obeyed
or refused, never silently replaced; held candidates are skipped, also when the holder listens on
another address than the one asked about (`0.0.0.0` against `127.0.0.1`, or `::1`), which a bind
test alone misses on macOS; clients discover the API in the documented order, believing the
`.itp-api-url` note only when it answers like the catalogue, and find an API bound to all
interfaces; and the API announces itself under `127.0.0.1`, never `0.0.0.0`, which browsers have started to block.
It uses ports the OS hands out, so an API already running on this machine does not affect it.

## Current Status

Implemented:

- ITP message specification
- `Communication` session for storing and validating ITP messages
- abstract base class for internal formal models
- dummy formal models (`DummyIPCFormalModel`, `DummySASBFormalModel`) and `LASSIFormalModel`
- local interaction between two formal models
- ITP API (`docs/ITP_API_Specification.pdf`): model catalogue, interaction
  lifecycle, server-authoritative turns, participant registration, invitation
  codes, perception polling, idempotent action submission, problem+json errors
- two different formal models in one interaction, and the model of each agent
  in every interaction response
- validating state space schemas compiled from the IBSSS descriptions, with
  geometry constraints
- API client mirroring the JavaScript client
- value conversion between state spaces (`ac <-> ipc`, `sasb <-> ipc`) via `ConverterRegistry`
- interactive visualization of the `LASSIFormalModel` update step
- browser mock client of the API (`ui/index.html`), standing in for the JavaScript application.
  It is due to move into its own repository as the client participants use; see
  `docs/client_split.md`
- conformance test of `LASSIFormalModel` against the handoff vectors of `lassi_simulations`

Not yet implemented:

- interaction expiry and cleanup: no reaper, no interaction lifetime, no cap
  (`docs/api_design.md`)
- persistence beyond the process lifetime
- full interaction context logic
- standardized context representation
- interaction paradigms
- LLM-based enactment of formal models
- geometry constraints inside the converters in general: the API validates
  converted vectors and fails the interaction when one leaves the target space,
  but the converters do not yet keep them inside it. The one case that is
  settled is the IPC neutral center, which the circumplex now includes and
  marks with `R = 0` (`docs/api_design.md`)
- analysis-unit conversion (e.g. monadic <-> transitive)

## Next Steps

Roughly in the order of what blocks what. Each item names the code it touches, so none of it
has to be re-derived later.

### 1. Serve the API from the university host

Resources for a server at the University of Münster have been granted. Everything in `src/API/`
currently assumes a single process on `localhost`, and four of the *Known gaps* in
`docs/api_design.md` stop being theoretical the moment it is deployed:

- **HTTPS and the proxy.** The process serves plain HTTP and has to sit behind a terminating
  proxy. That proxy must forward the client address: the `clientRequestId` replay scoping and
  the join rate limiter both key on the socket address, and behind a proxy that does not forward
  it, every client collapses into one and the rate limit becomes global.
- **CORS.** `DEFAULT_ALLOWED_ORIGINS` in `APISpecification` is the loopback development range,
  `localhost` and `127.0.0.1` on 5173–5182, so the mock client can move ports when one is taken.
  The deployed origin of the JavaScript application replaces it, and it has to be decided whether
  the mock client keeps an origin there at all. Ten loopback ports are harmless on a development
  machine and would not be in a deployment.
- **Interaction lifetime.** There is no reaper. The `expired` status and the `interactionExpired`
  and `registrationTimeout` end reasons exist and nothing sets them, so a process that is up for
  weeks accumulates interactions until it restarts. It needs an expiry, a cap on concurrent
  interactions, or both.
- **State beyond the process.** Records are written to `results/` as interactions run, but the
  interactions themselves live in memory: a restart drops every one in flight, with its tokens
  and invitation codes. This is accepted for now. A client asking about an interaction the server
  no longer knows gets a `404` saying so, and starts a new one. The alternative, a store from
  which interactions resume after a restart, is described with its costs in `docs/api_design.md`
  under *Server restarts*; the hard part is serializing each formal model's state exactly.

Open: which host, whether the API and the JavaScript application share one, and how it is
deployed — a service on the machine, a container, or the university's own platform.

### 2. Mirroring between GitHub and the university GitLab

Undecided, and worth settling before the server is set up, because whichever side is primary is
the side the deployment pulls from. The two arrangements are not symmetric:

- **GitHub primary, `zivgitlab.uni-muenster.de` a push mirror.** Work stays where it is; the
  university side is a read-only copy that a WWU-internal deployment can reach without opening
  anything outward. Mirroring is one-way, so a hotfix committed on the GitLab side would be
  overwritten.
- **GitLab primary, GitHub a public mirror.** CI, deployment and the code sit on the same host,
  which is where most PerTRAIN repositories already are, and GitHub becomes the public release
  surface. The cost is that day-to-day work moves.

Whichever way it goes, it is worth writing down: who may push where, whether the mirror is
automatic or a step in a release, and which branch the deployment follows.

### 3. Interaction paradigms over the API: LASSI, movES, Direct

Today a behavior is a numerical vector and the partner receives a numerical vector. A paradigm
belongs between the two: the model's output is *enacted* — as an utterance, a movement, a
rendered scene — and what the partner perceives is coded back into numbers. That is the design
the protocol was written for (see *General Idea*), and the API's wire format already draws the
boundary in the right place: `behavior` goes in, `experience` comes out.

What is missing is the seam. In `src/API/Interaction.py`, `_apply_behavior` turns a submitted
behavior into an ITP message, hands it to `_convert_for_target`, validates the result and makes
the partner's perception out of it. Enactment and coding would hook in exactly there, where a
behavior becomes an experience — today the only thing that happens on that path is a state space
conversion.

Three things follow from that, and none of them exist yet:

- a way for a model entry, or an interaction, to declare which paradigm it runs under, so that
  the same formal model can be exchanged directly in one study and enacted in another
- a place for a paradigm to put what it produced beside the numbers, since an utterance or a
  rendered scene is not an ITP value and should not be squeezed into one; ITP `metadata` is the
  obvious candidate and has never been used for anything load-bearing
- `agents.X.configuration`, which the API accepts and stores but never passes to the model
  factory — a paradigm is the first thing that would need per-agent configuration to mean
  something

### 4. Already named in the code

Smaller, and each one already has a marker where it belongs:

- the trajectory dashboard — `InteractionVisualizer.build_body` raises `NotImplementedError`, and
  `trajectories()` below it is the data it would draw
- analysis-unit conversion (monadic ↔ transitive), which raises today and surfaces as a `422`
- geometry constraints inside the converters, rather than only at the API boundary
- chained conversion (for example `ac` to `sasb` through `ipc`), so that every pair of models can
  interact rather than only pairs with a direct converter

- interaction trajectory visualization (`InteractionVisualizer`)
- richer formal models
- production-level API handling, authentication, logging, and deployment