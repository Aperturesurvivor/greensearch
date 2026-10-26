"""Brevity layer: trim a draft answer to a sentence budget.

Clause-level only. We strip whole filler CLAUSES, never words from inside
a clause: deleting words mid-clause garbles meaning (this exact bug bit
PromptShrink v1.2 on the portfolio site, where "I was just wondering if
you could…" was shredded into "I was you could…"). A removed clause
leaves clean sentence boundaries behind.
"""

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Whole clauses that add no information. Each pattern matches a complete
# clause, including its trailing punctuation, so removal cannot strand
# half a sentence.
_FILLER_CLAUSES = [
    r"i hope you are doing well\.?",
    r"please let me know if you have any questions\.?",
    r"thanks so much for reaching out\.?",
    r"thank you so much in advance\.?",
    r"as an ai language model,?",
]

BUDGETS = {"sprout": 2, "canopy": 4, "full": 6}


def split_sentences(text):
    """Split text into sentences, dropping empties."""
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def strip_filler_clauses(text):
    """Remove whole filler clauses, then collapse leftover whitespace."""
    out = text
    for pattern in _FILLER_CLAUSES:
        out = re.sub(pattern, "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def apply_brevity(text, mode="full"):
    """Return text trimmed to the mode's sentence budget.

    Raises ValueError on an unknown mode. Never returns a half-sentence:
    trimming always cuts at sentence boundaries, and paragraph breaks
    are preserved (a multi-paragraph answer like an email keeps its
    shape instead of collapsing into one wall of text).
    """
    if mode not in BUDGETS:
        raise ValueError(
            f"unknown mode {mode!r}; expected one of {sorted(BUDGETS)}"
        )
    paragraphs = [
        p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()
    ]
    remaining = BUDGETS[mode]
    kept = []
    for paragraph in paragraphs:
        if remaining <= 0:
            break
        cleaned = strip_filler_clauses(paragraph)
        sentences = split_sentences(cleaned)
        take = sentences[:remaining]
        remaining -= len(take)
        if take:
            kept.append(" ".join(take))
    return "\n\n".join(kept)
