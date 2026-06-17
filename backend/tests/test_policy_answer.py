"""
Tests for the assistant-style policy Q&A endpoint (POST /policy/answer) and its
confidence logic.

All external AI calls are mocked — no live Anthropic or OpenAI usage. Retrieval
and the Anthropic client are patched so the tests are deterministic and offline.
"""

import pytest

from app.core.database import get_db
from app.main import app
from app.services import policy_answer
from app.services.anthropic_client import AnthropicNotConfigured
from app.services.policy_answer import (
    CONFLICT_SUFFIX,
    NO_ANSWER_MESSAGE,
    PolicyAnswerService,
    _build_context,
    _dedupe_chunks,
    _derive_confidence,
)
from app.services.retrieval import RetrievedChunk


# ── Test helpers ──────────────────────────────────────────────────────────────
def make_chunk(text: str, similarity: float) -> RetrievedChunk:
    return RetrievedChunk(
        document_id="policy1",
        page_number=1,
        section="2.1",
        chunk_text=text,
        similarity=similarity,
        confidence="high" if similarity >= 0.5 else "low",
    )


class _FakeToolBlock:
    type = "tool_use"

    def __init__(self, name: str, payload: dict):
        self.name = name
        self.input = payload


class _FakeResponse:
    stop_reason = "tool_use"

    def __init__(self, payload: dict):
        self.content = [_FakeToolBlock("record_answer", payload)]


class _FakeMessages:
    def __init__(self, payload: dict | None, exc: Exception | None):
        self._payload = payload
        self._exc = exc

    async def create(self, **_kwargs):
        if self._exc is not None:
            raise self._exc
        return _FakeResponse(self._payload)


class _FakeAnthropic:
    def __init__(self, payload: dict | None = None, exc: Exception | None = None):
        self.messages = _FakeMessages(payload, exc)


@pytest.fixture(autouse=True)
def _override_db():
    """Avoid touching a real database — retrieval is mocked, so the session is unused."""

    async def _fake_db():
        yield None

    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(get_db, None)


def patch_retrieval(monkeypatch, chunks=None, exc=None):
    async def _search(*_args, **_kwargs):
        if exc is not None:
            raise exc
        return list(chunks or [])

    monkeypatch.setattr(policy_answer.retrieval_service, "search", _search)


def patch_anthropic(monkeypatch, payload=None, exc=None):
    monkeypatch.setattr(
        policy_answer,
        "get_anthropic_client",
        lambda: _FakeAnthropic(payload=payload, exc=exc),
    )


# ── Unit: confidence derivation ────────────────────────────────────────────────
def test_confidence_high_for_strong_clear_match():
    chunks = [make_chunk("Meals are capped at $75/day.", 0.72)]
    assert (
        _derive_confidence(
            chunks=chunks, answer_found=True, requires_combining=False, conflicting=False
        )
        == "high"
    )


def test_confidence_medium_when_combining_required():
    chunks = [make_chunk("...", 0.72)]
    assert (
        _derive_confidence(
            chunks=chunks, answer_found=True, requires_combining=True, conflicting=False
        )
        == "medium"
    )


def test_confidence_medium_for_moderate_similarity():
    chunks = [make_chunk("...", 0.40)]
    assert (
        _derive_confidence(
            chunks=chunks, answer_found=True, requires_combining=False, conflicting=False
        )
        == "medium"
    )


def test_confidence_low_when_not_found_or_conflicting_or_empty():
    chunks = [make_chunk("...", 0.72)]
    assert (
        _derive_confidence(
            chunks=chunks, answer_found=False, requires_combining=False, conflicting=False
        )
        == "low"
    )
    assert (
        _derive_confidence(
            chunks=chunks, answer_found=True, requires_combining=False, conflicting=True
        )
        == "low"
    )
    assert (
        _derive_confidence(
            chunks=[], answer_found=True, requires_combining=False, conflicting=False
        )
        == "low"
    )


# ── Unit: dedupe + context budgeting ───────────────────────────────────────────
def test_dedupe_drops_identical_chunks():
    chunks = [make_chunk("same", 0.6), make_chunk("same", 0.5), make_chunk("other", 0.4)]
    unique = _dedupe_chunks(chunks)
    assert [c.chunk_text for c in unique] == ["same", "other"]


def test_build_context_truncates_and_omits_metadata():
    long_text = "word " * 1000
    ctx = _build_context([make_chunk(long_text, 0.6)])
    assert len(ctx) <= policy_answer.MAX_CHUNK_CHARS + 10
    # No document ids / sections / similarity leaked into the prompt context.
    assert "policy1" not in ctx
    assert "similarity" not in ctx


# ── Service: fallbacks without hitting Claude ──────────────────────────────────
async def test_service_no_chunks_returns_fallback(monkeypatch):
    patch_retrieval(monkeypatch, chunks=[])
    # Anthropic must not even be called when there is no context.
    patch_anthropic(monkeypatch, exc=AssertionError("Claude should not be called"))

    result = await PolicyAnswerService().answer(db=None, question="anything?")
    assert result.answer == NO_ANSWER_MESSAGE
    assert result.confidence == "low"


# ── Route: validation ──────────────────────────────────────────────────────────
async def test_empty_question_rejected(client):
    resp = await client.post("/api/v1/policy/answer", json={"question": ""})
    assert resp.status_code == 422


async def test_whitespace_question_rejected(client):
    resp = await client.post("/api/v1/policy/answer", json={"question": "    "})
    assert resp.status_code == 422


