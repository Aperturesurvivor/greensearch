#!/usr/bin/env python3
"""GreenSearch live backend: POST /api/chat and GET /api/health.

Standard library only. All secrets and model choices come from the
environment; nothing secret is ever accepted from, or returned to, the
client. See server/README.md for the full env var table and run steps.

Pipeline per chat request, in order:
  1. PromptShrink the prompt (greensearch.shrink).
  2. Session cache check (greensearch.cache), per client session id,
     mode-aware. A hit makes no model call: 0 new output tokens.
  3. Auto routing (greensearch.router), unless the client sent a mode.
  4. One call to the primary model (GREENSEARCH_MODEL, default
     qwen/qwen3-8b) with the brevity system prompt and token cap,
     logprobs requested. By default that is the only model call:
     escalated=false, reason "single model: no separate escalation
     model configured".
     Optional cascade: only if GREENSEARCH_ESCALATION_MODEL is set to a
     DIFFERENT model does the logprob-gated cascade run
     (greensearch.cascade): if avg_logprob is present and below the
     threshold, the escalation model is called with the SAME system
     prompt and cap. Missing logprobs never escalate. An escalation
     failure is an error to the client, never a silent fallback to the
     primary answer.
  5. apply_brevity as a safety-net trim (greensearch.brevity).

Delivery: the provider is called WITHOUT streaming, because step 5
needs the complete text to trim (and, with the optional cascade, step 4
needs the complete answer and its logprobs before it can decide whether
to escalate; streaming raw provider tokens would show the user a
low-confidence answer that might then be replaced). The finished answer is then sent to the browser as
Server-Sent Events (chunk events, then one meta event, then done), or
as one JSON object when the client sends "stream": false. Every meta
payload says which path was used ("delivery") and that provider-side
streaming is off ("provider_streaming": false).
"""

import argparse
import collections
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from greensearch.brevity import apply_brevity  # noqa: E402
from greensearch.cache import SessionCache, cache_key  # noqa: E402
from greensearch.cascade import CascadeResult, run_cascade  # noqa: E402
from greensearch.providers import (  # noqa: E402
    BREVITY_SYSTEM,
    MAX_TOKENS,
    OpenAICompatibleProvider,
    ProviderError,
)
from greensearch.router import route_mode  # noqa: E402
from greensearch.shrink import shrink  # noqa: E402

# ---------------------------------------------------------------------------
# Plain-language client messages. These are the ONLY error texts a client
# ever sees: no provider detail, no URL, no key, no traceback.
# ---------------------------------------------------------------------------

MSG_NOT_CONFIGURED = "Live backend is not configured yet (no API key on the server)"
MSG_MISCONFIGURED = "Live backend is misconfigured on the server, check its settings"
MSG_UNREACHABLE = "The model provider could not be reached, try again"
MSG_RATE_LIMITED = "Too many requests, try again later"
MSG_ESCALATION_FAILED = (
    "The escalation model could not be reached, so no answer was returned "
    "(the primary model's low-confidence answer was not used), try again"
)
MSG_ORIGIN = "This page's origin is not allowed to use this backend"
MSG_INTERNAL = "Something went wrong on the server, try again"
MSG_NOT_FOUND = "Not found"

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "qwen/qwen3-8b"
SINGLE_MODEL_REASON = "single model: no separate escalation model configured"
DEFAULT_ORIGINS = ("http://localhost:8000", "http://127.0.0.1:8000")
DEFAULT_PORT = 8000

MAX_BODY_BYTES = 16 * 1024
MAX_PROMPT_CHARS = 4000
MAX_SESSIONS = 1000
MAX_CACHE_ENTRIES_PER_SESSION = 200
CHUNK_WORDS = 3

MODES = ("sprout", "canopy", "full")
_SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
# Fields a client must never send. The key lives on the server only, and
# model choice is server configuration.
_FORBIDDEN_FIELDS = {
    "api_key", "apikey", "key", "token", "authorization", "secret",
    "openai_api_key", "greensearch_api_key", "model", "base_url",
}

