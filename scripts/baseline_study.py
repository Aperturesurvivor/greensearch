"""Baseline study: measure concise vs unconstrained over the fixed corpus.

Method (see BASELINE.md for the full write-up):
  For each prompt in spec/corpus.json:
    1. Shrink the prompt with PromptShrink (input side).
    2. Get a concise answer: brevity system prompt + max_tokens cap
       (live) or the demo provider's canned draft trimmed to the mode.
    3. Get an unconstrained baseline answer: no system prompt, no cap.
    4. Compare tokens. Live runs use provider-reported tokens when
       available; demo runs use the word estimate and are labelled
       CANNED, never presented as real-model measurements.

Usage:
  python scripts/baseline_study.py --provider demo --report-out BASELINE.md
  python scripts/baseline_study.py --provider live \
      --base-url https://openrouter.ai/api/v1 \
      --report-out results/baseline_live.md
  # --model defaults to google/gemma-4-31b-it:free (an OpenRouter id, so
  # pass the OpenRouter --base-url); --model still overrides it.
  # Live mode requires GREENSEARCH_API_KEY. Without it, this script
  # exits 2 and writes nothing -- it never fabricates a live result.

Output JSON (with --json-out) records, per prompt, the model, mode,
token source (provider / estimate / canned), and all token counts, so
a later run can be compared exactly.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from greensearch.brevity import apply_brevity
from greensearch.footprint import footprint
from greensearch.providers import (
    BREVITY_SYSTEM,
    MAX_TOKENS,
    DemoProvider,
    OpenAICompatibleProvider,
    ProviderError,
)
from greensearch.shrink import shrink
from greensearch.tokens import est_tokens

ROOT = Path(__file__).resolve().parents[1]


def run_study(provider, mode):
    corpus = json.loads((ROOT / "spec" / "corpus.json").read_text())
    rows = []
    for entry in corpus["prompts"]:
        sr = shrink(entry["raw"])
        try:
            concise = provider.complete_ex(
                sr.text,
                system=BREVITY_SYSTEM[mode] if provider.live else None,
                max_tokens=MAX_TOKENS[mode] if provider.live else None,
            )
            baseline = provider.complete_ex(entry["raw"])
        except (ValueError, ProviderError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return None
        answer = apply_brevity(concise.text, mode)
        if provider.live and concise.completion_tokens is not None and baseline.completion_tokens is not None:
            out_tokens = concise.completion_tokens
            baseline_tokens = baseline.completion_tokens
            token_source = "provider"
        elif provider.live:
            out_tokens = est_tokens(answer)
            baseline_tokens = est_tokens(baseline.text)
            token_source = "estimate (provider reported no usage)"
        else:
            out_tokens = est_tokens(answer)
            baseline_tokens = est_tokens(baseline.text)
            token_source = "canned (demo provider, word estimate)"
        fp = footprint(out_tokens, mode, baseline_tokens=baseline_tokens)
        rows.append({
            "id": entry["id"],
            "topic": entry["topic"],
            "raw_in": sr.original_tokens,
            "shrunk_in": sr.shrunk_tokens,
            "input_saved": sr.saved_tokens,
            "out_tokens": out_tokens,
            "baseline_out": baseline_tokens,
            "out_saved_pct": fp["saved_pct"],
            "total_concise": sr.shrunk_tokens + out_tokens,
            "total_baseline": sr.original_tokens + baseline_tokens,
        })
    return rows


def markdown_report(rows, provider_name, model, mode, token_source):
    total_in_saved = sum(r["input_saved"] for r in rows)
    total_raw_in = sum(r["raw_in"] for r in rows)
    total_concise = sum(r["total_concise"] for r in rows)
    total_baseline = sum(r["total_baseline"] for r in rows)
    total_pct = round((1 - total_concise / total_baseline) * 100) if total_baseline else 0
    in_pct = round((total_in_saved / total_raw_in) * 100) if total_raw_in else 0
    now = datetime.datetime.now().isoformat(timespec="seconds")
    lines = [
        "# Baseline study",
        "",
        f"Generated: {now} | Provider: {provider_name} | Model: {model} | Mode: {mode}",
        f"Token source: {token_source}",
        "",
    ]
    if provider_name.startswith("demo"):
        lines += [
            "> **CANNED, NOT A REAL-MODEL MEASUREMENT.** These numbers use the",
            "> offline demo provider's pre-written answers. They show the",
            "> arithmetic of the corpus, not what any real model would do.",
            "> Run this script with `--provider live` and a key for a real study.",
            "",
        ]
    lines += [
        "| Prompt | Raw in | Shrunk in | In saved | Out | Baseline out | Out saved % | Total concise | Total baseline |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['raw_in']} | {r['shrunk_in']} | {r['input_saved']} | "
            f"{r['out_tokens']} | {r['baseline_out']} | {r['out_saved_pct']}% | "
            f"{r['total_concise']} | {r['total_baseline']} |"
        )
    lines += [
        "",
        f"**Totals ({len(rows)} prompts):** input saved {total_in_saved} / {total_raw_in} tokens ({in_pct}%), "
        f"total concise {total_concise} vs baseline {total_baseline} tokens ({total_pct}% saved).",
        "",
        "Method: PromptShrink first, then a concise answer (brevity system prompt + token cap in live mode, "
        "sentence-budget trim in demo mode) versus an unconstrained baseline answer for the same prompt. "
        "Energy and CO2e are deliberately not reported here: they would be arithmetic from assumed factors, "
        "not measurements, and the token saving is the only thing this study measures.",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the GreenSearch baseline study over spec/corpus.json.")
    parser.add_argument("--provider", choices=["demo", "live"], default="demo")
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    parser.add_argument("--model", default="google/gemma-4-31b-it:free")
    parser.add_argument("--mode", choices=["sprout", "canopy", "full"], default="canopy")
    parser.add_argument("--report-out", default=None, help="Write a markdown report to this path")
    parser.add_argument("--json-out", default=None, help="Write per-prompt JSON results to this path")
    args = parser.parse_args(argv)

    if args.provider == "demo":
        provider = DemoProvider()
        model = "demo (canned)"
    else:
        try:
            provider = OpenAICompatibleProvider(args.base_url, model=args.model)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        model = args.model

    rows = run_study(provider, args.mode)
    if rows is None:
        return 2
    token_source = (
        "canned (demo provider, word estimate)" if args.provider == "demo"
        else "provider-reported when available, else word estimate"
    )
    if args.report_out:
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_out).write_text(
            markdown_report(rows, provider.name, model, args.mode, token_source)
        )
        print(f"Report written to {args.report_out}")
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps({
            "provider": provider.name, "model": model, "mode": args.mode,
            "token_source": token_source, "rows": rows,
        }, indent=2))
        print(f"JSON written to {args.json_out}")
    total_concise = sum(r["total_concise"] for r in rows)
    total_baseline = sum(r["total_baseline"] for r in rows)
    pct = round((1 - total_concise / total_baseline) * 100) if total_baseline else 0
    print(f"{len(rows)} prompts | total concise {total_concise} vs baseline {total_baseline} ({pct}% saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
