# Interpersonal Transaction Protocol (ITP)

This repository contains a minimal Python reference implementation for letting formal models of interpersonal interaction communicate with each other. The implementation is intentionally simple and transparent. It is not intended to be a production system yet.

## General Idea

The project is built around the idea that formal models can interact in two complementary ways: either directly, by exchanging standardized numerical ITP messages, or indirectly, by being embedded in interaction paradigms such as LASSI, movES, or Direct. In the latter case, the paradigm receives numerical outputs from the formal models, uses them to enact an interaction, for example through LLM-based agents that communicate with one another and assess each other’s behavior, and then returns the resulting numerical information to the formal models. For now, we focus on the formal-modeling part of this process. The central goal is to establish a shared protocol that specifies which information is passed to and from formal models during an interaction, such as another model’s behavior, the interaction turn, and the broader interaction context.
A formal model can participate in an interaction in two ways:

1. **Internal model**
   - The formal model is implemented directly in this repository.
   - It inherits from `BaseFormalModel`.
   - It implements the required methods for integrating numerical input and generating numerical output.

2. **External model**
   - The formal model runs somewhere else.
   - It does not need to inherit from `BaseFormalModel`.
   - It communicates with the ITP framework via API calls.
   - It still needs to consume and produce messages that follow the ITP specification.

The ITP specification defines the shared input/output format for both internal and external models.

## Current ITP Message Format

A minimal ITP message looks like this:

```json
{
    "schema_version": "0.1",
    "source_model_id": "model_a",
    "target_model_id": "model_b",
    "interaction_turn": 1,
    "values": {
        "communion": 3.75
    },
    "context": "workplace_colleague_conversation"
}
```

Note: For now, this neglects sth like a mapping between different interpersonal frameworks (e.g., IPC and SASB), but this can be extended. However, I would probably define the mapping independent of the protocol and internally check if a mapping is available so that two frameworks can interact. 

### Fields

| Field | Description |
|---|---|
| `schema_version` | Version of the ITP message schema. |
| `source_model_id` | Identifier of the model that produced the message. |
| `target_model_id` | Identifier of the model that should receive the message. |
| `interaction_turn` | Sequential turn in the interaction. |
| `values` | Numerical output produced by the source model. Currently focused on interpersonal circumplex dimensions such as `agency` and `communion`. |
| `context` | String describing the interaction context. |
| `metadata` | Optional free-form metadata. |

## Project Structure

```text
itp/
├── README.md
├── configs/
│   └── example_itp_message.json
├── results/
│   └── ITPs/
│       ├── turn_001_model_a_to_model_b.json
│       ├── turn_001_model_b_to_model_a.json
│       └── ...
├── src/
│   ├── ITPSpecification.py
│   ├── run_local_interaction.py
│   ├── run_API_interaction.py
│   ├── run_model_api.py
│   │
│   ├── API/
│   │   ├── APIClient.py
│   │   └── APISpecification.py
│   │
│   ├── FormalModels/
│   │   ├── BaseFormalModel.py
│   │   └── DummyFormalModel.py
│   │
│   ├── InteractionContexts/
│   │   ├── BaseInteractionContext.py
│   │   └── WorkContext.py
│   │
│   ├── Paradigms/
│   │   ├── BaseParadigm.py
│   │   ├── BaseGenerator.py
│   │   ├── BaseAssessor.py
│   │   ├── DummyParadigm.py
│   │   ├── DummyGenerator.py
│   │   └── DummyAssessor.py
│   │
│   └── Visualization/
```

## Main Components

### `ITPSpecification`

Defines and validates the message format used by formal models.

This is the central shared interface between models. Both internal and external models should produce and consume messages that satisfy this specification.

### `BaseFormalModel`

Abstract base class for formal models implemented inside this repository.

Internal formal models must implement:

```python
integrate_numerical_input()
generate_numerical_output()
```

The base class also provides shared helper methods for converting model output to ITP messages and integrating ITP messages as input.

### `DummyFormalModel`

A simple reference model used for testing.

Currently, the dummy model:

- focuses only on `communion`
- initializes its state randomly between 1 and 5
- updates its state according to:

```text
new_state = mean(old_state, other_state)
```

### `API`

The API module allows formal models to communicate across processes or locations.

The current REST API exposes endpoints such as:

```text
GET  /info
POST /generate
POST /step
```

This allows one model to run locally while another model runs remotely but still communicates through ITP messages.

### `InteractionContexts`

Placeholder module for defining interaction contexts. This we should discuss for several reasons: 
- We thought that the context should influence not only the paradimgs but also the formal model. However, if we only define the protocol, we can say that all models must accept context information but we do not know what they do with it
- Also, it is not clear yet what the context is. The following is one possibility (assigning some string values) 

```text
workplace_colleague_conversation
romantic_partner_conflict
stranger_smalltalk
```

- but this would require some predefined list of possible contexts. Probably some dimensions (e.g., something like the interpersonal diamonds) with certain justified effects would be better. Maybe sth like values on dimensions that are relevant for the interpersonal dynamics we aim to model (e.g., status difference, familiarity of interaction partner, ...)

For now, context is represented as a string in the ITP message but has no effect on the interaction. 

### `Paradigms`

Placeholder module for interaction paradigms.

This is not yet implemented. The intended purpose is to enact formal models in specific interaction paradigms, for example:

- LLM-based conversations
- structured social-interaction tasks
- repeated dyadic exchanges
- simulated interpersonal situations

The files are already present, but the paradigm logic still needs to be developed. All paradimgs will use the inputs of the formal models and produce outputs for the formal models. 

### `results`

Stores generated interaction protocols.

For example, running a local interaction can generate one JSON message per model output:

```text
results/ITPs/
├── turn_001_model_a_to_model_b.json
├── turn_001_model_b_to_model_a.json
├── turn_002_model_a_to_model_b.json
├── turn_002_model_b_to_model_a.json
└── ...
```

### `configs`

Stores example configuration files and reference messages.

For example:

```text
configs/example_itp_message.json
```

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn requests
```

## Running a Local Interaction

Run:

```bash
python src/run_local_interaction.py
```

This instantiates two internal dummy models and lets them interact sequentially over multiple interaction turns.

One interaction turn means:

1. the first model generates output
2. the second model integrates this output
3. the second model generates output
4. the first model integrates this output

The generated ITP messages can be stored as JSON files in the `results/ITPs/` folder.

## Running an API-Based Interaction

First, start a model API in one terminal:

```bash
python src/run_model_api.py
```

The API should be available at:

```text
http://127.0.0.1:8001
```

Useful endpoints:

```text
http://127.0.0.1:8001/info
http://127.0.0.1:8001/docs
```

Then, in another terminal, run the API-based interaction:

```bash
python src/run_API_interaction.py
```

This lets a local model communicate with a remote model through REST API calls while still exchanging standard ITP messages.

## Current Status

Implemented:

- ITP message specification
- abstract base class for internal formal models
- dummy formal model
- local sequential interaction between two formal models
- JSON protocol output
- REST API wrapper for exposing a formal model
- API client for communicating with a remote formal model

Not yet implemented:

- full interaction context logic
- interaction paradigms
- LLM-based enactment of formal models
- visualization of interactions
- richer formal models beyond the dummy implementation
- production-level API handling, authentication, logging, and deployment
- visualization 