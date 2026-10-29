"""PromptShrink quality harness: tokens saved AND answers changed.

Usage:
  python scripts/shrink_quality.py [--backend estimate|tiktoken]

For every prompt in spec/corpus.json, compare v1 (shrink) and v2
(shrink_v2) on estimated (or real, with --backend tiktoken) tokens,
and compare DemoProvider answers for the original, v1, and v2 prompts.
A v2 answer that differs from the v1 answer is flagged CHANGED: the
DemoProvider is keyword-based, so a change means v2 removed or altered
a keyword the answer depended on, which is a quality loss, not a saving.
No network, no key, no live model: this is an offline harness.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arboris.providers import DemoProvider
from arboris.shrink import shrink, shrink_v2
from arboris.tokenizer import count_tokens

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description="PromptShrink v1 vs v2 quality harness.")
    parser.add_argument("--backend", choices=["estimate", "tiktoken"], default="estimate")
    args = parser.parse_args(argv)

    def count(text):
        return count_tokens(text, backend=args.backend)

    corpus = json.loads((ROOT / "spec" / "corpus.json").read_text())
    provider = DemoProvider()
    print(f"| Prompt | Orig | v1 | v2 | v2 saved % | v2 vs v1 answer |")
    print(f"|---|---:|---:|---:|---:|---|")
    total_orig = total_v1 = total_v2 = 0
    changed = 0
    for entry in corpus["prompts"]:
        r1 = shrink(entry["raw"], count_fn=count)
        r2 = shrink_v2(entry["raw"], count_fn=count)
        a1 = provider.complete(r1.text)
        a2 = provider.complete(r2.text)
        same = a1 == a2
        if not same:
            changed += 1
        total_orig += r1.original_tokens
        total_v1 += r1.shrunk_tokens
        total_v2 += r2.shrunk_tokens
        pct = round((1 - r2.shrunk_tokens / r1.original_tokens) * 100) if r1.original_tokens else 0
        print(f"| {entry['id']} | {r1.original_tokens} | {r1.shrunk_tokens} | {r2.shrunk_tokens} | {pct}% | {'same' if same else 'CHANGED'} |")
    print()
    print(f"Totals ({len(corpus['prompts'])} prompts, {args.backend} tokens): "
          f"original {total_orig}, v1 {total_v1} ({round((1 - total_v1 / total_orig) * 100)}% saved), "
          f"v2 {total_v2} ({round((1 - total_v2 / total_orig) * 100)}% saved), "
          f"v2 extra over v1: {total_v1 - total_v2} tokens, answers changed v2 vs v1: {changed}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
