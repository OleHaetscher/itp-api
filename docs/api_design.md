# ITP Model API — Design

Implements `docs/ITP_API_Specification.pdf`. This document records what the
code does, where it extends the specification, and what is deliberately left
out. The specification PDF is the contract; this file is the implementation
note beside it.

Status: implemented in `src/API/` unless marked *not implemented*.

## What replaced what

The previous API served one hard-coded formal model through `/info` and
`/sessions`, exchanged full ITP messages over the wire, had no authentication,
no human participants, no turn engine, and no schema validation. It is kept for
reference in `src/deprecated/APISpecification_deprecated.py` and
`src/deprecated/APIClient_deprecated.py` and is no longer mounted.

## Module layout

| Module | Responsibility |
|---|---|
| `src/API/APISpecification.py` | FastAPI app: routing, bearer auth, error rendering, CORS, long polling |
| `src/API/APIModels.py` | Pydantic request and response models, camelCase, unknown keys rejected |
| `src/API/APIProblem.py` | `application/problem+json` documents and the problem type table |
| `src/API/Interaction.py` | Lifecycle, turns, perceptions, actions, ITP messages |
| `src/API/InteractionRegistry.py` | Interactions, tokens, invitations, idempotency, rate limiting |
| `src/API/Invitation.py` | Six-digit codes, token generation, join rate limiter |
| `src/API/ModelCatalogue.py` | Model entries, versions, constraints, model factories |
| `src/API/StateSpaceSchema.py` | IBSSS description → validating JSON Schema, geometry checks |
| `src/API/APIClient.py` | Python client mirroring the JavaScript client |

The HTTP layer holds no interaction state. Everything stateful lives in
`Interaction` and `InteractionRegistry`, which is why the turn rules can be
tested without a server.

## Wire format: bare vectors, ITP messages inside

The specification exchanges bare `experience` and `behavior` objects, not ITP
messages. That is what the API does on the wire. Internally every behavior is
wrapped into a full ITP message and stored in a `Communication` object, so an
interaction driven through the API produces the same record as one driven by
`src/run_local_interaction.py`. `GET /interactions/{sessionId}/results` returns
both representations: `turns` for the JavaScript client, `itpMessages` for
anything ITP-aware.

The browser therefore never assembles `source_agent`, `target_agent`, or a
timecode. It posts `{actionId, turn, behavior}` and reads `experience`.

## The shared state space schema

The specification requires one `stateSpaceSchema` per model that validates both
the experience vectors the perception endpoint returns and the behavior vectors
the action endpoint accepts:

```text
schema(experience) = schema(behavior) = stateSpaceSchema
```

The repository already describes its state spaces in
`schema/interpersonal-behavior-state-space/`, but those are IBSSS *descriptions*
of a space, not validators of a vector: nothing in `ipc.json` rejects
`{"Theta": 400.0}`. `StateSpaceSchema` therefore compiles the description into
a draft-2020-12 JSON Schema, so the two cannot drift apart:

| IBSSS | Compiled schema |
|---|---|
| `type: euclidean`, `discrete` dimension `range` | `number` / `integer` with `minimum` and `maximum` |
| `minimumInclusive: false` | `exclusiveMinimum` |
| angular dimension, `unit: degree` | `number`, `minimum: 0`, `exclusiveMaximum: 360` — the period is exclusive because 360° and 0° are the same state |
| every dimension | `required`, plus `additionalProperties: false` |

`GET /models/{modelId}` returns the compiled schema under `stateSpaceSchema`
and the IBSSS source under `stateSpace.stateSpaceDescription`, so a client can
validate against the first and render labels, captions, and geometry from the
second.

### Geometry

JSON Schema cannot express the SASB diamond or the friendly-distancing simplex.
Those constraints are compiled into a separate list of checks that runs after
schema validation, and are echoed in the schema under `x-itp-geometry` so a
client can see them. Supported: `box`, `diamond`, `circle`, `disk`, and
`constrained` with `sumEquals`, `weightedSum`, and `manhattanDistance`.

This closes the gap the README notes under converters: geometry is now enforced
at the API boundary, even though the converters themselves still do not enforce
it in general. See *Known gaps* below.

### The IPC neutral center

One geometric case was not a gap but a state space definition that had to be
settled. A Cartesian space contains its own center — SASB has `(Aff 0, Int 0)`,
the agency-communion box has `(A 4, C 4)` — and the dummy SASB model converges
on exactly that state. Converting it into the polar IPC space gives a radius of
zero, where no angle is defined.

