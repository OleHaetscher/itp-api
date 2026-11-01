# Interpersonal Transaction Protocol (ITP)

The ITP framework makes formal models of interpersonal dynamics interoperable, comparable, and
usable in human interaction. It has three parts:

- **The ITP**, a common format in which formal models exchange numerical information across state
  spaces.
- **The ITP platform**, a shared environment that hosts models and runs and records interactions
  between two models, or between a model and a human.
- **The ITP interfaces**, which connect formal models to interactive paradigms that translate
  model states into observable behavior and the partner's behavior back into model input.

This repository holds the code for all three, in Python. It is work in progress.

## The ITP

The ITP represents an interaction as an alternating sequence of messages between two agents,
either two formal models or a formal model and a human. Agents keep their internal mechanisms. They
send and receive numerical states in an explicitly declared state space. One message:

```json
{
    "schema_version": "0.2",
    "source_agent": {"id": "model_sasb", "state_space": "sasb", "analysis_unit": "monadic"},
    "target_agent": {"id": "model_ipc", "state_space": "ipc", "analysis_unit": "monadic"},
    "timecode": {"timestamp": "0:00", "interaction_turn": 1},
    "values": {
        "state_space": "sasb",
        "analysis_unit": "monadic",
        "data": {"Aff": 1, "Int": -1}
    },
    "context": "workplace_colleague_conversation"
}
```

| Field | Description |
|---|---|
| `schema_version` | Version of the message schema (currently `0.2`) |
| `source_agent`, `target_agent` | The producing and the receiving agent, each with its state space and analysis unit |
| `timecode` | When the message occurred: `timestamp` and `interaction_turn` |
| `values` | The values, as dimension names and numbers, in a named state space |
| `context` | The interaction context, currently a string |
| `metadata` | Optional free-form information (e.g., the provenance of a conversion) |

Machine-readable schemas in `schema/` define each state space by its type, dimensions, ranges, and
geometric constraints. They cover the interpersonal circumplex (`ipc`), its Cartesian
agency-communion form (`ac`), the Structural Analysis of Social Behavior (`sasb`), and the
relational state space of Westermann and Banisch (2025). When two agents use different state
spaces, a registered converter (`src/converter/`) translates the values before delivery, and the
message records the conversion. The message format and its validation are in
`src/ITPSpecification.py`, the session that stores the messages of one interaction in
`src/communication/`.

## The ITP platform

The platform is a web API (`src/API/`) that implements the specification in
`docs/ITP_API_Specification.pdf`. It runs interactions between two models, or between a model and
a human. The server keeps the turns, runs the hosted models itself,
converts and validates every message, and stores every exchange as ITP messages. Clients send and
receive bare vectors: a client submits its agent's `behavior` and perceives the partner's behavior,
converted into its own state space, as `experience`. With persistence enabled, every interaction is
recorded in `results/`, one folder per interaction. Figure 1 of the paper shows this workflow; it
is section 00 of `itp-api-flow.html`, with *Download SVG* and *Download PNG* under the figure.

Models are hosted in the shared codebase (`src/formalmodels/`), where each one declares its state
space and implements how it integrates input and generates output. Two dummy models, one in `ipc`
and one in `sasb`, average their state with what they receive. `LASSIFormalModel` is the model of
LLM-based agent simulations for modeling individual differences in social interactions (LASSI), in
`ac` with 1 to 7 on each axis. Its behavioral default (`BD`) and reactivity (`IR`) can be set per agent and
per interaction, by hand or as a seeded random draw. A remote model stays on its own infrastructure
and takes part through the web API, like a human client.

The design of the API and its extensions to the specification are in `docs/api_design.md`. The
deployed platform runs at `https://itp-api.uni-muenster.de`; `docs/deployment.md` describes how a
new version goes live.

## The ITP interfaces

An interface connects the platform to an interactive paradigm. The paradigm sends the partner's
observed behavior to the platform and receives the behavioral state the formal model prescribes.

**PerTRAIN** is the interface connected so far. In it, LLM-based agents chat with each other or
with people, following the LASSI paradigm: an LLM turns an agent's interpersonal state into an
utterance and codes the partner's utterances in agency and communion. A formal model on the
platform sets each agent's state for its next message. Figure 2 of the paper shows such a dialog,
a conflict in a bar between two agents, one steered by LASSI and one by the dummy circumplex model
(see *Visualization and didactics*). Connecting the **MovES** paradigm is planned.

