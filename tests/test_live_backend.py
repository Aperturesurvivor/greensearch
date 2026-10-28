"""Tests for the Phase 2 live backend (server/app.py).

No API key and no network to any provider: every model call goes to a
FakeProvider. HTTP tests bind a throwaway server on 127.0.0.1 (loopback
only). Run from the repository root:
    python -m unittest discover -s tests -v
"""

import http.client
import io
import json
import re
import subprocess
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greensearch.brevity import apply_brevity  # noqa: E402
from greensearch.providers import BREVITY_SYSTEM, MAX_TOKENS, Completion, ProviderError  # noqa: E402
from greensearch.router import route_mode  # noqa: E402
from greensearch.shrink import shrink  # noqa: E402
from server.app import (  # noqa: E402
    MSG_ESCALATION_FAILED,
    MSG_NOT_CONFIGURED,
    MSG_ORIGIN,
    MSG_RATE_LIMITED,
    MSG_UNREACHABLE,
    SINGLE_MODEL_REASON,
    Backend,
    ChatRequest,
    ClientError,
    Config,
    RateLimiter,
    chunk_text,
    make_server,
    parse_chat_request,
    parse_sse,
    sse_event,
)

# A sentinel placeholder, NOT a real key: tests assert it never leaks.
SENTINEL_KEY = "sk-TEST-SENTINEL-not-a-real-key"
SESSION = "test-session-0001"
LONG_ANSWER = (
    "DNS turns names into IP addresses. Your browser asks a resolver. "
    "The resolver asks root servers. Then it asks the TLD servers. "
    "Then the authoritative server answers. The result is cached. "
    "Caching makes later lookups fast. That is the whole trick."
)


class FakeProvider:
    """Records every call; returns a fixed completion or raises."""

    def __init__(self, model, text=LONG_ANSWER, avg_logprob=None,
                 completion_tokens=50, prompt_tokens=10, error=None):
        self.model = model
        self.text = text
        self.avg_logprob = avg_logprob
        self.completion_tokens = completion_tokens
        self.prompt_tokens = prompt_tokens
        self.error = error
        self.calls = []

    def complete_ex(self, prompt, system=None, max_tokens=None, logprobs=False):
        self.calls.append({"prompt": prompt, "system": system,
                           "max_tokens": max_tokens, "logprobs": logprobs})
        if self.error is not None:
            raise self.error
        return Completion(
            text=self.text,
            completion_tokens=self.completion_tokens,
            prompt_tokens=self.prompt_tokens,
            avg_logprob=self.avg_logprob if logprobs else None,
        )


PRIMARY = "qwen/qwen3-8b"
# Only used by the opt-in cascade tests; not a model choice for Phase 2.
ESCALATION = "example/escalation-model"


def make_backend(primary=None, big=None, baseline=None, **config_overrides):
    """A Backend whose models are fakes. Returns (backend, primary, big).

    Default config: single model (qwen/qwen3-8b), no escalation model, so
    big must never be built. Pass escalation_model=ESCALATION to enable
    the cascade. The primary model's first instance answers the pipeline;
    if baseline is given, later primary instances (the baseline call) use it.
    """
    config = Config(api_key=SENTINEL_KEY, **config_overrides)
    primary = primary or FakeProvider(config.model, avg_logprob=-0.2)
    big = big or FakeProvider(config.escalation_model, text="Escalated answer. Second sentence.",
                              completion_tokens=30, prompt_tokens=12)
    made = {"primary": 0}

    def factory(model):
        if model == config.model:
            made["primary"] += 1
            # Each request builds one primary provider for the pipeline; a
            # second one in the same request is the baseline call.
            if baseline is not None and made["primary"] % 2 == 0:
                return baseline
            return primary
        if config.cascade_enabled and model == config.escalation_model:
            return big
        raise AssertionError(f"unexpected model {model}")

    backend = Backend(config, provider_factory=factory, log_stream=io.StringIO(), quiet=True)
    return backend, primary, big


def make_cascade_backend(primary=None, big=None, **config_overrides):
    """make_backend with a DIFFERENT escalation model, so the cascade runs."""
    return make_backend(primary=primary, big=big, escalation_model=ESCALATION,
                        **config_overrides)