`ipc.json` previously excluded that point, so the conversion had no valid
target and the old code silently emitted `{"Theta": 0.0, "R": 0.0}`: an invalid
state whose angle came from `math.atan2(0, 0)` and happened to read as **LM**,
pure communion. A neutral partner was reported as maximally warm.

The circumplex now **includes** its neutral center, marked by `R = 0`:

- `ipc.json` sets `minimumInclusive: true` on the radius, and its `Theta` and
  `R` descriptions state that the angle carries no information at `R = 0` and
  must not be interpreted there.
- `R = 0` is itself the sentinel. No out-of-range magic number is used, because
  every value in `[0, 360)` is a real angle and none can be spared.
- `BehavioralStateSpaceConverters.NEUTRAL_CENTER_ANGLE` is the angle reported
  there, so the convention is explicit rather than an artefact of `atan2`.
- `_ipc_to_cartesian` already collapses every angle at `R = 0` onto the origin,
  which is the correct reading, so round trips through the center are exact:
  `(Aff 0, Int 0) → (0, 0) → (Aff 0, Int 0)`.
- `DummyIPCFormalModel` reads a partner's angle only when the partner's radius
  is greater than zero, so it does not move toward a direction that does not
  exist.

This is a change to a published state space definition, not only to code. The
document version of `ipc.json` is unchanged at `0.2.0`; bump it if the schema is
treated as released.

## Turn model

Interactions are **alternating**: one turn is one action slot with exactly one
acting agent. That is what `activeAgentIds` and the `results` representation
(one `actorAgentId` per turn) describe, so `numberOfTurns` counts single
actions, not exchanges. An API turn maps onto the ITP timecode as:

```python
interaction_turn = (turn + 1) // 2
message_index    = 2 - (turn % 2)
```

so API turns 1 and 2 are the two messages of ITP interaction turn 1.

The server is authoritative. It picks the acting agent, runs formal model
agents itself the moment it is their turn, converts every behavior into the
partner's state space, produces the partner's perception, and advances the
turn. A model-to-model interaction therefore runs to completion inside the
creation request, and in a human-to-model dyad the participant always finds a
perception waiting.

### Actions

`actionId` is generated by the client, one fresh value per action (a random
UUID is enough). Resubmitting the same action under the same id, for example
after a timeout, returns the original acceptance instead of applying it twice.
The same id with different content is `409 action-conflict`.

`actionId` is scoped to the agent that submitted it, not to the interaction.
The two clients generate their identifiers independently, so an interaction-wide
namespace would make a counter-style id such as `action-1` collide between them
and tell the second client its own first action conflicts.

An action that is accepted but then fails while being applied — a model that
raises, or one that emits a vector outside its own state space — is removed
from the idempotency record. Applying an action is what advances the
interaction, so an action that never applied must not be replayable as an
accepted one.

### Perceptions

A perception carries the experience the partner's action produced. That
experience is the partner's behavior vector, converted into the perceiving
agent's state space and nothing more. No perception is modelled on this path,
so when both agents share a state space the experience equals the partner's
behavior, and `sourceAgentId` names the partner. A client therefore reads its
partner's behavior from its own agent's perceptions. It never polls the
partner's agent, which its token may not address (see *Tokens are bound to an
agent*).

Its `turn` is the turn in which the perceiving agent is expected to act. A
client may submit it back unchanged with its action, or leave `turn` out, in
which case the server takes the current turn. Either way an action from an
agent whose turn it is not is `409`. The explicit turn only matters to a client
that re-sends a behavior after a failure and wants it refused if the
interaction has moved on; a retry under the same `actionId` is recognised
either way, because the idempotency check uses the turn as sent.

Polling never consumes a perception. The same request repeated returns the same
perception until the client advances `after` past its `cursor`. Cursors are
monotonic per interaction.

A client's first poll sends no `after`. If its agent opens the interaction, that
poll returns an `actionRequired` perception without an `experience` (see
*Extensions to the specification*). The partner's first behavior arrives only
on a later poll with `after` set to that perception's cursor. If the partner
opens, the first poll already returns the partner's behavior at cursor 1, so a
client that starts with `after=1` skips it and is never told it must act.

`cursor` and `turn` count different things. `turn` is the action slot the client
submits next. `cursor` is the perception's position in the interaction's
stream, which also counts the other agent's perceptions. They coincide when the
client's agent opens and differ otherwise (cursor 1 with turn 2). A client takes
both from the last perception it received and computes neither.

