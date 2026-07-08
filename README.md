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
    "schema_version": "0.1",
    "source_agent": "model_a",
    "target_agent": "subject_b",
    "timecode": {
        "timestamp": "0:00",
        "interaction_turn": 1
    },
    "values": {
        "communion": 3.75
    },
    "context": "workplace_colleague_conversation"
}
```

### Fields

| Field | Description |
|---|---|
| `schema_version` | Version of the ITP message schema. |
| `source_agent` | Identifier of the agent that produced the message. |
| `target_agent` | Identifier of the agent that should receive the message. |
| `timecode` | Dictionary containing time information, currently `timestamp` and `interaction_turn`. |
| `values` | Numerical output produced by the source agent, for example `agency` or `communion`. |
| `context` | String describing the interaction context. |
| `metadata` | Optional free-form metadata. |

Mappings between different interpersonal frameworks, for example IPC and SASB, are not yet implemented. These mappings should probably be handled outside the core protocol and checked when two agents use different state spaces.

## Project Structure

```text
itp/
├── README.md
├── requirements.txt
├── .gitignore
├── src/
│   ├── ITPSpecification.py
│   ├── run_API_interaction.py
│   ├── run_local_interaction.py
│   ├── run_model_api.py
│   │
│   ├── API/
│   │   ├── APIClient.py
│   │   └── APISpecification.py
│   │
│   ├── communication/
│   │   └── Communication.py
│   │
│   ├── converter/
│   │   └── BaseConverter.py
│   │
│   ├── deprecated/
│   │   └── StateSpaceConverter_deprecated.py
│   │
│   ├── formalmodels/
│   │   ├── BaseFormalModel.py
│   │   └── DummyFormalModel.py
│   │
│   ├── interactioncontext/
│   │   └── InteractionContext.py
│   │
│   ├── paradigms/
│   │   ├── BaseAssessor.py
│   │   ├── BaseGenerator.py
│   │   ├── BaseParadigm.py
│   │   ├── DummyAssessor.py
│   │   ├── DummyGenerator.py
│   │   └── DummyParadigm.py
│   │
│   └── visualization/
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

### `DummyFormalModel`

Simple reference model for testing.

Currently, the dummy model:

- uses only `communion`
- initializes its state randomly between 1 and 5
- updates its state according to:

```text
new_state = mean(old_state, other_state)
```

### `API`

The API module allows formal models to communicate across processes or machines.

Current endpoints:

```text
GET  /info
POST /generate
POST /step
```

This allows one model to run locally while another model runs remotely, while both still exchange standard ITP messages.

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

Placeholder module for mappings or conversions between state spaces.

This may later support interactions between models based on different interpersonal frameworks.

### `paradigms`

Placeholder module for interaction paradigms.

Future paradigms may include:

- LLM-based conversations
- structured social-interaction tasks
- repeated dyadic exchanges
- simulated interpersonal situations

A paradigm should consume numerical model outputs and return numerical inputs to formal models through ITP-compatible messages.

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

Run:

```bash
python src/run_local_interaction.py
```

This instantiates two internal dummy models and lets them interact sequentially.

One interaction turn currently means:

1. the first model generates an ITP message
2. the communication session stores and validates it
3. the second model integrates it
4. the second model generates an ITP message
5. the communication session stores and validates it
6. the first model integrates it

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

Then, in another terminal, run:

```bash
python src/run_API_interaction.py
```

This lets a local model communicate with a remote model through REST API calls while still exchanging standard ITP messages.

## Current Status

Implemented:

- ITP message specification
- `Communication` session for storing and validating ITP messages
- abstract base class for internal formal models
- dummy formal model
- local interaction between two formal models
- REST API wrapper for exposing a formal model
- API client for communicating with a remote model

Not yet implemented:

- full interaction context logic
- standardized context representation
- interaction paradigms
- LLM-based enactment of formal models
- mappings between interpersonal frameworks
- visualization
- richer formal models
- production-level API handling, authentication, logging, and deployment