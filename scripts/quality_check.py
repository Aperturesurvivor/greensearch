"""Score saved live answers against spec/quality_cases.json.

This is the measurement tool for the efficiency brief's definition of
done (a quality golden set, judged before/after a routing change).
It does NOT call a model and does NOT judge quality itself: it checks
whether each saved answer contains the key facts listed for its
prompt, case-insensitively. A pass means the facts are present, not
that the answer is good; a fail means a fact is missing or wrong,
which is worth investigating. Creative cases only check topic.

Usage:
    python scripts/quality_check.py --answers answers.json
    python scripts/quality_check.py --answers answers.json \
        --cases spec/quality_cases.json

answers.json format, either shape:
    {"cases": [{"prompt": "...", "answer": "..."}, ...]}
    [{"prompt": "...", "answer": "..."}, ...]

Matching is by exact prompt string. Cases with no saved answer are
reported as missing, not as failures, and the exit code is 1 if any
case fails or is missing, 0 only when every case passes.
"""

import argparse
import json
import sys
from pathlib import Path


def load_cases(path):
    data = json.loads(Path(path).read_text())
    cases = data["cases"] if isinstance(data, dict) else data
    return cases


def load_answers(path):
    data = json.loads(Path(path).read_text())
    entries = data["cases"] if isinstance(data, dict) else data
    return {e["prompt"]: e.get("answer", "") for e in entries}


def check_case(case, answer):
    """Return (status, missing_facts): status is PASS, FAIL, or MISSING."""
    if answer is None:
        return "MISSING", list(case.get("must_contain", []))
    lowered = answer.lower()
    missing = [f for f in case.get("must_contain", [])
               if f.lower() not in lowered]
    return ("PASS" if not missing else "FAIL"), missing


def check_all(cases, answers_by_prompt):
    results = []
    for case in cases:
        prompt = case["prompt"]
        status, missing = check_case(
            case, answers_by_prompt.get(prompt) if prompt in answers_by_prompt else None)
        results.append({"prompt": prompt, "task_type": case.get("task_type"),
                        "status": status, "missing": missing})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score saved answers against the quality golden set.")
    parser.add_argument("--answers", required=True, help="JSON file of saved answers (see module docstring).")
    parser.add_argument("--cases", default=None, help="Quality cases file; default spec/quality_cases.json next to the repo root.")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    cases_path = args.cases or str(root / "spec" / "quality_cases.json")
    cases = load_cases(cases_path)
    answers = load_answers(args.answers)
    results = check_all(cases, answers)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    missing = sum(1 for r in results if r["status"] == "MISSING")
    for r in results:
        line = f"{r['status']:7} [{r['task_type']}] {r['prompt']}"
        if r["missing"]:
            line += f"  missing: {', '.join(r['missing'])}"
        print(line)
    print(f"\n{passed} pass, {failed} fail, {missing} missing, {len(results)} total")
    return 0 if failed == 0 and missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
