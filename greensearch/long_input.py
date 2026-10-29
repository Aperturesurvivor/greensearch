"""Conservative extractive pruning for long inputs (brief #6).

For a typical 20-token chat prompt, input shrink is negligible
energy and PromptShrink is enough. For a pasted document, prefill
and KV cost start to matter, and generic word deletion is the wrong
tool: it can drop negations, numbers, and identifiers. This module
is the long-input option only, and it is deliberately conservative:

- It only runs on prompts longer than max_chars (default 1500).
- It splits on sentence boundaries, with fenced code blocks kept
  whole and never dropped.
- It always keeps the first and last sentences.
- It keeps any sentence containing a digit, a question mark, a
  quoted string, or a capitalized word in the middle of the sentence
  (a rough proper-noun signal). Those are the sentences most likely
  to carry facts, constraints, or the actual question.
- Other sentences are dropped, in original order, until the kept
  text fits keep_chars (default 1000), or all other sentences are
  dropped and the kept text still exceeds the budget, in which
  case kept sentences are dropped from the middle outward (never
  first, last, or code) until it fits.
- The returned text ends with a pruning note, so the model knows
  input was pruned and does not hallucinate the missing part as
  if it had seen it.

Returns (pruned_text, dropped_count, original_chars). Short prompts
return unchanged, with dropped_count 0. Nothing here is a learned
summarizer: it is an extractive baseline, and its limits are stated
so it is not sold as understanding the document.
"""

import re

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PROPER_NOUN = re.compile(r"\b[A-Z][a-z]{2,}\b")
_QUOTED = re.compile(r'["\'].*?["\']')


def _split_sentences(text):
    parts = []
    for chunk in _SENTENCE_SPLIT.split(text.strip()):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


def _is_code(placeholder_map, sentence):
    return any(key in sentence for key in placeholder_map)


def _keep_sentence(sentence, placeholder_map):
    if _is_code(placeholder_map, sentence):
        return True
    if any(ch.isdigit() for ch in sentence):
        return True
    if "?" in sentence:
        return True
    if _QUOTED.search(sentence):
        return True
    # A capitalized word after the first word: a rough proper noun.
    words = sentence.split()
    if len(words) > 1 and any(_PROPER_NOUN.fullmatch(w.strip(".,;:!?()\"'")) for w in words[1:]):
        return True
    return False


def prune_long_prompt(prompt, max_chars=1500, keep_chars=1000):
    """Prune a long prompt, or return it unchanged if it is short.

    Returns (text, dropped_count, original_chars).
    """
    original_chars = len(prompt)
    if original_chars <= max_chars:
        return prompt, 0, original_chars
    # Stash code fences so they are never split or dropped.
    fences = {}

    def _stash(match):
        key = f"\x00FENCE{len(fences)}\x00"
        fences[key] = match.group(0)
        return key

    protected = _FENCE.sub(_stash, prompt)
    sentences = _split_sentences(protected)
    if len(sentences) <= 2:
        return prompt, 0, original_chars
    kept = []
    dropped = 0
    for i, sentence in enumerate(sentences):
        if i == 0 or i == len(sentences) - 1 or _keep_sentence(sentence, fences):
            kept.append(sentence)
        else:
            dropped += 1
    # If the kept set still exceeds the budget, drop from the middle
    # outward, never first, last, or code.
    while kept and sum(len(s) + 1 for s in kept) > keep_chars and len(kept) > 2:
        middle = len(kept) // 2
        # Find the nearest droppable sentence at or after the middle.
        idx = None
        for j in range(middle, len(kept) - 1):
            if not _is_code(fences, kept[j]):
                idx = j
                break
        if idx is None:
            break
        kept.pop(idx)
        dropped += 1
    text = " ".join(kept)
    for key, block in fences.items():
        text = text.replace(key, block)
    if dropped:
        text += (f"\n\n[Pruned for efficiency: {dropped} sentence(s) dropped "
                 "from a long input; numbers, names, questions, and code "
                 "were kept.]")
    return text, dropped, original_chars
