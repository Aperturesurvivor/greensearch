# GreenSearch chat website demo

A single-file, ChatGPT-style demo. Open index.html in a browser. No server, no backend, no API call, nothing leaves the page.

## What it does

- Chat input, multi-turn in one session, with sample chips for the 6 covered topics.
- PromptShrink first: trims filler and verbose phrases from the question, protecting code fences.
- Session cache: a repeated question (after trimming, to the same core) reuses the earlier answer, with 0 new answer tokens.
- GreenSearch routing: Sprout (12 words or fewer), Canopy, or Forest (35 words or more, complexity markers, or 2+ question marks).
- Per-answer and session savings: tokens before/after, estimated CO2e vs a defined baseline.
- Finland panel: Google Cloud Finland (europe-north1) 98% carbon-free energy, grid 30 gCO2eq/kWh; Hamina 97%; global Google data centers 65% in 2025. The panel states clearly that this demo runs locally, not in Finland, so Finland numbers do not change the demo CO2 numbers. Token savings are the demo saving. Clean-energy hosting is a separate lever for a live version.

## Baseline, stated, not assumed

Baseline per message: original question tokens + Forest (full) answer tokens for the same topic, with no trimming, no routing, no reuse.
GreenSearch per message: trimmed question tokens + routed answer tokens, or trimmed question only on a cache hit.
Tokens: words x 1.33, minimum 1. CO2e: tokens x 0.0018 g. Both are estimates, not measurements.

## What it does not do

- No live model. Answers are the same pre-written templates as the integration demo, for email, APIs, workouts, backups, firewalls/Portcullis, and DNS. Anything else gets the honest generic fallback.
- No cascade, confidence gating, per-model energy measurement, or real tokenizer.
- No measured ChatGPT or Gemini comparison. "Regular LLM" in the demo means the verbose/full version of the same answer, as defined above.
- No Finland hosting yet. A live version would need an explicit model, key, and region choice from Grant.

## Test

The inline script is checked from the repo root by `tests/site_conformance.js` (run through `python -m unittest discover -s tests`). Manual checks worth repeating after edits:

- "Explain DNS simply" routes Sprout, topic dns, and saves vs its Forest baseline.
- The bloated DNS sample from the integration corpus shrinks and saves more than the concise version.
- A repeated DNS question, trimmed to the same core, is a cache hit with 0 new answer tokens.
- "capital" does not route to API, and an empty question returns empty, with no invented answer.

PromptShrink keeps words that carry instructions ("simply", "clearly") and does not collapse repeated numbers or words.

## Sources for Finland numbers

- Google Cloud region carbon data: https://cloud.google.com/sustainability/region-carbon
- Google 2026 Environmental Report: https://sustainability.google/files/google-2026-environmental-report/
