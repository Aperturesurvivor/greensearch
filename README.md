# GreenSearch

A small, runnable harness for answering questions concisely and estimating
the footprint of the shorter answer, plus a browser demo of the same idea.
Standard library only, Python 3.9+.

**Vision.** An eco-friendly AI chat that runs on very low-carbon electricity
(reference point: Google Cloud europe-north1 in Finland, cited in
`website/README.md`), with PromptShrink trimming prompts before they reach a
model. **This repository is not that yet.** There is no Finland hosting, no
live chat service and no measured per-model energy use. The harness shows
the mechanics honestly; the numbers it prints are estimates.

## Quickstart (offline, no key)

```bash
pip install -e .
greensearch --demo                          # all topics, with totals
greensearch "explain DNS simply" --mode auto
greensearch "explain DNS simply" --session-file session.json
python -m greensearch "explain DNS simply"  # without installing
```

Modes: `sprout` (about 2 sentences), `canopy` (4), `full` (6, default), or
`auto`, which picks one from the prompt (length, complexity phrases, number
of questions). The offline provider returns canned answers for six topics
(email, API, workout, backup, firewall/Portcullis, DNS) and says plainly when
a topic is not covered.

Open `website/index.html` in a browser for the chat-style demo: no server,
no network, same canned topics.

## How the numbers work

```
tokens   = words x 1.33                       (an estimate, not a tokenizer)
CO2e (g) = tokens x wh_per_token / 1000 x grid_g_per_kwh
```

Defaults are 0.0045 Wh/token and 400 g CO2e/kWh, which multiply to the
0.0018 g/token this project has always used. They are illustrative, not
sourced. For scale, Google reports about 0.24 Wh and 0.03 g CO2e for a median
Gemini text prompt (its 2025 methodology paper), and earlier public estimates
ranged far higher, so published figures differ by more than 10x. Override
both factors to run your own scenario:

```bash
greensearch "explain DNS simply" --grid-g-per-kwh 30   # a low-carbon grid
greensearch "explain DNS simply" --wh-per-token 0.001
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
export GREENSEARCH_API_KEY="your-key"
greensearch "explain DNS simply" --provider live --base-url https://api.openai.com/v1 --mode sprout
```

Any OpenAI-compatible `/chat/completions` endpoint works. Plain `http` base
URLs are refused except for localhost, because the key travels in a header.

Brevity only saves compute if it happens during generation. By default the
harness asks the model for a short answer (system prompt) and caps its output
(`max_tokens`), then trims at sentence boundaries as a safety net. With
`--no-constrain` it generates in full and trims afterwards, and the footprint
then uses the provider-reported generated tokens, which shows that trimming
after the fact saves nothing.

## Tests

```bash
python -m unittest discover -s tests -v
```

89 tests, standard library only (tiktoken is an optional extra, tested
separately in a venv). The website check needs Node and is skipped
without it. `spec/routing_cases.json` holds hand-written routing expectations
that both the Python router and the website's `routeMode()` must satisfy, so
the two implementations cannot drift silently.

## Known differences from the site

| | Site demo | Harness |
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

- `greensearch/brevity.py`: sentence budgets; keeps lists, code, subject and sign-off
- `greensearch/router.py`: `--mode auto` rules, shared with the site
- `greensearch/tokens.py`, `footprint.py`: estimates and the CO2e formula
- `greensearch/tokenizer.py`: optional real tiktoken counting
- `greensearch/cache.py`: session cache, ported from the website demo
- `greensearch/cascade.py`: logprob-gated escalation, no invented confidence
- `greensearch/providers.py`: offline provider and OpenAI-compatible provider
- `greensearch/session.py`: totals, markdown report, atomic JSON persistence
- `spec/routing_cases.json`, `spec/corpus.json`, `tests/`: shared spec, fixed corpus, tests
- `scripts/baseline_study.py`: canned/live baseline study over the corpus
- `BASELINE.md`: baseline study results (canned until a live run is done)
- `website/`: browser demo and its README
- `CHANGELOG.md`: history, including the rename from EcoGPT

MIT licensed. See `LICENSE`.