class PipelineTests(unittest.TestCase):
    PROMPT = "Could you please explain DNS in order to understand it?"

    def test_shrink_route_brevity_pipeline(self):
        backend, small, big = make_backend()
        result = backend.chat(ChatRequest(prompt=self.PROMPT, session_id=SESSION))
        shrunk = shrink(self.PROMPT).text
        mode = route_mode(shrunk)
        self.assertEqual(len(small.calls), 1)
        call = small.calls[0]
        self.assertEqual(call["prompt"], shrunk)             # PromptShrink ran
        self.assertNotIn("please", call["prompt"].lower())
        self.assertEqual(call["system"], BREVITY_SYSTEM[mode])  # brevity system prompt
        self.assertEqual(call["max_tokens"], MAX_TOKENS[mode])  # token cap
        self.assertTrue(call["logprobs"])                    # logprobs requested
        self.assertEqual(big.calls, [])
        meta = result["meta"]
        self.assertEqual(meta["mode"], mode)
        self.assertEqual(meta["mode_source"], "auto")
        self.assertEqual(result["answer"], apply_brevity(LONG_ANSWER, mode))  # safety-net trim
        self.assertTrue(meta["trimmed"])
        self.assertEqual(meta["model"], PRIMARY)
        self.assertEqual(meta["primary_model"], PRIMARY)
        self.assertFalse(meta["escalated"])
        self.assertEqual(meta["escalation_reason"], SINGLE_MODEL_REASON)
        self.assertEqual(meta["avg_logprob"], -0.2)
        self.assertFalse(meta["cache_hit"])
        self.assertEqual((meta["input_tokens"], meta["output_tokens"]), (10, 50))
        self.assertEqual(meta["tokens_source"], "provider-reported")
        self.assertIsNone(meta["baseline"])
        self.assertFalse(meta["provider_streaming"])
        self.assertIsInstance(meta["latency_ms"], int)

    def test_explicit_mode_overrides_routing(self):
        backend, small, _ = make_backend()
        result = backend.chat(ChatRequest(prompt="Explain DNS", mode="full"))
        self.assertEqual(route_mode("Explain DNS"), "sprout")
        self.assertEqual(result["meta"]["mode"], "full")
        self.assertEqual(result["meta"]["mode_source"], "explicit")
        self.assertEqual(small.calls[0]["max_tokens"], MAX_TOKENS["full"])

    def test_tokens_none_when_provider_does_not_report(self):
        small = FakeProvider(PRIMARY, avg_logprob=-0.1,
                             completion_tokens=None, prompt_tokens=None)
        backend, _, _ = make_backend(primary=small)
        meta = backend.chat(ChatRequest(prompt="Explain DNS"))["meta"]
        self.assertIsNone(meta["output_tokens"])
        self.assertEqual(meta["tokens_source"], "not reported by provider")


class SingleModelTests(unittest.TestCase):
    """Default Phase 2 behaviour: Qwen3-8B only, never an escalation call."""

    def test_low_logprob_does_not_escalate_without_escalation_model(self):
        small = FakeProvider(PRIMARY, avg_logprob=-5.0)
        built = []

        def factory(model):
            built.append(model)
            return small

        backend = Backend(Config(api_key=SENTINEL_KEY), provider_factory=factory,
                          log_stream=io.StringIO(), quiet=True)
        meta = backend.chat(ChatRequest(prompt="Explain DNS"))["meta"]
        self.assertEqual(built, [PRIMARY])  # exactly one provider, one call
        self.assertEqual(len(small.calls), 1)
        self.assertTrue(small.calls[0]["logprobs"])
        self.assertFalse(meta["escalated"])
        self.assertEqual(meta["model"], PRIMARY)
        self.assertEqual(meta["avg_logprob"], -5.0)
        self.assertEqual(meta["escalation_reason"], SINGLE_MODEL_REASON)
        self.assertEqual((meta["input_tokens"], meta["output_tokens"]), (10, 50))

    def test_escalation_model_equal_to_primary_is_single_model(self):
        cfg = Config.from_env({"GREENSEARCH_API_KEY": "placeholder",
                               "GREENSEARCH_ESCALATION_MODEL": PRIMARY})
        self.assertFalse(cfg.cascade_enabled)
        small = FakeProvider(PRIMARY, avg_logprob=-5.0)
        backend, _, _ = make_backend(primary=small, escalation_model=PRIMARY)
        meta = backend.chat(ChatRequest(prompt="Explain DNS"))["meta"]
        self.assertFalse(meta["escalated"])
        self.assertEqual(len(small.calls), 1)

    def test_primary_failure_is_plain_error_not_escalation_message(self):
        small = FakeProvider(PRIMARY, error=ProviderError("timed out"))
        backend, _, _ = make_backend(primary=small)
        with self.assertRaises(ClientError) as ctx:
            backend.chat(ChatRequest(prompt="Explain DNS"))
        self.assertEqual((ctx.exception.status, ctx.exception.message), (502, MSG_UNREACHABLE))