# (name, default shown in --help and README, description)
ENV_VARS = [
    ("GREENSEARCH_API_KEY", "(unset)",
     "Provider API key. Server-side only. Unset = /api/chat returns 503."),
    ("GREENSEARCH_BASE_URL", DEFAULT_BASE_URL,
     "OpenAI-compatible base URL (https; http only for localhost)."),
    ("GREENSEARCH_MODEL", DEFAULT_MODEL, "Primary model; answers every request."),
    ("GREENSEARCH_ESCALATION_MODEL", "(= GREENSEARCH_MODEL: no escalation)",
     "Optional. Set to a DIFFERENT model to enable the logprob cascade."),
    ("GREENSEARCH_CASCADE_THRESHOLD", "-1.0",
     "Mean-logprob escalation threshold, must be <= 0. Cascade only."),
    ("GREENSEARCH_BACKEND_ORIGIN", ",".join(DEFAULT_ORIGINS),
     "Comma-separated CORS allowlist of exact origins. '*' is refused."),
    ("GREENSEARCH_RATE_LIMIT_PER_HOUR", "100",
     "Chat requests per client IP per rolling hour. 0 disables the limit."),
    ("GREENSEARCH_DEBUG_LOG", "off",
     "1/true/yes/on logs prompts to local stderr only, never to responses."),
    ("PORT", str(DEFAULT_PORT), "Listen port (also --port)."),
]


