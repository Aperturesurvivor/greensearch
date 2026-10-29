"""Tests for greensearch/long_input.py: conservative extractive pruning.

Run from the repository root: python -m unittest tests.test_long_input
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from greensearch.long_input import prune_long_prompt

PLAIN = ("The weather was pleasant and the road was long and winding "
         "through the hills and valleys of the countryside. ")


def _long_prompt():
    parts = ["Here is a long document about Mars. "]
    parts.append(PLAIN * 20)
    parts.append("In 1969, Apollo landed on the Moon. ")
    parts.append("What does this mean for future missions? ")
    parts.append("```python\nx = 1\nprint(x)\n``` ")
    parts.append("That is the end of the document.")
    return "".join(parts)


class TestLongInput(unittest.TestCase):
    def test_short_prompt_unchanged(self):
        text, dropped, orig = prune_long_prompt("What is DNS?", max_chars=1500)
        self.assertEqual((text, dropped, orig), ("What is DNS?", 0, 12))

    def test_long_prompt_keeps_facts_and_code_drops_plain(self):
        prompt = _long_prompt()
        self.assertGreater(len(prompt), 1500)
        text, dropped, _ = prune_long_prompt(prompt)
        self.assertGreater(dropped, 0)
        self.assertIn("Here is a long document about Mars.", text)
        self.assertIn("That is the end of the document.", text)
        self.assertIn("1969", text)
        self.assertIn("What does this mean for future missions?", text)
        self.assertIn("```python", text)
        self.assertNotIn("The weather was pleasant", text)
        self.assertIn("Pruned for efficiency", text)

    def test_two_sentence_long_prompt_not_pruned(self):
        # With only two sentences there is nothing safe to drop.
        text, dropped, _ = prune_long_prompt("A" * 800 + ". " + "B" * 800 + ".")
        self.assertEqual(dropped, 0)


if __name__ == "__main__":
    unittest.main()
