"""Session cache, ported from the website demo's integrateChat().

Website rule, kept exactly for the key:
  key = shrunk prompt, lowercased, with every character that is not
  a-z, 0-9 or a space removed, whitespace collapsed, trimmed.
  An empty key is never cached.

One intentional deviation from the website: the harness key also
includes the resolved mode. The website reuses a cached answer even
if the routed mode would now differ; the harness does not, because a
user who explicitly asks for sprout should not silently receive a
full-length cached answer. A repeat of the same shrunk prompt in the
same mode is a hit: 0 new output tokens, the cached answer reused
verbatim.

Cache entries are stored in the session (see session.py) so a cache
survives across CLI runs that share a --session-file, and are dropped
when the session file is not used. Cached live answers are reused
verbatim and may be stale; pass --no-cache to bypass the cache.
"""

import re


def cache_key(shrunk_prompt, mode):
    """Return the cache key for a shrunk prompt and resolved mode, or ''."""
    if not shrunk_prompt:
        return ""
    key = shrunk_prompt.lower()
    key = re.sub(r"[^a-z0-9 ]", "", key)
    key = re.sub(r"\s+", " ", key).strip()
    if not key:
        return ""
    return f"{mode}:{key}"


class SessionCache:
    """A small in-memory key -> {mode, answer, standard_tokens} store."""

    def __init__(self, entries=None):
        self.entries = dict(entries) if entries else {}

    def lookup(self, key):
        entry = self.entries.get(key) if key else None
        if not isinstance(entry, dict):
            return None
        if not isinstance(entry.get("answer"), str):
            return None
        return entry

    def store(self, key, mode, answer, standard_tokens):
        if not key:
            return
        self.entries[key] = {
            "mode": mode,
            "answer": answer,
            "standard_tokens": standard_tokens,
        }

    def to_dict(self):
        return self.entries

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            return cls()
        return cls(entries=data)
