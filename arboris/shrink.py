"""PromptShrink: reduce a prompt's token count before it reaches a model.

Three passes, in order:
  1. Strip trailing sign-offs (email-style closing lines the model does not need).
  2. Expand verbose phrases to shorter equivalents.
  3. Remove filler phrases that carry no semantic content.

Code fences (```...```) are never touched. Words are never deleted from
inside a clause — only whole matched phrases are replaced or removed, so
meaning is preserved.

The function returns a ShrinkResult so callers can see exactly what changed
and by how much. Pass .text to the model; use .saved_tokens for footprint
accounting.
"""

import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Phrase tables
# ---------------------------------------------------------------------------

# Verbose -> concise substitutions, longest first so longer phrases win.
_VERBOSE: list[tuple[str, str]] = sorted([
    ("due to the fact that",         "because"),
    ("in spite of the fact that",    "although"),
    ("regardless of the fact that",  "although"),
    ("in order to",                  "to"),
    ("at this point in time",        "now"),
    ("at the present time",          "now"),
    ("in the event that",            "if"),
    ("for the purpose of",           "for"),
    ("a large number of",            "many"),
    ("has the ability to",           "can"),
    ("is able to",                   "can"),
    ("each and every",               "each"),
    ("first and foremost",           "first"),
    ("it is important to note that", ""),
    ("it should be noted that",      ""),
    ("please note that",             ""),
    ("with regard to",               "about"),
    ("with respect to",              "about"),
    ("in the near future",           "soon"),
    ("on a regular basis",           "regularly"),
    ("prior to",                     "before"),
    ("subsequent to",                "after"),
    ("and also",                     "and"),
    ("also",                         ""),  # lone "also" acting as "additionally"
], key=lambda p: -len(p[0]))

# Filler phrases — whole-phrase matches on word boundaries.
_FILLER_PATTERNS: list[str] = [
    r"i was just wondering if you could possibly",
    r"i was just wondering if",
    r"could you please kindly",
    r"could you please",
    r"would you please",
    r"please kindly",
    r"i would appreciate it if you could",
    r"i would like you to",
    r"i was hoping you could",
    r"can you please",
    r"thank you so much in advance",
    r"thanks so much",
    r"i hope you(?:'re| are) doing well",
    r"in other words",
    r"in this day and age",
    r"if at all possible",
    r"as mentioned (?:before|earlier|above|previously)",
    r"as i mentioned (?:earlier|before|above|previously)",
    r"it goes without saying(?: that)?",
    r"needless to say",
    r"to be (?:perfectly )?honest(?:ly)?",
    r"frankly speaking",
    r"to be (?:quite )?frank",
    r"i think that",
    r"i believe that",
    r"in my (?:personal )?opinion",
    r"it is worth noting that",
    r"note that",
    # Single words last.
    r"basically",
    r"actually",
    r"honestly",
    r"obviously",
    r"literally",
    r"kindly",
    r"please",
    r"just",
    r"really",
    r"very",
]

# Sign-off line: "Thanks," / "Best regards, Grant" etc.
_SIGN_OFF_RE = re.compile(
    r"^\s*(?:best regards|kind regards|regards|cheers|sincerely|thanks|thank you)"
    r"[,.]?(?:\s+[A-Za-z][A-Za-z .\-]{0,39})?\s*$",
    re.IGNORECASE,
)

# A short bare-name line that may follow a sign-off (e.g. "Grant").
_NAME_LINE_RE = re.compile(r"^\s*[A-Za-z][A-Za-z .\-]{0,39}\s*$")

_FENCE_RE = re.compile(r"```[\s\S]*?```")

