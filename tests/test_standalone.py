"""Standalone-program tests: entry points and --demo mode.

Run from the greensearch directory:
    python -m unittest discover -s tests -v
"""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import greensearch
from greensearch.cli import DEMO_PROMPTS, main

ROOT = Path(__file__).resolve().parents[1]


class TestEntryPoints(unittest.TestCase):
    def test_version_matches_pyproject(self):
        self.assertEqual(greensearch.__version__, "0.4.0")

    def test_demo_prompts_cover_all_six_topics_plus_generic(self):
        topics = [topic for topic, _prompt in DEMO_PROMPTS]
        self.assertEqual(
            topics,
            ["email", "API", "workout", "backup", "firewall", "DNS", "generic"],
        )

    def test_no_prompt_without_demo_returns_2(self):
        self.assertEqual(main([]), 2)

    def test_python_m_entry_point_exists(self):
        result = subprocess.run(
            [sys.executable, "-m", "greensearch", "Explain DNS simply", "--mode", "sprout"],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("internet phone book", result.stdout)

    def test_legacy_cli_shim_still_works(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "cli.py"), "Explain DNS simply", "--mode", "sprout"],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("internet phone book", result.stdout)


class TestDemoMode(unittest.TestCase):
    def test_demo_runs_offline_and_prints_totals(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--demo", "--mode", "canopy"])
        output = buffer.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("GreenSearch demo", output)
        self.assertIn("internet phone book", output)
        self.assertIn("Demo totals: 7 calls", output)
        self.assertIn("No template covers that topic yet", output)

    def test_demo_with_session_file_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_file = str(Path(tmp) / "session.json")
            report_file = str(Path(tmp) / "report.md")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main([
                    "--demo", "--mode", "sprout",
                    "--session-file", session_file,
                    "--report-out", report_file,
                ])
            self.assertEqual(code, 0)
            data = json.loads(Path(session_file).read_text())
            self.assertEqual(len(data["calls"]), 7)
            report = Path(report_file).read_text()
            self.assertIn("Calls: 7", report)

    def test_demo_forces_offline_even_with_live_flag(self):
        # --demo must not require a key or network, even if --provider
        # live is also passed; it always uses the demo provider.
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--demo", "--provider", "live", "--mode", "sprout"])
        self.assertEqual(code, 0)
        self.assertIn("demo (offline)", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