Two **example clients** show how other applications connect:

- `ui/`, a browser client that exposes every step of the API and logs each request and response.
  It runs interactions with any hosted model, as a participant or between two models.
- `examples/itp-api-basic-web-client/`, a minimal participant-facing web application for one
  paradigm: LASSI against a person who places points in the circumplex. It keeps the API key and
  the interaction token on its own server and runs against the deployed platform.

## Visualization and didactics

The repository makes interactions and models visible, for research figures and for teaching.

- **Interaction reports.** `src/run_interaction_report.py` turns a recorded interaction into one
  self-contained HTML page that opens from disk. A slider steps through the turns. The figure shows
  the dialogue, one plane per agent in its own state space with the partner's behavior as it
  arrived, and each dimension over turns. *Download SVG* and *Download PNG* export the figure at
  the selected turn. The text of an interaction never passes through the platform; it is supplied
  as a CSV with the columns `turn`, `role` and `text`. Figure 2 of the paper is a frame of such a
  report, and `examples/interaction-report/` holds the PerTRAIN run behind it.
- **The LASSI dashboard.** `src/run_lassi_visualization.py` walks through one update of the LASSI
  model: how the mean moves between where the agent was, its behavioral default, and the partner's
  behavior, and how the state distribution follows. Sliders vary the parameters.
- **Flow diagrams.** `itp-api-flow.html` takes the platform workflow apart step by step, with
  Figure 1 of the paper as its first section. `itp-communication-flow.html` follows one ITP message
  through the codebase.

Planned: visualizations of the other formal models, and a dashboard of interaction trajectories.

## Getting started

Python 3.13. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

All runners are started as modules from the repository root.

```bash
# two dummy models interact locally, without the platform
python -m src.run_local_interaction

# the platform, at http://127.0.0.1:8001 (interactive docs at /docs)
python -m src.run_model_api

# with the platform running, in a second terminal: one interaction of each kind
python -m src.run_API_interaction

# with the platform running: the browser client, at http://127.0.0.1:5173
python -m src.run_mock_ui

# a report of a recorded interaction, written into its folder
python -m src.run_interaction_report results/<folder> --text dialogue.csv

# the LASSI dashboard, one update step of the model, at http://127.0.0.1:8050
python -m src.run_lassi_visualization

# the tests
python -m pytest tests
```

If a port is taken, each runner takes the next free one and prints its address. Clients find the
platform on their own (`docs/development.md`, *Ports and discovery*). In the browser client, keep
*Keep the record* checked to have an interaction written to `results/`.

## How to contribute

The deployed platform needs an API key. For now, open an issue in this repository and describe
briefly what you want to do:

- use the platform, for example with the browser client or your own scripts;
- contribute a formal model, a state space, or a converter;
- connect a client application, such as an interactive paradigm.

You then get an API key and can use the platform.

A client application keeps its own data. With persistence enabled, the platform stores only the
ITP messages of an interaction (the numerical states, their state spaces, and their timing) and a
description of the interaction (its agents, models, and parameters). It never stores the material a
paradigm produces. For PerTRAIN, for example, the chat transcripts stay in PerTRAIN.

Code contributions follow established practice: work on a feature branch, open a pull request, and
merge after code review, with `python -m pytest tests` passing. A new formal model comes with tests
of its update rule. `docs/development.md` describes the layout and the decisions the code relies
on.

## Status

Implemented: the message format and its validation, state space schemas with their geometry,
conversion between `ac`, `ipc` and `sasb`, the platform for interactions between two models or a
model and a human, model parameters per agent, the dummy models and LASSI, the PerTRAIN interface,
the example clients, the interaction report, and a conformance test of the LASSI implementation
against its reference.

Planned: more formal models, converters, and state spaces; context-specific interactions; the
MovES interface; more visualizations; and interactions between two humans, which the API already
supports but which have not been tested with participants.

## Further documentation

| Document | Content |
|---|---|
| `docs/ITP_API_Specification.pdf` | The API specification |
| `docs/api_design.md` | How the platform implements and extends the specification, and its known gaps |
| `docs/development.md` | Layout, design decisions, ports, tests, and planned work |
| `docs/deployment.md` | The deployed platform and how a new version goes live |
| `docs/client_split.md` | The planned move of the browser client into its own repository |
| `itp-api-flow.html` | The platform workflow step by step, with Figure 1 as its first section |
| `itp-communication-flow.html` | How one ITP message passes through the codebase |
