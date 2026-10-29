# GreenSearch live backend (Phase 2, local only)

A thin server that lets the website's **Live mode** get real model answers
without ever putting an API key in the browser. Python standard library
only, Python 3.9+, no new dependencies. **Not deployed anywhere.** It has
only been run on localhost: the tests use fake providers, and one local
live run with an OpenRouter key (2026-10-27) found the bugs fixed in the
"Model and fallbacks" section below.

**Default model: `google/gemma-4-31b-it:free`**, a named general chat
model. `openrouter/free` (OpenRouter's router over its free models, not a
named model) was the default until Unreleased, and is now only the
**last** fallback. Why: as primary, the router sent a hamburger question
to a content-safety model, which answered "User Safety: safe...". The
router can pick non-chat free models, and the fallback chain only
triggers on errors, never on a wrong-type answer, so a named chat model
must answer first. Free models are rate-limited and rotate in and out of
service. An older default, `qwen/qwen3-8b`, was deprecated on OpenRouter
on 2026-10-09 and now returns 404. Set `GREENSEARCH_MODEL` to pin a
different model. The logprob cascade remains available only as an
opt-in: set `GREENSEARCH_ESCALATION_MODEL` to a *different* model to turn
it on.

## Model and fallbacks

Each request first calls `GREENSEARCH_MODEL`. If that call fails, the
models in `GREENSEARCH_MODEL_FALLBACKS` are tried in order, and the first
one that answers is used. **Exception, opt-in only:** with
`GREENSEARCH_SMALL_MODEL_ROUTING` on, sprout prompts (short, simple, per
`route_mode`: at most 12 words, no complexity markers, at most one
question) try `GREENSEARCH_SMALL_MODEL` (default 2.6B) first, then the
primary chain. That routing is a length heuristic, not a measured
difficulty score, so small-model answers need live judging before routing
is left on. Meta reports `routed_to_small` and `model_tier` (`small` /
`primary`) for every answer, and the session cache keeps small and
primary answers under separate keys.

- **Falls back** on provider HTTP 429 (rate limited), 404 (model not found
  or deprecated), 502 and 503.
- **402 (no credits)** falls back only when the next model to try is a
  `:free` model or `openrouter/free`; a paid next model is not tried.
- **Empty content** (HTTP 200 with null/empty text, seen once from Gemma)
  falls back to the next model in the chain. If every model returns
  empty, the client gets "The model returned no answer, try again" (502),
  not a generic unreachable message.

Before any model is called, a **no-model gate** answers pure arithmetic
locally (`greensearch/local_calc.py`): a prompt that is only an
expression, after stripping "what is / calculate / compute", is parsed
(not executed) and answered with 0 tokens and 0 estimated energy.
Division by zero, any letters, `**`, `//`, unbalanced parentheses, or
a prompt longer than 100 characters all fall through to the normal
model pipeline. Meta reports `local_answer: true` and
`model_tier: "local"` for these answers. The site renders an
"answered locally" tag for them.

## Energy receipt

Every answer carries `meta.energy`, a per-answer receipt the site can
render, built from provider-reported tokens only:

- `energy_wh` = output tokens x 0.0006 Wh + input tokens x 0.0006 / 800 Wh.
  Output tokens are the provider's completion count, which includes
  reasoning tokens. Sources and the published range (0.0006-0.005 Wh
  per output token) are in `greensearch/footprint.py`.
