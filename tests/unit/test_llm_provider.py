"""
Unit tests for LLMProvider protocol and AnthropicProvider.

Contract tests use mocked Anthropic client — no API calls.
"""

from unittest.mock import MagicMock

from guardrails.adapters import AnthropicProvider, LLMProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_provider(
    response_text: str = "Hello",
) -> AnthropicProvider:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = response_text
    mock_response.content = [mock_content]
    mock_client.messages.create.return_value = mock_response
    return AnthropicProvider(client=mock_client)


# ---------------------------------------------------------------------------
# Protocol check
# ---------------------------------------------------------------------------


def test_provider_protocol_runtime_check():
    assert isinstance(_make_mock_provider(), LLMProvider)


# ---------------------------------------------------------------------------
# Complete — happy path
# ---------------------------------------------------------------------------


def test_complete_returns_text():
    provider = _make_mock_provider(response_text="Olá, como posso ajudar?")
    result = provider.complete(messages=[{"role": "user", "content": "Qual o saldo?"}])
    assert result == "Olá, como posso ajudar?"


def test_complete_passes_model():
    provider = _make_mock_provider()
    provider.complete(
        messages=[{"role": "user", "content": "Hi"}],
        model="custom-model",
    )
    provider.client.messages.create.assert_called_once()
    kwargs = provider.client.messages.create.call_args[1]
    assert kwargs["model"] == "custom-model"


def test_complete_passes_temperature():
    provider = _make_mock_provider()
    provider.complete(
        messages=[{"role": "user", "content": "Hi"}],
        temperature=0.7,
    )
    kwargs = provider.client.messages.create.call_args[1]
    assert kwargs["temperature"] == 0.7


def test_complete_passes_max_tokens():
    provider = _make_mock_provider()
    provider.complete(
        messages=[{"role": "user", "content": "Hi"}],
        max_tokens=2048,
    )
    kwargs = provider.client.messages.create.call_args[1]
    assert kwargs["max_tokens"] == 2048


def test_complete_passes_messages():
    provider = _make_mock_provider()
    msgs = [{"role": "user", "content": "Test"}]
    provider.complete(messages=msgs)
    kwargs = provider.client.messages.create.call_args[1]
    assert kwargs["messages"] == msgs


# ---------------------------------------------------------------------------
# Complete — error path
# ---------------------------------------------------------------------------


def test_complete_fail_closed_on_api_exception():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("API failure")
    provider = AnthropicProvider(client=mock_client)
    result = provider.complete(messages=[{"role": "user", "content": "Hi"}])
    assert result == ""


# ---------------------------------------------------------------------------
# Complete with tools — happy path
# ---------------------------------------------------------------------------


def test_complete_with_tools_returns_raw_response():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.input = {"verdict": "pass", "rule_violated": None, "reasoning": "OK"}
    mock_response.content = [mock_tool_use]
    mock_response.stop_reason = "tool_use"
    mock_client.messages.create.return_value = mock_response
    provider = AnthropicProvider(client=mock_client)

    response = provider.complete_with_tools(
        messages=[{"role": "user", "content": "Evaluate this"}],
        tools=[{"name": "test_tool", "input_schema": {"type": "object", "properties": {}}}],
        tool_choice={"type": "tool", "name": "test_tool"},
    )
    assert response is mock_response
    assert response.content[0].input["verdict"] == "pass"


def test_complete_with_tools_passes_max_tokens():
    provider = _make_mock_provider()
    provider.complete_with_tools(
        messages=[{"role": "user", "content": "Hi"}],
        tools=[],
        max_tokens=1024,
    )
    kwargs = provider.client.messages.create.call_args[1]
    assert kwargs["max_tokens"] == 1024


def test_complete_with_tools_defaults_max_tokens():
    provider = _make_mock_provider()
    provider.complete_with_tools(
        messages=[{"role": "user", "content": "Hi"}],
        tools=[],
    )
    kwargs = provider.client.messages.create.call_args[1]
    assert kwargs["max_tokens"] == 512


def test_complete_with_tools_passes_system():
    provider = _make_mock_provider()
    provider.complete_with_tools(
        messages=[{"role": "user", "content": "Hi"}],
        tools=[],
        system="You are a judge.",
    )
    kwargs = provider.client.messages.create.call_args[1]
    assert "system" in kwargs
    assert kwargs["system"][0]["text"] == "You are a judge."
    assert kwargs["system"][0]["cache_control"]["type"] == "ephemeral"


# ---------------------------------------------------------------------------
# Complete with tools — error path
# ---------------------------------------------------------------------------


def test_complete_with_tools_fail_closed_on_exception():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ConnectionError("Network error")
    provider = AnthropicProvider(client=mock_client)
    result = provider.complete_with_tools(
        messages=[{"role": "user", "content": "Hi"}],
        tools=[],
    )
    assert result is None


# ---------------------------------------------------------------------------
# Default model
# ---------------------------------------------------------------------------


def test_default_model_used_when_none_passed():
    provider = _make_mock_provider()
    provider.complete(messages=[{"role": "user", "content": "Hi"}])
    kwargs = provider.client.messages.create.call_args[1]
    assert kwargs["model"] == provider.model
