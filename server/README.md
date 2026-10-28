# GreenSearch live backend (Phase 2, local only)

A thin server that lets the website's **Live mode** get real model answers
without ever putting an API key in the browser. Python standard library
only, Python 3.9+, no new dependencies. **Not deployed anywhere.** It has
only been run on localhost, and only with fake providers in tests: no
provider key exists yet, so no real model call has been made.

**Model: Qwen3-8B only (`qwen/qwen3-8b`).** Phase 2 uses a single primary
model, the one we already have data on. Each request is one call to it.
The earlier 4B-first pipeline and the planned Qwen3-4B vs 8B comparison
were dropped by the user. `scripts/compare_qwen.py` is still in the tree
but is not needed for the model decision. The logprob cascade remains
available only as an opt-in: set `GREENSEARCH_ESCALATION_MODEL` to a
*different* model to turn it on.

## Run it locally

From the repository root:

```bash
python3 server/app.py --help     # lists every env var
python3 server/app.py            # http://127.0.0.1:8000, no key: "not configured"
```

Then open <http://localhost:8000/>. The server also serves
`website/index.html` at `/`, so the page and the API share one origin and
the default backend URL in the page (`http://localhost:8000/api/chat`) works
as is.

With a key (once you have one; never commit it):

```bash
cp .env.example .env              # .env is git-ignored
# edit .env: set GREENSEARCH_API_KEY
set -a; . ./.env; set +a
python3 server/app.py
```

Quick checks:

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Explain DNS simply", "session_id": "my-session-01"}'
```

Options: `--host` (default `127.0.0.1`, local only) and `--port` (default
`$PORT` or 8000).

## Demo mode vs live mode

| | Demo mode (default) | Live mode (toggle, off by default) |
|---|---|---|
| Needs this server | No. Open `website/index.html` directly or from any static host | Yes |
| Answers | Canned, 95-topic library, in the browser | Real model via this server |
| Network | None | Prompt goes to the backend URL you set, then to its provider |
| Tokens | Estimates (words × 1.33) | Provider-reported |
| Totals | Demo row | Separate LIVE row, never mixed with demo totals |
| Saved in localStorage | Chat under `greensearch-demo-v1` | Only the backend URL, under `greensearch-live-backend-url` |

Live mode resets to OFF on every page load. **Measure baseline** is also off
by default and resets to off: when on, every live message makes a second,
unconstrained call (original prompt, no brevity system prompt, no token cap)
to measure real savings. **That doubles API cost.**

## Environment variables

All configuration comes from the environment. Secrets are never read from
requests, files in the repo, or the command line.

| Variable | Default | Meaning |
|---|---|---|
| `GREENSEARCH_API_KEY` | unset | Provider key. Server-side only. Unset means `/api/chat` returns 503 and no provider is called. |
| `GREENSEARCH_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible base URL. https required (http only for localhost). |
| `GREENSEARCH_MODEL` | `qwen/qwen3-8b` | Primary model. Answers every request. |
| `GREENSEARCH_ESCALATION_MODEL` | value of `GREENSEARCH_MODEL` | Optional. While it equals `GREENSEARCH_MODEL` (the default) there is **no** escalation call. Set it to a different model to turn on the logprob cascade. |
| `GREENSEARCH_CASCADE_THRESHOLD` | `-1.0` | Cascade only: escalate when the primary model's mean token logprob is below this. Must be ≤ 0. A starting point to tune, not a sourced constant. |
| `GREENSEARCH_BACKEND_ORIGIN` | `http://localhost:8000,http://127.0.0.1:8000` | Comma-separated CORS allowlist of exact origins. `*` is refused at startup. |
| `GREENSEARCH_RATE_LIMIT_PER_HOUR` | `100` | `/api/chat` requests per client IP per rolling hour. `0` disables. |
| `GREENSEARCH_DEBUG_LOG` | off | `1`/`true`/`yes`/`on` logs prompts to local stderr. Never sent in responses. |
| `PORT` | `8000` | Listen port (`--port` overrides). |

Invalid values (a positive threshold, `*` origin, a non-numeric rate limit)
stop the server at startup with a plain message instead of running
misconfigured.