class ClientError(Exception):
    """An error with an HTTP status and a plain message safe to show users."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class Config:
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    # Empty or equal to model = no escalation call at all.
    escalation_model: str = ""
    cascade_threshold: float = -1.0
    allowed_origins: tuple = DEFAULT_ORIGINS
    rate_limit_per_hour: int = 100
    debug_log: bool = False

    def __post_init__(self):
        if not self.escalation_model:
            self.escalation_model = self.model

    @property
    def configured(self):
        return bool(self.api_key)

    @property
    def cascade_enabled(self):
        """True only when a separate escalation model is configured."""
        return self.escalation_model != self.model

    @classmethod
    def from_env(cls, env=None):
        """Build a Config from environment variables.

        Raises ValueError with a plain message on an invalid value, so
        the server refuses to start instead of running misconfigured.
        """
        env = os.environ if env is None else env

        def get(name, default):
            value = env.get(name, "").strip()
            return value or default

        model = get("GREENSEARCH_MODEL", DEFAULT_MODEL)
        try:
            threshold = float(get("GREENSEARCH_CASCADE_THRESHOLD", "-1.0"))
        except ValueError:
            raise ValueError("GREENSEARCH_CASCADE_THRESHOLD must be a number, e.g. -1.0")
        if threshold != threshold or threshold > 0:  # NaN or positive
            raise ValueError("GREENSEARCH_CASCADE_THRESHOLD must be <= 0 (logprobs are <= 0)")
        try:
            rate = int(get("GREENSEARCH_RATE_LIMIT_PER_HOUR", "100"))
        except ValueError:
            raise ValueError("GREENSEARCH_RATE_LIMIT_PER_HOUR must be a whole number")
        if rate < 0:
            raise ValueError("GREENSEARCH_RATE_LIMIT_PER_HOUR must be 0 or more")
        raw_origins = env.get("GREENSEARCH_BACKEND_ORIGIN", "").strip()
        origins = tuple(
            o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip()
        ) or DEFAULT_ORIGINS
        if any(o == "*" or "*" in o for o in origins):
            raise ValueError("GREENSEARCH_BACKEND_ORIGIN must list exact origins; '*' is not allowed")
        return cls(
            api_key=env.get("GREENSEARCH_API_KEY", "").strip(),
            base_url=get("GREENSEARCH_BASE_URL", DEFAULT_BASE_URL),
            model=model,
            escalation_model=get("GREENSEARCH_ESCALATION_MODEL", model),
            cascade_threshold=threshold,
            allowed_origins=origins,
            rate_limit_per_hour=rate,
            debug_log=env.get("GREENSEARCH_DEBUG_LOG", "").strip().lower()
            in ("1", "true", "yes", "on"),
        )


# ---------------------------------------------------------------------------
# Rate limiting and per-session caches (in memory, per process)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Rolling-window request counter per client key (the client IP).

    In memory only: it resets when the server restarts and is not shared
    between processes. limit <= 0 disables it.
    """

    def __init__(self, limit, window_seconds=3600.0, clock=time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, client):
        if self.limit <= 0:
            return True
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(client, collections.deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 10000:  # drop idle clients so memory stays bounded
                for key in [k for k, v in self._hits.items() if not v]:
                    del self._hits[key]
            return True


class SessionStore:
    """session id -> SessionCache, least recently used evicted first."""

    def __init__(self, max_sessions=MAX_SESSIONS):
        self.max_sessions = max_sessions
        self._caches = collections.OrderedDict()
        self.lock = threading.Lock()

    def get(self, session_id):
        """Return the cache for session_id. Call with self.lock held."""
        cache = self._caches.get(session_id)
        if cache is None:
            cache = SessionCache()
            self._caches[session_id] = cache
            while len(self._caches) > self.max_sessions:
                self._caches.popitem(last=False)
        else:
            self._caches.move_to_end(session_id)
        return cache


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------

@dataclass
class ChatRequest:
    prompt: str
    mode: str = "auto"
    session_id: Optional[str] = None
    stream: bool = True
    measure_baseline: bool = False


def parse_chat_request(body):
    """Validate a JSON request body (bytes). Raises ClientError(400)."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ClientError(400, "Request body must be valid JSON")
    if not isinstance(data, dict):
        raise ClientError(400, "Request body must be a JSON object")
    if any(str(k).lower() in _FORBIDDEN_FIELDS for k in data):
        raise ClientError(
            400,
            "Do not send an API key, model or provider URL; those are set on the server only",
        )
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ClientError(400, "Prompt is empty: type a question first")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ClientError(400, f"Prompt is too long (max {MAX_PROMPT_CHARS} characters)")
    mode = data.get("mode", "auto")
    if mode is None:
        mode = "auto"
    if mode == "forest":  # the website's name for full
        mode = "full"
    if mode != "auto" and mode not in MODES:
        raise ClientError(400, "Mode must be one of auto, sprout, canopy, full")
    session_id = data.get("session_id")
    if session_id is not None and (
        not isinstance(session_id, str) or not _SESSION_ID.match(session_id)
    ):
        raise ClientError(400, "session_id must be 8-64 letters, digits, '-' or '_'")
    stream = data.get("stream", True)
    measure = data.get("measure_baseline", False)
    if not isinstance(stream, bool) or not isinstance(measure, bool):
        raise ClientError(400, "stream and measure_baseline must be true or false")
    return ChatRequest(
        prompt=prompt, mode=mode, session_id=session_id,
        stream=stream, measure_baseline=measure,
    )


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

class _Recorder:
    """Wraps a provider to remember whether it was called and what it returned.

    run_cascade only returns the final completion; the server also needs
    the primary model's usage when it escalated, and needs to know whether
    a failure came from the escalation call.
    """

    def __init__(self, provider):
        self.provider = provider
        self.model = getattr(provider, "model", getattr(provider, "name", "unknown"))
        self.attempted = False
        self.completion = None

    def complete_ex(self, prompt, system=None, max_tokens=None, logprobs=False):
        self.attempted = True
        self.completion = self.provider.complete_ex(
            prompt, system=system, max_tokens=max_tokens, logprobs=logprobs
        )
        return self.completion


def _sum_or_none(values):
    """Sum provider-reported counts; None if any call did not report one."""
    if not values or any(v is None for v in values):
        return None
    return sum(values)


def _provider_error(exc):
    """Map a ProviderError to a plain ClientError. The detail is dropped."""
    if "HTTP 429" in str(exc):
        return ClientError(429, MSG_RATE_LIMITED)
    return ClientError(502, MSG_UNREACHABLE)


class Backend:
    """Runs the chat pipeline. Holds config, caches and the rate limiter."""

    def __init__(self, config, provider_factory=None, clock=time.monotonic,
                 log_stream=None, quiet=False):
        self.config = config
        self.provider_factory = provider_factory or self._default_provider
        self.rate_limiter = RateLimiter(config.rate_limit_per_hour, 3600.0, clock)
        self.sessions = SessionStore()
        self.log_stream = log_stream if log_stream is not None else sys.stderr
        self.quiet = quiet

    def _default_provider(self, model):
        return OpenAICompatibleProvider(
            self.config.base_url, api_key=self.config.api_key, model=model
        )

    def log(self, message):
        if not self.quiet:
            print(f"[greensearch-server] {message}", file=self.log_stream, flush=True)

    def debug(self, message):
        """Prompt-bearing log lines: only with GREENSEARCH_DEBUG_LOG, stderr only."""
        if self.config.debug_log:
            print(f"[greensearch-server debug] {message}", file=self.log_stream, flush=True)

    def _make(self, model):
        try:
            return self.provider_factory(model)
        except ValueError:
            # e.g. a non-https base URL. The detail stays on the server.
            self.log("provider setup failed: check GREENSEARCH_BASE_URL")
            raise ClientError(503, MSG_MISCONFIGURED)

    def health(self):
        cfg = self.config
        return {
            "status": "ok",
            "configured": cfg.configured,
            "model": cfg.model,
            "escalation_model": cfg.escalation_model,
            "cascade_enabled": cfg.cascade_enabled,
            "cascade_threshold": cfg.cascade_threshold,
            "rate_limit_per_hour": cfg.rate_limit_per_hour,
            "provider_streaming": False,
        }

    def chat(self, req):
        """Run the pipeline. Returns {"answer": str, "meta": dict}.

        Raises ClientError with a plain message on any failure.
        """
        started = time.monotonic()
        cfg = self.config
        if not cfg.configured:
            raise ClientError(503, MSG_NOT_CONFIGURED)

        # 1. PromptShrink.
        sr = shrink(req.prompt)
        prompt = sr.text
        if not prompt.strip():
            raise ClientError(400, "Prompt is empty after removing filler words: add a question")

        # 3 (needed for the cache key). Routing, unless the client chose a mode.
        mode = route_mode(prompt) if req.mode == "auto" else req.mode
        self.debug(f"prompt={req.prompt!r} shrunk={prompt!r} mode={mode}")

        meta = {
            "mode": mode,
            "mode_source": "auto" if req.mode == "auto" else "explicit",
            "shrink": {
                "original_tokens_est": sr.original_tokens,
                "shrunk_tokens_est": sr.shrunk_tokens,
                "saved_tokens_est": sr.saved_tokens,
                "changed": sr.changed,
            },
            "provider_streaming": False,
            "baseline": None,
        }

        # 2. Session cache (mode-aware key, per client session id).
        key = cache_key(prompt, mode) if req.session_id else ""
        if key:
            with self.sessions.lock:
                entry = self.sessions.get(req.session_id).lookup(key)
                entry = dict(entry) if entry else None
            if entry is not None:
                meta.update({
                    "cache_hit": True,
                    "model": None,
                    "cached_from_model": entry.get("model"),
                    "escalated": False,
                    "cached_answer_was_escalated": bool(entry.get("escalated")),
                    "escalation_reason": "cache hit: no model call",
                    "avg_logprob": None,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "new_output_tokens": 0,
                    "tokens_source": "cache hit: no model call, 0 new tokens",
                    "trimmed": False,
                    "latency_ms": round((time.monotonic() - started) * 1000),
                })
                return {"answer": entry["answer"], "meta": meta}

        # 4. Primary model; logprob-gated escalation only if a separate
        #    escalation model is configured.
        primary = _Recorder(self._make(cfg.model))
        escalation = _Recorder(self._make(cfg.escalation_model)) if cfg.cascade_enabled else None
        try:
            if escalation is not None:
                result = run_cascade(
                    primary, escalation, prompt,
                    system=BREVITY_SYSTEM[mode], max_tokens=MAX_TOKENS[mode],
                    threshold=cfg.cascade_threshold,
                )
            else:
                comp = primary.complete_ex(
                    prompt, system=BREVITY_SYSTEM[mode], max_tokens=MAX_TOKENS[mode],
                    logprobs=True,
                )
                result = CascadeResult(
                    completion=comp, escalated=False, avg_logprob=comp.avg_logprob,
                    reason=SINGLE_MODEL_REASON, primary_model=primary.model,
                )
        except ProviderError as exc:
            if escalation is not None and escalation.attempted:
                self.log("escalation call failed; no answer returned")
                raise ClientError(502, MSG_ESCALATION_FAILED)
            self.log("primary call failed")
            raise _provider_error(exc)
        except ValueError:
            self.log("pipeline rejected a value (see cascade/provider)")
            raise ClientError(500, MSG_INTERNAL)

        comp = result.completion
        calls = [primary.completion] + ([escalation.completion] if result.escalated else [])

        # 5. Safety-net trim.
        raw_text = comp.text.strip()
        answer = apply_brevity(raw_text, mode).strip()
        if not answer:
            answer = raw_text  # nothing trimmable survived; show the model's text as-is
        output_tokens = _sum_or_none([c.completion_tokens for c in calls])
        input_tokens = _sum_or_none([c.prompt_tokens for c in calls])
        model_used = escalation.model if result.escalated else primary.model

        if key:
            with self.sessions.lock:
                cache = self.sessions.get(req.session_id)
                if key not in cache.entries and len(cache.entries) >= MAX_CACHE_ENTRIES_PER_SESSION:
                    cache.entries.pop(next(iter(cache.entries)))
                cache.store(key, mode, answer, output_tokens or 0)
                cache.entries[key].update(model=model_used, escalated=result.escalated)

        meta.update({
            "cache_hit": False,
            "model": model_used,
            "primary_model": primary.model,
            "escalated": result.escalated,
            "escalation_reason": result.reason,
            "avg_logprob": result.avg_logprob,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "new_output_tokens": output_tokens,
            "tokens_source": "provider-reported" if output_tokens is not None
            else "not reported by provider",
            "trimmed": answer != raw_text,
        })

        if req.measure_baseline:
            meta["baseline"] = self._baseline(req.prompt, input_tokens, output_tokens)

        meta["latency_ms"] = round((time.monotonic() - started) * 1000)
        return {"answer": answer, "meta": meta}

    def _baseline(self, original_prompt, input_tokens, output_tokens):
        """One extra, unconstrained call: original prompt, no system prompt,
        no token cap, same primary model. Doubles API cost; opt-in only.
        A failure here never affects the answer already produced."""
        cfg = self.config
        try:
            base = self._make(cfg.model).complete_ex(original_prompt)
        except (ProviderError, ValueError, ClientError):
            self.log("baseline call failed")
            return {"error": "Baseline call failed, savings were not measured"}
        out = {
            "model": cfg.model,
            "input_tokens": base.prompt_tokens,
            "output_tokens": base.completion_tokens,
            "saved_output_tokens": None,
            "saved_total_tokens": None,
            "note": "measured: unconstrained call vs GreenSearch call, provider-reported tokens",
        }
        if base.completion_tokens is not None and output_tokens is not None:
            out["saved_output_tokens"] = base.completion_tokens - output_tokens
            if base.prompt_tokens is not None and input_tokens is not None:
                out["saved_total_tokens"] = (
                    base.prompt_tokens + base.completion_tokens
                    - input_tokens - output_tokens
                )
        else:
            out["note"] = "provider did not report token counts, savings not measured"
        return out


# ---------------------------------------------------------------------------
# Server-Sent Events
# ---------------------------------------------------------------------------

def sse_event(event, data):
    """Encode one SSE event. data is JSON-encoded on a single line."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def parse_sse(text):
    """Parse an SSE stream into a list of (event, data) with data JSON-decoded."""
    events = []
    for block in re.split(r"\r?\n\r?\n", text):
        name, data_lines = "message", []
        for line in block.splitlines():
            if not line or line.startswith(":"):
                continue
            field_name, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field_name == "event":
                name = value
            elif field_name == "data":
                data_lines.append(value)
        if data_lines:
            events.append((name, json.loads("\n".join(data_lines))))
    return events


def chunk_text(text, words_per_chunk=CHUNK_WORDS):
    """Split text into chunks that join back to exactly the original text."""
    pieces = re.findall(r"\s*\S+\s*", text) or ([text] if text else [])
    return [
        "".join(pieces[i:i + words_per_chunk])
        for i in range(0, len(pieces), words_per_chunk)
    ]


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

def make_handler(backend):
    site_index = ROOT / "website" / "index.html"

    class Handler(BaseHTTPRequestHandler):
        server_version = "GreenSearch"
        sys_version = ""

        # -- helpers --------------------------------------------------------

        def _origin_ok(self):
            origin = self.headers.get("Origin")
            # No Origin header: not a cross-site browser request (curl, tests).
            return origin is None or origin.rstrip("/") in backend.config.allowed_origins

        def _cors_headers(self):
            origin = self.headers.get("Origin")
            if origin and origin.rstrip("/") in backend.config.allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

        def _send_json(self, status, obj, extra=None):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, status, message, extra=None):
            self._send_json(status, {"error": message}, extra)

        def log_request(self, code="-", size="-"):
            # Method, path and status only: never a body, never a prompt.
            backend.log(f"{self.command} {self.path.split('?')[0]} -> {code}")

        def log_message(self, fmt, *args):
            backend.log(fmt % args)

        # -- verbs ----------------------------------------------------------

        def do_OPTIONS(self):
            path = self.path.split("?")[0]
            if path not in ("/api/chat", "/api/health"):
                return self._send_error(404, MSG_NOT_FOUND)
            if not self._origin_ok():
                return self._send_error(403, MSG_ORIGIN)
            self.send_response(204)
            self._cors_headers()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/health":
                if not self._origin_ok():
                    return self._send_error(403, MSG_ORIGIN)
                return self._send_json(200, backend.health())
            if path in ("/", "/index.html") and site_index.is_file():
                body = site_index.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._send_error(404, MSG_NOT_FOUND)

        def do_POST(self):
            path = self.path.split("?")[0]
            if path != "/api/chat":
                return self._send_error(404, MSG_NOT_FOUND)
            if not self._origin_ok():
                return self._send_error(403, MSG_ORIGIN)
            if not backend.rate_limiter.allow(self.client_address[0]):
                return self._send_error(429, MSG_RATE_LIMITED, {"Retry-After": "3600"})
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._send_error(400, "Request body is missing")
            if length <= 0:
                return self._send_error(400, "Request body is missing")
            if length > MAX_BODY_BYTES:
                return self._send_error(413, "Request body is too large")
            body = self.rfile.read(length)
            try:
                req = parse_chat_request(body)
                result = backend.chat(req)
            except ClientError as exc:
                return self._send_error(exc.status, exc.message)
            except Exception as exc:  # never a traceback to the client
                backend.log(f"unexpected error: {type(exc).__name__}")
                return self._send_error(500, MSG_INTERNAL)

            meta = result["meta"]
            try:
                if req.stream:
                    meta["delivery"] = "sse"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Accel-Buffering", "no")
                    self._cors_headers()
                    self.end_headers()
                    for piece in chunk_text(result["answer"]):
                        self.wfile.write(sse_event("chunk", {"text": piece}))
                        self.wfile.flush()
                    self.wfile.write(sse_event("meta", meta))
                    self.wfile.write(sse_event("done", {}))
                    self.wfile.flush()
                else:
                    meta["delivery"] = "json"
                    self._send_json(200, result)
            except (BrokenPipeError, ConnectionResetError):
                backend.log("client disconnected mid-response")

    return Handler


