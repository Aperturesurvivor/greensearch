# Baseline study

Generated: 2026-10-27T13:21:34 | Provider: demo (offline) | Model: demo (canned) | Mode: canopy
Token source: canned (demo provider, word estimate)

> **CANNED, NOT A REAL-MODEL MEASUREMENT.** These numbers use the
> offline demo provider's pre-written answers. They show the
> arithmetic of the corpus, not what any real model would do.
> Run this script with `--provider live` and a key for a real study.

| Prompt | Raw in | Shrunk in | In saved | Out | Baseline out | Out saved % | Total concise | Total baseline |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| dns-plain | 4 | 4 | 0 | 101 | 101 | 0% | 105 | 105 |
| dns-polite | 9 | 5 | 4 | 101 | 101 | 0% | 106 | 110 |
| dns-verbose | 31 | 13 | 18 | 101 | 101 | 0% | 114 | 132 |
| api-plain | 7 | 7 | 0 | 94 | 94 | 0% | 101 | 101 |
| api-polite | 35 | 25 | 10 | 94 | 94 | 0% | 119 | 129 |
| api-verbose | 39 | 17 | 22 | 94 | 94 | 0% | 111 | 133 |
| backup-plain | 11 | 11 | 0 | 88 | 88 | 0% | 99 | 99 |
| backup-polite | 32 | 24 | 8 | 88 | 88 | 0% | 112 | 120 |
| email-plain | 15 | 15 | 0 | 43 | 43 | 0% | 58 | 58 |
| email-verbose | 39 | 21 | 18 | 43 | 43 | 0% | 64 | 82 |
| workout-plain | 13 | 13 | 0 | 48 | 86 | 44% | 61 | 99 |
| firewall-plain | 12 | 12 | 0 | 72 | 101 | 29% | 84 | 113 |

**Totals (12 prompts):** input saved 80 / 247 tokens (32%), total concise 1134 vs baseline 1281 tokens (11% saved).

Method: PromptShrink first, then a concise answer (brevity system prompt + token cap in live mode, sentence-budget trim in demo mode) versus an unconstrained baseline answer for the same prompt. Energy and CO2e are deliberately not reported here: they would be arithmetic from assumed factors, not measurements, and the token saving is the only thing this study measures.