The action response carries a `cursor` as well: the acting agent's cursor from
before the action. Polling with `after` set to it returns the perception the
action leads to, which for a model partner is already there when the action
response arrives, because the server runs a model's turn inside the action
request. A client that acts and then reads the answer therefore keeps no cursor
between turns.

`wait` enables long polling. The request is held open until a perception
appears or the deadline passes, capped at 30 seconds by the server. Every step
of the poll that touches an interaction runs in a worker thread: an interaction
is guarded by a threading lock that a model step can hold for as long as that
step takes, and taking it on the event loop would stall every request in the
process rather than only the poll.

A perception issued before the interaction ended no longer reports
`actionRequired: true` once it has, so a client cannot be told to submit a
behavior that is guaranteed to be refused.

When the interaction ends, perceptions the agent has not yet read are still
delivered, with `sessionStatus: "completed"`; `interactionEnded` follows once
the cursor has caught up. Without that, the final experience of an interaction
would be visible only through `/results`.

## Extensions to the specification

These go beyond the PDF. They are additive: a client that ignores them behaves
exactly as the specification describes.

| Extension | Why |
|---|---|
| Perception state `actionRequired` | The agent that opens the interaction must act but has nothing to perceive yet. The three states of the specification cannot express that without inventing an opening state vector, and this codebase does not fabricate values. |
| `context` on `POST /interactions` | ITP messages require an interaction context. Defaults to `workplace_colleague_conversation`. |
| `startingAgentRole` on `POST /interactions` | Which role acts in turn 1. Defaults to `"A"`. |
| `stateSpace` on a human agent | Lets a participant work in a different state space from the model, with perceptions converted into it. Formal model agents must use their model's state space. |
| `sourceAgentId` on a perception | Names the agent whose behavior produced the experience. |
| `itpMessages` in `/results` | The ITP record of the interaction, beside the specification's `turns`. |
| `resultsFolder` in `/results` | Names the folder the record was written to, relative to the configured results root, so a client can say where the run landed. `null` when nothing was written. |
| `turn` optional on an action | Without it the server takes the current turn. A client that only ever acts when told to keeps no turn of its own. |
| `cursor` in the action response | The cursor to poll after for the perception the action leads to, so a client keeps no cursor between turns. |
| A repeated `clientRequestId` returns the current state | Lets a client that lost its state recover the session and token and continue, instead of getting the creation response with its stale turn. |
| `modelId` and `modelVersion` on a model agent | Lets the two agents run different models. See *Two models in one interaction*. |
| `model` on every agent | The model the agent runs, as `{id, version, name}`, or `null` for a human. In the status, creation, join and results responses. |

## Two models in one interaction

The specification binds an interaction to one `modelId`. A model agent may now
name its own with `agents.X.modelId` (and optionally `agents.X.modelVersion`),
which overrides the top-level model for that agent:

```json
{
  "modelId": "lassi",
  "numberOfTurns": 20,
  "agents": {
    "A": {"type": "model"},
    "B": {"type": "model", "modelId": "dummy-ipc"}
  }
}
```

A request without per-agent models means what it meant before. The top-level
`modelId` stays required: it is the model a human agent is paired with, decides
a human agent's default state space, and is what the top-level `model` field of
every response reports. Which model an agent actually runs is in that agent's
`model` field, `null` for a human. A client that needs to know who ran what reads
it there, not from the top level.

Creation checks every model involved: each must exist and be available, the
number of turns must lie within every model's limits, and persistence must be
supported by every one. A human agent given a `modelId` is refused, because it
runs no model.

When the two agents work in different state spaces, every behavior has to be
converted, and creation refuses the pair unless a converter exists in both
directions. Converters are looked up directly and not chained, so `lassi`
(`ac`) with `dummy-ipc` (`ipc`) works, while `lassi` with `dummy-sasb` (`sasb`)
is a `422` with the error code `noConverter`. Before this check, such a pair was
created and failed on its first action. The same check now covers a human agent
that declares a `stateSpace` no converter reaches.

## Authentication

`POST /interactions` issues one interaction-scoped bearer token. `POST
/interactions/join` issues a second one to the joining client. Tokens are
`secrets.token_urlsafe(32)` and are stored only as SHA-256 hashes, keyed to a
session id. A token is checked against the `sessionId` in the path, so a token
for one interaction cannot address another.

A request without a token is `401 missing-token`, and the detail says how to
send one: `Authorization: Bearer <interactionToken>`, with the token from the
creation or the join response. That holds for `/end` as well. Ending needs no
token of its own, since any token of the interaction may end it.

