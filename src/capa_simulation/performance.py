# Purpose: Lightweight in-process timing helpers for optional UI diagnostics.

"""Lightweight in-process timing helpers for optional UI diagnostics."""

from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class PerformanceTrace:
    """Record sequential phase durations without logging input or business data."""

    _started_at: float = field(default_factory=perf_counter)
    _checkpoint_at: float = field(init=False)
    _phases: list[tuple[str, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._checkpoint_at = self._started_at

    def mark(self, phase: str) -> None:
        now = perf_counter()
        self._phases.append((phase, now - self._checkpoint_at))
        self._checkpoint_at = now

    @property
    def total_seconds(self) -> float:
        return perf_counter() - self._started_at

    def rows(self) -> list[dict[str, str]]:
        rows = [{"단계": phase, "시간": f"{duration:.3f}초"} for phase, duration in self._phases]
        rows.append({"단계": "합계", "시간": f"{self.total_seconds:.3f}초"})
        return rows
