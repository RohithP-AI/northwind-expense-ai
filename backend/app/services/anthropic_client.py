"""
Shared, lazily-constructed Anthropic client.

Importing this module never requires a key; the client is built on first use so
the app can boot (and unrelated endpoints can run) without ANTHROPIC_API_KEY.
Callers that need Claude should call `get_anthropic_client()` and let the
RuntimeError propagate to a 503 if the key is missing.
"""

from anthropic import AsyncAnthropic

from app.core.config import settings


class AnthropicNotConfigured(RuntimeError):
    """Raised when a Claude-backed feature is used without ANTHROPIC_API_KEY."""


_client: AsyncAnthropic | None = None


def get_anthropic_client() -> AsyncAnthropic:
    global _client
    if not settings.ANTHROPIC_API_KEY:
        raise AnthropicNotConfigured(
            "ANTHROPIC_API_KEY is not set — this feature requires the Claude API."
        )
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def extract_tool_use(response, tool_name: str) -> dict:
    """
    Pull the input of the first `tool_use` block matching `tool_name`.

    Used for schema-constrained JSON: we force the model to call a tool whose
    input_schema is our target shape, then read that structured input back.
    """
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return dict(block.input)
    raise ValueError(
        f"Claude response contained no '{tool_name}' tool_use block "
        f"(stop_reason={getattr(response, 'stop_reason', '?')})."
    )