Interactions and tokens live in memory, so a server restart drops them. A
request naming an interaction the server does not know is `404
interaction-not-found`, whatever token it carries or lacks, and the detail says that a restart
drops interactions and that the client should start a new one. A token that is
unknown while its interaction exists stays `401 invalid-token`. Telling the two
apart reveals only whether a session id exists, and session ids are random
UUIDs. Why interactions do not survive a restart, and what it would take, is
under *Server restarts*.

`GET /models` and `GET /models/{modelId}` need no token. `POST
/interactions` needs none, because nothing exists yet to be scoped to. `POST
/interactions/join` needs none, which is the point of the invitation code.

### Tokens are bound to an agent

The specification allows one shared token for all clients of an interaction,
but also requires that "a client must only request perceptions for its assigned
agent". Those two cannot both hold with a single shared token, so this
implementation issues a token per client and binds it:

- a token becomes bound to the agent it is used to register, and the joining
  token is bound to the invited agent at join time
- a bound token may only poll perceptions and submit behavior for its own
  agent; addressing the other agent is `403`
- reading interaction status and ending the interaction stay open to any token
  of that interaction, because both clients legitimately need them
- the creating token stays unbound until it registers a participant, since an
  interaction between two formal models has no agent to bind it to

Formal model agents are executed by the server, so submitting a behavior for
one is `403` regardless of the token.

### clientRequestId is scoped to its client

The creation response carries the interaction token, and `clientRequestId` is
a client-chosen string — the specification's own example is the fixed value
`create-interaction-7d14d66f`. Replaying a stored response to anyone who
repeats the identifier would therefore hand out another client's token. A
replay must match both the exact request payload and the source address;
anything else is `409` rather than a second interaction or a leaked token.

A matching repeat returns the interaction as it is now: the same session and
token, with the current turn, status and registrations, not the response from
when it was created. This is how a client recovers after losing its own state,
for example through a restart: it sends the same creation request again and
continues. It only works if `clientRequestId` is stable per interaction and per
creating client. The PerTRAIN backend should use the dialog instance id, which
is reused after a restart and differs between the two agents of an
agent-agent dialog. After an ITP restart the identifier is unknown again, so
the same request creates a new interaction, and a request for the old session
gets the `404` described in *Server restarts*.

The source address comes from the socket, so a deployment behind a proxy must
forward it or this scoping collapses to the proxy address. The same applies to
the join rate limiter, which counts per source.

## Invitation codes

Generated only when a second human participant must join, that is when both
agents are human. The code is bound to one interaction and one agent, is
single-use, and expires after 30 minutes.

- six decimal digits, `^[0-9]{6}$`, from `secrets.randbelow`
- unique among active invitations
- stored as a SHA-256 hash, never in plaintext
- disclosed exactly once, in the creation response; `GET /interactions/{id}`
  returns the invitation *status* without the code
- redemption and registration happen inside one registry lock, so concurrent
  joins cannot register two participants for one agent

Failure modes follow the specification: `404` for an unknown code without
disclosing whether it once existed, `410` for an expired code, `409` for a used
one.

### Rate limiting

`JoinRateLimiter` counts failed attempts in a 60-second fixed window across
four keys: source address, client identifier, individual code, and a global
counter. Defaults are 10 per source or client, 5 per code, 200 overall. Over
the limit the endpoint returns `429` with `retryAfterSeconds` and a
`Retry-After` header.

## Errors

Every error is an RFC 9457 problem document with the
`application/problem+json` media type, carrying `type`, `title`, `status`,
`detail`, `instance`, a `requestId`, and, for schema violations, an `errors`
array of `{path, code, message}`. Request validation failures, unhandled
exceptions, and domain errors all pass through the same handler, so there is
one error shape.

The status code table of the specification is implemented in full: 400, 401,
403, 404, 409, 410, 422, 429, 500. Problem type slugs are listed in
`APIProblem.PROBLEM_TYPES`.

## CORS

```python
allow_origins=[...]   # localhost and 127.0.0.1 on 5173-5182
allow_credentials=False
allow_methods=["GET", "POST", "OPTIONS"]
allow_headers=["Content-Type", "Authorization", "X-API-Key"]
```

`Authorization` is allowed because the API is now authenticated. `X-API-Key`
is the header the gateway in front of the deployed API checks. This process
ignores it, but a browser client sending it is preflighted here whenever the
gateway passes CORS through. `DELETE` is
gone with the old `/sessions` endpoints. Pass `allowed_origins` to
`APISpecification` to change the list; if cookie-based auth is ever introduced,
`allow_credentials` and the origin list must be revisited together, because
wildcards are then invalid.

