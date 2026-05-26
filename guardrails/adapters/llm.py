"""
LLMProvider protocol and AnthropicProvider implementation.

`complete()` returns the response text string. `complete_with_tools()` returns
the raw Anthropic Message object for callers that need tool-use parsing.

The protocol uses @runtime_checkable so isinstance() works at runtime.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

DEFAULT_MODEL = "claude-sonnet-4-6-20251105"
JUDGE_MODEL = "claude-haiku-4-5-20251001"


@runtime_checkable
class LLMProvider(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str: ...

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> Any: ...


class AnthropicProvider:
    def __init__(
        self,
        client=None,
        model: str = DEFAULT_MODEL,
        timeout: float = 10.0,
    ) -> None:
        self.client = client if client is not None else self._create_client(timeout)
        self.model = model
        self.timeout = timeout

    @staticmethod
    def _create_client(timeout: float = 10.0):
        from anthropic import Anthropic

        return Anthropic(timeout=timeout)

    def complete(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        try:
            response = self.client.messages.create(
                model=model or self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,
                timeout=self.timeout,
            )
            return response.content[0].text
        except Exception:
            return ""

    def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any] | None = None,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "tools": tools,
            "messages": messages,
            "timeout": self.timeout,
        }
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if system is not None:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        try:
            return self.client.messages.create(**kwargs)
        except Exception:
            return None
