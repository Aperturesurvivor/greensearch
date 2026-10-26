"""Word-based token estimation.

This is an ESTIMATE, not a real tokenizer: production tokenizers split
words into subwords, so true token counts differ. We use words * 1.33,
the same approximation as the portfolio site demo, so the two agree.
"""


def est_tokens(text):
    """Estimate tokens for text. Minimum 1, even for empty input."""
    words = len(text.split())
    return max(1, round(words * 1.33))