async def test_overlong_question_rejected(client):
    resp = await client.post(
        "/api/v1/policy/answer", json={"question": "x" * 5000}
    )
    assert resp.status_code == 422


# ── Route: happy paths ─────────────────────────────────────────────────────────
async def test_valid_question_high_confidence(client, monkeypatch):
    patch_retrieval(monkeypatch, chunks=[make_chunk("Meals capped at $75/day.", 0.8)])
    patch_anthropic(
        monkeypatch,
        payload={
            "answer_found": True,
            "answer": "Employees can claim up to $75 per day for meals.",
            "requires_combining": False,
            "conflicting": False,
        },
    )
    resp = await client.post(
        "/api/v1/policy/answer", json={"question": "What is the meal limit?"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "answer": "Employees can claim up to $75 per day for meals.",
        "confidence": "high",
    }
    # Public response stays small — no retrieval internals leak.
    assert set(body.keys()) == {"answer", "confidence"}


async def test_response_never_exposes_references_or_chunks(client, monkeypatch):
    """The public contract must not surface any retrieval/citation internals."""
    patch_retrieval(monkeypatch, chunks=[make_chunk("Meals capped at $75/day.", 0.8)])
    patch_anthropic(
        monkeypatch,
        payload={
            "answer_found": True,
            "answer": "Employees can claim up to $75 per day for meals.",
            "requires_combining": False,
            "conflicting": False,
        },
    )
    resp = await client.post(
        "/api/v1/policy/answer", json={"question": "What is the meal limit?"}
    )
    assert resp.status_code == 200
    body = resp.json()
    forbidden = {
        "results",
        "chunks",
        "source_chunks",
        "citations",
        "policy_citations",
        "references",
        "documents",
        "document_id",
        "page_number",
        "section",
        "similarity",
        "chunk_text",
    }
    assert forbidden.isdisjoint(body.keys())
    # The answer text itself carries no inline citation markers like "[1]".
    assert "[1]" not in body["answer"]


async def test_valid_question_medium_confidence(client, monkeypatch):
    patch_retrieval(monkeypatch, chunks=[make_chunk("Hotel rules vary by city.", 0.40)])
    patch_anthropic(
        monkeypatch,
        payload={
            "answer_found": True,
            "answer": "Hotel limits depend on the destination city.",
            "requires_combining": True,
            "conflicting": False,
        },
    )
    resp = await client.post(
        "/api/v1/policy/answer", json={"question": "What is the hotel limit?"}
    )
    assert resp.status_code == 200
    assert resp.json()["confidence"] == "medium"


async def test_no_answer_uses_fallback_message(client, monkeypatch):
    patch_retrieval(monkeypatch, chunks=[make_chunk("Unrelated travel text.", 0.22)])
    patch_anthropic(
        monkeypatch,
        payload={
            "answer_found": False,
            "answer": "The policies do not mention this.",
            "requires_combining": False,
            "conflicting": False,
        },
    )
    resp = await client.post(
        "/api/v1/policy/answer", json={"question": "Are pet expenses covered?"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == NO_ANSWER_MESSAGE
    assert body["confidence"] == "low"


async def test_conflicting_policy_flags_inconsistency(client, monkeypatch):
    patch_retrieval(monkeypatch, chunks=[make_chunk("Alcohol may be claimed.", 0.7)])
    patch_anthropic(
        monkeypatch,
        payload={
            "answer_found": True,
            "answer": "Some passages allow alcohol while others prohibit it.",
            "requires_combining": False,
            "conflicting": True,
        },
    )
    resp = await client.post(
        "/api/v1/policy/answer", json={"question": "Are alcohol expenses reimbursable?"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"].endswith(CONFLICT_SUFFIX)
    assert body["confidence"] == "low"


# ── Route: failure handling (no internals leaked) ──────────────────────────────
async def test_ai_provider_not_configured_returns_503(client, monkeypatch):
    patch_retrieval(monkeypatch, chunks=[make_chunk("text", 0.7)])
    monkeypatch.setattr(
        policy_answer,
        "get_anthropic_client",
        lambda: (_ for _ in ()).throw(AnthropicNotConfigured("no key")),
    )
    resp = await client.post(
        "/api/v1/policy/answer", json={"question": "What is the meal limit?"}
    )
    assert resp.status_code == 503
    assert "key" not in resp.json()["detail"].lower()


async def test_ai_provider_error_returns_502(client, monkeypatch):
    patch_retrieval(monkeypatch, chunks=[make_chunk("text", 0.7)])
    # A generic provider/API error (not RuntimeError) → handled as a bad gateway.
    patch_anthropic(monkeypatch, exc=Exception("anthropic 500 internal"))
    resp = await client.post(
        "/api/v1/policy/answer", json={"question": "What is the meal limit?"}
    )
    assert resp.status_code == 502
    assert "anthropic" not in resp.json()["detail"].lower()


async def test_retrieval_unavailable_returns_503(client, monkeypatch):
    patch_retrieval(monkeypatch, exc=RuntimeError("OPENAI_API_KEY is not set"))
    resp = await client.post(
        "/api/v1/policy/answer", json={"question": "What is the meal limit?"}
    )
    assert resp.status_code == 503
    assert "openai" not in resp.json()["detail"].lower()


async def test_database_failure_returns_502(client, monkeypatch):
    patch_retrieval(monkeypatch, exc=ValueError("connection to server failed"))
    resp = await client.post(
        "/api/v1/policy/answer", json={"question": "What is the meal limit?"}
    )
    assert resp.status_code == 502
    assert "connection" not in resp.json()["detail"].lower()
