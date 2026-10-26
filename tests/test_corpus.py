"""Corpus test: verify shrink outputs match spec and measure saving.

Two modes:
  1. Offline (default): runs the demo provider, verifies shrunk forms match
     spec/corpus.json, and prints a saving summary. Always runs in CI.
  2. Live (GREENSEARCH_CORPUS_LIVE=1): uses the real model with
     --measure-baseline logic and writes results/corpus_results.json.
     Skip this in CI unless you want to spend API tokens.

Run: python -m unittest tests.test_corpus -v
     GREENSEARCH_CORPUS_LIVE=1 python -m unittest tests.test_corpus -v
"""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from greensearch.providers import DemoProvider
from greensearch.router import route_mode
from greensearch.shrink import shrink
from greensearch.tokens import est_tokens

ROOT = Path(__file__).resolve().parents[1]
CORPUS = json.loads((ROOT / "spec" / "corpus.json").read_text())
PROMPTS = CORPUS["prompts"]


class TestCorpusShrink(unittest.TestCase):
    """Verify every corpus prompt shrinks to its expected form."""

    def test_shrunk_forms_match_corpus(self):
        failures = []
        for entry in PROMPTS:
            r = shrink(entry["raw"])
            if r.text != entry["shrunk"]:
                failures.append(
                    f"  {entry['id']}:\n"
                    f"    raw:      {entry['raw']!r}\n"
                    f"    expected: {entry['shrunk']!r}\n"
                    f"    got:      {r.text!r}"
                )
        if failures:
            self.fail("Shrunk output mismatches:\n" + "\n".join(failures))

    def test_no_filler_prompts_are_unchanged(self):
        for entry in PROMPTS:
            if entry.get("note", "").startswith("no filler"):
                r = shrink(entry["raw"])
                self.assertFalse(
                    r.changed,
                    f"{entry['id']}: expected no change, but got {r.text!r}",
                )

    def test_topics_route_correctly(self):
        for entry in PROMPTS:
            shrunk = shrink(entry["raw"]).text
            topic_keywords = {
                "dns":      ["dns", "domain name"],
                "api":      ["api"],
                "backup":   ["backup"],
                "email":    ["email", "follow-up"],
                "workout":  ["workout", "exercise"],
                "firewall": ["firewall", "portcullis"],
            }
            expected_topic = entry["topic"]
            keywords = topic_keywords[expected_topic]
            matched = any(k in shrunk.lower() for k in keywords)
            self.assertTrue(
                matched,
                f"{entry['id']}: topic keyword {keywords!r} not found in shrunk prompt {shrunk!r}",
            )


class TestCorpusSavings(unittest.TestCase):
    """Report saving statistics across the corpus (offline, demo provider)."""

    def test_corpus_saving_summary(self):
        """Print a saving summary table and assert overall saving is positive."""
        from greensearch.brevity import apply_brevity
        from greensearch.footprint import footprint

        provider = DemoProvider()
        results = []
        for entry in PROMPTS:
            sr = shrink(entry["raw"])
            raw_answer = provider.complete(sr.text)
            answer = apply_brevity(raw_answer, "canopy")
            fp = footprint(est_tokens(answer), "canopy",
                           baseline_tokens=est_tokens(raw_answer))
            results.append({
                "id": entry["id"],
                "raw_in": sr.original_tokens,
                "shrunk_in": sr.shrunk_tokens,
                "input_saved": sr.saved_tokens,
                "out_tokens": fp["eco_tokens"],
                "baseline_out": fp["standard_tokens"],
                "out_saved_pct": fp["saved_pct"],
            })

        total_raw_in = sum(r["raw_in"] for r in results)
        total_shrunk_in = sum(r["shrunk_in"] for r in results)
        total_input_saved = sum(r["input_saved"] for r in results)
        total_out = sum(r["out_tokens"] for r in results)
        total_base_out = sum(r["baseline_out"] for r in results)
        overall_pct = round((1 - total_out / total_base_out) * 100) if total_base_out else 0

        # Print the table (visible with -v).
        print(f"\n{'ID':<25} {'RawIn':>6} {'ShrIn':>6} {'InSav':>6} {'OutTok':>7} {'BasOut':>7} {'OutSav%':>8}")
        print("-" * 70)
        for r in results:
            print(f"{r['id']:<25} {r['raw_in']:>6} {r['shrunk_in']:>6} {r['input_saved']:>6} "
                  f"{r['out_tokens']:>7} {r['baseline_out']:>7} {r['out_saved_pct']:>7}%")
        print("-" * 70)
        print(f"{'TOTAL':<25} {total_raw_in:>6} {total_shrunk_in:>6} {total_input_saved:>6} "
              f"{total_out:>7} {total_base_out:>7} {overall_pct:>7}%")
        input_pct = round((total_input_saved / total_raw_in) * 100) if total_raw_in else 0
        print(f"\nInput saving: {total_input_saved} tokens / {input_pct}% across {len(results)} prompts")
        print(f"Output saving (canopy vs measured draft baseline): {overall_pct}%")
        print("(These numbers use the demo provider's canned answers, not a real model.)")

        # The corpus has a mix of plain and verbose prompts; input saving must be positive.
        self.assertGreater(total_input_saved, 0, "corpus produced no input saving")
        self.assertGreater(overall_pct, 0, "corpus produced no output saving")


if __name__ == "__main__":
    unittest.main()
