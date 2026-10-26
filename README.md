# GreenSearch — low-carbon GPT-wrapper harness

A real, runnable wrapper harness (not just a website demo). It takes a
prompt, gets a draft answer from a provider, trims it through a brevity
layer to a sentence budget, and reports token and CO2e estimates against
an estimated verbose baseline.

## Vision, restated 2026-10-26

GreenSearch is meant to be an eco-friendly AI chat, in the spirit of an
EcoGPT clone, that uses almost carbon-free electricity so environmentally
conscious people can use AI models with less impact. The reference point
is Google Cloud in Finland: europe-north1 at 98% carbon-free energy.
PromptShrink is the token-saving utility that works with it, trimming
prompts before they reach a model.

This harness is not that full vision yet. It has no Finland hosting, no
live chat website, and no measured per-model energy use. The chat-style
website demo that moves toward the vision is in `website/index.html`
in this repo, and it says so plainly: it runs locally, with canned
answers, and its savings come from fewer tokens, not from Finland
hosting. Do not describe this harness as Finland-hosted or as a
measured ChatGPT/Gemini comparison until a live version actually is.

## Website demo

Open `website/index.html` in a browser. No server, no backend, no API
call. It is a ChatGPT-style chat with PromptShrink trimming, session
cache reuse, Sprout/Canopy/Forest routing, per-answer and session
savings, and a Finland panel that keeps clean-energy hosting separate
from token savings. See `website/README.md` for its baseline, formulas,
and limits.

> **Name.** Renamed from the EcoGPT concept to GreenSearch on 2026-10-24
> following business research (the real EcoGPT at ecogpt.com publishes no
> per-query energy figure — measured, open methodology is this project's
> opening). The harness was renamed in Step 3 (2026-10-26) from
> `eco-wrapper` / `ecowrapper` to `greensearch` / `greensearch`. The old
> folder is gone; a moved-note README is left at the old location only
> if one was created during the move. The live-provider key is now
> `GREENSEARCH_API_KEY`; `ECOWRAPPER_API_KEY` still works as a
> one-version fallback.

## Install (standalone program)

No dependencies beyond Python 3.9+ (standard library only). From this
folder:

```bash
pip install -e .
greensearch "explain DNS simply" --mode sprout
# Or without installing:
python -m greensearch "explain DNS simply" --mode sprout
python cli.py "explain DNS simply" --mode sprout   # legacy entry point
```

## Demo (no key, no network)

The fastest way to show the work — one command, offline, all six
topics plus the honest generic fallback, with session totals at the end:

```bash
greensearch --demo
greensearch --demo --mode canopy --report-out demo-report.md
```

## Quickstart (no key, no network)

```bash
greensearch "explain DNS simply" --mode sprout
greensearch "write a follow-up email" --mode canopy --report-out report.md
greensearch "explain DNS simply" --session-file session.json
greensearch "explain APIs" --session-file session.json
# The second run prints "Session totals: 2 calls" — without
# --session-file, each run is a single-call session.
```

## Modes

- `sprout` — shortest, ~2 sentences
- `canopy` — medium, ~4 sentences
- `full` — fuller, ~6 sentences (default)

## Live provider mode

```bash
export GREENSEARCH_API_KEY="your-key"
greensearch "explain DNS simply" --provider live --base-url https://api.openai.com/v1
```

Any OpenAI-compatible `/chat/completions` endpoint works. Without a key,
live mode refuses to run — it never pretends a demo answer came from a
model.

## Site demo vs harness — shared spec

The portfolio site demo and this harness are two implementations of the
same idea, and they must not drift apart silently. This table is the
spec both are checked against (Step 1, 2026-10-24).

