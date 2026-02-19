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
class BaseTimeline:
    """Shared base for Timeline and BPMTimeline.

    Provides event storage, add/remove/clear, the render pipeline
    (sync-first with async fallback), and result composition.
    Subclasses implement ``render``, ``start``, and ``duration``.
    """

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

    def _render_at(self, position: float, ctx) -> dict:
        """Core render logic: find active clips at *position* and compose."""
        right = bisect.bisect_right(self.events, position, key=lambda e: e[0])

        active = []
        for i in range(right - 1, -1, -1):
            start_pos, c = self.events[i]
            local_t = position - start_pos
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


@dataclass
class Timeline(BaseTimeline):

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
        return self._render_at(t, ctx)


def _fade_envelope(t, duration, fade_in, fade_out):
    """Linear fade envelope returning 0.0-1.0."""
    if duration is None or duration <= 0:
        return 1.0
    f = 1.0
    if fade_in > 0 and t < fade_in:
        f = min(f, t / fade_in)
    if fade_out > 0 and t > duration - fade_out:
        f = min(f, (duration - t) / fade_out)
    return max(0.0, min(1.0, f))


class NestedBPMClip:
    """Wraps a BPMTimeline for nesting inside a parent BPMTimeline.

    A parent BPMTimeline passes t in beats (via _render_at). A nested
    BPMTimeline's render() would incorrectly convert beats→beats again.
    This wrapper bypasses that conversion by calling _render_at() directly.
    Duration is returned in beats for correct parent scheduling.
    """

    def __init__(self, inner):
        self.inner = inner  # BPMTimeline

    @property
    def duration(self):
        if not self.inner.events:
            return 0.0
        max_end = None
        for start_beat, c in self.inner.events:
            dur = c.duration
            if dur is None:
                return None
            end_beat = start_beat + dur
            if max_end is None or end_beat > max_end:
                max_end = end_beat
        return max_end

    def render(self, t, ctx):
        return self.inner._render_at(t, ctx)


class ScaledClip:
    """Wraps a clip, scaling its render output by fade envelope * amount.

    Used to apply fade in/out and wet/dry amount to nested timeline references.
    The scale_fn is domain-specific (e.g., scale_deltas for lighting).
    """

    def __init__(self, inner, *, fade_in=0, fade_out=0, amount=1.0, scale_fn=None, duration_override=None):
        self.inner = inner
        self.fade_in = fade_in
        self.fade_out = fade_out
        self.amount = amount
        self.scale_fn = scale_fn
        self.duration_override = duration_override

    @property
    def duration(self):
        if self.duration_override is not None:
            return self.duration_override
        return self.inner.duration

    def render(self, t, ctx):
        result = self.inner.render(t, ctx)
        factor = self.amount * _fade_envelope(t, self.duration, self.fade_in, self.fade_out)
        if factor >= 1.0:
            return result
        if factor <= 0.0:
            return {}
        if self.scale_fn:
            return self.scale_fn(result, factor)
        return result
