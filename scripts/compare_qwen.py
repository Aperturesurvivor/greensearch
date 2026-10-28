"""Compare Qwen3-4B vs Qwen3-8B on the fixed corpus, GreenSearch-style.

Method: for each prompt in spec/corpus.json, for each model:
  1. Shrink the prompt with PromptShrink (input side, same as production).
  2. Get a concise answer: brevity system prompt + max_tokens cap,
     with logprobs requested so cascade coverage can be measured.
  3. Record provider-reported tokens when available (else word estimate),
     latency, mean logprob when reported, and simple answer checks
     (empty, hit the token cap, sentence count).

Quality is NOT auto-scored here. The JSON output contains the full
answer text for every prompt and model, so a human (or a judge model
later) can score correctness / completeness / brevity on the same
answers. Do not present token or latency numbers as quality scores.

Usage:
  python scripts/compare_qwen.py --base-url https://openrouter.ai/api/v1 \
      --model-4b qwen/qwen3-4b --model-8b qwen/qwen3-8b \
      --report-out results/qwen_compare.md --json-out results/qwen_compare.json

  # Optional pricing (per million tokens, input/output):
  #   --input-price 0.06 --output-price 0.20
  # Without prices, no cost is reported -- it is never guessed.

Live mode requires GREENSEARCH_API_KEY. Without it, this script
exits 2 and writes nothing -- it never fabricates a live result.
For OpenRouter, set GREENSEARCH_API_KEY to your OpenRouter key.
"""

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from greensearch.providers import (
    BREVITY_SYSTEM,
    MAX_TOKENS,
    OpenAICompatibleProvider,
    ProviderError,
)
from greensearch.shrink import shrink
from greensearch.tokens import est_tokens

ROOT = Path(__file__).resolve().parents[1]