- `co2e_g` = `energy_wh` / 1000 x `GREENSEARCH_GRID_G_PER_KWH`.
- `water_ml_low` / `water_ml_high` = `energy_wh` x WUE, with WUE
  0.1-0.3 L/kWh (modern closed-loop cooling only; electricity-
  generation water is excluded, and the receipt's note says so).
- `basis` is always "estimate", with the factors stated in the receipt
  itself. These are arithmetic estimates from the project's existing
  footprint factors, not measurements and not carbon accounting:
  published per-prompt figures differ by more than 10x between studies.
- A cache hit is 0 Wh / 0 g / 0 mL, with a note saying why (no new
  model call). If the provider did not report token usage, status is
  "unavailable" and every figure is null: no number is invented.
- Escalated answers cover both the primary and the escalation call.
- No region is claimed for the receipt: OpenRouter does not disclose
  where inference ran, so a backend region does not prove inference
  location.
- **401 (key rejected)** never falls back: every model would reject the
  same key. Any other failure (timeouts, network errors, HTTP 500) also
  stops at once.
- **Logprobs**: if the call with logprobs fails with an error that mentions
  logprobs, the **same** model is retried once without logprobs before
  any fallback. The answer then has no `avg_logprob`, so the optional
  cascade does not fire for that request (`escalated: false`). Which free
  models support logprobs has not been tested.
- If every model fails, the client gets the first error's message, unless
  a later error has a specific code (401/402/404/429) and the first was
  generic (502/503 or no HTTP status).
- With the cascade on, the fallback chain applies to the primary side
  only. An escalation failure still returns the escalation error, with no
  fallback and no logprobs retry.
- The opt-in measured baseline calls the model that answered, with no
  fallback chain.

The server log gets one line per failed attempt and one for the answer,
with the HTTP status and model id only, never the key, the prompt or the
provider's error text, e.g. `primary call failed: HTTP 404
model=qwen/qwen3-8b`, `fallback call failed: HTTP 429 model=...`,
`answered by fallback model=liquid/lfm-2.5-2.6b:free`.

`meta.model` is the model id the server sent in the request that
answered. If the last-resort `openrouter/free` answered, that is
`openrouter/free`, which hides the underlying model. `meta.provider_model`
passes through the `model`
field of the provider's response, when the response has one. For a router
id it may name the routed model, but that has not been verified against a
live OpenRouter response here, so treat it as the provider's claim.

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
| `GREENSEARCH_MODEL` | `google/gemma-4-31b-it:free` | Primary model, called first on every request. A named chat model; do not set the `openrouter/free` router here (it can route to non-chat models, see above). |
| `GREENSEARCH_MODEL_FALLBACKS` | `liquid/lfm-2.5-2.6b:free,thinkingmachines/inkling-small:free,poolside/laguna-xs-2.1:free,openrouter/free` | Comma-separated models tried in order when the primary call fails (see "Model and fallbacks"). Whitespace, empty entries, repeats and the primary model are dropped. Unset or empty uses the default list; `none` disables fallbacks. |
| `GREENSEARCH_ESCALATION_MODEL` | value of `GREENSEARCH_MODEL` | Optional. While it equals `GREENSEARCH_MODEL` (the default) there is **no** escalation call. Set it to a different model to turn on the logprob cascade. |
| `GREENSEARCH_CASCADE_THRESHOLD` | `-1.0` | Cascade only: escalate when the primary model's mean token logprob is below this. Must be ≤ 0. A starting point to tune, not a sourced constant. |
| `GREENSEARCH_BACKEND_ORIGIN` | `http://localhost:8000,http://127.0.0.1:8000` | CORS allowlist of exact origins, separated by commas and/or whitespace (so a space-separated list works too). Trailing slashes are stripped, so `https://example.com/` matches `https://example.com`. Matching is otherwise exact; `*` is refused at startup. For Cloud Run, see `CLOUDRUN.md` (env-vars file, commas, no spaces). |
| `GREENSEARCH_RATE_LIMIT_PER_HOUR` | `30` | `/api/chat` requests per client IP per rolling hour. `0` disables. |
| `GREENSEARCH_RATE_LIMIT_PER_DAY` | `100` | `/api/chat` requests per client IP per rolling day. `0` disables. |
| `GREENSEARCH_GLOBAL_LIMIT_PER_DAY` | `800` | `/api/chat` requests in total per rolling day, all IPs combined. `0` disables. POC guard: keeps one abusive IP, or many IPs, from burning the OpenRouter free quota (1000/day after a $10 credit) or paid credits. |
| `GREENSEARCH_ALLOW_PAID_MODELS` | off | `1`/`true`/`yes`/`on` allows a non-free primary, fallback, or escalation model. Off by default: a paid model must be enabled deliberately, so a config mistake cannot drain credits. Server refuses to start on a paid model without it. |
| `GREENSEARCH_SMALL_MODEL` | `liquid/lfm-2.5-2.6b:free` | Small model tried first for sprout prompts when small-model routing is on. Must be free unless `GREENSEARCH_ALLOW_PAID_MODELS` is on. |
| `GREENSEARCH_SMALL_MODEL_ROUTING` | off | `1`/`true`/`yes`/`on` routes sprout prompts (short, simple, per `route_mode`) to `GREENSEARCH_SMALL_MODEL` first, with the primary chain as fallback. Off by default. |
| `GREENSEARCH_SHRINK_VERSION` | `v1` | PromptShrink version for live requests: `v1` (default) or `v2` (redundancy + gated telegraphic, 39% vs 32% saved on the corpus). v2 is opt-in only; any other value refuses to start. Meta reports the version used. |
| `GREENSEARCH_GRID_G_PER_KWH` | `400` | Grid carbon intensity for the per-answer energy receipt, in gCO2e/kWh. Default 400 is illustrative, not measured: OpenRouter does not disclose where inference ran, so no region is claimed. Must be positive; anything else refuses to start. |
| `GREENSEARCH_TASK_ROUTING` | `off` | `1`/`true`/`yes`/`on` routes by task type (fact, definition, steps, reasoning, math, code, creative, other; see `greensearch/task_router.py` and `spec/task_cases.json`) instead of word count, for auto mode only. Unknown prompts fall back to word-count routing, and an explicit client mode always wins. Off by default. Meta reports `task_type`, `task_tier`, and `routed_by` on every answer. When task routing is on, the task tier replaces the sprout rule for small-model routing: a long, easy fact goes small, a short, hard question goes primary. Small-model routing must still be enabled separately for the small model to be used at all. |
| `GREENSEARCH_DIFFICULTY_ROUTING` | `off` | `1`/`true`/`yes`/`on` lets a 0-1 difficulty score override the task tier when task routing is on: below the threshold goes small, at or above goes primary. The score is a transparent feature formula (`difficulty_score` in `greensearch/task_router.py`), not a learned RouteLLM-style router: at the default 0.5 threshold it reproduces the task tiers exactly, so turning it on alone changes nothing. Moving the threshold is what moves traffic. Meta reports `difficulty_score`, `difficulty_tier`, and `router_threshold`. |
| `GREENSEARCH_ROUTER_THRESHOLD` | `0.5` | Difficulty-score threshold for small vs primary, 0-1. Overridden by `GREENSEARCH_QUALITY_TARGET=eco` (0.7) or `=quality` (0.3). |
| `GREENSEARCH_QUALITY_TARGET` | `balanced` | Routing preset: `eco` (threshold 0.7, more small-model answers), `balanced` (uses `GREENSEARCH_ROUTER_THRESHOLD`), `quality` (0.3, more primary answers). Only affects routing when difficulty routing is on. Any other value refuses to start. |
| `GREENSEARCH_SCORER_ESCALATION` | `off` | `1`/`true`/`yes`/`on` lets the transparent answer scorer (`greensearch/scorer.py`, FrugalGPT-style but local and rule-based, no model call) trigger escalation when its score is below `GREENSEARCH_SCORE_THRESHOLD`. Off by default: the score is still reported in meta as `answer_score`, but only the logprob cascade can escalate. Unlike logprobs, the scorer works when logprobs are unavailable. |
| `GREENSEARCH_SCORE_THRESHOLD` | `0.5` | Answer-score escalation threshold, 0-1. Only used when `GREENSEARCH_SCORER_ESCALATION` is on. |
| `GREENSEARCH_MAX_CASCADE_OUTPUT_TOKENS` | `0` | Budget gate: if the primary answer already used more than this many output tokens, no escalation happens, even on a low-confidence trigger. `0` disables. Provider-reported tokens only; unreported tokens never block escalation. |
| `GREENSEARCH_SEMANTIC_CACHE` | `off` | `1`/`true`/`yes`/`on` enables a conservative lexical semantic cache: a fact/definition prompt with difflib ratio at least 0.90 and token overlap at least 0.80 against a cached prompt in the same session, with identical numbers, reuses the cached answer. String similarity, not an embedding model, so it misses true paraphrases rather than risking a wrong answer. Meta reports `semantic_cache_hit` and `semantic_similarity` when it fires. |
| `GREENSEARCH_MAX_TOKENS_MULTIPLIER` | `1.0` | Multiplier on the per-mode max_tokens cap (120/240/400). 1.0 is the current behaviour. Above 1.0, max_tokens becomes a safety net well above the expected budget, with format suffixes and (optionally) stop sequences doing the length control. Must be > 0 and at most 4. Meta reports `max_tokens_used`. |
| `GREENSEARCH_TASK_TEMPERATURE` | `off` | `1`/`true`/`yes`/`on` sends a temperature by task type (fact, definition, math, code 0.2; steps, reasoning 0.5; creative 0.8; other: provider default) when task routing is on. Off by default: no temperature is sent. Meta reports `temperature`. |
| `GREENSEARCH_TASK_STOP_SEQUENCES` | `off` | `1`/`true`/`yes`/`on` sends stop `["\n\n"]` for fact and definition prompts when task routing is on, so the model ends at a paragraph boundary. Off by default. Never sent for expansions. Meta reports `stop_sequences`. |
| `GREENSEARCH_LONG_INPUT_PRUNING` | `off` | `1`/`true`/`yes`/`on` enables conservative extractive pruning for prompts longer than `GREENSEARCH_LONG_INPUT_MAX_CHARS` (see `greensearch/long_input.py`): first/last sentences plus sentences with digits, questions, quoted strings, proper nouns, or code are kept; other sentences are dropped, with a pruning note appended. Off by default. Meta reports `long_input_pruned`, `pruned_sentences`, and `pruned_chars`. |
| `GREENSEARCH_LONG_INPUT_MAX_CHARS` | `1500` | Prompt length above which pruning runs, when pruning is on. Must be at least 500. |
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
- `expand_of` (optional, a non-empty string): the original prompt this request expands on. An expansion always goes full mode and primary tier, with "Explain in detail." instead of the task format suffix, and meta reports `expansion: true` and `expanded_from`. It is equivalent to an explicit `mode: "full"` request plus measurement; the site sends it from the "More detail" button under each live answer. A cached answer that was truncated or scored below 0.3 is not reused on a repeat: the model is called again, and if that call fails the cached answer is returned as a fallback (meta `cache_fallback: true`), so a bad cached answer never turns into an error.
- Sending `api_key`, `key`, `token`, `authorization`, `model` or `base_url`
  is a 400: those live on the server only.

Pipeline, in order: PromptShrink → session cache (per session id,
mode-aware key; a hit makes no model call and reports 0 new output tokens)
→ routing (or the explicit mode) → one call to the primary model
(`google/gemma-4-31b-it:free` by default, then the fallbacks if it fails) with the
brevity system prompt and token cap, logprobs requested → `apply_brevity`
safety-net trim. By default that is the only
model call: `meta.escalated` is `false` and `meta.escalation_reason` is
`single model: no separate escalation model configured`. `avg_logprob` is
still reported when the provider returns it.

Optional cascade (off by default): only when `GREENSEARCH_ESCALATION_MODEL`
is set to a different model, the escalation model is called with the
**same** system prompt and cap if `avg_logprob` is present **and** below
the threshold (missing logprobs never escalate). If that escalation call
fails, the client gets a 502 and **no answer**. The primary model's
low-confidence answer is never silently returned instead. All of this reuses `greensearch/shrink.py`,
`cache.py`, `router.py`, `cascade.py`, `providers.py` and `brevity.py`.

Cut-off answers: a model that hits its token cap stops mid-sentence (a
live Sprout answer read "Machine learning is a type" at exactly the
120-token cap). `apply_brevity` now drops a final prose sentence that does
not end in `.`, `!` or `?` (closing quotes, brackets and markdown emphasis
allowed) when another unit is kept. If the fragment is the whole answer it
is kept with `…` appended. List items, code blocks, headers and sign-offs
are never treated as fragments. Note: a legitimately unpunctuated
one-word answer (e.g. `Paris`) also gets the `…`. `meta.truncated` is
`true` when this happened or when the provider reported `finish_reason:
"length"`.

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
  data: {"mode":"sprout","model":"google/gemma-4-31b-it:free","escalated":false,"cache_hit":false,...}

  event: done
  data: {}
  ```

- **JSON fallback (`"stream": false`)**: `{"answer": "...", "meta": {...}}`.

`meta.delivery` says which was used (`"sse"` or `"json"`), and
`meta.provider_streaming` is always `false`. The SSE stream therefore does
not shorten time-to-first-token; it delivers the finished answer progressively.

`meta` fields: `mode`, `mode_source` (`auto`/`explicit`), `model` (null on
a cache hit; otherwise the model that answered, which may be a fallback),
`primary_model` (the primary-side model that answered), `requested_model`
(`GREENSEARCH_MODEL`), `fallback_used`, `provider_model` (the response's own
`model` field, or null), `escalated`, `escalation_reason`,
`avg_logprob`, `cache_hit`, `cached_from_model` and
`cached_answer_was_escalated` (cache hits only), `input_tokens`,
`output_tokens` and `new_output_tokens` (provider-reported, summed over
both calls when escalated, `null` if the provider did not report them, 0 on
a cache hit; failed attempts are not counted), `tokens_source`, `trimmed`,
`truncated` (false on a cache hit), `shrink` (estimated token counts
before and after PromptShrink), `latency_ms`, `delivery`,
`provider_streaming`, and `baseline` (null unless measured).

### Errors

Every error is JSON `{"error": "<plain message>"}`. No provider detail, URL,
key or traceback is ever returned. Provider errors are mapped after the
fallback chain has run (see "Model and fallbacks").

| Status | When | Message |
|---|---|---|
| 400 | Bad JSON, empty/too-long prompt, bad mode or session id, key/model fields sent | A plain reason, e.g. `Prompt is empty: type a question first` |
| 403 | Browser `Origin` not in the allowlist | `This page's origin is not allowed to use this backend` |
| 413 | Body over 16 KB | `Request body is too large` |
| 401 | Provider rejected the API key (HTTP 401) | `The model provider rejected the API key, check the key on the server` |
| 402 | Provider reports no credits for a paid model (HTTP 402) | `The model provider reports no credits for this paid model: add credits or switch GREENSEARCH_MODEL to a free model` |
| 404 | Model not found or deprecated (HTTP 404) | `The model was not found or is deprecated at the provider: check the GREENSEARCH_MODEL id` |
| 429 | Over the per-IP limit, or the provider rate-limited us | `Too many requests, try again later` |
| 502 | Provider unreachable, or any other provider error (incl. HTTP 502/503/500) | `The model provider could not be reached, try again` |
| 502 | Escalation call failed (optional cascade only) | `The escalation model could not be reached, so no answer was returned (...)` |
| 503 | No API key on the server | `Live backend is not configured yet (no API key on the server)` |
| 503 | Bad base URL | `Live backend is misconfigured on the server, check its settings` |
| 500 | Anything unexpected | `Something went wrong on the server, try again` |

### `GET /api/health`

`{"status":"ok","configured":false,"model":"google/gemma-4-31b-it:free","fallbacks":["liquid/lfm-2.5-2.6b:free","thinkingmachines/inkling-small:free","poolside/laguna-xs-2.1:free","openrouter/free"],"escalation_model":"google/gemma-4-31b-it:free","cascade_enabled":false,"cascade_threshold":-1.0,"rate_limit_per_hour":30,"rate_limit_per_day":100,"global_limit_per_day":800,"allow_paid_models":false,"provider_streaming":false}`.
Never includes the key.

## Security and limits

- **CORS**: only the exact origins in `GREENSEARCH_BACKEND_ORIGIN` get
  `Access-Control-Allow-Origin`, echoed back, never `*`. Requests with a
  disallowed `Origin` get 403 before any model call. Requests without an
  `Origin` header (curl, server-to-server) are allowed. CORS protects
  browsers, not the API, so the rate limit still applies.
- **Rate limits (proof-of-concept abuse guards, not commercial metering)**:
  per client IP 30/hour and 100/day, plus 800/day in total across all IPs,
  all rolling windows, all in memory and per process. They reset on restart
  and are not shared across processes, so on Cloud Run the effective caps
  multiply by the instance count. The global cap sits below OpenRouter's
  free-model daily quota (1000/day after a $10 credit), so abuse burns the
  day's allowance, not the credit balance. Behind a proxy every client
  would share the proxy's IP. `X-Forwarded-For` is deliberately **not**
  trusted, because clients can forge it. A deployment would need a trusted-proxy setting.
- **Paid models blocked by default**: with `GREENSEARCH_ALLOW_PAID_MODELS`
  off, the server refuses to start if the primary, any fallback, or the
  escalation model is not a `:free` model. Paid use must be enabled
  deliberately, and the daily caps still apply then. The default model
  chain is free-only, so a $10 OpenRouter credit is not spent by normal
  traffic; it raises the free-model daily quota and removes the 402
  insufficient-credits error for paid models if they are later enabled.
- **Usage logging**: each chat logs one line to stderr (Cloud Run logs)
  with model, input/output tokens, cache hit, escalation, and latency.
  No prompt text unless `GREENSEARCH_DEBUG_LOG` is on.
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

- **Measured live numbers**: beyond one local live run, live answers,
  latency and measured savings are unmeasured. The fallback chain and the
  error mapping are tested with fake providers only.
- **Provider data policy check** (retention and training, for the exact
  account settings, the primary model, the fallbacks, and every model the
  last-resort `openrouter/free` may route to) before any privacy claim.
- **Hosting account** (GCP, Vercel or Cloudflare) for any deployment.
- **Domain** for a public origin and the matching CORS setting.

`scripts/compare_qwen.py` is still in the tree but targets the Qwen3
models, including the deprecated `qwen/qwen3-8b`; it is not part of the
server and was not changed.
