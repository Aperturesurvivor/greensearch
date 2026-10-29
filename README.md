# Arboris

A small, runnable harness for answering questions concisely and estimating
the footprint of the shorter answer, plus a browser demo of the same idea.
Standard library only, Python 3.9+.

**Vision.** An eco-friendly AI chat that runs on very low-carbon electricity
(reference point: Google Cloud europe-north1 in Finland, cited in
`website/README.md`), with PromptShrink trimming prompts before they reach a
model. **This repository is part of the way there.** A live backend runs on
Google Cloud Run (currently us-central1, not Finland), there is no measured
per-model energy use, and hosting region says nothing about where the model
provider runs inference. The harness shows the mechanics honestly; the
numbers it prints are estimates.

## Quickstart (offline, no key)

```bash
pip install -e .
arboris --demo                          # all topics, with totals
arboris "explain DNS simply" --mode auto
arboris "explain DNS simply" --session-file session.json
python -m arboris "explain DNS simply"  # without installing
```

Modes: `sprout` (about 2 sentences), `canopy` (4), `full` (6, default), or
`auto`, which picks one from the prompt (length, complexity phrases, number
of questions). The offline provider returns canned answers for 95 topics:
the original six (email, API, workout, backup, firewall/Portcullis, DNS),
which keep priority, plus 89 more from `spec/templates.json` (technology,
science, math, history, business, health, cooking, home maintenance,
programming). It says plainly when a topic is not covered.

Open `website/index.html` in a browser for the chat-style demo site,
**Arboris**: no server, no network, same canned topics.

**Renamed from GreenSearch (0.9.0).** The package, CLI and environment
variables are now `arboris`, `arboris` and `ARBORIS_*`. For one release the
old names still work: `import greensearch`, `python -m greensearch` and the
`greensearch` command forward to `arboris`, and the server and live provider
read a `GREENSEARCH_*` variable when its `ARBORIS_*` twin is unset, logging
which legacy names it used. The GitHub repository is renamed separately;
GitHub redirects the old URL.

## How the numbers work

```
tokens   = words x 1.33                       (an estimate, not a tokenizer)
Wh       = output_tokens x wh_per_token + input_tokens x wh_per_token / 800
CO2e (g) = Wh / 1000 x grid_g_per_kwh
```