The list is a range rather than the single port 5173 because the mock client is
a separate process on a separate origin — that is what makes the check
observable at all — and the API has to allow that origin before either process
starts. It cannot observe which port the client took, so it allows every port
the client picks from, which is the range in `src/utils/ports.py`. An explicit
`ITP_UI_PORT` outside the range is added as well, since both processes read the
same variable. Widening a development origin list to ten loopback ports costs
nothing: an origin here is trusted exactly as far as a browser tab on the same
machine is. A deployment replaces the list outright.

## Persistence

`persistence.enabled` controls whether an interaction keeps its record after it
ends. With persistence on, `GET /interactions/{sessionId}/results` returns the
turn record and the ITP messages. With persistence off, both are dropped the
moment the interaction ends and `/results` returns `410`, while an interaction
that never existed returns `404`.

The in-memory record does not survive the process. A record on disk does.

### Writing the record

`APISpecification(results_root=...)` names a directory, and every interaction
with persistence enabled records itself below `<results_root>/results/`.
`src/run_model_api.py` passes the repository root, so records land in
`results/` beside the ones `src/run_local_interaction.py` writes. Without
`results_root` the process writes nothing to disk, which is the default and what
the test runners use. With persistence off nothing is written either: the flag
means what the specification says, and a client that wants a record asks for
one.

One folder per interaction, named `<creation timestamp>_<first eight characters
of the session id>`. The timestamp alone is what `Communication.save_messages`
uses, and it collides when two interactions start within the same second, which
a server with several in flight can do.

The record is written as the interaction runs, not at its end:

1. At creation, the folder and `interaction.json` with what does not change:
   the agents, the model and state space of each, the context, the number of
   turns, and the starting role.
2. Each ITP message as it is stored, through `Communication.save_message`.
3. `interaction.json` again when the interaction starts, and when it ends
   (normally, through `/end`, or by failing), with status, end reason, final
   turn, and message count.

An interaction ended early through `/end` therefore leaves every message up to
that point, and so does a process that dies, although `interaction.json` then
records no end.

```text
results/20260914_155820_9aa18034/
├── interaction.json
├── message_001_<source>_to_<target>_original.json
├── message_002_<source>_to_<target>_converted.json
└── …
```

The message files are what `Communication` already writes, so an interaction
driven through the API leaves the same record as one driven locally, including
the `_converted` copy whenever the two agents work in different state spaces.
`interaction.json` holds what only the API knows: which agent was human and
which was a model, which model each ran, the state space each worked in, the
end reason, and the timestamps. The behavior vectors are in the message files
and are not repeated there; `/results` still returns them as `turns`.

Every write is reported on the server log and swallowed rather than raised: a
full disk should not turn a running interaction into a `500`. If the folder
cannot be created, `resultsFolder` in the `/results` response is `null`, which
is how a client can tell.

## Server restarts

Everything an interaction needs while it runs lives in the memory of one
process: the `Interaction` objects with their turn state, perceptions and
actions, the formal model instances, the token and invitation hashes, and the
idempotency records. A restart, whether a deployment, a crash, or a host
reboot, drops all of it. The record on disk survives (see *Persistence*), but
it is a record, not something the server can resume from. There are two ways to
handle this.

### Option 1: no continuation after a restart (implemented)

An interaction in flight during a restart is lost, and the client starts a new
one. The server makes this explicit rather than leaving the client to guess:
any request naming an interaction it does not know is `404
interaction-not-found`, and the detail says that a restart drops interactions
and that the client should start a new interaction. A client therefore needs
one rule: on that `404` for an interaction it created, create a new one, and
treat the old one as ended.

What is lost: the turns of the interrupted interaction from the client's point
of view. With persistence enabled, every ITP message up to the restart is still
in `results/`, and `interaction.json` then has no end status, end reason or
`endedAt`, which marks the interaction as interrupted rather than ended.

This costs nothing on the server, and it is acceptable as long as interactions
are short and restarts are rare and planned. It is not acceptable once a study
cannot afford to lose a participant's half-finished interaction to a
deployment.

### Option 2: interactions survive a restart (not implemented)

The registry would write its state to a store as the interactions run and
reload it on startup, so a client could continue with the token it holds.
That requires:

