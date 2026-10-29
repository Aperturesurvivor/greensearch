"""Task-type routing: golden cases, plus the two cases word-count
routing gets backwards, plus the substring traps.

Run from the repository root: python -m unittest tests.test_task_routing
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arboris.task_router import classify_task, route_task


class TestGoldenCases(unittest.TestCase):
    def test_spec_cases(self):
        cases = json.loads((ROOT / "spec" / "task_cases.json").read_text())["cases"]
        self.assertGreaterEqual(len(cases), 15)
        for case in cases:
            with self.subTest(prompt=case["prompt"]):
                route = route_task(case["prompt"])
                self.assertEqual(route.task_type, case["task_type"])
                self.assertEqual(route.tier, case["tier"])
                self.assertEqual(route.mode, case["mode"])


class TestWordCountFailures(unittest.TestCase):
    def test_long_easy_fact_is_still_small_sprout(self):
        route = route_task(
            "Could you please tell me, in your own words and whenever "
            "you have a moment, what the capital of France actually is?")
        self.assertEqual((route.task_type, route.tier, route.mode),
                         ("fact", "small", "sprout"))

    def test_short_hard_question_is_still_primary_full(self):
        route = route_task("Prove the Pythagorean theorem.")
        self.assertEqual((route.task_type, route.tier, route.mode),
                         ("reasoning", "primary", "full"))


class TestTraps(unittest.TestCase):
    def test_history_is_not_a_story(self):
        # "history" contains "story" as a substring.
        self.assertEqual(classify_task("Tell me about history."), "other")

    def test_capital_is_a_fact_not_a_definition(self):
        self.assertEqual(classify_task("What is the capital of France?"), "fact")

    def test_multi_number_word_problem_is_math_not_fact(self):
        route = route_task(
            "A shop sells 12 boxes with 30 pens each and 5 boxes with "
            "6 pens each. How many pens in total?")
        self.assertEqual((route.task_type, route.tier, route.mode),
                         ("math", "primary", "full"))

    def test_unknown_falls_back_to_word_count(self):
        route = route_task("Tell me about dogs.")
        self.assertTrue(route.fallback)
        self.assertEqual(route.task_type, "other")
        self.assertEqual(route.mode, "sprout")

    def test_comparison_gets_table_suffix_other_reasoning_does_not(self):
        self.assertIn("table", route_task("Compare electric cars and petrol cars.").format_suffix)
        self.assertIn("conclusion first", route_task("Prove the Pythagorean theorem.").format_suffix)
        self.assertNotIn("table", route_task("Prove the Pythagorean theorem.").format_suffix)

    def test_format_suffixes_stay_short(self):
        for prompt in ["What is DNS?", "How do I reset my router?",
                       "Compare solar and wind power."]:
            route = route_task(prompt)
            self.assertLessEqual(len(route.format_suffix.split()), 10)


if __name__ == "__main__":
    unittest.main()