class CacheTests(unittest.TestCase):
    def test_cache_hit_returns_zero_new_tokens(self):
        backend, small, _ = make_backend()
        first = backend.chat(ChatRequest(prompt="Explain DNS", session_id=SESSION))
        second = backend.chat(ChatRequest(prompt="explain dns!", session_id=SESSION))
        self.assertEqual(len(small.calls), 1)  # no second model call
        meta = second["meta"]
        self.assertTrue(meta["cache_hit"])
        self.assertEqual(meta["new_output_tokens"], 0)
        self.assertEqual(meta["output_tokens"], 0)
        self.assertEqual(meta["input_tokens"], 0)
        self.assertIsNone(meta["model"])
        self.assertEqual(meta["cached_from_model"], PRIMARY)
        self.assertEqual(second["answer"], first["answer"])

    def test_cache_is_per_session_and_mode_aware(self):
        backend, small, _ = make_backend()
        backend.chat(ChatRequest(prompt="Explain DNS", session_id=SESSION))
        backend.chat(ChatRequest(prompt="Explain DNS", session_id="other-session-02"))
        backend.chat(ChatRequest(prompt="Explain DNS", session_id=SESSION, mode="full"))
        self.assertEqual(len(small.calls), 3)

    def test_no_session_id_never_caches(self):
        backend, small, _ = make_backend()
        backend.chat(ChatRequest(prompt="Explain DNS"))
        result = backend.chat(ChatRequest(prompt="Explain DNS"))
        self.assertEqual(len(small.calls), 2)
        self.assertFalse(result["meta"]["cache_hit"])

    def test_cache_hit_reports_original_escalation(self):
        small = FakeProvider(PRIMARY, avg_logprob=-3.0)
        backend, _, big = make_cascade_backend(primary=small)
        backend.chat(ChatRequest(prompt="Explain DNS", session_id=SESSION))
        meta = backend.chat(ChatRequest(prompt="Explain DNS", session_id=SESSION))["meta"]
        self.assertTrue(meta["cache_hit"])
        self.assertFalse(meta["escalated"])  # no escalation happened on this request
        self.assertTrue(meta["cached_answer_was_escalated"])
        self.assertEqual(meta["cached_from_model"], ESCALATION)
        self.assertEqual(len(big.calls), 1)