Generating a token costs far more energy than reading one, so the estimate
is output-weighted. Defaults are 0.0006 Wh per output token (Epoch AI's
2025 estimate of about 0.3 Wh for a GPT-4o query with 500 output tokens)
and 400 g CO2e/kWh, which multiply to 0.00024 g per output token. Input
tokens count at 1/800 of an output token, the midpoint of the 750-850x
ratio Ruf and Detyniecki measured on vLLM (HotCarbon '26). These are
derived from published figures, not measured for any model this project
calls. For scale, Google reports about 0.24 Wh for a median Gemini text
prompt (2025). Until 2026-10-29 the default was 0.0045 Wh for every token,
input and output alike, which priced answers 7 to 9 times above the 2025
estimates. Override the factors to run your own scenario:

```bash
arboris "explain DNS simply" --grid-g-per-kwh 30   # a low-carbon grid
arboris "explain DNS simply" --wh-per-token 0.001
```

Changing the grid factor changes CO2e only; token savings are unaffected.
That is the point of keeping the two levers separate.

**The baseline matters more than the factors.**

- *Assumed* (default): the verbose reply is the concise reply times 3.4 / 2.6
  / 1.9 for sprout / canopy / full. The saved percentage then depends only on
  the mode (71 / 62 / roughly 47 to 50), never on the content. It demonstrates the
  arithmetic and proves nothing, and the output says so.
- *Measured* (`--measure-baseline`): compares against a real unconstrained
  reply. With `--provider live` this makes one extra API call and uses the
  token counts the provider reports. Energy and grid factors remain
  assumptions, but the token saving is then real.

## Live mode

```bash
export ARBORIS_API_KEY="your-key"
arboris "explain DNS simply" --provider live --base-url https://api.openai.com/v1 --mode sprout
```

Any OpenAI-compatible `/chat/completions` endpoint works. Plain `http` base
URLs are refused except for localhost, because the key travels in a header.

Brevity only saves compute if it happens during generation. By default the
harness asks the model for a short answer (system prompt) and caps its output
(`max_tokens`), then trims at sentence boundaries as a safety net. With
`--no-constrain` it generates in full and trims afterwards, and the footprint
then uses the provider-reported generated tokens, which shows that trimming
after the fact saves nothing.

## Unreleased -- Phase 2 (local only, not deployed, not pushed)

Built and tested locally. Not released, not deployed, not pushed. The
version stays 0.8.0.

- **`server/app.py`**: a thin backend, stdlib only. `POST /api/chat` and
  `GET /api/health`, and it also serves the website at `/`. Run it with
  `python3 server/app.py` (port 8000, or `PORT` / `--port`); `--help`
  lists every env var. The key, base URL, model, cascade threshold, CORS
  origins, rate limit and debug logging all come from the environment
  only. Per request: PromptShrink → per-session, mode-aware cache → routing
  → one call to the primary model (`ARBORIS_MODEL`, default
  `google/gemma-4-31b-it:free`, a named general chat model; free models
  are rate-limited and rotate) with the brevity
  prompt, token cap and logprobs → `apply_brevity`. If that call fails
  with HTTP 429/404/502/503 (or 402 when the next model is free), the
  models in `ARBORIS_MODEL_FALLBACKS` are tried in order; 401 never
  falls back. If a provider rejects logprobs, the same model is retried
  once without them. `meta.model` reports the model id that answered
  (`openrouter/free` itself when the last-resort router answered; `meta.provider_model`
  passes through the response's own `model` field, unverified live). There is
  no escalation call by default. The logprob cascade runs only if
  `ARBORIS_ESCALATION_MODEL` is set to a different model, and then an
  escalation failure returns an error, never a downgrade. Answers
  stream as SSE (chunk, meta, done), with a JSON fallback (`"stream": false`).
  The provider itself is called without streaming because the brevity
  trim (and the optional cascade) needs the full answer first. Errors are plain messages (503 not
  configured, 401 key rejected, 402 no credits for a paid model, 404 model
  not found or deprecated, 429 rate limited, 502 provider unreachable,
  400 invalid). A final sentence cut off at the token cap is dropped, or
  marked with `…` when it is the whole answer, and `meta.truncated` says so. It
  has a per-IP in-memory rate limit and an exact-origin CORS allowlist
  (never `*`; entries split on commas and/or spaces, trailing slashes
  stripped). See [`server/README.md`](server/README.md) and, for Cloud
  Run env vars, [`server/CLOUDRUN.md`](server/CLOUDRUN.md).
- **Website (Arboris) Live mode**: a labelled toggle, OFF on every load. With it off,
  the demo behaves exactly as before. With it on, the page shows a LIVE
  pill and a banner saying it is not browser-only. It sends the raw prompt
  to an editable backend URL (stored under `arboris-live-backend-url`),
  renders streamed chunks, and shows the model (plus the provider-reported
  model when it differs), escalation, cache hit, tokens, latency and a
  truncated marker when the answer was cut at the token cap. Backend errors show as plain chat messages. Live
  totals are in a separate LIVE row, never mixed with demo estimates. A
  **Measure baseline** checkbox (off by default) makes a second,
  unconstrained call to measure savings, which doubles API cost.
- **`tests/test_live_backend.py`**: 63 tests, with fake providers only and
  no key or network (the HTTP tests use loopback).
- **`.env.example`**: placeholders only, `ARBORIS_MODEL=google/gemma-4-31b-it:free`
  and the default `ARBORIS_MODEL_FALLBACKS` list (`openrouter/free` last).

Model decision: the default was Qwen3-8B (`qwen/qwen3-8b`) until OpenRouter
deprecated it on 2026-10-09, then briefly `openrouter/free`. It is now the
named chat model `google/gemma-4-31b-it:free`, with a fallback chain of
free models ending in `openrouter/free` as the last resort. Why not the
router as primary: it sent a hamburger question to a content-safety model
that answered "User Safety: safe...". The router can pick non-chat free
models, and fallback only triggers on errors, not on wrong-type answers. `scripts/compare_qwen.py` remains in the tree but is
not needed for the model decision.

Still blocked, on accounts rather than code: a provider API key (so no
real model call has been made, and live savings and latency are
unmeasured), a provider data-policy check (retention and training) before
any privacy claim, a hosting account (Cloud Run europe-north1, Vercel or
Cloudflare are noted as future options only), and a domain.

## Tests

```bash
python -m unittest discover -s tests -v
```

162 tests, standard library only (tiktoken is an optional extra, tested
separately in a venv). The website check needs Node and is skipped
without it. `spec/routing_cases.json` holds hand-written routing expectations
that both the Python router and the website's `routeMode()` must satisfy, so
the two implementations cannot drift silently.

## Known differences from the site

| | Site demo (Arboris) | Harness |
|---|---|---|
| Mode names | Sprout / Canopy / Forest | Sprout / Canopy / Full |
| Prompt trimming (PromptShrink) | Yes | Yes, since 0.6.0 (shrink.py, input-side accounting) |
| Session cache | Yes | Yes, since 0.7.0 (cache.py, persisted in the session file, `--no-cache` to bypass) |
| Mode selection | Automatic | Manual or `--mode auto` |
| Answers | Authored per mode | One draft, trimmed |

## Roadmap, in order

1. Measure, don't assume, on real models: run `scripts/baseline_study.py`
   with `--provider live` over the fixed corpus on two or more real
   models and publish the method and results. The canned study in
   BASELINE.md is not that; the live study is blocked only on an API
   key. This is the opening the project names: no one else publishes
   an open methodology.
2. Source the energy and grid factors, with ranges and region presets.
3. A judge-model cascade as an alternative to the logprob cascade
   (separate design: judge prompt plus a threshold for the judge's
   score, with tests).

Done in 0.6.0-0.7.0, previously on this list: PromptShrink in the
harness, a real tokenizer as an optional extra (`--tokenizer tiktoken`),
session caching, and a logprob-gated cascade (`--cascade`).

## Honest limits

- Token counts are estimates by default; `--tokenizer tiktoken` counts
  real subword tokens. CO2e figures are arithmetic from them, never
  measurements.
- The default verbose baseline is an assumption. Only `--measure-baseline`
  measures anything, and only tokens.
- The offline provider is canned keyword answers, not a model. Routing is a
  heuristic on prompt text.
- Brevity trims at sentence boundaries and never deletes words inside a
  sentence. Abbreviation handling is a heuristic and can misjudge edge cases.
- Session files store prompts and answers in plain text.

## Layout

- `arboris/brevity.py`: sentence budgets; keeps lists, code, subject and sign-off
- `arboris/router.py`: `--mode auto` rules, shared with the site
- `arboris/tokens.py`, `footprint.py`: estimates and the CO2e formula
- `arboris/tokenizer.py`: optional real tiktoken counting
- `arboris/cache.py`: session cache, ported from the website demo
- `arboris/cascade.py`: logprob-gated escalation, no invented confidence
- `arboris/providers.py`: offline provider (6 hardcoded + 89 templated topics) and OpenAI-compatible provider
- `spec/templates.json`: the 89-topic expanded canned-answer library
- `arboris/session.py`: totals, markdown report, atomic JSON persistence
- `spec/routing_cases.json`, `spec/corpus.json`, `tests/`: shared spec, fixed corpus, tests
- `scripts/baseline_study.py`: canned/live baseline study over the corpus
- `BASELINE.md`: baseline study results (canned until a live run is done)
- `website/`: the Arboris browser demo site and its README
- `server/`: Phase 2 live backend (local only) and its README; `.env.example` lists its settings
- `CHANGELOG.md`: history, including the rename from EcoGPT

MIT licensed. See `LICENSE`.