def run_model(provider, mode):
    corpus = json.loads((ROOT / "spec" / "corpus.json").read_text())
    rows = []
    for entry in corpus["prompts"]:
        sr = shrink(entry["raw"])
        t0 = time.monotonic()
        try:
            out = provider.complete_ex(
                sr.text,
                system=BREVITY_SYSTEM[mode],
                max_tokens=MAX_TOKENS[mode],
                logprobs=True,
            )
        except (ValueError, ProviderError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return None
        latency = time.monotonic() - t0
        text = out.text or ""
        if out.completion_tokens is not None:
            out_tokens = out.completion_tokens
            token_source = "provider"
        else:
            out_tokens = est_tokens(text)
            token_source = "estimate (provider reported no usage)"
        sentences = len([s for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()])
        rows.append({
            "id": entry["id"],
            "topic": entry["topic"],
            "shrunk_in": sr.shrunk_tokens,
            "out_tokens": out_tokens,
            "total_tokens": sr.shrunk_tokens + out_tokens,
            "latency_s": round(latency, 2),
            "avg_logprob": out.avg_logprob,
            "token_source": token_source,
            "empty": not text.strip(),
            "hit_cap": out_tokens >= MAX_TOKENS[mode],
            "sentences": sentences,
            "words": len(text.split()) if text.strip() else 0,
            "answer": text,
        })
    return rows


def totals(rows, in_price, out_price):
    n = len(rows)
    total_tokens = sum(r["total_tokens"] for r in rows)
    total_out = sum(r["out_tokens"] for r in rows)
    total_in = sum(r["shrunk_in"] for r in rows)
    with_lp = [r for r in rows if r["avg_logprob"] is not None]
    cost = None
    if in_price is not None and out_price is not None:
        cost = round(total_in * in_price / 1_000_000 + total_out * out_price / 1_000_000, 6)
    return {
        "prompts": n,
        "total_tokens": total_tokens,
        "total_in": total_in,
        "total_out": total_out,
        "avg_latency_s": round(sum(r["latency_s"] for r in rows) / n, 2) if n else 0,
        "failures_empty": sum(1 for r in rows if r["empty"]),
        "hit_cap": sum(1 for r in rows if r["hit_cap"]),
        "logprob_coverage": f"{len(with_lp)}/{n}",
        "avg_logprob": round(sum(r["avg_logprob"] for r in with_lp) / len(with_lp), 4) if with_lp else None,
        "cost_usd": cost,
    }


def markdown_report(models, mode, base_url):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    lines = [
        "# Qwen3-4B vs Qwen3-8B comparison",
        "",
        f"Generated: {now} | Base URL: {base_url} | Mode: {mode}",
        "Method: PromptShrink first, then a concise answer (brevity system prompt + token cap, logprobs requested) over the fixed 12-prompt corpus. Tokens are provider-reported when available, else word estimates. Quality is not auto-scored -- score the answers in the JSON output before picking a model.",
        "",
        "| Model | Prompts | Total tokens | Avg latency | Empty | Hit cap | Logprob coverage | Avg logprob | Cost (USD) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, data in models.items():
        t = data["totals"]
        lines.append(
            f"| {name} | {t['prompts']} | {t['total_tokens']} | {t['avg_latency_s']}s | "
            f"{t['failures_empty']} | {t['hit_cap']} | {t['logprob_coverage']} | "
            f"{t['avg_logprob'] if t['avg_logprob'] is not None else 'n/a'} | "
            f"{t['cost_usd'] if t['cost_usd'] is not None else 'not priced'} |"
        )
    lines += [
        "",
        "## Per-prompt (concise, tokens + latency)",
        "",
        "| Prompt | Model | Out tokens | Latency | Avg logprob | Hit cap |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for name, data in models.items():
        for r in data["rows"]:
            lines.append(
                f"| {r['id']} | {name} | {r['out_tokens']} | {r['latency_s']}s | "
                f"{r['avg_logprob'] if r['avg_logprob'] is not None else 'n/a'} | "
                f"{'yes' if r['hit_cap'] else 'no'} |"
            )
    lines += [
        "",
        "## How to pick",
        "",
        "1. Read the full answers in the JSON output for the same prompt side by side.",
        "2. Score each answer 0-2 for correctness, completeness, and brevity.",
        "3. Pick the smallest model whose scored quality is acceptable -- not the",
        "   model with the fewest tokens. A 4B answer that is wrong or truncated",
        "   is not cheaper than an 8B answer that is right.",
        "4. Check logprob coverage: if a provider reports no logprobs, the",
        "   logprob cascade cannot escalate on that provider, for either model.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare Qwen3-4B vs Qwen3-8B on the fixed corpus.")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--model-4b", default="qwen/qwen3-4b")
    parser.add_argument("--model-8b", default="qwen/qwen3-8b")
    parser.add_argument("--mode", choices=["sprout", "canopy", "full"], default="canopy")
    parser.add_argument("--input-price", type=float, default=None, help="USD per million input tokens")
    parser.add_argument("--output-price", type=float, default=None, help="USD per million output tokens")
    parser.add_argument("--report-out", default=None)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    models = {}
    for label, model_id in [("4B", args.model_4b), ("8B", args.model_8b)]:
        try:
            provider = OpenAICompatibleProvider(args.base_url, model=model_id)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        rows = run_model(provider, args.mode)
        if rows is None:
            return 2
        models[f"{label} ({model_id})"] = {
            "rows": rows,
            "totals": totals(rows, args.input_price, args.output_price),
        }

    if args.report_out:
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_out).write_text(markdown_report(models, args.mode, args.base_url))
        print(f"Report written to {args.report_out}")
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps({
            "base_url": args.base_url, "mode": args.mode, "models": models,
        }, indent=2))
        print(f"JSON written to {args.json_out}")
    for name, data in models.items():
        print(f"{name}: {data['totals']['total_tokens']} tokens, avg {data['totals']['avg_latency_s']}s, "
              f"logprobs {data['totals']['logprob_coverage']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