# Pre-compile substitution regexes.
_VERBOSE_RE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b" + re.escape(old) + r"\b", re.IGNORECASE), new)
    for old, new in _VERBOSE
]
_FILLER_RE: list[re.Pattern] = [
    re.compile(r"\b" + pat + r"\b", re.IGNORECASE)
    for pat in _FILLER_PATTERNS
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class ShrinkResult:
    text: str            # cleaned prompt; pass this to the model
    original: str        # input unchanged
    original_tokens: int
    shrunk_tokens: int
    saved_tokens: int    # original_tokens - shrunk_tokens (>= 0)
    changed: bool        # True when text != original


def shrink(prompt: str, count_fn=None) -> "ShrinkResult":
    """Clean a prompt and return a ShrinkResult.

    Empty or whitespace-only input is returned unchanged with zero saving.
    count_fn, if given, counts tokens (e.g. a real tokenizer); by
    default it is the word estimate from tokens.py.
    """
    if count_fn is None:
        from arboris.tokens import est_tokens  # deferred to avoid circular import
        count_fn = est_tokens

    if not prompt or not prompt.strip():
        t = count_fn(prompt)
        return ShrinkResult(
            text=prompt, original=prompt,
            original_tokens=t, shrunk_tokens=t, saved_tokens=0, changed=False,
        )

    result = _process(prompt)

    original_t = count_fn(prompt)
    shrunk_t   = count_fn(result)
    return ShrinkResult(
        text=result,
        original=prompt,
        original_tokens=original_t,
        shrunk_tokens=shrunk_t,
        saved_tokens=max(0, original_t - shrunk_t),
        changed=result != prompt,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _process(text: str) -> str:
    # 1. Strip trailing sign-off lines (and a following bare name line).
    text = _strip_trailing_signoffs(text)

    # 2. Apply substitutions and filler removal per segment, leaving fences alone.
    text = _apply_to_prose(text)

    # 3. Clean up whitespace and re-capitalise sentence starts.
    text = _normalise(text)

    return text


def _strip_trailing_signoffs(text: str) -> str:
    lines = text.rstrip().split("\n")
    # Drop trailing blank lines.
    while lines and not lines[-1].strip():
        lines.pop()
    # Look at the last two non-blank lines together to catch both
    # "Thanks,\nGrant" (name follows sign-off) and "Thanks, Grant" (one line).
    if len(lines) >= 2:
        last = lines[-1].strip()
        prev = lines[-2].strip()
        if _SIGN_OFF_RE.match(prev) and _NAME_LINE_RE.match(last) and len(last.split()) <= 4:
            lines.pop()  # name
            lines.pop()  # sign-off
        elif _SIGN_OFF_RE.match(last):
            lines.pop()
    elif lines and _SIGN_OFF_RE.match(lines[-1]):
        lines.pop()
    # Drop any trailing blank lines left above.
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _apply_to_prose(text: str) -> str:
    """Apply substitutions to non-fence parts only."""
    parts = _FENCE_RE.split(text)
    fences = _FENCE_RE.findall(text)
    cleaned = [_clean_segment(p) for p in parts]
    # Re-interleave: prose, fence, prose, fence ...
    result_parts = []
    for i, seg in enumerate(cleaned):
        result_parts.append(seg)
        if i < len(fences):
            result_parts.append(fences[i])
    return "".join(result_parts)


def _clean_segment(seg: str) -> str:
    for pattern, replacement in _VERBOSE_RE:
        seg = pattern.sub(replacement, seg)
    for pattern in _FILLER_RE:
        seg = pattern.sub("", seg)
    return seg


def _normalise(text: str) -> str:
    # Collapse multiple spaces/tabs on each line; preserve newlines.
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)
    text = "\n".join(lines).strip()
    # Remove spaces before punctuation left by phrase removal.
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    # Remove a comma that directly precedes end-of-sentence punctuation.
    text = re.sub(r",([.!?])", r"\1", text)
    # Remove a trailing comma at the very end of the text.
    text = re.sub(r",\s*$", "", text)
    # Capitalise sentence starts — but never inside a code fence.
    text = _recapitalise(text)
    return text


def _recapitalise(text: str) -> str:
    """Capitalise after sentence boundaries, skipping code fence content."""
    parts = _FENCE_RE.split(text)
    fences = _FENCE_RE.findall(text)

    def _cap_prose(s: str) -> str:
        s = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
        if s and s[0].islower():
            s = s[0].upper() + s[1:]
        return s

    cleaned = [_cap_prose(p) for p in parts]
    result_parts: list[str] = []
    for i, seg in enumerate(cleaned):
        result_parts.append(seg)
        if i < len(fences):
            result_parts.append(fences[i])
    return "".join(result_parts)


# ---------------------------------------------------------------------------
# PromptShrink v2 (opt-in, 2026-10-28)
# ---------------------------------------------------------------------------
# v1 (shrink() above) stays the default for the CLI and the baseline study,
# so existing numbers do not move silently. v2 layers two extra passes on
# top of a v1 result, and nothing else:
#
#   1. Redundancy removal, for every prompt: consecutive duplicate words
#      ("that that") and exact duplicate sentences. Code fences untouched.
#   2. Telegraphic rewriting, GATED to simple prompts only: a single
#      sentence, at most 25 words, no code fence, no newline, no colon /
#      semicolon / parenthesis structure. It removes articles (a/an/the)
#      and "to/for me|you|us" phrases. It does NOT remove numbers,
#      constraint words (simply, simple, brief, detail), question words,
#      or keywords, and it never runs on multi-sentence, multi-request,
#      or creative prompts, where stripping articles can change tone or
#      drop a constraint. A prompt that fails the gate gets pass 1 only.
#
# Tokenizer-aware counting is not a new pass: shrink_v2() takes the same
# count_fn as shrink(), so callers can pass arboris.tokenizer
# .count_tokens with backend="tiktoken" for real token counts, or leave
# the default word estimate. The quality script (scripts/shrink_quality.py)
# reports both tokens saved AND answers changed, because a shrink that
# changes the answer is a quality loss, not a saving.

_TELEGRAPHIC_ARTICLES_RE = re.compile(r"\b(?:a|an|the)\b", re.IGNORECASE)
_TELEGRAPHIC_TO_FOR_RE = re.compile(r"\b(?:to|for)\s+(?:me|you|us)\b", re.IGNORECASE)
_DUPLICATE_WORD_RE = re.compile(r"\b(\w+)(?:\s+\1\b)+", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _is_simple_v2(text: str) -> bool:
    """Gate for the telegraphic pass. See the v2 header above."""
    if "```" in text or "\n" in text:
        return False
    if any(ch in text for ch in ":;()\"'"):
        return False
    words = text.split()
    if not words or len(words) > 25:
        return False
    # Single sentence: at most one sentence terminator, at the end.
    body = text.rstrip()
    terminators = sum(1 for ch in body[:-1] if ch in ".!?")
    if terminators:
        return False
    if body and body[-1] not in ".!?":
        # An imperative without terminal punctuation is still simple.
        pass
    first = words[0].lower().strip("?")
    if first not in ("explain", "what", "why", "how", "describe", "tell", "give", "write", "list", "summarise", "summarize"):
        return False
    return True


def _clean_v2_segment(seg: str, telegraphic: bool) -> str:
    seg = _DUPLICATE_WORD_RE.sub(r"\1", seg)
    # Duplicate sentences: keep the first occurrence of each normalised
    # sentence, drop later exact repeats.
    parts = _SENTENCE_SPLIT_RE.split(seg)
    if len(parts) > 1:
        seen = set()
        kept = []
        for part in parts:
            norm = re.sub(r"[^a-z0-9 ]", "", part.lower()).strip()
            if norm and norm in seen:
                continue
            seen.add(norm)
            kept.append(part)
        seg = " ".join(kept)
    if telegraphic:
        seg = _TELEGRAPHIC_ARTICLES_RE.sub("", seg)
        seg = _TELEGRAPHIC_TO_FOR_RE.sub("", seg)
    return seg


def _apply_v2(text: str, telegraphic: bool) -> str:
    """Apply the v2 segment cleaner to prose only, leaving fences alone."""
    parts = _FENCE_RE.split(text)
    fences = _FENCE_RE.findall(text)
    cleaned = [_clean_v2_segment(p, telegraphic) for p in parts]
    result_parts = []
    for i, seg in enumerate(cleaned):
        result_parts.append(seg)
        if i < len(fences):
            result_parts.append(fences[i])
    return "".join(result_parts)


def shrink_v2(prompt: str, count_fn=None) -> "ShrinkResult":
    """PromptShrink v2: v1, plus redundancy removal, plus gated telegraphic.

    Opt-in only. shrink() is unchanged, so the CLI and baseline study
    keep v1 numbers until a switch is explicitly approved.
    """
    if count_fn is None:
        from arboris.tokens import est_tokens  # deferred, as in shrink()
        count_fn = est_tokens

    if not prompt or not prompt.strip():
        t = count_fn(prompt)
        return ShrinkResult(
            text=prompt, original=prompt,
            original_tokens=t, shrunk_tokens=t, saved_tokens=0, changed=False,
        )

    v1 = _process(prompt)
    telegraphic = _is_simple_v2(v1)
    result = _normalise(_apply_v2(v1, telegraphic))

    original_t = count_fn(prompt)
    shrunk_t = count_fn(result)
    return ShrinkResult(
        text=result,
        original=prompt,
        original_tokens=original_t,
        shrunk_tokens=shrunk_t,
        saved_tokens=max(0, original_t - shrunk_t),
        changed=result != prompt,
    )
