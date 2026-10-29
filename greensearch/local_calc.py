"""No-model gate: answer pure arithmetic without calling a model.

This is the "don't default to the LLM" step from the efficiency
research. A prompt that is only an arithmetic expression has a
deterministic answer; sending it to a 31B model burns tokens, time,
and quota for a result a parser computes exactly, with 0 tokens and
0 estimated energy. FrugalGPT's lesson is the same shape: the cheapest
correct answer wins, and the cheapest correct answer here is not a
model at all.

Rules, deliberately strict so a wrong local answer is impossible by
construction:
- After stripping a leading "what is / calculate / compute / work
  out" and a trailing "?", the prompt must contain no letters at all,
  only digits, spaces, + - * / % ( ) and a decimal point.
- No "**" (exponent), no "//", no exponent notation, parentheses
  must balance, length at most 100 characters.
- Division or modulo by zero falls through to the model (returns
  None), never an error and never a guessed answer.
- Results are formatted as integers when integral, otherwise to
  6 significant digits. That rounding is stated, not hidden: a
  repeating decimal is an approximation, and the answer shows the
  equation so the user can check it.

Anything that fails these rules returns None, and the normal model
pipeline runs unchanged. This module never executes prompt text:
it parses it with a small recursive-descent parser.
"""

import re

_ALLOWED = re.compile(r"^[\d\s+\-*/().%]+$")
_PREFIX = re.compile(r"^(please\s+)?(what is|calculate|compute|work out)\s+", re.IGNORECASE)


def _clean(prompt):
    s = prompt.strip()
    s = _PREFIX.sub("", s)
    s = s.rstrip("?!").strip()
    return s


class _Parser:
    def __init__(self, text):
        self.tokens = re.findall(r"\d+(?:\.\d+)?|[+\-*/%()]", text)
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def parse(self):
        value = self._expr()
        if self.pos != len(self.tokens):
            raise ValueError("trailing tokens")
        return value

    def _expr(self):
        value = self._term()
        while self.peek() in ("+", "-"):
            op = self.take()
            rhs = self._term()
            value = value + rhs if op == "+" else value - rhs
        return value

    def _term(self):
        value = self._factor()
        while self.peek() in ("*", "/", "%"):
            op = self.take()
            rhs = self._factor()
            if op == "*":
                value = value * rhs
            elif op == "/":
                if rhs == 0:
                    raise ZeroDivisionError
                value = value / rhs
            else:
                if rhs == 0:
                    raise ZeroDivisionError
                value = value % rhs
        return value

    def _factor(self):
        tok = self.peek()
        if tok == "-":
            self.take()
            return -self._factor()
        if tok == "(":
            self.take()
            value = self._expr()
            if self.take() != ")":
                raise ValueError("unbalanced parenthesis")
            return value
        if tok is not None and re.fullmatch(r"\d+(?:\.\d+)?", tok):
            self.take()
            return float(tok)
        raise ValueError("unexpected token")


def try_local_calc(prompt):
    """Return a local answer string for pure arithmetic, or None.

    Example: "What is 12 + 7?" -> "12 + 7 = 19".
    """
    expr = _clean(prompt)
    if not expr or len(expr) > 100:
        return None
    if "**" in expr or "//" in expr:
        return None
    if expr.count("(") != expr.count(")"):
        return None
    if not _ALLOWED.fullmatch(expr):
        return None
    if not any(op in expr for op in "+-*/%"):
        return None
    try:
        value = _Parser(expr).parse()
    except (ValueError, ZeroDivisionError):
        return None
    if not (value == value and abs(value) != float("inf")):
        return None
    shown = re.sub(r"\s+", " ", expr).strip()
    if abs(value - round(value)) < 1e-9:
        result = str(int(round(value)))
    else:
        result = format(value, ".6g")
    return f"{shown} = {result}"
