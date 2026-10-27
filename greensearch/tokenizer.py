"""Real token counting, as an optional extra.

The default estimate (words x 1.33, see tokens.py) is kept as the
default so the harness stays dependency-free and its numbers stay
comparable with the website demo. A real tokenizer is better in two
ways the estimate is not: it splits words into subwords the way a
model does, and it counts unspaced scripts (e.g. Chinese) properly
instead of reporting 1 token for a whole sentence.

Supported backend, for now: tiktoken's cl100k_base encoding (the
GPT-4o family encoding). Install it with:

    pip install 'greensearch[tokenizer]'

If tiktoken is not installed and a caller asks for it, count_tokens
raises TokenizerError instead of silently falling back to the
estimate -- a silent fallback would make a "real tokenizer" number
indistinguishable from an estimate.
"""

from greensearch.tokens import est_tokens


class TokenizerError(Exception):
    """Raised when the requested real tokenizer is unavailable."""


def count_tokens(text, backend="estimate", encoding="cl100k_base"):
    """Count tokens for text.

    backend="estimate": words x 1.33, minimum 1 (the default).
    backend="tiktoken": real tiktoken count; raises TokenizerError
        if tiktoken is not installed, or the encoding is unknown.
    """
    if backend == "estimate":
        return est_tokens(text)
    if backend == "tiktoken":
        try:
            import tiktoken
        except ImportError as exc:
            raise TokenizerError(
                "tiktoken is not installed: pip install 'greensearch[tokenizer]'"
            ) from exc
        try:
            enc = tiktoken.get_encoding(encoding)
        except Exception as exc:
            raise TokenizerError(f"unknown tiktoken encoding {encoding!r}: {exc}") from exc
        return len(enc.encode(text))
    raise TokenizerError(f"unknown tokenizer backend {backend!r}; expected 'estimate' or 'tiktoken'")