def make_server(backend, host="127.0.0.1", port=DEFAULT_PORT):
    server = ThreadingHTTPServer((host, port), make_handler(backend))
    server.daemon_threads = True
    return server


def _help_epilog():
    width = max(len(name) for name, _, _ in ENV_VARS)
    lines = ["environment variables (all optional; secrets are read ONLY from here):"]
    for name, default, desc in ENV_VARS:
        lines.append(f"  {name.ljust(width)}  {desc}")
        lines.append(f"  {' ' * width}  default: {default}")
    lines += [
        "",
        "endpoints: POST /api/chat (SSE, or JSON with \"stream\": false),",
        "           GET /api/health, GET / (serves website/index.html).",
        "The API key is never accepted from clients and never returned.",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python server/app.py",
        description="GreenSearch live backend (local; stdlib only).",
        epilog=_help_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default 127.0.0.1, local only)")
    parser.add_argument("--port", type=int, default=None,
                        help=f"listen port (default $PORT or {DEFAULT_PORT})")
    args = parser.parse_args(argv)

    try:
        config = Config.from_env()
        port = args.port if args.port is not None else int(os.environ.get("PORT", DEFAULT_PORT))
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    backend = Backend(config)
    server = make_server(backend, args.host, port)
    backend.log(
        f"listening on http://{args.host}:{server.server_address[1]} | "
        f"live: {'configured' if config.configured else 'NOT configured (no API key)'} | "
        f"model: {config.model} | "
        f"escalation: {config.escalation_model if config.cascade_enabled else 'off (single model)'} | "
        f"CORS: {', '.join(config.allowed_origins)} | "
        f"rate limit: {config.rate_limit_per_hour}/h | "
        f"prompt logging: {'ON (stderr only)' if config.debug_log else 'off'}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
