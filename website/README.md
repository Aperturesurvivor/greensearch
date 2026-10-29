# Arboris chat website demo

The demo site, Python package and CLI are all named **Arboris** (renamed from GreenSearch in 0.9.0). Chats saved under the old `greensearch-*` localStorage keys are moved to the `arboris-*` keys on first load.

A single-file, ChatGPT-style demo. Open index.html in a browser. No server, no backend, no API call, no external fonts, images or scripts, and nothing leaves the page. See [SELFHOST.md](SELFHOST.md) for hosting it.

## What it does

- Chat input, multi-turn in one session, with sample chips for the original 6 covered topics, plus 89 more templated topics (95 total).
- PromptShrink first: trims filler and verbose phrases from the question, protecting code fences. A live preview under the input shows what will be trimmed, and each sent message shows a diff row.
- Session cache: a repeated question (after trimming, to the same core) reuses the earlier answer, with 0 new answer tokens.
- Arboris routing: Sprout (12 words or fewer), Canopy, or Forest (35 words or more, complexity markers, or 2+ question marks).
- Per-answer and session savings: tokens before/after, estimated CO2e vs a defined baseline, a session stats panel and a message history panel.
- Finland panel: Google Cloud Finland (europe-north1) 98% carbon-free energy, grid 30 gCO2eq/kWh; Hamina 97%; global Google data centers 65% in 2025. The panel states clearly that this demo runs locally, not in Finland, so Finland numbers do not change the demo CO2 numbers. Token savings are the demo saving. Clean-energy hosting is a separate lever for a live version.

### Saved in your browser (localStorage)

- The conversation is saved to `localStorage` under the key **`arboris-demo-v1`** after every send, edit, regenerate and clear. It holds each question, its answer, mode, savings and token figures, plus the session totals and history.
- On reload the transcript is restored as it was: no typing animation, no re-counting of totals. A small "Restored from your last session" note marks it. The session cache is rebuilt from the saved turns, so a repeated question is still a cache hit.
- Corrupt or unreadable saved data is ignored. If storage is disabled (some private modes), the chat still works but won't persist.
- **Clear** (the ✕ next to Send) empties the chat, totals, history and cache, and deletes the `arboris-demo-v1` key. You can also delete it in your browser's dev tools (Application → Local Storage).

### Export

**Export** in the header downloads the transcript as a readable Markdown file named `arboris-chat-YYYY-MM-DD-HHMMSS.md`. It lists each question and answer with its mode (including cache hits and regenerated answers), baseline vs Arboris tokens, tokens saved and estimated CO2e saved, followed by the session totals and a note on what the numbers are. The file is built in the browser as a local Blob, with no server involved.

### Per-message actions

- **Copy** (on each answer) copies the answer text to the clipboard and confirms with a toast. If the clipboard API is blocked, it falls back to a legacy copy, and if that also fails it tells you to select and copy manually.
- **Regenerate** (on each answer) reruns the same original question with the cache skipped and replaces that answer in place. Totals are adjusted by subtracting the old turn's contribution and adding the new one, so the message count does not change. Regenerating a cache hit counts the answer tokens again, which honestly lowers the saving. Answers are deterministic templates, so the regenerated text matches what an uncached ask would give.
- **Edit** (on each question) turns it into a text box with Save and Cancel (Ctrl/Cmd+Enter saves, Escape cancels). Save replaces that question and its answer, then replays every turn in order from scratch, rebuilding the cache, totals and history. A later question that used to be a cache hit may no longer be one, and the totals reflect that.

### Topic browser

