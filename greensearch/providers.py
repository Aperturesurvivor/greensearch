"""Provider interface: where answers come from.

Two providers, kept strictly separate so demo output can never be
mistaken for a live model response:

- DemoProvider: offline, keyword canned answers covering the same six
  topics as the portfolio site demo (email, API, workout, backup,
  firewall/Portcullis, DNS). No network, no key, no model. For trying
  the harness. Note one deliberate difference from the site: the site
  uses authored mode-specific variants, while this provider returns one
  full draft and the brevity layer trims it to the mode budget.
- OpenAICompatibleProvider: POSTs to a /chat/completions endpoint with a
  bearer key from the environment (GREENSEARCH_API_KEY). Only used when
  the user explicitly asks for live mode and supplies a key and base URL.
  Standard library only (urllib).
"""

import json
import os
import re
import urllib.error
import urllib.request


class ProviderError(Exception):
    """A live-provider failure, raised instead of leaking a traceback.

    The CLI catches this and exits 2 with the message. HTTP status,
    connection failures, timeouts, and malformed responses all become
    this one readable error type.
    """


def _matches(prompt, *patterns):
    """True if any pattern matches on a word boundary.

    Word-boundary matching matters: plain substring matching routed
    "capital" and "rapid growth" to the API answer, because both contain
    "api" as a substring. ``\\bapi\\b`` does not match inside those words.
    """
    return any(re.search(pattern, prompt, flags=re.IGNORECASE) for pattern in patterns)


class DemoProvider:
    """Offline canned answers. No network, no model."""

    name = "demo (offline)"

    def complete(self, prompt):
        if prompt is None or not prompt.strip():
            raise ValueError("Empty prompt: type a prompt first.")
        p = prompt.lower()
        if _matches(p, r"\bemail\b", r"\bfollow-up\b", r"\bfollow up\b"):
            return (
                "Subject: Quick follow-up\n\nHi — just circling back on our call. "
                "Happy to reschedule at your convenience, or send a summary by email "
                "if easier. What works best for you?\n\nThanks,\nGrant"
            )
        if _matches(p, r"\bapi\b", r"\bapis\b"):
            return (
                "An API is a waiter for software: your app orders from a menu, and "
                "the API brings back exactly what was asked for. Your app never "
                "needs to see how the other program works inside. It just gets "
                "the result. That separation is why apps can use maps, payments, "
                "or weather data without building those systems themselves, and "
                "why a change inside one program does not have to break the other."
            )
        if _matches(p, r"\bworkout\b", r"\bexercise\b"):
            return (
                "Day 1: Squats, push-ups, glute bridges — 3×10 each. "
                "Day 2: Rest or walk 20 min. "
                "Day 3: Lunges, wall push-ups, dead bugs — 3×10. "
                "Rest 60s between sets, keep form clean, and add reps weekly. "
                "Start lighter than you think you need to, stop a set if your "
                "form breaks down, and repeat the same three days next week "
                "before adding weight or reps."
            )
        if _matches(p, r"\bbackup\b", r"\bbackups\b"):
            return (
                "Backups matter because hardware fails, files get deleted, and "
                "ransomware encrypts, usually at the worst time. "
                "A tested backup turns a business-ending day into a bad morning. "
                "Rule of thumb: 3 copies, 2 media types, 1 off-site. "
                "The key word is tested: a backup you have never restored from "
                "is a hope, not a plan, so restore a file now and then to prove "
                "it works."
            )
        if _matches(p, r"\bfirewall\b", r"\bportcullis\b"):
            return (
                "A portcullis firewall is a gatekeeper for a network: it checks "
                "what software is running and flags known-vulnerable versions. "
                "Portcullis does this through your AI agent instead of a "
                "dashboard. It runs a daily check and stays silent when "
                "everything is clean. When something is at risk, it explains "
                "the risk in plain English. For a small business, that means "
                "catching one outdated, exploitable program before it becomes "
                "a breach, without hiring a full security team."
            )
        if _matches(p, r"\bdns\b", r"\bdomain name\b"):
            return (
                "DNS is the internet phone book: it turns a name like "
                "example.com into the number (IP address) a computer needs to "
                "reach it. You type the name, DNS looks up the matching address, "
                "and your browser connects there, so you never have to memorize "
                "numbers. If DNS cannot find a name, the site will not load "
                "even when your connection is fine, which is why a DNS problem "
                "can look like the whole internet is down."
            )
        cleaned = " ".join(prompt.split())
        topic = cleaned[:80].strip() + "…" if len(cleaned) > 80 else cleaned
        return (
            f"No template covers that topic yet, so this is not a specific "
            f"answer to: “{topic}”. In general, pin down three things first: "
            f"what it is, why it matters, and one next step. Start by "
            f"narrowing the question to one part — for example, what it is, "
            f"or what to do first — and ask for just that part. These "
            f"templates only cover email, APIs, workouts, backups, "
            f"firewalls/Portcullis, and DNS, so anything else needs a source "
            f"that actually covers it."
        )


class OpenAICompatibleProvider:
    """Live provider via an OpenAI-compatible /chat/completions endpoint."""

    name = "openai-compatible (live)"

    def __init__(self, base_url, api_key=None, model="gpt-4o-mini"):
        self.base_url = base_url.rstrip("/")
        # GREENSEARCH_API_KEY is canonical since the 0.3.0 rename.
        # ECOWRAPPER_API_KEY is accepted as a one-version fallback so
        # existing local setups do not break silently; it will be
        # removed in a later release.
        self.api_key = (
            api_key
            or os.environ.get("GREENSEARCH_API_KEY", "")
            or os.environ.get("ECOWRAPPER_API_KEY", "")
        )
        if not self.api_key:
            raise ValueError(
                "No API key: set GREENSEARCH_API_KEY or pass api_key explicitly."
            )
        self.model = model

    def complete(self, prompt):
        if prompt is None or not prompt.strip():
            raise ValueError("Empty prompt: type a prompt first.")
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                raw = exc.read().decode(errors="replace")[:500]
                parsed = json.loads(raw) if raw else {}
                error = parsed.get("error") if isinstance(parsed, dict) else None
                if isinstance(error, dict) and error.get("message"):
                    detail = f": {error['message']}"
                elif raw:
                    detail = f": {raw}"
            except (json.JSONDecodeError, ValueError):
                detail = ""
            raise ProviderError(
                f"Live provider returned HTTP {exc.code}{detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(
                f"Could not reach live provider at {self.base_url}: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                "Live provider timed out after 60s."
            ) from exc
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"Live provider returned a response that is not valid JSON: {exc}"
            ) from exc
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderError(
                f"Live provider returned an unexpected response shape: {exc}"
            ) from exc
