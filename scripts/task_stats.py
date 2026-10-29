"""Aggregate per-task totals from Arboris server log lines.

The server logs one line per chat (see server/app.py): model, in/out
tokens, cache_hit, escalated, expansion, task, tier, score, latency.
This script reads those lines from a file or stdin and reports, per
task type, counts, cache-hit rate, escalation rate, expansion rate,
total and average tokens, average score, and average latency. It is
the brief's "tokens per resolved task" report, built from logs rather
than a new runtime store, so it works on Cloud Run logs with no
extra infrastructure and no session IDs in the input (the server
never logs session IDs, so follow-up rate within a session cannot
be derived here; expansion and re-ask flags in meta are the proxy).

Usage:
    gcloud run logs read arboris --region us-central1 | python scripts/task_stats.py
    python scripts/task_stats.py server.log
    python scripts/task_stats.py server.log --json

Lines that are not chat lines are ignored. Old log lines without
task/tier/score are counted under task "-" with score unknown.
"""

import argparse
import json
import re
import sys
from collections import defaultdict

_CHAT = re.compile(
    r"chat (?:model=(?P<model>\S+) )?"
    r"(?:local_calc |cache_hit |semantic_cache_hit |cache_fallback )?"
    r".*?in=(?P<in>\d+|None) out=(?P<out>\d+|None)"
    r"(?:.*?cache_hit=(?P<cache_hit>True|False))?"
    r"(?:.*?escalated=(?P<escalated>True|False))?"
    r"(?:.*?expansion=(?P<expansion>True|False))?"
    r"(?:.*?task=(?P<task>\S+))?"
    r"(?:.*?tier=(?P<tier>\S+))?"
    r"(?:.*?score=(?P<score>None|[-0-9.]+))?"
    r"(?:.*?latency_ms=(?P<latency>\d+))?"
)


def _int_or_zero(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_lines(lines):
    """Parse chat log lines into per-task aggregates and totals."""
    by_task = defaultdict(lambda: {
        "count": 0, "cache_hits": 0, "local_answers": 0, "escalations": 0, "expansions": 0,
        "input_tokens": 0, "output_tokens": 0, "scores": [], "latencies": [],
    })
    for line in lines:
        if "chat " not in line:
            continue
        match = _CHAT.search(line)
        if not match:
            continue
        # Skip non-chat log lines that happen to contain "chat " but
        # have no token counts (e.g. cache_bypass lines).
        if match.group("in") is None and "in=" not in line:
            continue
        task = match.group("task") or "-"
        agg = by_task[task]
        agg["count"] += 1
        # Cache-hit lines are "chat cache_hit ..." (space, not "="),
        # while model lines say "cache_hit=False" and must not count.
        if (match.group("cache_hit") == "True"
                or "chat cache_hit " in line
                or "semantic_cache_hit" in line
                or "cache_fallback" in line):
            agg["cache_hits"] += 1
        if "local_calc" in line:
            agg["local_answers"] += 1
        if match.group("escalated") == "True":
            agg["escalations"] += 1
        if match.group("expansion") == "True":
            agg["expansions"] += 1
        agg["input_tokens"] += _int_or_zero(match.group("in"))
        agg["output_tokens"] += _int_or_zero(match.group("out"))
        if match.group("score") and match.group("score") != "None":
            agg["scores"].append(float(match.group("score")))
        if match.group("latency"):
            agg["latencies"].append(int(match.group("latency")))
    out = {}
    for task, agg in by_task.items():
        count = agg["count"]
        out[task] = {
            "count": count,
            "cache_hit_rate": round(agg["cache_hits"] / count, 3) if count else 0,
            "local_rate": round(agg["local_answers"] / count, 3) if count else 0,
            "escalation_rate": round(agg["escalations"] / count, 3) if count else 0,
            "expansion_rate": round(agg["expansions"] / count, 3) if count else 0,
            "input_tokens": agg["input_tokens"],
            "output_tokens": agg["output_tokens"],
            "total_tokens": agg["input_tokens"] + agg["output_tokens"],
            "avg_tokens_per_task": round((agg["input_tokens"] + agg["output_tokens"]) / count, 1) if count else 0,
            "avg_score": round(sum(agg["scores"]) / len(agg["scores"]), 3) if agg["scores"] else None,
            "avg_latency_ms": round(sum(agg["latencies"]) / len(agg["latencies"]), 1) if agg["latencies"] else None,
        }
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Aggregate Arboris chat log lines by task type.")
    parser.add_argument("file", nargs="?", help="Log file; default stdin.")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of a table.")
    args = parser.parse_args(argv)
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            lines = handle.readlines()
    else:
        lines = sys.stdin.readlines()
    stats = parse_lines(lines)
    if args.json:
        print(json.dumps(stats, indent=2, sort_keys=True))
        return 0
    total = sum(s["count"] for s in stats.values())
    print(f"{'task':12} {'n':>4} {'cache':>6} {'local':>6} {'esc':>6} {'exp':>6} {'tokens':>8} {'avg/task':>8} {'score':>6}")
    for task in sorted(stats):
        s = stats[task]
        print(f"{task:12} {s['count']:>4} {s['cache_hit_rate']:>6.2f} "
              f"{s['local_rate']:>6.2f} "
              f"{s['escalation_rate']:>6.2f} {s['expansion_rate']:>6.2f} "
              f"{s['total_tokens']:>8} {s['avg_tokens_per_task']:>8.1f} "
              f"{s['avg_score'] if s['avg_score'] is not None else '-':>6}")
    print(f"\nTotal tasks: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
