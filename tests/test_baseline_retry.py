"""Baseline study: 429s are retried, other errors are not."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from baseline_study import _complete_with_retry
from greensearch.providers import Completion, ProviderError


class Flaky:
    live = True
    def __init__(self, fails):
        self.fails = fails
        self.calls = 0
    def complete_ex(self, prompt, system=None, max_tokens=None):
        self.calls += 1
        if self.calls <= self.fails:
            raise ProviderError("Live provider returned HTTP 429", status=429)
        return Completion(text="Short answer.", completion_tokens=10, prompt_tokens=5)


class Always429:
    live = True
    def complete_ex(self, prompt, system=None, max_tokens=None):
        raise ProviderError("Live provider returned HTTP 429", status=429)


class BadKey:
    live = True
    def complete_ex(self, prompt, system=None, max_tokens=None):
        raise ProviderError("Live provider returned HTTP 401", status=401)


class TestBaselineRetry(unittest.TestCase):
    def test_429_retried_then_succeeds(self):
        p = Flaky(2)
        out = _complete_with_retry(p, "hi", None, None, retries=5, base_delay=1, sleep=lambda s: None)
        self.assertEqual(out.text, "Short answer.")
        self.assertEqual(p.calls, 3)

    def test_429_exhausted_raises(self):
        with self.assertRaises(ProviderError) as ctx:
            _complete_with_retry(Always429(), "hi", None, None, retries=2, base_delay=1, sleep=lambda s: None)
        self.assertEqual(ctx.exception.status, 429)

    def test_non_429_not_retried(self):
        with self.assertRaises(ProviderError) as ctx:
            _complete_with_retry(BadKey(), "hi", None, None, retries=5, base_delay=1, sleep=lambda s: None)
        self.assertEqual(ctx.exception.status, 401)


if __name__ == "__main__":
    unittest.main()