class OptionalCascadeTests(unittest.TestCase):
    """Only when GREENSEARCH_ESCALATION_MODEL is a DIFFERENT model."""

    def test_escalates_when_logprob_below_threshold(self):
        small = FakeProvider(PRIMARY, avg_logprob=-2.0)
        backend, _, big = make_cascade_backend(primary=small)
        result = backend.chat(ChatRequest(prompt="Explain DNS"))
        meta = result["meta"]
        self.assertTrue(meta["escalated"])
        self.assertEqual(meta["model"], ESCALATION)
        self.assertEqual(meta["primary_model"], PRIMARY)
        self.assertEqual(result["answer"], "Escalated answer. Second sentence.")
        # Same system prompt and cap for the escalation call.
        self.assertEqual(big.calls[0]["system"], small.calls[0]["system"])
        self.assertEqual(big.calls[0]["max_tokens"], small.calls[0]["max_tokens"])
        self.assertEqual(big.calls[0]["prompt"], small.calls[0]["prompt"])
        # Both calls' tokens are counted: they were both generated.
        self.assertEqual(meta["output_tokens"], 50 + 30)
        self.assertEqual(meta["input_tokens"], 10 + 12)

    def test_no_escalation_at_or_above_threshold(self):
        for avg in (-0.5, -1.0):
            with self.subTest(avg=avg):
                small = FakeProvider(PRIMARY, avg_logprob=avg)
                backend, _, big = make_cascade_backend(primary=small)
                meta = backend.chat(ChatRequest(prompt="Explain DNS"))["meta"]
                self.assertFalse(meta["escalated"])
                self.assertEqual(big.calls, [])

    def test_never_escalates_when_logprobs_missing(self):
        small = FakeProvider(PRIMARY, avg_logprob=None)
        backend, _, big = make_cascade_backend(primary=small)
        meta = backend.chat(ChatRequest(prompt="Explain DNS"))["meta"]
        self.assertFalse(meta["escalated"])
        self.assertIsNone(meta["avg_logprob"])
        self.assertIn("logprobs unavailable", meta["escalation_reason"])
        self.assertEqual(big.calls, [])

    def test_threshold_comes_from_config(self):
        small = FakeProvider(PRIMARY, avg_logprob=-0.5)
        backend, _, big = make_cascade_backend(primary=small, cascade_threshold=-0.25)
        self.assertTrue(backend.chat(ChatRequest(prompt="Explain DNS"))["meta"]["escalated"])
        self.assertEqual(len(big.calls), 1)

    def test_escalation_failure_does_not_silently_downgrade(self):
        small = FakeProvider(PRIMARY, text="LOW-CONFIDENCE ANSWER.", avg_logprob=-3.0)
        big = FakeProvider(ESCALATION, error=ProviderError(
            "Could not reach live provider at https://openrouter.ai/api/v1: timed out"))
        backend, _, _ = make_cascade_backend(primary=small, big=big)
        with self.assertRaises(ClientError) as ctx:
            backend.chat(ChatRequest(prompt="Explain DNS", session_id=SESSION))
        self.assertEqual(ctx.exception.status, 502)
        self.assertEqual(ctx.exception.message, MSG_ESCALATION_FAILED)
        self.assertNotIn("LOW-CONFIDENCE", ctx.exception.message)
        # Nothing was cached either: a retry calls the models again.
        with self.assertRaises(ClientError):
            backend.chat(ChatRequest(prompt="Explain DNS", session_id=SESSION))
        self.assertEqual(len(small.calls), 2)


class BaselineTests(unittest.TestCase):
    def test_baseline_off_by_default(self):
        backend, small, _ = make_backend()
        backend.chat(ChatRequest(prompt="Explain DNS"))
        self.assertEqual(len(small.calls), 1)

    def test_measure_baseline_makes_one_unconstrained_call(self):
        baseline = FakeProvider(PRIMARY, completion_tokens=200, prompt_tokens=14)
        backend, small, _ = make_backend(baseline=baseline)
        prompt = "Could you please explain DNS?"
        meta = backend.chat(ChatRequest(prompt=prompt, measure_baseline=True))["meta"]
        self.assertEqual(len(baseline.calls), 1)
        call = baseline.calls[0]
        self.assertEqual(call["prompt"], prompt)  # original, unshrunk
        self.assertIsNone(call["system"])
        self.assertIsNone(call["max_tokens"])
        self.assertEqual(meta["baseline"]["saved_output_tokens"], 200 - 50)
        self.assertEqual(meta["baseline"]["saved_total_tokens"], (200 + 14) - (50 + 10))
        self.assertEqual(meta["baseline"]["model"], PRIMARY)  # primary model, not a smaller one

    def test_baseline_failure_keeps_answer(self):
        baseline = FakeProvider(PRIMARY, error=ProviderError("HTTP 500: boom"))
        backend, _, _ = make_backend(baseline=baseline)
        result = backend.chat(ChatRequest(prompt="Explain DNS", measure_baseline=True))
        self.assertTrue(result["answer"])
        self.assertIn("error", result["meta"]["baseline"])
        self.assertNotIn("boom", json.dumps(result))


