"""FrugalGPT-style answer scoring, kept transparent and cheap.

FrugalGPT (Chen et al., 2023) cascades from cheap to expensive models
and stops when a learned scorer says the current answer is good
enough. Arboris cannot train that scorer: it has no logged outcomes
yet, and a learned scorer would be a black box. So this module is the
transparent version of the same idea:

- No model call. The score is computed locally from the prompt, the
  answer, and (when available) the primary model's own logprobs.
- Every component is named and weighted in the open, so a bad score
  can be argued with and fixed from one example.
- The score is reported in meta on every answer. It only triggers
  escalation when the server is explicitly configured to let it
  (ARBORIS_SCORER_ESCALATION). Otherwise it is a measurement, not
  a decision, and the logprob cascade keeps its old behaviour.

Components (weights sum to 1):
- logprob (0.4): the primary model's mean logprob, mapped linearly
  from -3.0 (0.1) to 0.0 (1.0). If logprobs are unavailable the
  component is neutral (0.5) and flagged, never invented.
- completeness (0.3): ends with terminal punctuation, a code fence,
  or (for math) a digit; a finish_reason of "length" scores 0.2,
  because a cut-off answer is a failure, not a short answer.
- format (0.15): steps answers should list, code answers should
  fence, math answers should contain a digit. Other task types are
  neutral (0.5): no format claim is made about them.
- coverage (0.15): how many of the prompt's content words appear in
  the answer. This is the weakest signal (a good paraphrase can miss
  words, a bad answer can copy them), which is why it is weighted
  lowest. It is a tripwire for answers that ignore the question, not
  a quality judge.

A score below 0.5 is the default escalation trigger when scorer
escalation is on. That threshold is a starting point to tune against
real runs, not a sourced constant.
"""

import re

_STOPWORDS = {
    "what", "which", "where", "when", "who", "how", "why", "is", "are",
    "was", "were", "the", "a", "an", "of", "to", "in", "on", "for",
    "and", "or", "with", "please", "tell", "me", "you", "us", "can",
    "could", "would", "should", "explain", "write", "give", "show",
    "answer", "about", "does", "do", "did", "it", "its", "this", "that",
}

_WORD = re.compile(r"[a-z0-9']+")
_LIST_MARKER = re.compile(r"(?m)^\s*(\d+[.)]|[-*])\s+\S")


def _content_words(prompt):
    return [
        w for w in _WORD.findall(prompt.lower())
        if len(w) >= 4 and w not in _STOPWORDS
    ]


def _logprob_component(avg_logprob):
    if avg_logprob is None:
        return 0.5, True
    score = 1.0 + avg_logprob / 3.0
    return max(0.1, min(1.0, score)), False


def _completeness_component(answer, task_type, finish_reason):
    if finish_reason == "length":
        return 0.2
    tail = answer.rstrip()
    if not tail:
        return 0.0
    last = tail[-1]
    if last in ".!?" or last in "`}]":
        return 1.0
    if task_type == "math" and last.isdigit():
        return 0.9
    return 0.5


def _format_component(answer, task_type):
    if task_type == "steps":
        return 1.0 if _LIST_MARKER.search(answer) else 0.4
    if task_type == "code":
        return 1.0 if "```" in answer else 0.4
    if task_type == "math":
        return 1.0 if any(ch.isdigit() for ch in answer) else 0.3
    return 0.5


def _coverage_component(prompt, answer):
    words = _content_words(prompt)
    if not words:
        return 0.5
    lowered = answer.lower()
    hit = sum(1 for w in words if re.search(r"\b" + re.escape(w) + r"\b", lowered))
    ratio = hit / len(words)
    if ratio >= 0.6:
        return 1.0
    if ratio >= 0.3:
        return 0.6
    return 0.3


def score_answer(prompt, answer, mode="canopy", task_type=None,
                 avg_logprob=None, finish_reason=None):
    """Score an answer. Returns a dict with score, components, reasons."""
    if not answer or not answer.strip():
        return {
            "score": 0.0,
            "components": {"logprob": 0.0, "completeness": 0.0,
                           "format": 0.0, "coverage": 0.0},
            "logprob_unknown": avg_logprob is None,
            "reasons": ["empty answer"],
        }
    logprob, unknown = _logprob_component(avg_logprob)
    completeness = _completeness_component(answer, task_type, finish_reason)
    fmt = _format_component(answer, task_type)
    coverage = _coverage_component(prompt, answer)
    score = round(
        0.4 * logprob + 0.3 * completeness + 0.15 * fmt + 0.15 * coverage, 3
    )
    reasons = []
    if logprob < 0.5:
        reasons.append("low logprob" if not unknown else "logprob unavailable")
    if completeness < 0.5:
        reasons.append("answer looks cut off" if finish_reason == "length"
                       else "answer does not end cleanly")
    if fmt < 0.5:
        reasons.append("expected format missing for task type")
    if coverage < 0.5:
        reasons.append("answer covers few of the prompt's content words")
    return {
        "score": score,
        "components": {"logprob": round(logprob, 3),
                       "completeness": completeness,
                       "format": fmt, "coverage": coverage},
        "logprob_unknown": unknown,
        "reasons": reasons,
    }
