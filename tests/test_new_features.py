"""Tests for the 0.7.0 features: cache, tokenizer, cascade.

Run from the repository root:
    python -m unittest discover -s tests -v
"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arboris.cache import SessionCache, cache_key
from arboris.cascade import run_cascade
from arboris.cli import main
from arboris.providers import Completion
from arboris.session import Session
from arboris.tokenizer import TokenizerError, count_tokens


class FakeProvider:
    """A provider returning a fixed completion, for cascade tests."""

    def __init__(self, text, avg_logprob=None, model="fake-small", fail=False):
        self.text = text
        self.avg_logprob = avg_logprob
        self.model = model
        self.live = True
        self.calls = 0
        self.fail = fail

    def complete_ex(self, prompt, system=None, max_tokens=None, logprobs=False):
        self.calls += 1
        if self.fail:
            raise ValueError("escalation failed")
        return Completion(text=self.text, avg_logprob=self.avg_logprob)


class TestCache(unittest.TestCase):
    def test_key_matches_website_rule(self):
        # Website: lowercase, strip non [a-z0-9 ], collapse whitespace.
        self.assertEqual(cache_key("Explain  DNS Simply!", "sprout"), "sprout:explain dns simply")
        self.assertEqual(cache_key("   ", "full"), "")
        self.assertEqual(cache_key("", "full"), "")

    def test_key_is_mode_aware(self):
        self.assertNotEqual(cache_key("Explain DNS simply", "sprout"),
                            cache_key("Explain DNS simply", "full"))

    def test_cli_cache_hit_reuses_answer_at_zero_output_tokens(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            session_file = str(Path(tmp) / "session.json")
            out1 = io.StringIO()
            with redirect_stdout(out1):
                code1 = main(["Explain DNS simply", "--mode", "sprout",
                              "--session-file", session_file])
            out2 = io.StringIO()
            with redirect_stdout(out2):
                code2 = main(["Explain DNS simply", "--mode", "sprout",
                              "--session-file", session_file])
            self.assertEqual(code1, 0)
            self.assertEqual(code2, 0)
            self.assertIn("Cache hit", out2.getvalue())
            self.assertIn("Output: 0 vs", out2.getvalue())
            session = Session.load(session_file)
            self.assertEqual(session.totals["calls"], 2)
            self.assertEqual(session.totals["cache_hits"], 1)
            self.assertEqual(session.calls[1]["eco_tokens"], 0)

    def test_no_cache_bypasses(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            session_file = str(Path(tmp) / "session.json")
            for _ in range(2):
                out = io.StringIO()
                with redirect_stdout(out):
                    code = main(["Explain DNS simply", "--mode", "sprout",
                                 "--session-file", session_file, "--no-cache"])
                self.assertEqual(code, 0)
                self.assertNotIn("Cache hit", out.getvalue())

    def test_old_session_file_without_cache_still_loads(self):
        session = Session.from_dict({"version": 1, "calls": []})
        self.assertEqual(session.cache.entries, {})


class TestTokenizer(unittest.TestCase):
    def test_estimate_matches_words_times_1_33(self):
        self.assertEqual(count_tokens("Hello world", backend="estimate"), 3)

    def test_unknown_backend_raises(self):
        with self.assertRaises(TokenizerError):
            count_tokens("hi", backend="nope")

    def test_tiktoken_counts_real_subwords_when_installed(self):
        try:
            import tiktoken  # noqa: F401
        except ImportError:
            self.skipTest("tiktoken not installed")
        self.assertEqual(count_tokens("Hello world", backend="tiktoken"), 2)
        # Unspaced scripts: the word estimate reports 1 token for the
        # whole string; a real tokenizer counts several.
        self.assertGreater(count_tokens("你好世界", backend="tiktoken"), 1)
        self.assertEqual(count_tokens("你好世界", backend="estimate"), 1)

    def test_cli_tiktoken_without_install_exits_2(self):
        try:
            import tiktoken  # noqa: F401
            self.skipTest("tiktoken is installed in this environment")
        except ImportError:
            pass
        self.assertEqual(main(["Explain DNS simply", "--tokenizer", "tiktoken"]), 2)


class TestCascade(unittest.TestCase):
    def test_high_confidence_does_not_escalate(self):
        primary = FakeProvider("short answer", avg_logprob=-0.2)
        escalation = FakeProvider("longer answer", avg_logprob=-0.1, model="fake-large")
        result = run_cascade(primary, escalation, "Explain DNS simply", threshold=-1.0)
        self.assertFalse(result.escalated)
        self.assertEqual(result.completion.text, "short answer")
        self.assertEqual(escalation.calls, 0)

    def test_low_confidence_escalates(self):
        primary = FakeProvider("short answer", avg_logprob=-2.5)
        escalation = FakeProvider("longer answer", avg_logprob=-0.1, model="fake-large")
        result = run_cascade(primary, escalation, "Explain DNS simply", threshold=-1.0)
        self.assertTrue(result.escalated)
        self.assertEqual(result.completion.text, "longer answer")
        self.assertEqual(escalation.calls, 1)

    def test_no_logprobs_never_escalates(self):
        primary = FakeProvider("short answer", avg_logprob=None)
        escalation = FakeProvider("longer answer", avg_logprob=-0.1, model="fake-large")
        result = run_cascade(primary, escalation, "Explain DNS simply", threshold=-1.0)
        self.assertFalse(result.escalated)
        self.assertEqual(escalation.calls, 0)
        self.assertIn("logprobs unavailable", result.reason)

    def test_positive_threshold_rejected(self):
        primary = FakeProvider("x", avg_logprob=-0.2)
        escalation = FakeProvider("y", avg_logprob=-0.1)
        with self.assertRaises(ValueError):
            run_cascade(primary, escalation, "hi", threshold=0.5)

    def test_cli_cascade_with_demo_exits_2(self):
        self.assertEqual(main(["Explain DNS simply", "--cascade"]), 2)


if __name__ == "__main__":
    unittest.main()
