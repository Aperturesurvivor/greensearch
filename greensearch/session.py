"""Session savings tracker: records calls and exports a markdown report.

A Session is in-memory by default. Pass a JSON file to the CLI with
``--session-file`` and calls persist across runs, so totals accumulate
instead of resetting to one call per invocation (the pre-Step-2
behaviour). The file format is ``{"version": 1, "calls": [...]}``; a
missing file means an empty session, while a present-but-invalid file
is an error, not silently discarded data.
"""

import datetime
import json
import os
import tempfile

from greensearch.cache import SessionCache

_REQUIRED_CALL_KEYS = (
    "prompt",
    "answer",
    "mode",
    "eco_tokens",
    "standard_tokens",
    "saved_pct",
    "saved_co2_g",
)


class Session:
    """Accumulates one wrapper session's calls and footprint totals."""

    def __init__(self, calls=None, cache=None):
        self.calls = list(calls) if calls else []
        self.cache = cache if cache is not None else SessionCache()

    def record(self, prompt, answer, mode, footprint):
        self.calls.append(
            {"prompt": prompt, "answer": answer, "mode": mode, **footprint}
        )

    @property
    def totals(self):
        return {
            "calls": len(self.calls),
            "cache_hits": sum(1 for c in self.calls if c.get("cache_hit")),
            "input_saved_tokens": sum(c.get("shrink_saved_tokens", 0) for c in self.calls),
            "eco_tokens": sum(c["eco_tokens"] for c in self.calls),
            "standard_tokens": sum(c["standard_tokens"] for c in self.calls),
            "saved_co2_g": round(sum(c["saved_co2_g"] for c in self.calls), 4),
        }

    def to_dict(self):
        # "cache" is new in this version; old readers ignore unknown keys,
        # and from_dict treats a missing cache as empty, so old files load.
        return {"version": 1, "calls": self.calls, "cache": self.cache.to_dict()}

    @classmethod
    def from_dict(cls, data, path="<session>"):
        if not isinstance(data, dict) or not isinstance(data.get("calls"), list):
            raise ValueError(
                f"Session file {path} is not valid: expected an object "
                f"with a 'calls' list."
            )
        for i, call in enumerate(data["calls"]):
            if not isinstance(call, dict) or any(
                key not in call for key in _REQUIRED_CALL_KEYS
            ):
                raise ValueError(
                    f"Session file {path} is not valid: call {i + 1} is "
                    f"missing required fields."
                )
        return cls(calls=data["calls"], cache=SessionCache.from_dict(data.get("cache")))

    def save(self, path):
        """Write this session to a JSON file. Raises OSError on failure."""
        # Write to a temp file in the same folder, then swap it in, so a
        # crash mid-write cannot leave a half-written session file.
        directory = os.path.dirname(os.path.abspath(path))
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".session-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(self.to_dict(), handle, indent=2)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, path):
        """Load a session from a JSON file, or return an empty session
        if the file does not exist. Raises ValueError for invalid content
        and OSError for unreadable files."""
        try:
            with open(path) as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return cls()
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Session file {path} is not valid JSON: {exc}"
            ) from exc
        return cls.from_dict(data, path=path)

    def markdown_report(self):
        totals = self.totals
        lines = [
            "# GreenSearch session report",
            "",
            f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}",
            "",
            f"Calls: {totals['calls']} (cache hits: {totals['cache_hits']}) | "
            f"Input tokens saved by PromptShrink: {totals['input_saved_tokens']} | "
            f"Output eco tokens: {totals['eco_tokens']} | "
            f"Output standard tokens (est.): {totals['standard_tokens']} | "
            f"CO2e saved (est.): {totals['saved_co2_g']} g",
            "",
        ]
        for i, call in enumerate(self.calls, 1):
            lines += [
                f"## Call {i} (mode: {call['mode']}{' , cache hit' if call.get('cache_hit') else ''})",
                f"Prompt: {call['prompt']}",
                "",
                f"Answer: {call['answer']}",
                "",
                (f"PromptShrink: saved {call['shrink_saved_tokens']} input tokens" 
                if call.get("shrink_saved_tokens") else "PromptShrink: no change"),
                f"Output: {call['eco_tokens']} vs {call['standard_tokens']} "
                f"standard ({call.get('baseline_kind', 'assumed')}), saved {call['saved_pct']}% / "
                f"{call['saved_co2_g']} g CO2e (est.)",
                "",
            ]
        return "\n".join(lines)
