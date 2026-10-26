"""GreenSearch CLI: concise answers with a footprint comparison.

Installed entry points (see pyproject.toml):
  greensearch "explain DNS simply" --mode sprout
  python -m greensearch "explain DNS simply" --mode sprout
  python cli.py "explain DNS simply" --mode sprout   (legacy, same code)

Demo mode (offline, no key, no network):
  greensearch --demo
  greensearch --demo --mode canopy --report-out demo-report.md

Without --provider live, runs the offline demo provider: no key, no
network, no model. Live mode needs GREENSEARCH_API_KEY in the
environment. With --session-file, calls persist to a JSON file across
runs and the printed session totals accumulate; without it, each run
is a single-call session. All user-facing failures exit 2 with a
readable "Error:" line, never a traceback.
"""

import argparse
import sys

from greensearch.brevity import apply_brevity
from greensearch.tokens import est_tokens
from greensearch.footprint import footprint
from greensearch.providers import (
    DemoProvider,
    OpenAICompatibleProvider,
    ProviderError,
)
from greensearch.session import Session

# The demo runs the same six topics the site demo covers, plus one
# uncovered topic to show the honest generic fallback. It always uses
# the offline demo provider, so it works with no key and no network.
DEMO_PROMPTS = [
    ("email", "Write a polite follow-up email to a client who missed our call"),
    ("API", "Explain APIs to a 10-year-old"),
    ("workout", "Give me a 3-day workout plan for beginners at home"),
    ("backup", "Summarize why backups matter for a small office"),
    ("firewall", "Explain what a portcullis firewall does and why a small business should care, in plain English"),
    ("DNS", "Explain DNS simply"),
    ("generic", "Explain quantum computing simply"),
]


def _load_session(session_file):
    """Return (session, error_message_or_None) for a session file."""
    if not session_file:
        return Session(), None
    try:
        return Session.load(session_file), None
    except ValueError as exc:
        return None, str(exc)
    except OSError as exc:
        return None, f"Could not read session file {session_file}: {exc}"


def _save_session(session, session_file):
    """Return an error message or None after persisting a session."""
    if not session_file:
        return None
    try:
        session.save(session_file)
    except OSError as exc:
        return f"Could not write session file {session_file}: {exc}"
    return None


def _write_report(session, report_out):
    """Return an error message or None after writing a report."""
    if not report_out:
        return None
    try:
        with open(report_out, "w") as handle:
            handle.write(session.markdown_report())
    except OSError as exc:
        return f"Could not write report {report_out}: {exc}"
    return None


def _run_one(provider, session, prompt, mode):
    """Run one prompt through a provider, record it, and print it.

    Returns an error message or None.
    """
    try:
        raw = provider.complete(prompt)
    except (ValueError, ProviderError) as exc:
        return str(exc)
    answer = apply_brevity(raw, mode)
    fp = footprint(est_tokens(answer), mode)
    session.record(prompt, answer, mode, fp)
    print(f"[{provider.name} | mode: {mode}]\n")
    print(answer)
    print(
        f"\nTokens: {fp['eco_tokens']} vs {fp['standard_tokens']} standard (est.) | "
        f"CO2e: {fp['eco_co2_g']}g vs {fp['standard_co2_g']}g (est.) | "
        f"Saved: {fp['saved_pct']}% / {fp['saved_co2_g']}g (est.)"
    )
    return None


def _run_demo(session, mode):
    """Run the offline demo: all six topics plus a generic fallback."""
    provider = DemoProvider()
    print("[demo (offline) | GreenSearch demo]\n")
    print(
        "Six templated topics, plus one uncovered topic to show the "
        "honest fallback. No key, no network, no model.\n"
    )
    for topic, prompt in DEMO_PROMPTS:
        print(f"--- {topic}: {prompt}")
        error = _run_one(provider, session, prompt, mode)
        if error:
            return error
        print()
    totals = session.totals
    print(
        f"Demo totals: {totals['calls']} calls | Eco tokens: "
        f"{totals['eco_tokens']} | Standard tokens (est.): "
        f"{totals['standard_tokens']} | CO2e saved (est.): "
        f"{totals['saved_co2_g']} g"
    )
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="GreenSearch: concise answers, estimated footprint.")
    parser.add_argument("prompt", nargs="?", default=None,
                        help="Prompt to answer (omit with --demo)")
    parser.add_argument("--mode", choices=["sprout", "canopy", "full"], default="full")
    parser.add_argument("--provider", choices=["demo", "live"], default="demo")
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--report-out", default=None,
                        help="Write a markdown session report to this path")
    parser.add_argument("--session-file", default=None,
                        help="JSON file to persist session calls across runs")
    parser.add_argument("--demo", action="store_true",
                        help="Run the offline demo (all topics, no key needed)")
    args = parser.parse_args(argv)

    if args.demo:
        session, error = _load_session(args.session_file)
        if error:
            print(f"Error: {error}", file=sys.stderr)
            return 2
        error = _run_demo(session, args.mode)
        if error:
            print(f"Error: {error}", file=sys.stderr)
            return 2
        error = _save_session(session, args.session_file)
        if error:
            print(f"Error: {error}", file=sys.stderr)
            return 2
        print("\nNote: CO2e figures are estimates from token counts, not measurements.")
        error = _write_report(session, args.report_out)
        if error:
            print(f"Error: {error}", file=sys.stderr)
            return 2
        if args.report_out:
            print(f"Report written to {args.report_out}")
        return 0

    if not args.prompt:
        print("Error: a prompt is required unless --demo is given", file=sys.stderr)
        return 2

    if args.provider == "demo":
        provider = DemoProvider()
    else:
        try:
            provider = OpenAICompatibleProvider(args.base_url, model=args.model)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    session, error = _load_session(args.session_file)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    error = _run_one(provider, session, args.prompt, args.mode)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    error = _save_session(session, args.session_file)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    print("\nNote: CO2e figures are estimates from token counts, not measurements.")
    if args.session_file:
        totals = session.totals
        print(
            f"Session totals: {totals['calls']} calls | Eco tokens: "
            f"{totals['eco_tokens']} | CO2e saved (est.): {totals['saved_co2_g']} g"
        )
    error = _write_report(session, args.report_out)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    if args.report_out:
        print(f"Report written to {args.report_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
