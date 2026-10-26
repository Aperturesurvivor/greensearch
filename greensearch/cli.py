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
from greensearch.shrink import shrink
from greensearch.tokens import est_tokens
from greensearch.footprint import GRID_G_PER_KWH, WH_PER_TOKEN, footprint
from greensearch.router import route_mode
from greensearch.providers import (
    BREVITY_SYSTEM,
    MAX_TOKENS,
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


def _run_one(provider, session, prompt, mode_arg, opts=None):
    """Run one prompt through a provider, record it, and print it.

    Returns an error message or None.

    Two-sided accounting:
      Input side:  PromptShrink trims the prompt; saved_input_tokens is the
                   difference, credited before any model call.
      Output side: the model receives the shrunk prompt. If live and
                   constrained (default), a system-prompt + max_tokens cap
                   limits generation. The footprint uses provider-reported
                   token counts when available.
    """
    opts = opts or {}

    # --- Input side: shrink the prompt ---
    sr = shrink(prompt)
    shrunk_prompt = sr.text
    mode = route_mode(shrunk_prompt) if mode_arg == "auto" else mode_arg
    mode_label = f"{mode} (auto)" if mode_arg == "auto" else mode
    live = getattr(provider, "live", False)
    constrain = live and not opts.get("no_constrain")

    # --- Output side: call the model ---
    try:
        comp = provider.complete_ex(
            shrunk_prompt,
            system=BREVITY_SYSTEM[mode] if constrain else None,
            max_tokens=MAX_TOKENS[mode] if constrain else None,
        )
        base = None
        if opts.get("measure_baseline"):
            base = provider.complete_ex(prompt) if live else provider.complete_ex(prompt)
    except (ValueError, ProviderError) as exc:
        return str(exc)

    answer = apply_brevity(comp.text, mode)

    # Token accounting: use provider counts when available; fall back to estimates.
    # Never mix counted and estimated in the same comparison.
    out_tokens = est_tokens(answer)
    baseline_tokens = None
    if comp.completion_tokens is not None:
        out_tokens = comp.completion_tokens
    if base is not None:
        if base.completion_tokens is not None and comp.completion_tokens is not None:
            baseline_tokens = base.completion_tokens
        else:
            out_tokens = est_tokens(answer)
            baseline_tokens = est_tokens(base.text)

    fp = footprint(
        out_tokens, mode,
        baseline_tokens=baseline_tokens,
        wh_per_token=opts.get("wh_per_token", WH_PER_TOKEN),
        grid_g_per_kwh=opts.get("grid_g_per_kwh", GRID_G_PER_KWH),
    )
    # Attach input-side saving to the footprint dict so it travels to the report.
    fp["shrink_saved_tokens"] = sr.saved_tokens
    fp["shrink_original_tokens"] = sr.original_tokens
    fp["shrink_changed"] = sr.changed

    session.record(prompt, answer, mode, fp)
    print(f"[{provider.name} | mode: {mode_label}]\n")
    print(answer)

    # Print a clear two-line breakdown: input side then output side.
    if sr.changed:
        print(
            f"\nPromptShrink: {sr.original_tokens} → {sr.shrunk_tokens} input tokens "
            f"(saved {sr.saved_tokens})"
        )
    else:
        print(f"\nPromptShrink: no change ({sr.original_tokens} input tokens)")
    print(
        f"Output: {fp['eco_tokens']} vs {fp['standard_tokens']} standard "
        f"({fp['baseline_kind']} baseline) | "
        f"CO2e: {fp['eco_co2_g']}g vs {fp['standard_co2_g']}g (est.) | "
        f"Saved: {fp['saved_pct']}% / {fp['saved_co2_g']}g (est.)"
    )
    if fp["baseline_kind"] == "assumed":
        print("  (assumed baseline: saved % depends only on mode, not content;",
              "use --measure-baseline for a real comparison)")
    return None


def _run_demo(session, mode, opts=None):
    """Run the offline demo: all six topics plus a generic fallback."""
    provider = DemoProvider()
    print("[demo (offline) | GreenSearch demo]\n")
    print(
        "Six templated topics, plus one uncovered topic to show the "
        "honest fallback. No key, no network, no model.\n"
    )
    for topic, prompt in DEMO_PROMPTS:
        print(f"--- {topic}: {prompt}")
        error = _run_one(provider, session, prompt, mode, opts)
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
    parser.add_argument("--mode", choices=["sprout", "canopy", "full", "auto"], default="full",
                        help="Answer length; auto picks one from the prompt")
    parser.add_argument("--provider", choices=["demo", "live"], default="demo")
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--report-out", default=None,
                        help="Write a markdown session report to this path")
    parser.add_argument("--session-file", default=None,
                        help="JSON file to persist session calls across runs")
    parser.add_argument("--measure-baseline", action="store_true",
                        help="Compare against a real unconstrained reply (live: one extra API call)")
    parser.add_argument("--no-constrain", action="store_true",
                        help="Live: do not ask for a short answer; generate in full, then trim")
    parser.add_argument("--wh-per-token", type=float, default=WH_PER_TOKEN,
                        help="Assumed energy per generated token, in Wh (default %(default)s)")
    parser.add_argument("--grid-g-per-kwh", type=float, default=GRID_G_PER_KWH,
                        help="Assumed grid intensity, g CO2e per kWh (default %(default)s)")
    parser.add_argument("--demo", action="store_true",
                        help="Run the offline demo (all topics, no key needed)")
    args = parser.parse_args(argv)
    if args.wh_per_token <= 0 or args.grid_g_per_kwh <= 0:
        print("Error: --wh-per-token and --grid-g-per-kwh must be positive", file=sys.stderr)
        return 2
    opts = {
        "measure_baseline": args.measure_baseline,
        "no_constrain": args.no_constrain,
        "wh_per_token": args.wh_per_token,
        "grid_g_per_kwh": args.grid_g_per_kwh,
    }

    if args.demo:
        session, error = _load_session(args.session_file)
        if error:
            print(f"Error: {error}", file=sys.stderr)
            return 2
        if args.prompt:
            print("Note: --demo ignores the prompt you gave.", file=sys.stderr)
        error = _run_demo(session, args.mode, opts)
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
    error = _run_one(provider, session, args.prompt, args.mode, opts)
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