## API

### `POST /api/chat`

Request (JSON):

```json
{"prompt": "Explain DNS simply", "session_id": "web-0123abcd", "mode": "auto",
 "stream": true, "measure_baseline": false}
```

- `prompt` (required, ≤ 4000 characters). Send the raw text: the server
  shrinks it. The page does not shrink before sending, so nothing is shrunk twice.
- `session_id` (optional, 8–64 of `A-Z a-z 0-9 _ -`). Enables the session
  cache. Without it nothing is cached.
- `mode`: `auto` (default), `sprout`, `canopy`, `full` (`forest` accepted).
- `stream`: `true` (default) for SSE, `false` for one JSON object.
- `measure_baseline`: `false` by default. See the cost note above.
- Sending `api_key`, `key`, `token`, `authorization`, `model` or `base_url`
  is a 400: those live on the server only.

Pipeline, in order: PromptShrink → session cache (per session id,
mode-aware key; a hit makes no model call and reports 0 new output tokens)
→ routing (or the explicit mode) → one call to the primary model
(`qwen/qwen3-8b`) with the brevity system prompt and token cap, logprobs
requested → `apply_brevity` safety-net trim. By default that is the only
model call: `meta.escalated` is `false` and `meta.escalation_reason` is
`single model: no separate escalation model configured`. `avg_logprob` is
still reported when the provider returns it.

Optional cascade (off by default): only when `GREENSEARCH_ESCALATION_MODEL`
is set to a different model, the escalation model is called with the
**same** system prompt and cap if `avg_logprob` is present **and** below
the threshold (missing logprobs never escalate). If that escalation call
fails, the client gets a 502 and **no answer**. The primary model's
low-confidence answer is never silently returned instead. All of this reuses `greensearch/shrink.py`,
`cache.py`, `router.py`, `cascade.py`, `providers.py` and `brevity.py`
unchanged.

### Streaming: which path is used

The server calls the provider **without** streaming (the existing
`OpenAICompatibleProvider.complete_ex`). The brevity trim needs the
complete text, and the optional cascade needs the complete answer and its
logprobs before it can decide whether to escalate (streaming raw provider
tokens would show users a low-confidence answer that might then be
replaced). Once the answer is final, it is sent to the browser:

- **SSE (default, `"stream": true`)**: `Content-Type: text/event-stream`,
  one `chunk` event per few words, then one `meta` event, then `done`:

  ```
  event: chunk
  data: {"text":"DNS is the "}

  event: meta
  data: {"mode":"sprout","model":"qwen/qwen3-8b","escalated":false,"cache_hit":false,...}

  event: done
  data: {}
  ```

- **JSON fallback (`"stream": false`)**: `{"answer": "...", "meta": {...}}`.

`meta.delivery` says which was used (`"sse"` or `"json"`), and
`meta.provider_streaming` is always `false`. The SSE stream therefore does
not shorten time-to-first-token; it delivers the finished answer progressively.

`meta` fields: `mode`, `mode_source` (`auto`/`explicit`), `model` (null on
a cache hit), `primary_model`, `escalated`, `escalation_reason`,
`avg_logprob`, `cache_hit`, `cached_from_model` and
`cached_answer_was_escalated` (cache hits only), `input_tokens`,
`output_tokens` and `new_output_tokens` (provider-reported, summed over
both calls when escalated, `null` if the provider did not report them, 0 on
a cache hit), `tokens_source`, `trimmed`, `shrink` (estimated token counts
before and after PromptShrink), `latency_ms`, `delivery`,
`provider_streaming`, and `baseline` (null unless measured).

### Errors

Every error is JSON `{"error": "<plain message>"}`. No provider detail, URL,
key or traceback is ever returned.

