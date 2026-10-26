"""Step 2 tests: persistent sessions and clean live-provider errors.

Run from the repository root:
    python -m unittest discover -s tests -v
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from greensearch.providers import OpenAICompatibleProvider, ProviderError
from greensearch.session import Session

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FP = {
    "eco_tokens": 10,
    "standard_tokens": 34,
    "eco_co2_g": 0.02,
    "standard_co2_g": 0.06,
    "saved_pct": 71,
    "saved_co2_g": 0.04,
}


class TestSessionPersistence(unittest.TestCase):
    def test_save_then_load_round_trip_accumulates_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            session = Session()
            session.record("first", "answer one", "sprout", SAMPLE_FP)
            session.record("second", "answer two", "canopy", SAMPLE_FP)
            session.save(str(path))
            loaded = Session.load(str(path))
            self.assertEqual(loaded.totals["calls"], 2)
            self.assertEqual(loaded.totals["eco_tokens"], 20)
            self.assertEqual(loaded.totals["saved_co2_g"], 0.08)
            self.assertIn("first", loaded.markdown_report())
            self.assertIn("second", loaded.markdown_report())

    def test_load_missing_file_returns_empty_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            loaded = Session.load(str(Path(tmp) / "does-not-exist.json"))
            self.assertEqual(loaded.totals["calls"], 0)

    def test_load_invalid_json_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not json")
            with self.assertRaises(ValueError):
                Session.load(str(path))

    def test_load_wrong_shape_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wrong.json"
            path.write_text(json.dumps({"calls": [{"prompt": "only this"}]}))
            with self.assertRaises(ValueError):
                Session.load(str(path))


class TestLiveProviderErrors(unittest.TestCase):
    def setUp(self):
        self.provider = OpenAICompatibleProvider(
            "https://example.invalid/v1", api_key="test-key"
        )

    def test_http_error_becomes_provider_error_with_status(self):
        error = urllib.error.HTTPError(
            url="https://example.invalid/v1/chat/completions",
            code=401, msg="Unauthorized", hdrs=None, fp=io.BytesIO(b'{"error": {"message": "bad key"}}'),
        )
        with mock.patch("greensearch.providers.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.complete("hello")
            self.assertIn("401", str(ctx.exception))
            self.assertIn("bad key", str(ctx.exception))

    def test_connection_failure_becomes_provider_error(self):
        with mock.patch(
            "greensearch.providers.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.complete("hello")
            self.assertIn("Could not reach", str(ctx.exception))

    def test_malformed_response_shape_becomes_provider_error(self):
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"no_choices": true}')
        with mock.patch("greensearch.providers.urllib.request.urlopen", return_value=response):
            with self.assertRaises(ProviderError):
                self.provider.complete("hello")

    def test_empty_prompt_raises_value_error_not_provider_error(self):
        with self.assertRaises(ValueError):
            self.provider.complete("   ")


class TestCliSessionAndLiveErrors(unittest.TestCase):
    def test_cli_session_file_accumulates_across_two_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_file = str(Path(tmp) / "session.json")
            for prompt in ("Explain DNS simply", "Explain APIs"):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "cli.py"), prompt,
                     "--mode", "sprout", "--session-file", session_file],
                    capture_output=True, text=True, cwd=ROOT,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Session totals: 2 calls", result.stdout)
            data = json.loads(Path(session_file).read_text())
            self.assertEqual(len(data["calls"]), 2)

    def test_cli_corrupt_session_file_exits_2_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{oops")
            result = subprocess.run(
                [sys.executable, str(ROOT / "cli.py"), "hello",
                 "--session-file", str(path)],
                capture_output=True, text=True, cwd=ROOT,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Error:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_cli_live_connection_failure_exits_2_without_traceback(self):
        env = dict(os.environ, GREENSEARCH_API_KEY="test-key")
        result = subprocess.run(
            [sys.executable, str(ROOT / "cli.py"), "hello",
             "--provider", "live", "--base-url", "http://127.0.0.1:1"],
            capture_output=True, text=True, cwd=ROOT, env=env,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("Traceback", result.stdout)


if __name__ == "__main__":
    unittest.main()
