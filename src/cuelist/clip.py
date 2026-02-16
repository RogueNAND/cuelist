"""Generic clip protocol and timeline scheduling."""

from __future__ import annotations

import asyncio
import bisect
import inspect
from dataclasses import dataclass, field
from typing import Callable, Protocol, Self, TypeVar, runtime_checkable

Ctx = TypeVar("Ctx")
Target = TypeVar("Target")
Delta = TypeVar("Delta")

ComposeFn = Callable[[list[Delta]], Delta]


def compose_last(deltas):
    return deltas[-1]


def compose_sum(deltas):
    return sum(deltas)


async def _resolve_render(clip, t, ctx):
    result = clip.render(t, ctx)
    if inspect.isawaitable(result):
        return await result
    return result


@runtime_checkable
class Clip(Protocol[Ctx, Target, Delta]):

    @property
    def duration(self) -> float | None: ...

    def render(self, t: float, ctx: Ctx) -> dict[Target, Delta]: ...


class _FnClip:
    def __init__(self, duration, render_fn):
        self._duration = duration
        self._render_fn = render_fn

    @property
    def duration(self):
        return self._duration

    def render(self, t, ctx):
        return self._render_fn(t, ctx)


def clip(
    duration: float | None,
    render_fn: Callable[[float, Ctx], dict[Target, Delta]],
) -> Clip[Ctx, Target, Delta]:
    """Create a clip from a duration and a render function.

    >>> c = clip(2.0, lambda t, ctx: {"ch": t})
    >>> c.duration
    2.0
    >>> c.render(1.0, None)
    {'ch': 1.0}
    """
    return _FnClip(duration, render_fn)


@dataclass
class Timeline:

    compose_fn: ComposeFn = field(default=compose_last)
    events: list[tuple[float, Clip]] = field(default_factory=list)

    def add(self, position: float, clip: Clip) -> Self:
        bisect.insort(self.events, (position, clip), key=lambda e: e[0])
        return self

    def remove(self, position: float, clip: Clip) -> Self:
        self.events.remove((position, clip))
        return self

    def clear(self) -> Self:
        self.events.clear()
        return self

    @property
    def start(self) -> float:
        if not self.events:
            return 0.0
        return min(start_time for start_time, _ in self.events)

    @property
    def duration(self) -> float | None:
        if not self.events:
            return 0.0
        max_end = None
        for start_time, c in self.events:
            clip_dur = c.duration
            if clip_dur is None:
                return None
            end = start_time + clip_dur
            if max_end is None or end > max_end:
                max_end = end
        return max_end

    def render(self, t: float, ctx) -> dict:
        # Binary search: find rightmost event that could be active (start_time <= t)
        right = bisect.bisect_right(self.events, t, key=lambda e: e[0])

        active = []
        for i in range(right - 1, -1, -1):
            start_time, c = self.events[i]
            local_t = t - start_time
            if c.duration is not None and local_t > c.duration:
                continue
            active.append((local_t, c))
        if not active:
            return {}
        active.reverse()

        # Sync fast path: try rendering all clips synchronously
        results = []
        for lt, c in active:
            result = c.render(lt, ctx)
            if inspect.isawaitable(result):
                # Fall back to async for remaining clips
                return self._render_async(active, ctx, results, result)
            results.append(result)

        return self._compose_results(results)

    async def _render_async(self, active, ctx, partial_results, pending_awaitable):
        """Async fallback when a clip returns an awaitable."""
        partial_results.append(await pending_awaitable)
        # Find where we left off and continue with remaining
        start_idx = len(partial_results)
        if start_idx < len(active):
            remaining = await asyncio.gather(
                *(_resolve_render(c, lt, ctx) for lt, c in active[start_idx:])
            )
            partial_results.extend(remaining)
        return self._compose_results(partial_results)

    def _compose_results(self, results: list[dict]) -> dict:
        target_deltas: dict = {}
        for deltas in results:
            for target, delta in deltas.items():
                target_deltas.setdefault(target, []).append(delta)
        return {
            target: self.compose_fn(deltas)
            for target, deltas in target_deltas.items()
        }