| Status | When | Message |
|---|---|---|
| 400 | Bad JSON, empty/too-long prompt, bad mode or session id, key/model fields sent | A plain reason, e.g. `Prompt is empty: type a question first` |
| 403 | Browser `Origin` not in the allowlist | `This page's origin is not allowed to use this backend` |
| 413 | Body over 16 KB | `Request body is too large` |
| 429 | Over the per-IP limit, or the provider rate-limited us | `Too many requests, try again later` |
| 502 | Provider unreachable or returned an error | `The model provider could not be reached, try again` |
| 502 | Escalation call failed (optional cascade only) | `The escalation model could not be reached, so no answer was returned (...)` |
| 503 | No API key on the server | `Live backend is not configured yet (no API key on the server)` |
| 503 | Bad base URL | `Live backend is misconfigured on the server, check its settings` |
| 500 | Anything unexpected | `Something went wrong on the server, try again` |

### `GET /api/health`

`{"status":"ok","configured":false,"model":"qwen/qwen3-8b","escalation_model":"qwen/qwen3-8b","cascade_enabled":false,"cascade_threshold":-1.0,"rate_limit_per_hour":100,"provider_streaming":false}`.
Never includes the key.

## Security and limits

- **CORS**: only the exact origins in `GREENSEARCH_BACKEND_ORIGIN` get
  `Access-Control-Allow-Origin`, echoed back, never `*`. Requests with a
  disallowed `Origin` get 403 before any model call. Requests without an
  `Origin` header (curl, server-to-server) are allowed. CORS protects
  browsers, not the API, so the rate limit still applies.
- **Rate limit**: in memory, per client IP, rolling hour. It resets on
  restart and is not shared across processes. Behind a proxy every client
  would share the proxy's IP. `X-Forwarded-For` is deliberately **not**
  trusted, because clients can forge it. A deployment would need a trusted-proxy setting.
- **Session cache**: in memory, per process, up to 1000 sessions × 200
  entries, least recently used evicted. Cached answers are reused verbatim and may be stale.
- **Logging**: by default only method, path and status go to stderr. No
  prompts, no bodies. `GREENSEARCH_DEBUG_LOG` adds prompts to local stderr only.

## Privacy notes

- The API key lives only in the server's environment. The page never
  sees, stores or sends one, and the server refuses requests that try to send one.
- Live mode is **not** browser-only: prompts go to this server and from
  there to the configured provider (default OpenRouter, which routes to
  an upstream model host).
- **Do not claim "privacy-first" until the provider's data-retention and
  training policy has been checked** for the exact account settings and
  models used (OpenRouter's own policy and the upstream host's). That check
  has not been done.
- Demo mode is unchanged: no network requests.

## Deployment: future options only

> **Requires an account the user has not set up yet. Do not deploy from this repo.**
> Nothing below has been done or tested.

- **Google Cloud Run, europe-north1 (Finland).** This matches the project's
  low-carbon goal (the region Google reports as about 98% carbon-free). A
  container would run `python server/app.py --host 0.0.0.0` with `PORT`
  from Cloud Run, and the key in Secret Manager. Needs: a GCP account and
  billing, a trusted-proxy rate-limit design (see above), and a production
  origin in `GREENSEARCH_BACKEND_ORIGIN`. *Requires an account the user has
  not set up yet; do not deploy from this repo.*
- **Vercel serverless.** It would need a thin adapter that calls
  `Backend.chat()` from a Python function handler. In-memory rate limits
  and caches do not survive across serverless instances, so it would need
  a shared store. *Requires an account the user has not set up yet; do not
  deploy from this repo.*
- **Cloudflare Workers.** Workers run JavaScript/Wasm, not this Python
  server, so this would be a port of the pipeline (or Workers' Python
  beta, with its own limits), not a drop-in deploy. The adapter would have
  to keep the same rules: key in a Worker secret, exact-origin CORS, no
  silent downgrade. *Requires an account the user has not set up yet; do not
  deploy from this repo.*

## Still blocked (on accounts and APIs, not code)

- **Provider API key** (e.g. OpenRouter): no real model call to
  `qwen/qwen3-8b` has been made. Live answers, latency and measured
  savings are all unknown.
- **Provider data policy check** (retention and training, for the exact
  account settings and the Qwen3-8B route) before any privacy claim.
- **Hosting account** (GCP, Vercel or Cloudflare) for any deployment.
- **Domain** for a public origin and the matching CORS setting.

Not blocking: the model choice. Qwen3-8B is decided; no 4B vs 8B
comparison is needed, so `scripts/compare_qwen.py` does not have to be run.
