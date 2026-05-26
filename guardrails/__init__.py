import importlib


def __getattr__(name):
    if name in ("EnhancedLLMGuardrails", "CustomGuardrails"):
        module = importlib.import_module("guardrails_legacy")
        return getattr(module, name)
    raise AttributeError(f"module 'guardrails' has no attribute {name!r}")


__all__ = [
    "CustomGuardrails",
    "EnhancedLLMGuardrails",
]