- **The formal model's own state.** This is the hard part. A model instance is
  a Python object whose state is whatever the model keeps between turns: for
  `LASSIFormalModel`, per axis the current and previous state distribution and
  the sampled state. Sampling draws from NumPy's global random generator, which
  is shared by every interaction in the process, so a non-deterministic model
  cannot be resumed reproducibly without giving each instance its own seeded
  generator first. `BaseFormalModel` would need a `to_state()` / `from_state()` pair that every
  model implements exactly, and the conformance vectors would have to cover the
  round trip, because a model reloaded slightly differently produces different
  behavior from then on without any error.
- **The interaction itself.** Status, current turn, active agent, cursor, the
  perceptions and actions issued so far, the turn records, and the
  `Communication` messages. All of it is plain data and serializes directly.
- **The registry.** Token hashes and their agent bindings, invitation hashes
  with their expiry, and the `clientRequestId` records. Only hashes are stored
  today, so nothing secret would be written. Invitation expiry runs on
  `time.monotonic()`, which does not survive a process, and would have to
  switch to wall-clock time.
- **When to write.** After every state change, that is every action, inside the
  interaction lock, and atomically (write to a temporary file, then rename), so
  a crash mid-write cannot leave a state the server half-reloads.
- **Code changes between write and reload.** A redeployment that changes a
  model's code or parameters would resume old interactions under the new model.
  Each stored interaction would have to carry the model version and be refused,
  or ended as `serverError`, when it no longer matches.
- **Participant data at rest.** A participant's behavior already reaches disk
  when persistence is on. With a store, it also reaches disk when persistence
  is off, which contradicts what the flag promises. The store would then have to
  be deleted as soon as such an interaction ends.

Of these, only the formal model state touches the scientific code. The rest is
ordinary engineering, roughly a store class, a reload path in
`InteractionRegistry`, and tests that restart an API mid-interaction.

## Known gaps

These are real and should be decided rather than discovered later.

- **Converter geometry in general.** The neutral center is settled (see *The
  IPC neutral center* above), but the converters still do not enforce the
  geometry of their target space in general: nothing stops a future converter
  from leaving the SASB diamond or the friendly-distancing simplex. The API
  catches such a vector when it validates the experience, and fails the
  interaction with `serverError` and a problem document naming the conversion,
  which is a backstop rather than a fix.
- **Interaction expiry.** The `expired` status and the `interactionExpired`
  and `registrationTimeout` end reasons exist, but nothing sets them: there is
  no reaper, no interaction lifetime, and no cap on the number of interactions.
  A long-running process accumulates interactions until it is restarted.
- **The `ready` state.** Interactions move from `waitingForRegistration`
  straight to `running`, which the specification permits.
- **Rate limiting beyond the join endpoint.** Polling and action submission are
  not rate-limited. The `429` shape exists if that changes.
- **HTTPS.** The process serves plain HTTP and must sit behind a terminating
  proxy or stay on a trusted network.
- **Analysis-unit conversion.** Still unimplemented, as in the rest of the
  codebase; a message requiring it raises and surfaces as `422`.
- **Ending a model-to-model interaction early.** The server runs both models
  inside the creation request, so the interaction has ended before the client
  could ask. Ending early only applies when a human agent is involved.
- **Restarts.** Interactions and tokens do not survive the process. The
  client has to start a new interaction. See *Server restarts* for the
  alternative and what it would take.
- **Model configuration.** `agents.X.configuration` is accepted and stored but
  not passed to the model factory, so two agents of one interaction always run
  the same parameters. `LASSIFormalModel` does take per-instance parameters (its
  `parameters` argument overrides the config), so the missing piece is the model
  factory signature and a per-model schema for what `configuration` may contain,
  not the models.

## Endpoint summary

```text
GET    /api/v1/models                                              model catalogue
GET    /api/v1/models/{modelId}                                    definition + stateSpaceSchema
POST   /api/v1/interactions                                        create, issue token and invitation
POST   /api/v1/interactions/join                                   redeem invitation code
GET    /api/v1/interactions/{sessionId}                            status
POST   /api/v1/interactions/{sessionId}/agents/{agentId}/register  register a participant
GET    /api/v1/interactions/{sessionId}/agents/{agentId}/perception poll, optional long poll
POST   /api/v1/interactions/{sessionId}/agents/{agentId}/actions    submit a behavior
POST   /api/v1/interactions/{sessionId}/end                        terminate
GET    /api/v1/interactions/{sessionId}/results                    persisted record
```

The generated OpenAPI document is at `/docs` and carries payload schemas for
every endpoint, so the JavaScript client has something to type against.
