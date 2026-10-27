# Splitting the browser client out of this repository

Status: decided in principle, not started. Recorded 2026-09-24.

## Decision

`ui/index.html` began as a mock of the JavaScript application the API
specification assumes. It is becoming more than that: the simple client
participants use to let their own formal model exchange ITP numbers with other
models. That makes it a product with its own users and release cycle, and it
should not ship inside the reference implementation of the protocol.

It will probably move into a separate repository. The cut happens later, on its
own branch, after the port work is committed. Until then, nothing new should
make the client depend on `src/` or on running from this checkout.

How participants get the client is not decided: a hosted static page, a local
copy each participant runs, or both. The API configuration below is to stay
explicit enough for either.

## What ties the client to this repository today

| Coupling | Where | What it becomes after the split |
|---|---|---|
| The page itself | `ui/index.html` | Moves as is. It has no imports and no build step. |
| The server | `src/run_mock_ui.py` imports `resolve_port`, `discover_api_base_url` and `looks_like_itp_api` from `src/utils/ports.py` | Needs its own copy of the logic, or a plain static server plus an explicit API URL. |
| API discovery through the note file | `.itp-api-url` at this repo's root, read by `discover_api_base_url` | Does not work from another checkout. Keep the probing and `ITP_API_BASE_URL`, and drop the note or point to it by path. |
| API base URL handed to the page | `mock-ui-config.json`, answered from memory by `run_mock_ui` | Stays useful for a local copy. A hosted page needs the URL at deploy time or from a query parameter. |
| Default base URL in the page | `value="http://127.0.0.1:8001"` in `ui/index.html` | Fine for local use; wrong for a hosted page. |
| CORS | `DEFAULT_ALLOWED_ORIGINS` in `src/API/APISpecification.py`: loopback 5173-5182, plus `ITP_UI_PORT` | Hosted: the page's origin has to be allowed, most likely through configuration rather than code. The origin list and the port range in `ports.py` then stop being one contract. |
| Wire contract | `docs/ITP_API_Specification.pdf`, plus the extensions in `docs/api_design.md` | The client repo pins which API version it speaks. Nothing in either repo checks that today. |
| Design | PerTRAIN design system, `#2C6BB5`, system sans, no font binaries | Carried over as a rule in the new repo's `CLAUDE.md`. |

## Open questions

1. How does a participant's formal model reach the client? At present a human
   types behavior vectors built from `stateSpaceSchema`. "Let their formal model
   communicate" could mean that, a model running in the page, or a participant's
   own script calling the API directly, with the page only watching.
2. Is the participant client the JavaScript application the specification
   describes, or a second client next to it?
3. Hosted, local, or both (see above). This decides the CORS and discovery work.
4. Name and host of the new repository.
5. Whether this repository keeps a minimal mock for its own development, or
   depends on the client repo for manual testing.
