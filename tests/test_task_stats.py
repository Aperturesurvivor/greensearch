"""Tests for scripts/task_stats.py.

Run from the repository root: python -m unittest tests.test_task_stats
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.task_stats import parse_lines

SAMPLE = [
    "chat model=gemma in=22 out=51 cache_hit=False escalated=False expansion=False task=fact tier=small score=0.9 latency_ms=2243",
    "chat model=gemma in=30 out=80 cache_hit=False escalated=True expansion=False task=reasoning tier=primary score=0.4 latency_ms=3000",
    "chat cache_hit model=gemma in=0 out=0 task=fact tier=small",
    "chat local_calc in=0 out=0 task=math tier=local",
    "not a chat line, ignored",
    "chat cache_bypass reason=cached answer was truncated: calling model again",
]


class TestTaskStats(unittest.TestCase):
    def test_aggregates_by_task(self):
        stats = parse_lines(SAMPLE)
        self.assertEqual(stats["fact"]["count"], 2)
        self.assertEqual(stats["fact"]["cache_hit_rate"], 0.5)
        self.assertEqual(stats["fact"]["total_tokens"], 73)
        self.assertEqual(stats["reasoning"]["escalation_rate"], 1.0)
        self.assertEqual(stats["math"]["count"], 1)
        self.assertEqual(stats["math"]["total_tokens"], 0)
        self.assertEqual(stats["math"]["local_rate"], 1.0)
        self.assertNotIn("cache_bypass", stats)

    def test_empty_input(self):
        self.assertEqual(parse_lines([]), {})


if __name__ == "__main__":
    unittest.main()