A sidebar panel lists all 95 topics, grouped as Original six, Technology, Programming, Science, Math, History, Business, Health, Cooking, Home maintenance, and Learning & skills (the catch-all for writing, study, music and similar topics that don't fit the others). A search box filters by topic name, sample question or category. Each topic shows one sample question; clicking it sends that question.

The list is built from the existing topic data (the six `TEMPLATES` plus `EXPANDED_TOPICS`). The only extra metadata is `TOPIC_META` (category, label and sample question per topic). It contains no answers. Every sample question has been checked to route back to its own topic through `shrinkPrompt` → `detectTopic` (95/95).

### How this demo works

The **How this demo works** button in the header opens an in-page dialog, with no new page and no external link. It explains, in plain language, that answers are canned templates and not a live model, that tokens are estimates, and that the baseline is assumed rather than measured. It also notes that the live baseline study script (`scripts/baseline_study.py`) exists but has no live results because there is no API key yet, and that no live numbers are invented. It covers what would change with a live model (a backend, a real tokenizer, a logprob cascade, Finland hosting) and how privacy works.

### Mobile and accessibility

- Buttons, chips, topic entries and message actions are at least 44px tall (Send, Clear and the chat input 56px), and every control has a visible focus outline.
- Icon buttons (theme, copy stats, clear, export, how-it-works, close) and the topic search box have aria-labels. Message action labels name the question they act on.
- Only new or regenerated bot answers are announced, through one polite live region. Re-rendering after an edit or restore does not re-announce the whole transcript, and the cache flash is hidden from screen readers.
- Under 860px wide, the sidebar collapses behind a "Topics, stats & how it works" toggle instead of a cramped strip.
- `prefers-reduced-motion` turns off CSS animation and also skips the typewriter and counter animations.
- Dark and light themes share one restrained green accent (buttons, LIVE pill, links, focus rings, savings tags). Every text/background pair in both palettes was checked at 4.5:1 or better (WCAG AA) by calculation; it has not been checked in a browser.
- Base text is 17px (16px on phones), with larger chat bubbles, softer borders and shadows, and a divider-free totals row.

## Baseline, stated, not assumed

Baseline per message: original question tokens + Forest (full) answer tokens for the same topic, with no trimming, no routing, no reuse.
Arboris per message: trimmed question tokens + routed answer tokens, or trimmed question only on a cache hit.
Tokens: words x 1.33, minimum 1. CO2e is output-weighted: output tokens x 0.0006 Wh x 400 g/kWh (0.00024 g each), input tokens at 1/800 of that. All are estimates, not measurements.

## What it does not do

- No live model. Answers are pre-written templates: the original six (email, APIs, workouts, backups, firewalls/Portcullis, DNS) plus 89 more from spec/templates.json, inlined into this page. Anything else gets the honest generic fallback.
- No cascade, confidence gating, per-model energy measurement, or real tokenizer.
- No measured ChatGPT or Gemini comparison. "Regular LLM" in the demo means the verbose/full version of the same answer, as defined above.
- No live baseline results. `scripts/baseline_study.py` can run a live study, but it needs an API key. Until then, nothing in the demo or the repo is a live measurement.
- No Finland hosting yet. A live version would need an explicit model, key, and region choice from Grant.
- Saved chats live only in the browser that made them. They don't sync between devices and are lost if site data is cleared.

## Test

The inline script is checked from the repo root by `tests/site_conformance.js` (run through `python -m unittest discover -s tests`). Those tests take the first `<script>` block and run it in Node, so the pure logic must stay in that first block, and the DOM code must stay behind its `typeof document` guard. Manual checks worth repeating after edits:

- "Explain DNS simply" routes Sprout, topic dns, and saves vs its Forest baseline.
- The bloated DNS sample from the integration corpus shrinks and saves more than the concise version.
- A repeated DNS question, trimmed to the same core, is a cache hit with 0 new answer tokens.
- "capital" does not route to API, and an empty question returns empty, with no invented answer.
- Regenerate on a cache hit leaves the message count unchanged and lowers the saving. Regenerating it again does not change the totals.
- Edit the first question, then check that the totals equal a fresh session asking the same questions in order.
- Reload: the transcript and totals come back unchanged, with the "Restored" note. Clear, then reload: everything is empty.

PromptShrink keeps words that carry instructions ("simply", "clearly") and does not collapse repeated numbers or words.

## Sources for Finland numbers

- Google Cloud region carbon data: https://cloud.google.com/sustainability/region-carbon
- Google 2026 Environmental Report: https://sustainability.google/files/google-2026-environmental-report/
