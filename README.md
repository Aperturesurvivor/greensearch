# Arboris

Lower-carbon AI chat. Shorter, right-sized answers, with an honest energy
estimate for each one. Standard library only, Python 3.9+.

The idea is simple: trim the prompt, answer with the smallest model that
will do, and only escalate when confidence is low. The savings are shown
as a receipt, not a marketing number. Token counts from a live model are
provider-reported. Energy and CO2e are estimates from published factors,
not measurements of any data centre.

Package and CLI are `arboris` since 0.9.0 (renamed from GreenSearch). The
GitHub repo is still `succulentsdev/greensearch`. Old `greensearch` and
`GREENSEARCH_*` names still work for one release.

## Quickstart, offline, no key

```bash
pip install -e .
arboris --demo                          # all topics, with totals
arboris "explain DNS simply" --mode auto
arboris "explain DNS simply" --session-file session.json
python -m arboris "explain DNS simply"  # without installing
```

Modes: `sprout` (about 2 sentences), `canopy` (4), `full` (6, default),
or `auto`, which picks from the prompt (length, complexity phrases,
number of questions).

The offline provider returns canned answers for 95 topics: the original
six (email, API, workout, backup, firewall/Portcullis, DNS), which keep
priority, plus 89 more from `spec/templates.json`. It says plainly when
a topic is not covered. This is the harness only. The website is live
only and has no canned answers.

## Website and live backend

The website is a single file, `website/index.html`. It is live only:
every question goes to a backend, which holds the API key. The page
never sees a key.

The backend is `server/app.py` (standard library only). It serves the
site at `/`, answers at `POST /api/chat`, and reports health at
`GET /api/health`. Run it locally with `python3 server/app.py` (port
8000, or `PORT` / `--port`); `--help` lists every setting.

The hosted backend runs on Google Cloud Run in us-central1:
https://arboris-1037861813679.us-central1.run.app

Per request: PromptShrink, per-session cache, routing, one call to the
primary model (default `google/gemma-4-31b-it:free`) with a brevity
prompt, token cap and logprobs, then a sentence-boundary trim. If that
call fails with 429, 404, 502 or 503 (or 402 when the next model is
free), the models in `ARBORIS_MODEL_FALLBACKS` are tried in order; 401
never falls back. Answers stream as SSE, with a JSON fallback when
streaming is off. The logprob cascade runs only when
`ARBORIS_ESCALATION_MODEL` is set to a different model. See
`server/README.md` and, for Cloud Run, `server/CLOUDRUN.md`.

Rate limits are in-memory and per-process, proof of concept only:
30 per hour and 100 per day per IP, 800 per day globally. Paid models
are blocked at startup unless `ARBORIS_ALLOW_PAID_MODELS=1` is set.

## How the numbers work

```
tokens   = words x 1.33                       (an estimate, not a tokenizer)
Wh       = output_tokens x wh_per_token + input_tokens x wh_per_token / 800
CO2e (g) = Wh / 1000 x grid_g_per_kwh
```

Generating a token costs far more energy than reading one, so the
estimate is output-weighted. Defaults are 0.0006 Wh per output token
(Epoch AI, 2025: about 0.3 Wh for a GPT-4o query with 500 output tokens)
and 400 g CO2e/kWh, which multiply to 0.00024 g per output token. Input
tokens count at 1/800 of an output token, the midpoint of the 750-850x
ratio Ruf and Detyniecki measured on vLLM (HotCarbon '26). These are
derived from published figures, not measured for any model this project
calls. For scale, Google reports about 0.24 Wh for a median Gemini text
prompt (2025).

Override the factors to run your own scenario:

```bash
arboris "explain DNS simply" --grid-g-per-kwh 30   # a low-carbon grid
arboris "explain DNS simply" --wh-per-token 0.001
```

Changing the grid factor changes CO2e only; token savings are
unaffected.

The baseline matters more than the factors. The default baseline is
assumed: the verbose reply is the concise reply times 3.4 / 2.6 / 1.9
for sprout / canopy / full, so the saved percentage then depends only
on the mode (71 / 62 / roughly 47 to 50), never on the content. It
demonstrates the arithmetic and proves nothing, and the output says so.
`--measure-baseline` compares against a real unconstrained reply. With
a live provider this makes one extra API call and uses the token counts
the provider reports. Energy and grid factors remain assumptions, but
the token saving is then real.

## Tests

```bash
python -m unittest discover -s tests -v
```

267 tests, standard library only. The website check needs Node and is
skipped without it. `spec/routing_cases.json` holds hand-written routing
expectations that both the Python router and the website's `routeMode()`
must satisfy, so the two implementations cannot drift silently.

Branches: `main` is stable (what the hosted backend deploys from).
Work goes on short-lived branches off `dev`, merged to `dev` first,
then to `main` for a release. `gh-pages` serves an older demo and is
not the live site.

## Honest limits

- Token counts are estimates by default; `--tokenizer tiktoken` counts
  real subword tokens. CO2e figures are arithmetic from them, never
  measurements.
- The default verbose baseline is an assumption. Only
  `--measure-baseline` measures anything, and only tokens.
- The offline provider is canned keyword answers, not a model. Routing
  is a heuristic on prompt text.
- Brevity trims at sentence boundaries and never deletes words inside a
  sentence. Abbreviation handling is a heuristic and can misjudge edge
  cases.
- Session files store prompts and answers in plain text.
- Hosting region says nothing about where the model provider runs
  inference. The backend runs in us-central1, not Finland, so no
  Finland claim is made for inference. Finland (europe-north1, about
  98% carbon-free) is a future hosting option, not a current claim.
- No systematic live baseline has been run yet, so no live savings
  figure is claimed.

## Layout

- `arboris/brevity.py`: sentence budgets; keeps lists, code, subject and sign-off
- `arboris/router.py`: `--mode auto` rules, shared with the site
- `arboris/tokens.py`, `footprint.py`: estimates and the CO2e formula
- `arboris/tokenizer.py`: optional real tiktoken counting
- `arboris/cache.py`: session cache
- `arboris/cascade.py`: logprob-gated escalation, no invented confidence
- `arboris/providers.py`: offline provider (6 hardcoded + 89 templated topics) and OpenAI-compatible provider
- `spec/templates.json`: the 89-topic expanded canned-answer library
- `arboris/session.py`: totals, markdown report, atomic JSON persistence
- `spec/routing_cases.json`, `spec/corpus.json`, `tests/`: shared spec, fixed corpus, tests
- `scripts/baseline_study.py`: canned/live baseline study over the corpus
- `BASELINE.md`: baseline study results (canned until a live run is done)
- `website/`: the live-only browser site and its README
- `server/`: live backend and its README; `.env.example` lists its settings
- `CHANGELOG.md`: history, including the rename from EcoGPT

MIT licensed. See `LICENSE`.
