"""Common compose functions for merging overlapping clip outputs."""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def compose_last(deltas: list[T]) -> T:
    """Return the last (most recently added) delta. Safe generic default."""
    return deltas[-1]


def compose_first(deltas: list[T]) -> T:
    """Return the first (earliest added) delta."""
    return deltas[0]


def compose_sum(deltas: list[float]) -> float:
    """Sum all deltas. Works with any numeric type supporting addition."""
    return sum(deltas)


def compose_mean(deltas: list[float]) -> float:
    """Average all deltas."""
    return sum(deltas) / len(deltas)
