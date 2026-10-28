# Changelog

- **Unreleased -- Phase 2 (local only, not deployed, not pushed):**
  - Model, CORS and site pass (local only; version stays 0.8.0):
    - Default model is now `google/gemma-4-31b-it:free`, a named general
      chat model (server default, `.env.example`, `--help`, docs).
      `GREENSEARCH_MODEL_FALLBACKS` default is now
      `liquid/lfm-2.5-2.6b:free,thinkingmachines/inkling-small:free,poolside/laguna-xs-2.1:free,openrouter/free`:
      gemma moved out (it is the primary) and `openrouter/free` is the
      last resort only. Why: as primary, `openrouter/free` routed a
      hamburger question to a content-safety model that answered "User
      Safety: safe...". The router can pick non-chat free models, and
      fallback only triggers on errors, not on wrong-type answers. This
      supersedes the `openrouter/free` default noted below.
    - CORS: `GREENSEARCH_BACKEND_ORIGIN` now splits on commas and/or
      whitespace (`re.split(r"[,\s]+")`, empties and repeats dropped), so
      a space-separated list no longer becomes one unmatchable origin.
      Trailing slashes are still stripped; matching is still exact and
      `*` is still refused. `server/CLOUDRUN.md` now uses an env-vars YAML
      file by default and warns that `--set-env-vars` replaces the whole
      env list (a single-var `--set-env-vars` wiped the CORS allowlist in
      production) while `--update-env-vars` keeps the rest. `env.yaml` is
      git- and docker-ignored.
    - Website renamed to **Arboris** in everything a visitor sees (title,
      wordmark, totals label, sidebar, footer, How-it-works dialog,
      welcome, copied stats, Markdown export and its file name
      `arboris-chat-*.md`). Package, CLI, repo, localStorage keys and API
      paths stay `greensearch`.
    - Website redesign (CSS only): one restrained green accent (buttons,
      LIVE pill, links, focus rings, savings tags), 17px base text, larger
      bubbles, a 56px input and Send/Clear, more whitespace, softer borders
      and shadows, a divider-free totals row, lighter metadata tags. All
      controls kept. Text contrast is 4.5:1 or better in both themes, by
      calculation only (not checked in a browser).
    - Live metadata row now shows `meta.provider_model` when present and
      different from `meta.model`, and a "truncated" tag when
      `meta.truncated` is true.
    - `scripts/baseline_study.py` `--model` default is now
      `google/gemma-4-31b-it:free` (was `gpt-4o-mini`). BASELINE.md has a
      "NOT YET MEASURED" section with the local run steps. No live
      baseline was run; the canned numbers are unchanged.
    - Tests: 160 to 162 (comma, space, mixed, trailing-slash and repeat
      origin parsing; exact matching of a space-separated list over HTTP;
      the new default model and fallback order).
  - Cloud Run prep (not deployed, no GCP account used): `Dockerfile`
    (Python 3.12-slim, stdlib only, binds 0.0.0.0 and reads $PORT),
    `.dockerignore` (never ships `.env`), and `server/CLOUDRUN.md`
    (project, Secret Manager key, deploy, CORS allowlist update, and
    teardown steps). Website live URL now defaults to the same origin
    on `*.run.app` hosts, so a Cloud Run deployment works without
    editing the URL field; everywhere else it still defaults to
    localhost, and a saved URL always wins.
  - Fixed after the first local live run (2026-10-27, OpenRouter key in a
    local `.env`), tested with fake providers only:
    - Default model is now `openrouter/free` (server default and
      `.env.example`). It is OpenRouter's router over its free models, not
      a named model; free models are rate-limited and rotate. The old
      default `qwen/qwen3-8b` was deprecated on OpenRouter on 2026-10-09.
      `GREENSEARCH_MODEL` still overrides it.
    - New `GREENSEARCH_MODEL_FALLBACKS` (comma-separated; default
      `liquid/lfm-2.5-2.6b:free,google/gemma-4-31b-it:free,thinkingmachines/inkling-small:free,poolside/laguna-xs-2.1:free`;
      `none` disables). The primary call (and the primary side of the
      optional cascade) tries each fallback in order on HTTP 429, 404, 502
      or 503, and on 402 only when the next model is free. 401 fails at
      once. `meta.model` reports the model that answered; new meta fields
      `requested_model`, `fallback_used` and `provider_model` (the
      response's own `model` field, passed through, not verified live).
      `/api/health` lists `fallbacks`. Escalation failures are unchanged.
    - Logprobs fallback: if the primary call with logprobs fails with an
      error mentioning logprobs, the same model is retried once without
      them; the cascade then does not fire for that request.
    - Fragment fix: `apply_brevity` drops a final sentence cut off at the
      token cap (it showed "Machine learning is a type"), or appends `…`
      when the fragment is the whole answer. New
      `apply_brevity_with_flag` returns `(text, truncated)`; `apply_brevity`
      still returns a string. New `meta.truncated` is true for that case or
      when the provider reports `finish_reason: "length"` (now parsed into
      `Completion.finish_reason`, default None).
    - Error messages: provider 401, 402 and 404 now get their own status
      and message (key rejected; no credits for a paid model; model not
      found or deprecated) instead of the generic 502. 429 and the generic
      502 are unchanged. Logs record the HTTP status and model of every
      failed attempt, never the key, the prompt or the provider's text.
      `ProviderError` now carries `status`.
    - Tests: 140 to 160.
  - Built: `server/app.py`, a stdlib-only backend with `POST /api/chat`
    and `GET /api/health` that also serves the website at `/`. The key,
    models, threshold, CORS origins, rate limit and debug logging are read
    from env only. The pipeline reuses shrink → cache (per session id,
    mode-aware) → router → one call to the single primary model,
    Qwen3-8B (`GREENSEARCH_MODEL`, default `qwen/qwen3-8b`), with logprobs
    requested and no escalation call → `apply_brevity`. The
    `run_cascade` path (same system prompt and cap, escalation only on a
    present, below-threshold mean logprob, an escalation failure returns
    502 with no answer) runs only if `GREENSEARCH_ESCALATION_MODEL` is set
    to a different model. Answers go out as SSE chunk/meta/done events, or JSON
    with `"stream": false`. The provider is called without streaming
    because the brevity trim needs the full answer first; meta
    reports `delivery` and `provider_streaming: false`. Errors are plain
    messages with no provider detail or key. The server has an in-memory
    per-IP rate limit (default 100/h), an exact-origin CORS allowlist (`*`
    refused), prompts kept out of logs by default, and an opt-in
    measured baseline. `providers.py` is unchanged.
  - Built: website Live mode, a toggle that is off on every load, so the
    demo is unchanged when it is off. It adds a LIVE pill, a "not
    browser-only" banner, an editable backend URL stored under
    `greensearch-live-backend-url`, the raw prompt sent with no client
    double-shrink, streamed rendering, and model, escalation, cache-hit,
    token and latency tags. Backend errors show as chat messages. A
    separate LIVE totals row keeps live numbers out of the demo totals.
    A Measure baseline checkbox (off by default, doubles API cost) is
    included. The How-it-works privacy text now distinguishes demo mode
    (no network) from live mode.
  - Built: `tests/test_live_backend.py` (41 tests, fake providers, no key,
    no network beyond loopback), `server/README.md` and `.env.example`
    (placeholders only). Tests: 99 to 140.
  - Changed: model decision. Phase 2 now uses Qwen3-8B only
    (`qwen/qwen3-8b`), the model we already have data on.
    `GREENSEARCH_MODEL_4B` / `GREENSEARCH_MODEL_8B` are replaced by one
    `GREENSEARCH_MODEL`; `GREENSEARCH_ESCALATION_MODEL` is an optional
    override that defaults to the primary model, and while the two are
    equal no escalation call is made (`escalated: false`, reason "single
    model: no separate escalation model configured"). `/api/health` now
    reports `model`, `escalation_model` and `cascade_enabled` instead of
    `model_4b` / `model_8b`; the measured baseline uses the primary model.
    The 4B-first pipeline and the Qwen3-4B vs 8B comparison were dropped
    by the user. `scripts/compare_qwen.py` remains in the tree but is not
    needed for the model decision.
  - Not verified: no real provider call has been made (no key), and the
    Live-mode UI has not been clicked through in a real browser; its
    request and stream code was run under Node against the local server.
  - Still blocked: a provider API key, a provider data-policy check
    (retention and training) before any privacy claim, a hosting account (Cloud Run europe-north1, Vercel or
    Cloudflare, noted as future options only), and a domain.
    `pyproject.toml` version not bumped.
- **0.8.0 (2026-10-27, expanded demo library):** expanded the offline
  demo from 6 to 95 topics: `spec/templates.json` adds 89 canned
  topics (technology, science, math, history, business, health,
  cooking, home maintenance, programming), lazy-loaded by
  `DemoProvider` with the original six keeping priority, and inlined
  into the website demo with Python/JS routing parity. Audit fixes
  applied during the port: `waterycle` renamed to `watercycle`,
  `periodicTable` renamed to `periodictable`, and a `climate action`
  keyword added to the climate-action topic (previously it matched
  only carbon-footprint/sustainability/recycling phrasing). Fallback
  wording changed to "not in the demo library yet" with the accurate
  95-topic count; existing fallback tests updated to match. Medical
  topics (first aid, vaccine, nutrition, sleep, stress, etc.) were
  spot-checked: general information only, with doctor/professional
  and emergency-services prompts where relevant, not specific medical
  advice. Still canned answers, not a model. Tests: 89 to 99.
- **0.7.0 (2026-10-27, audit + cache + tokenizer + cascade):** audit
  fixes (website Google Fonts removed so "nothing leaves the page" is
  true, changelog corpus figure corrected 30% to 32%, README test
  count and PromptShrink table corrected, redundant baseline ternary
  removed); baseline study script (`scripts/baseline_study.py`) and
  BASELINE.md with a canned 12-prompt canopy study (input 32%, total
  11% saved) — the live study is blocked only on an API key and the
  script exits 2 without one rather than fabricating results;
  website session cache ported to the harness (`greensearch/cache.py`,
  persisted in the session file, mode-aware key, `--no-cache` to
  bypass, cache runs bypassed when `--cascade` is on); real tokenizer
  as an optional extra (`--tokenizer tiktoken`, `greensearch[tokenizer]`,
  verified: "Hello world" 2 vs estimate 3, Chinese 5 vs estimate 1);
  confidence-gated cascade (`greensearch/cascade.py`, `--cascade`,
  `--escalation-model`, `--cascade-threshold` default -1.0) that
  escalates only on a real mean logprob below threshold, never
  escalates when logprobs are unavailable, and refuses cascade in
  demo mode. Tests: 75 to 89.
- **0.6.0 (2026-10-26, PromptShrink + corpus):** PromptShrink is now a
  first-class module (`greensearch/shrink.py`) wired into the CLI and session
  report; the footprint now accounts for both input and output tokens; a fixed
  test corpus (`spec/corpus.json`, 12 prompts) verifies shrunk forms and
  measures input saving (32% across the corpus with canned answers: 80 of 247 tokens); site
  PromptShrink spec extended to cover previously-broken cases ("simply",
  "clearly", "in detail", repeated numbers/words). Tests: 71 to 75.
- **0.5.0 (2026-10-26, review pass):** fixed filler stripping that could
  leave half a sentence; sentence splitting now respects abbreviations;
  list items, line breaks, code fences, email subject and sign-off survive
  trimming; live provider sends a brevity system prompt and a token cap
  (generation-side brevity), records provider-reported usage, rejects
  plain-http base URLs (except localhost), and turns null content, read
  timeouts (a separate class before Python 3.10) and invalid UTF-8 into a
  clean `Error:` exit; `--measure-baseline` compares against a real
  unconstrained reply; footprint factors are now explicit and overridable
  (`--wh-per-token`, `--grid-g-per-kwh`) and the baseline is labelled
  assumed or measured; `--mode auto` routes by prompt, with the rules
  shared with the site through `spec/routing_cases.json`; session files
  are written atomically; site: PromptShrink no longer deletes "simply" or
  "clearly" (instructions) or collapses repeated numbers/words. Tests: 37
  to 71.
- **0.4.0 (2026-10-26, standalone program):** packaged as an
  installable program — `pyproject.toml` with a `greensearch`
  console script, `python -m greensearch` entry point, legacy
  `python cli.py` shim, MIT LICENSE; new offline `--demo` mode
  (all six topics plus the generic fallback, with demo totals, no
  key or network required); CLI refactored into the package
  (`greensearch/cli.py`) with shared session/report handling.
- **0.3.0 (2026-10-26, Step 3, harness part):** renamed
  `eco-wrapper` / `ecowrapper` to `greensearch` / `greensearch`
  (folder, package, imports, CLI description, session report header);
  live-provider key is now `GREENSEARCH_API_KEY`, with
  `ECOWRAPPER_API_KEY` as a one-version fallback; cascade scope
  decided and documented — no cascade, confidence gating, caching,
  or per-model energy measurement is implemented, and those are
  listed as future work with prerequisites, not current features.
  Site part of Step 3 (panel routing + changelog claim) is complete:
  site routing is now word-boundary and plural-aware, the v1.2
  changelog claim is corrected, and Grant confirmed on 2026-10-26
  that the concurrent site changes in that build are good to go.
- **0.2.0 (2026-10-24, Step 2):** sessions persist with
  `--session-file` (JSON, `{"version": 1, "calls": [...]}`; missing file
  starts empty, corrupt file exits 2 with a readable error instead of
  discarding data); live-provider failures become a single
  `ProviderError` — HTTP status + provider message, connection failure,
  timeout, or malformed response — and the CLI exits 2 with an
  `Error:` line, never a traceback; report/session write failures also
  exit 2 cleanly. Test suite grows to 29 tests.
- **0.1.1 (2026-10-24, Step 1):** empty-prompt crash fixed (CLI now
  exits 2 with a readable error, no traceback); routing switched from
  substring to word-boundary matching; workout, firewall, and DNS
  templates added to the demo provider, matching the site's content;
  generic fallback made honest instead of echoing the prompt as an
  answer; test suite added (18 tests).
- **0.1.0:** initial harness — brevity layer, token/footprint
  estimation, demo + live providers, session reports.

Name history: Renamed from the EcoGPT concept to GreenSearch on 2026-10-24 > following business research (the real EcoGPT at ecogpt.com publishes no > per-query energy figure — measured, open methodology is this project's > opening). The harness was renamed in Step 3 (2026-10-26) from > `eco-wrapper` / `ecowrapper` to `greensearch` / `greensearch`. The old > folder is gone; a moved-note README is left at the old location only > if one was created during the move. The live-provider key is now > `GREENSEARCH_API_KEY`; `ECOWRAPPER_API_KEY` still works as a > one-version fallback.