| | Site demo | This harness |
|---|---|---|
| Topics | email, API, workout, backup, firewall/Portcullis, DNS | Same six topics |
| Modes | Sprout / Canopy / Forest, Canopy preselected | Sprout / Canopy / Full, Full is the CLI default |
| Sentence budgets | 2 / 4 / 6 | 2 / 4 / 6 |
| How modes shorten | Authored mode-specific variants | One full draft, trimmed by `apply_brevity` |
| Token estimate | Words × 1.33, minimum 1 | Same (`tokens.py`) |
| Footprint | Standard = output × 3.4 / 2.6 / 1.9; CO2e = tokens × 0.0018 g, illustrative only | Same (`footprint.py`) |
| Generic prompt | Honest fallback: no template covers that topic yet | Same honest fallback (full version, trimmed by mode) |
| Empty input | Shows a "type a prompt first" hint | CLI exits 2 with `Error: Empty prompt: type a prompt first.` |
| Routing | Word-boundary matching, plural-aware (`apis?`, `backups?`, etc.), fixed in Step 3 | Word-boundary matching, plural-aware (`\bapi\b` does not match "capital") |
| Changelog claim | v1.2 entry corrected in Step 3 to "mode-specific templates, honest generic fallback, assumed footprint math" | n/a |

Known divergences left, not hidden: mode names (Forest on the site
vs Full in the harness). The site's substring routing and its
live-preview/session-tracker changelog claim are both fixed as of
Step 3, and Grant confirmed on 2026-10-26 that the most recent site
changes (hero, doors, résumé, featured cards) are good to go.

## Tests

Stdlib unittest only, no extra dependencies:

```bash
python -m unittest discover -s tests -v
```

37 tests cover: empty/whitespace prompts, single-character prompts,
all six topics, substring traps ("capital", "rapid", "scraping"),
mode budgets and monotonic token counts, email paragraph shape, filler
stripping, footprint bounds, CLI exit codes, session save/load
round-trips, corrupt session files, live-provider HTTP/connection/
malformed-response failures, entry points, and `--demo` mode.

## Changelog

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

## Layout

- `greensearch/brevity.py` — clause-level filler stripping + sentence budgets
- `greensearch/tokens.py` — word-based token estimation (words × 1.33)
- `greensearch/footprint.py` — CO2e estimates (tokens × 0.0018 g) vs verbose baseline
- `greensearch/providers.py` — offline demo provider + OpenAI-compatible live provider
- `greensearch/session.py` — per-session savings totals + markdown report export + JSON persistence (`--session-file`)
- `cli.py` — command-line entry point

## What this harness does NOT do yet — cascade scope decision (Step 3)

The business case pitches a small-model-first cascade with
confidence-gated escalation, response caching, and per-answer
energy-source labeling. This harness does **none** of those yet, and
Step 3 deliberately does not ship a fake version of them:

- No cascade: there is one live provider at a time, with one model
  (default `gpt-4o-mini`). A fallback-on-error cascade would be real
  but is not confidence gating, and a heuristic "confidence" score
  invented from answer length or keywords would be a fabrication.
- No confidence gating: OpenAI-compatible endpoints do not reliably
  expose a confidence signal, and this harness has no judge model.
  Real gating would need logprobs or a judge, plus a stated threshold,
  plus tests showing it escalates when it should and does not when it
  should not.
- No response caching, no per-model energy measurement, no real
  tokenizer. The footprint figures remain token-count arithmetic, not
  measurements, and are labeled as such everywhere they appear.

Those items are future work with those prerequisites, not current
features. Do not describe them as implemented in the site, the README,
or a resume.

## Honest limits

- Token counts are estimates (words × 1.33), not a real tokenizer.
- CO2e figures are arithmetic from those estimates, not measurements.
  The verbose-baseline multipliers (3.4 / 2.6 / 1.9 by mode) are
  assumptions, disclosed here and in the code.
- The demo provider's answers are canned keyword responses. It exists so
  the harness runs anywhere; it is not an AI model.
- The brevity layer trims at sentence boundaries only. It never deletes
  words from inside a clause — that garbles meaning (the exact bug that
  bit PromptShrink v1.2 on the portfolio site, and the reason this
  layer is clause-level by design).
