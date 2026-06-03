"""Basic in-memory metrics.

A deliberately simple implementation (with no external dependencies) that exposes
cumulative counters and the last workflow run. It serves as a foundation for a
future Prometheus integration by replacing this module with an adapter.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Metrics:
    """Thread-safe registry of system counters and events."""

    _counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _last_run_at: datetime | None = None
    _last_run_status: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def record_run(self, status: str, at: datetime) -> None:
        with self._lock:
            self._last_run_at = at
            self._last_run_status = status

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
                "last_run_status": self._last_run_status,
            }


# Global per-process metrics singleton.
metrics = Metrics()