class ErrorMappingTests(unittest.TestCase):
    def assert_clean(self, text):
        for leak in (SENTINEL_KEY, "Traceback", "openrouter", "Errno", "Bearer", "HTTP 401"):
            self.assertNotIn(leak, text)

    def test_no_key_is_503_plain(self):
        backend = Backend(Config(api_key=""), log_stream=io.StringIO(), quiet=True)
        with self.assertRaises(ClientError) as ctx:
            backend.chat(ChatRequest(prompt="Explain DNS"))
        self.assertEqual(ctx.exception.status, 503)
        self.assertEqual(ctx.exception.message, MSG_NOT_CONFIGURED)

    def test_provider_errors_map_to_plain_messages(self):
        cases = [
            (ProviderError("Could not reach live provider at https://openrouter.ai/api/v1: "
                           "[Errno -2] Name or service not known"), 502, MSG_UNREACHABLE),
            (ProviderError(f"Live provider returned HTTP 401: Invalid key {SENTINEL_KEY}"),
             502, MSG_UNREACHABLE),
            (ProviderError("Live provider timed out after 60s."), 502, MSG_UNREACHABLE),
            (ProviderError("Live provider returned HTTP 429: slow down"), 429, MSG_RATE_LIMITED),
        ]
        for error, status, message in cases:
            with self.subTest(error=str(error)):
                small = FakeProvider(PRIMARY, error=error)
                backend, _, _ = make_backend(primary=small)
                with self.assertRaises(ClientError) as ctx:
                    backend.chat(ChatRequest(prompt="Explain DNS"))
                self.assertEqual((ctx.exception.status, ctx.exception.message), (status, message))
                self.assert_clean(ctx.exception.message)

    def test_invalid_requests_are_400(self):
        bad = [
            b"not json",
            b"[1, 2]",
            b'{"prompt": ""}',
            b'{"prompt": "   "}',
            b'{"prompt": 5}',
            b'{"prompt": "hi", "mode": "huge"}',
            b'{"prompt": "hi", "session_id": "x"}',
            b'{"prompt": "hi", "stream": "yes"}',
            b'{"prompt": "hi", "api_key": "anything"}',
            b'{"prompt": "hi", "model": "gpt-4o"}',
            json.dumps({"prompt": "x" * 4001}).encode(),
        ]
        for body in bad:
            with self.subTest(body=body[:40]):
                with self.assertRaises(ClientError) as ctx:
                    parse_chat_request(body)
                self.assertEqual(ctx.exception.status, 400)

    def test_forest_alias_and_defaults(self):
        req = parse_chat_request(b'{"prompt": "hi", "mode": "forest"}')
        self.assertEqual(req.mode, "full")
        self.assertTrue(req.stream)
        self.assertFalse(req.measure_baseline)

    def test_config_rejects_wildcard_origin_and_bad_values(self):
        for env in ({"GREENSEARCH_BACKEND_ORIGIN": "*"},
                    {"GREENSEARCH_BACKEND_ORIGIN": "http://localhost:8000,*"},
                    {"GREENSEARCH_CASCADE_THRESHOLD": "0.5"},
                    {"GREENSEARCH_CASCADE_THRESHOLD": "abc"},
                    {"GREENSEARCH_RATE_LIMIT_PER_HOUR": "-1"}):
            with self.subTest(env=env):
                with self.assertRaises(ValueError):
                    Config.from_env(env)

    def test_config_defaults(self):
        cfg = Config.from_env({})
        self.assertFalse(cfg.configured)
        self.assertEqual(cfg.base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(cfg.model, "qwen/qwen3-8b")
        self.assertEqual(cfg.escalation_model, "qwen/qwen3-8b")
        self.assertFalse(cfg.cascade_enabled)
        self.assertFalse(hasattr(cfg, "model_4b"))
        self.assertEqual(cfg.cascade_threshold, -1.0)
        self.assertEqual(cfg.rate_limit_per_hour, 100)
        self.assertEqual(cfg.allowed_origins, ("http://localhost:8000", "http://127.0.0.1:8000"))
        self.assertFalse(cfg.debug_log)
        cfg = Config.from_env({"GREENSEARCH_MODEL": "other/model"})
        self.assertEqual((cfg.model, cfg.escalation_model), ("other/model", "other/model"))
        self.assertFalse(cfg.cascade_enabled)
        cfg = Config.from_env({"GREENSEARCH_ESCALATION_MODEL": "big/model"})
        self.assertEqual((cfg.model, cfg.escalation_model), ("qwen/qwen3-8b", "big/model"))
        self.assertTrue(cfg.cascade_enabled)
        # The old 4B/8B variables are no longer read.
        cfg = Config.from_env({"GREENSEARCH_MODEL_4B": "qwen/qwen3-4b",
                               "GREENSEARCH_MODEL_8B": "x/y"})
        self.assertEqual((cfg.model, cfg.escalation_model), ("qwen/qwen3-8b", "qwen/qwen3-8b"))

    def test_prompts_not_logged_by_default(self):
        log = io.StringIO()
        backend, _, _ = make_backend()
        backend.log_stream, backend.quiet = log, False
        backend.chat(ChatRequest(prompt="SECRET-PROMPT-TEXT about DNS"))
        self.assertNotIn("SECRET-PROMPT-TEXT", log.getvalue())
        backend.config.debug_log = True
        result = backend.chat(ChatRequest(prompt="SECRET-PROMPT-TEXT about DNS"))
        self.assertIn("SECRET-PROMPT-TEXT", log.getvalue())  # stderr-style stream only
        self.assertNotIn("SECRET-PROMPT-TEXT", json.dumps(result["meta"]))


class RateLimiterTests(unittest.TestCase):
    def test_triggers_and_window_expires(self):
        now = [1000.0]
        limiter = RateLimiter(3, window_seconds=3600, clock=lambda: now[0])
        self.assertEqual([limiter.allow("1.2.3.4") for _ in range(4)], [True, True, True, False])
        self.assertTrue(limiter.allow("5.6.7.8"))  # per client
        now[0] += 3600
        self.assertTrue(limiter.allow("1.2.3.4"))

    def test_zero_disables(self):
        limiter = RateLimiter(0)
        self.assertTrue(all(limiter.allow("ip") for _ in range(500)))


class SSEFormatTests(unittest.TestCase):
    def test_build_and_parse_sample_stream(self):
        answer = "DNS is the phone book.\nIt maps names to numbers — \"quotes\" too."
        chunks = chunk_text(answer)
        self.assertEqual("".join(chunks), answer)
        stream = b"".join(
            [sse_event("chunk", {"text": c}) for c in chunks]
            + [sse_event("meta", {"mode": "sprout", "escalated": False}), sse_event("done", {})]
        ).decode("utf-8")
        # Wire format: every event is "event: X\ndata: <one line of JSON>\n\n".
        blocks = stream.split("\n\n")
        self.assertEqual(blocks[-1], "")
        for block in blocks[:-1]:
            self.assertRegex(block, r"\Aevent: (chunk|meta|done)\ndata: \{.*\}\Z")
        events = parse_sse(stream)
        self.assertEqual([e for e, _ in events], ["chunk"] * len(chunks) + ["meta", "done"])
        self.assertEqual("".join(d["text"] for e, d in events if e == "chunk"), answer)
        self.assertEqual(events[-2][1], {"mode": "sprout", "escalated": False})

    def test_parse_ignores_comments_and_crlf(self):
        text = ': keep-alive\r\n\r\nevent: chunk\r\ndata: {"text":"a"}\r\n\r\n'
        self.assertEqual(parse_sse(text), [("chunk", {"text": "a"})])


class HTTPTests(unittest.TestCase):
    """Real HTTP over loopback against a server with fake providers."""

    def start(self, backend):
        server = make_server(backend, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def request(self, port, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        payload = json.dumps(body).encode() if isinstance(body, dict) else body
        hdrs = {"Content-Type": "application/json"} if payload is not None else {}
        hdrs.update(headers or {})
        conn.request(method, path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        return resp, data

    def test_sse_stream_end_to_end(self):
        backend, small, _ = make_backend()
        port = self.start(backend)
        resp, data = self.request(port, "POST", "/api/chat",
                                  {"prompt": "Explain DNS", "session_id": SESSION},
                                  {"Origin": "http://localhost:8000"})
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.getheader("Content-Type").startswith("text/event-stream"))
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), "http://localhost:8000")
        events = parse_sse(data)
        names = [e for e, _ in events]
        self.assertGreater(names.count("chunk"), 1)
        self.assertEqual(names[-2:], ["meta", "done"])
        text = "".join(d["text"] for e, d in events if e == "chunk")
        self.assertEqual(text, apply_brevity(LONG_ANSWER, "sprout"))
        meta = events[-2][1]
        for k in ("mode", "model", "escalated", "cache_hit", "input_tokens",
                  "output_tokens", "latency_ms"):
            self.assertIn(k, meta)
        self.assertEqual(meta["delivery"], "sse")
        self.assertFalse(meta["provider_streaming"])
        self.assertNotIn(SENTINEL_KEY, data)

    def test_json_fallback(self):
        backend, _, _ = make_backend()
        port = self.start(backend)
        resp, data = self.request(port, "POST", "/api/chat", {"prompt": "Explain DNS", "stream": False})
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.getheader("Content-Type").startswith("application/json"))
        obj = json.loads(data)
        self.assertEqual(obj["meta"]["delivery"], "json")
        self.assertTrue(obj["answer"])

    def test_cors_rejects_unlisted_origin(self):
        backend, small, _ = make_backend()
        port = self.start(backend)
        evil = {"Origin": "https://evil.example"}
        resp, data = self.request(port, "OPTIONS", "/api/chat", None, evil)
        self.assertEqual(resp.status, 403)
        self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))
        resp, data = self.request(port, "POST", "/api/chat", {"prompt": "Explain DNS"}, evil)
        self.assertEqual(resp.status, 403)
        self.assertEqual(json.loads(data), {"error": MSG_ORIGIN})
        self.assertIsNone(resp.getheader("Access-Control-Allow-Origin"))
        self.assertEqual(small.calls, [])  # rejected before any model call

    def test_cors_allows_listed_origin_never_wildcard(self):
        backend, _, _ = make_backend(allowed_origins=("https://app.example",))
        port = self.start(backend)
        resp, _ = self.request(port, "OPTIONS", "/api/chat", None, {
            "Origin": "https://app.example", "Access-Control-Request-Method": "POST"})
        self.assertEqual(resp.status, 204)
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), "https://app.example")
        self.assertIn("Content-Type", resp.getheader("Access-Control-Allow-Headers"))
        resp, _ = self.request(port, "OPTIONS", "/api/chat", None, {"Origin": "http://localhost:8000"})
        self.assertEqual(resp.status, 403)

    def test_rate_limit_triggers_over_http(self):
        backend, small, _ = make_backend(rate_limit_per_hour=2)
        port = self.start(backend)
        statuses = []
        for _ in range(3):
            resp, data = self.request(port, "POST", "/api/chat", {"prompt": "Explain DNS"})
            statuses.append(resp.status)
        self.assertEqual(statuses, [200, 200, 429])
        self.assertEqual(json.loads(data), {"error": MSG_RATE_LIMITED})
        self.assertEqual(resp.getheader("Retry-After"), "3600")
        self.assertEqual(len(small.calls), 2)

    def test_no_key_over_http_and_health(self):
        backend = Backend(Config(api_key=""), log_stream=io.StringIO(), quiet=True)
        port = self.start(backend)
        resp, data = self.request(port, "POST", "/api/chat", {"prompt": "Explain DNS"})
        self.assertEqual(resp.status, 503)
        self.assertEqual(json.loads(data), {"error": MSG_NOT_CONFIGURED})
        resp, data = self.request(port, "GET", "/api/health")
        self.assertEqual(resp.status, 200)
        health = json.loads(data)
        self.assertFalse(health["configured"])
        self.assertEqual(health["model"], "qwen/qwen3-8b")
        self.assertEqual(health["escalation_model"], "qwen/qwen3-8b")
        self.assertFalse(health["cascade_enabled"])
        self.assertNotIn("model_4b", health)
        self.assertNotIn("model_8b", health)

    def test_error_bodies_never_contain_key_or_detail(self):
        small = FakeProvider(PRIMARY, error=ProviderError(
            f"Live provider returned HTTP 401: bad key {SENTINEL_KEY} at https://openrouter.ai"))
        backend, _, _ = make_backend(primary=small)
        port = self.start(backend)
        resp, data = self.request(port, "POST", "/api/chat", {"prompt": "Explain DNS"})
        self.assertEqual(resp.status, 502)
        self.assertEqual(json.loads(data), {"error": MSG_UNREACHABLE})
        resp, health = self.request(port, "GET", "/api/health")
        for body in (data, health):
            self.assertNotIn(SENTINEL_KEY, body)
            self.assertNotIn("Traceback", body)
        self.assertTrue(json.loads(health)["configured"])

    def test_unexpected_exception_is_plain_500(self):
        def boom(model):
            raise RuntimeError("internal detail /home/secret")
        backend = Backend(Config(api_key=SENTINEL_KEY), provider_factory=boom,
                          log_stream=io.StringIO(), quiet=True)
        port = self.start(backend)
        resp, data = self.request(port, "POST", "/api/chat", {"prompt": "Explain DNS"})
        self.assertEqual(resp.status, 500)
        self.assertNotIn("internal detail", data)
        self.assertNotIn("Traceback", data)

    def test_bad_body_and_unknown_path(self):
        backend, _, _ = make_backend()
        port = self.start(backend)
        resp, data = self.request(port, "POST", "/api/chat", b"{nope")
        self.assertEqual(resp.status, 400)
        self.assertEqual(json.loads(data), {"error": "Request body must be valid JSON"})
        resp, _ = self.request(port, "POST", "/api/other", {"prompt": "x"})
        self.assertEqual(resp.status, 404)


