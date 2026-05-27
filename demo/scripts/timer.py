"""Shared timing utilities for demo rehearsal scripts.

Mirrors LatencyBreakdown shape from guardrails/api/schemas.py.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator


class DemoTimeoutError(RuntimeError):
    """Raised when a demo stage exceeds its time budget."""

    pass


@dataclass
class Timer:
    """Simple wall-clock timer with millisecond precision."""

    start_time: float = field(init=False)
    end_time: float | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.start_time = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds since start (or until end_time if stopped)."""
        end = self.end_time if self.end_time is not None else time.perf_counter()
        return (end - self.start_time) * 1000

    def stop(self) -> float:
        """Stop the timer and return elapsed milliseconds."""
        self.end_time = time.perf_counter()
        return self.elapsed_ms


@dataclass
class StageTimer:
    """Accumulates multiple named stages into a LatencyBreakdown-style dict."""

    stages: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def stage(self, name: str) -> Generator[None, None, None]:
        """Context manager to time a named stage."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = (time.perf_counter() - t0) * 1000

    def add(self, name: str, elapsed_ms: float) -> None:
        """Manually add a stage timing in milliseconds."""
        self.stages[name] = elapsed_ms

    def total_ms(self) -> float:
        """Sum of all stage timings in milliseconds."""
        return sum(self.stages.values())

    def to_dict(self) -> dict[str, float]:
        """Return a dict like {"input_guard": 12.3, "total": 45.0}."""
        result: dict[str, Any] = dict(self.stages)
        result["total"] = self.total_ms()
        return result

    def __repr__(self) -> str:
        lines = [f"  {k}: {v:.1f}ms" for k, v in self.stages.items()]
        return "StageTimer\n" + "\n".join(lines) + f"\n  total: {self.total_ms():.1f}ms"


def assert_under_limit(total_seconds: float, limit_seconds: float = 480) -> None:
    """Raise DemoTimeoutError if total_seconds exceeds limit_seconds (default 8min = 480s).

    Args:
        total_seconds: Elapsed wall-clock time in seconds.
        limit_seconds: Maximum allowed time (default 480 = 8 minutes).

    Raises:
        DemoTimeoutError: If total_seconds > limit_seconds.
    """
    if total_seconds > limit_seconds:
        raise DemoTimeoutError(f"Demo exceeded time limit: {format_duration(total_seconds)} > {format_duration(limit_seconds)}")


def format_duration(seconds: float) -> str:
    """Format seconds into a human-friendly string like '4m 32s' or '45s'.

    Args:
        seconds: Duration in seconds.

    Returns:
        Human-readable duration string.
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"
