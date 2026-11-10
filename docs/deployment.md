# The deployed API

How the API reaches `https://itp-api.uni-muenster.de`, how a new version goes live, and what the
deployment still lacks. For the API's design, see `api_design.md`.

## Where it runs

The API runs at `https://itp-api.uni-muenster.de` (interactive docs at `/docs`), reachable from
anywhere, behind a gateway that expects an `X-API-Key`. Two GitLab projects carry
it:

- `cvmls/itp/itp-api` mirrors this repository from GitHub (GitLab lists it as a mirror; its `main`
  carries the GitHub merge commits). Its `.gitlab-ci.yml` builds a multi-arch image (amd64 and
  arm64) and pushes it to `harbor.uni-muenster.de/itp/itp-api` as `latest`. The job runs only when
  started by hand.
- `cvmls/itp/itp-deployment` (Pascal's) deploys that image with `podman kube play` under systemd,
  behind an nginx ingress, with the record in a persistent volume at `/app/results`. Its deploy
  pipeline is also started by hand.

A merged commit is therefore live only after both pipelines have run. Since 2026-11-01 the live
server runs `main` with PR #4: actions take an optional `turn` and return a `cursor`, and LASSI
publishes its `parameterSpace` (checked with a seeded LASSI interaction against the gateway). Since
2026-11-10 `main` also reports every model agent's `modelSeed` (PR #6); that build was not yet
deployed on that day. `modelSeed` does not appear in `/docs/openapi.json`, because the responses
are untyped there, so check a release like this one with an interaction against the gateway (the
creation response names `modelSeed` for every model agent). For other changes, check
`/docs/openapi.json` before pointing a client at features newer than the last build.

The image (`Dockerfile`) holds `src/`, `schema/` and `configs/` only. It runs
`python -m src.run_model_api` as the unprivileged `appuser` and exposes 8001. `/app` stays owned by
root, so the image alone cannot create `results/`; the deployment provides the writable volume. A
local container needs the same:

```bash
podman build -t itp-api .
podman run -p 8001:8001 -v "$PWD/results:/app/results" itp-api
```

## Releasing a new API version

GitHub is primary. Work happens there, and `main` is what the GitLab mirror and the image follow.
A release that clients depend on takes these steps, in this order:

1. Merge into `main` on GitHub, with `python -m pytest tests` passing.
2. Wait for the mirror to pick it up in `cvmls/itp/itp-api`, then start the image build there.
3. Start the deploy pipeline in `cvmls/itp/itp-deployment` (ask Pascal which branch; the recent
   runs started from `dev/apikey`).
4. Check `https://itp-api.uni-muenster.de/docs/openapi.json` for the change before telling a
   client it is live. A redeploy drops every running interaction (see below).
5. Tag the merge commit on GitHub and publish a release with notes on what changed for clients.

PerTRAIN's `ITPGenerator` (`personalization-backend`) depends on two releases. Its actions need the
one that made `turn` optional and returns the action `cursor` (on `main` since 2026-10-27). Its
parameter fields need the one that adds `parameterSpace`. Against an older server, a
`configuration` is accepted and silently ignored. On the PerTRAIN side, `perchat-deployment` does
not yet pass an `ITP_API_KEY` to the app container.

## The hosted browser client

`.github/workflows/pages.yml` publishes `ui/` to `https://olehaetscher.github.io/itp-api/` on every
push to `main` that touches `ui/`. Opened there, the page fills in the deployed API and waits for
a key. It needs nothing from the deployment: the gateway answers every origin.

## What the deployment still lacks

Three of the *Known gaps* in `api_design.md` matter for the deployment:

- **Proxy and client address.** The `clientRequestId` replay scoping and the join rate limiter key
  on the socket address. Behind a proxy that does not forward the client address, every client
  collapses into one, and the rate limit becomes global. Whether the ingress forwards it has not
  been checked from this repository.
- **Interaction lifetime.** There is no reaper. The `expired` status and the `interactionExpired`
  and `registrationTimeout` end reasons exist, and nothing sets them. A process that is up for
  weeks accumulates interactions until it restarts. It needs an expiry, a cap on concurrent
  interactions, or both.
- **State beyond the process.** Records are written to `results/` as interactions run, but the
  interactions themselves live in memory. A restart, including every redeploy, drops every one in
  flight, with its tokens and invitation codes. A client asking about an interaction the server no
  longer knows gets a `404` saying so, and starts a new one. The alternative, a store from which
  interactions resume after a restart, is described with its costs in `api_design.md` under
  *Server restarts*.

`DEFAULT_ALLOWED_ORIGINS` in `APISpecification` is still the loopback development range. The
example web client does not need more, because its browser talks only to its PHP adapter. A
JavaScript application calling the API from its own origin would.
