"""Tests for the GreenSearch harness (stdlib unittest only).

Run from the eco-wrapper directory:
    python -m unittest discover -s tests -v

These tests cover Step 1's fixes specifically: the empty-prompt crash,
word-boundary routing, the six demo topics, and mode ordering. They do
not test the portfolio site demo, whose code lives in the site artifact
and still uses substring routing — see README.md, "Site demo vs harness".
"""

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from greensearch.brevity import apply_brevity, split_sentences
from greensearch.footprint import footprint
from greensearch.providers import DemoProvider
from greensearch.tokens import est_tokens

ROOT = Path(__file__).resolve().parents[1]

TOPICS = {
    "email": ("Write a polite follow-up email to a client who missed our call", "Quick follow-up"),
    "api": ("Explain APIs to a 10-year-old", "waiter for software"),
    "workout": ("Give me a 3-day workout plan for beginners at home", "Squats"),
    "backup": ("Summarize why backups matter for a small office", "3 copies"),
    "firewall": ("Explain what a portcullis firewall does", "gatekeeper"),
    "dns": ("Explain DNS simply", "internet phone book"),
}


class TestDemoProvider(unittest.TestCase):
    def setUp(self):
        self.provider = DemoProvider()

    def test_empty_prompt_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.provider.complete("")

    def test_whitespace_only_prompt_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.provider.complete("   \n  ")

    def test_none_prompt_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.provider.complete(None)

    def test_single_character_prompt_does_not_crash(self):
        answer = self.provider.complete("a")
        self.assertIn("No template covers", answer)

    def test_each_topic_routes_to_its_template(self):
        for _name, (prompt, expected) in TOPICS.items():
            with self.subTest(prompt=prompt):
                self.assertIn(expected, self.provider.complete(prompt))

    def test_substring_traps_do_not_route_to_api(self):
        # "capital", "rapid", and "scraping" all contain "api" as a
        # substring; none of them is a question about APIs.
        for prompt in ("What is capital?", "Explain rapid growth", "Explain web scraping"):
            with self.subTest(prompt=prompt):
                self.assertNotIn("waiter for software", self.provider.complete(prompt))

    def test_generic_fallback_is_honest_not_an_answer(self):
        answer = self.provider.complete("Explain quantum computing simply")
        self.assertIn("No template covers that topic yet", answer)
        self.assertNotIn("covered in the essentials", answer)

    def test_long_generic_prompt_topic_is_truncated(self):
        answer = self.provider.complete("x" * 200)
        self.assertIn("…", answer)
        self.assertLess(len(answer), 1000)


class TestBrevityAndModes(unittest.TestCase):
    def test_mode_budgets_are_2_4_6(self):
        long_text = "One. Two. Three. Four. Five. Six. Seven. Eight."
        self.assertEqual(len(split_sentences(apply_brevity(long_text, "sprout"))), 2)
        self.assertEqual(len(split_sentences(apply_brevity(long_text, "canopy"))), 4)
        self.assertEqual(len(split_sentences(apply_brevity(long_text, "full"))), 6)

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            apply_brevity("Hello.", "forest")

    def test_topic_token_counts_are_monotonic_and_sprout_is_shortest(self):
        provider = DemoProvider()
        for name, (prompt, _expected) in TOPICS.items():
            draft = provider.complete(prompt)
            counts = {
                mode: est_tokens(apply_brevity(draft, mode))
                for mode in ("sprout", "canopy", "full")
            }
            with self.subTest(topic=name, counts=counts):
                self.assertLessEqual(counts["sprout"], counts["canopy"])
                self.assertLessEqual(counts["canopy"], counts["full"])
                self.assertLess(counts["sprout"], counts["full"])

    def test_email_keeps_paragraph_shape(self):
        answer = apply_brevity(DemoProvider().complete("write a follow-up email"), "full")
        self.assertIn("\n\n", answer)
        self.assertIn("Thanks,", answer)

    def test_filler_clauses_strip_cleanly(self):
        text = "I hope you are doing well. Here is the answer."
        self.assertEqual(apply_brevity(text, "full"), "Here is the answer.")


class TestTokensAndFootprint(unittest.TestCase):
    def test_est_tokens_minimum_is_one(self):
        self.assertEqual(est_tokens(""), 1)

    def test_footprint_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            footprint(10, "forest")

    def test_footprint_saved_pct_is_between_0_and_100(self):
        result = footprint(50, "sprout")
        self.assertTrue(0 <= result["saved_pct"] <= 100)
        self.assertGreater(result["standard_tokens"], result["eco_tokens"])


class TestCli(unittest.TestCase):
    def test_cli_empty_prompt_exits_2_without_traceback(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "cli.py"), "", "--mode", "sprout"],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("Traceback", result.stdout)

    def test_cli_dns_demo_returns_dns_template(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "cli.py"), "Explain DNS simply", "--mode", "sprout"],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("internet phone book", result.stdout)


if __name__ == "__main__":
    unittest.main()