class EntryPointAndSiteTests(unittest.TestCase):
    def test_help_lists_env_vars(self):
        out = subprocess.run([sys.executable, str(ROOT / "server" / "app.py"), "--help"],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0)
        for name in ("GREENSEARCH_API_KEY", "GREENSEARCH_BASE_URL", "GREENSEARCH_MODEL",
                     "GREENSEARCH_ESCALATION_MODEL",
                     "GREENSEARCH_CASCADE_THRESHOLD", "GREENSEARCH_BACKEND_ORIGIN",
                     "GREENSEARCH_RATE_LIMIT_PER_HOUR", "GREENSEARCH_DEBUG_LOG", "PORT"):
            self.assertIn(name, out.stdout)
        self.assertIn("qwen/qwen3-8b", out.stdout)
        self.assertNotIn("MODEL_4B", out.stdout)
        self.assertNotIn("qwen3-4b", out.stdout)

    def test_website_live_mode_off_by_default(self):
        html = (ROOT / "website" / "index.html").read_text(encoding="utf-8")
        toggle = re.search(r'<input[^>]*id="live-toggle"[^>]*>', html)
        baseline = re.search(r'<input[^>]*id="live-baseline"[^>]*>', html)
        self.assertIsNotNone(toggle)
        self.assertIsNotNone(baseline)
        self.assertNotIn("checked", toggle.group(0))
        self.assertNotIn("checked", baseline.group(0))
        self.assertIn("greensearch-live-backend-url", html)
        self.assertIn("http://localhost:8000/api/chat", html)
        self.assertIn("Live mode sends your prompt to the backend you configured", html)
        self.assertIn("STORE_KEY='greensearch-demo-v1'", html)
        # The page must never handle a provider key.
        self.assertNotIn("Authorization", html)
        self.assertNotRegex(html, r"api_key|apiKey|GREENSEARCH_API_KEY")

    def test_env_example_has_no_real_key(self):
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        match = re.search(r"^GREENSEARCH_API_KEY=(.*)$", text, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertNotRegex(match.group(1), r"sk-[A-Za-z0-9]{10,}")
        self.assertIn(match.group(1).strip(), ("", "replace-me"))
        self.assertRegex(text, r"(?m)^GREENSEARCH_MODEL=qwen/qwen3-8b$")
        self.assertNotIn("MODEL_4B", text)


if __name__ == "__main__":
    unittest.main()
