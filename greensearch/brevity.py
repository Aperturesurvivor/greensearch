"""Brevity layer: trim a draft answer to a sentence budget.

Clause-level only. Whole filler sentences are dropped; words are never
deleted from inside a sentence, because that garbles meaning.

Structure is preserved: paragraph breaks, single line breaks, list items,
fenced code blocks, an email "Subject:" line and a sign-off all survive
trimming. List items and code blocks each count as one unit of the budget.
"""

import re

BUDGETS = {"sprout": 2, "canopy": 4, "full": 6}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_ABBREVIATIONS = {
    "e.g.", "i.e.", "etc.", "vs.", "dr.", "mr.", "mrs.", "ms.", "prof.",
    "st.", "inc.", "ltd.", "approx.", "fig.", "no.",
}
_LIST_ITEM = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+")
_FREE_HEADER = re.compile(r"^\s*(?:subject|re)\s*:", re.IGNORECASE)
_SIGN_OFF = re.compile(
    r"^\s*(?:thanks|thank you|best|best regards|regards|kind regards|"
    r"sincerely|cheers)\s*[,.!]?\s*$",
    re.IGNORECASE,
)
_FENCE = re.compile(r"```.*?```", re.DOTALL)

# Whole filler sentences. A sentence is dropped only if it matches in full,
# so "Please let me know if you have any questions about the report." is
# kept intact instead of being cut down to "about the report."
_FILLER_SENTENCES = [
    r"i hope you(?: are|'re) doing well[.!]?",
    r"please let me know if you have any questions[.!]?",
    r"thanks so much for reaching out[.!]?",
    r"thank you so much in advance[.!]?",
]
_FILLER_FULL = [re.compile(p, re.IGNORECASE) for p in _FILLER_SENTENCES]
_FILLER_LEAD = re.compile(r"^as an ai language model,\s*", re.IGNORECASE)


def split_sentences(text):
    """Split text into sentences, dropping empties.

    Does not split after common abbreviations ("e.g.", "Dr.") or a single
    capital initial, nor before a lowercase letter.
    """
    pieces = [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]
    merged = []
    for piece in pieces:
        if merged:
            last_token = merged[-1].split()[-1].lower()
            is_initial = re.fullmatch(r"[A-Z]\.", merged[-1].split()[-1]) is not None
            if (
                last_token in _ABBREVIATIONS
                or is_initial
                or piece[0].islower()
            ):
                merged[-1] = merged[-1] + " " + piece
                continue
        merged.append(piece)
    return merged


def _is_filler(sentence):
    return any(p.fullmatch(sentence.strip()) for p in _FILLER_FULL)


def _clean_sentence(sentence):
    """Drop a leading 'As an AI language model,' and re-capitalise."""
    out = _FILLER_LEAD.sub("", sentence)
    if out != sentence and out:
        out = out[0].upper() + out[1:]
    return out


def strip_filler_clauses(text):
    """Remove whole filler sentences, keeping line structure."""
    lines_out = []
    for line in text.split("\n"):
        if _LIST_ITEM.match(line) or not line.strip():
            lines_out.append(line.rstrip())
            continue
        kept = [
            _clean_sentence(s)
            for s in split_sentences(re.sub(r"[ \t]+", " ", line))
            if not _is_filler(s)
        ]
        lines_out.append(" ".join(kept))
    return "\n".join(lines_out).strip()


def _paragraph_units(paragraph):
    """Return a paragraph as a list of lines, each a list of
    (text, counts_toward_budget) units."""
    lines = []
    after_sign_off = False
    for line in paragraph.split("\n"):
        if not line.strip():
            continue
        if after_sign_off and len(line.split()) <= 4 and not re.search(r"[.!?]$", line.strip()):
            # The signer's name under "Thanks," belongs to the sign-off.
            lines.append([(line.strip(), False, "keep")])
            after_sign_off = False
            continue
        after_sign_off = bool(_SIGN_OFF.match(line))
        if _LIST_ITEM.match(line):
            lines.append([(line.rstrip(), True, "\n")])
        elif _FREE_HEADER.match(line) or _SIGN_OFF.match(line):
            lines.append([(line.strip(), False, "\n")])
        else:
            cleaned = strip_filler_clauses(line)
            units = [(s, True, " ") for s in split_sentences(cleaned)]
            if units:
                lines.append(units)
    return lines


def apply_brevity(text, mode="full"):
    """Return text trimmed to the mode's sentence budget.

    Raises ValueError on an unknown mode or non-string input. Never
    returns a half-sentence, and never splits a fenced code block.
    """
    if mode not in BUDGETS:
        raise ValueError(
            f"unknown mode {mode!r}; expected one of {sorted(BUDGETS)}"
        )
    if not isinstance(text, str):
        raise ValueError("answer text must be a string")

    # Swap code fences for placeholders so they stay whole.
    fences = []

    def _stash(match):
        fences.append(match.group(0))
        return f"\x00{len(fences) - 1}\x00"

    protected = _FENCE.sub(_stash, text)
    paragraphs = [
        p.strip() for p in re.split(r"\n\s*\n", protected.strip()) if p.strip()
    ]

    remaining = BUDGETS[mode]
    out_paragraphs = []
    for paragraph in paragraphs:
        kept_lines = []
        for line in _paragraph_units(paragraph):
            kept_units = []
            for unit_text, counts, _sep in line:
                if counts:
                    if remaining <= 0:
                        break
                    remaining -= 1
                elif remaining <= 0 and _sep != "keep" and not _SIGN_OFF.match(unit_text):
                    # Free header: keep only while there is budget left.
                    break
                kept_units.append(unit_text)
            if kept_units:
                kept_lines.append(" ".join(kept_units))
        if kept_lines:
            out_paragraphs.append("\n".join(kept_lines))

    result = "\n\n".join(out_paragraphs)
    for i, block in enumerate(fences):
        result = result.replace(f"\x00{i}\x00", block)
    return result
