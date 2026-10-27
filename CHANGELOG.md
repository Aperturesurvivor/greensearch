# Changelog

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
