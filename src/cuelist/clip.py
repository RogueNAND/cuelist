"""Generic clip protocol and timeline scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, Protocol, Self, TypeVar, runtime_checkable

from .compose import compose_last

Ctx = TypeVar("Ctx")
Target = TypeVar("Target")
Delta = TypeVar("Delta")

ComposeFn = Callable[[list[Delta]], Delta]


@runtime_checkable
class Clip(Protocol[Ctx, Target, Delta]):

    @property
    def duration(self) -> float | None:
        ...

    def render(self, t: float, ctx: Ctx) -> dict[Target, Delta]:
        ...


# ---------------------------------------------------------------------------
# Convenience: clip() factory and BaseClip
# ---------------------------------------------------------------------------


class _FnClip(Generic[Ctx, Target, Delta]):
    """Lightweight clip wrapping a plain function. Created by :func:`clip`."""

    __slots__ = ("_duration", "_render_fn")

    def __init__(
        self,
        duration: float | None,
        render_fn: Callable[[float, Ctx], dict[Target, Delta]],
    ) -> None:
        self._duration = duration
        self._render_fn = render_fn

    @property
    def duration(self) -> float | None:
        return self._duration

    def render(self, t: float, ctx: Ctx) -> dict[Target, Delta]:
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


class BaseClip(Generic[Ctx, Target, Delta]):
    """Optional base class that handles the ``duration`` boilerplate.

    Subclasses can set ``duration`` as a class attribute or pass it to
    ``__init__``.  Only ``render`` needs to be implemented.

    >>> class MyClip(BaseClip):
    ...     def __init__(self):
    ...         super().__init__(duration=2.0)
    ...     def render(self, t, ctx):
    ...         return {"ch": t}
    """

    def __init__(self, duration: float | None = None) -> None:
        self._duration = duration

    @property
    def duration(self) -> float | None:
        return self._duration

    def render(self, t: float, ctx: Ctx) -> dict[Target, Delta]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# _BaseTimeline — shared logic for Timeline and BPMTimeline
# ---------------------------------------------------------------------------


@dataclass
class _BaseTimeline(Generic[Ctx, Target, Delta]):
    """Shared add/remove/clear and composition logic."""

    compose_fn: ComposeFn[Delta] = field(default=compose_last)
    events: list[tuple[float, Clip[Ctx, Target, Delta]]] = field(default_factory=list)

    def add(self, position: float, clip: Clip[Ctx, Target, Delta]) -> Self:
        self.events.append((position, clip))
        return self

    def remove(self, position: float, clip: Clip[Ctx, Target, Delta]) -> Self:
        self.events.remove((position, clip))
        return self

    def clear(self) -> Self:
        self.events.clear()
        return self

    def _collect_deltas(
        self, local_times: list[tuple[float, Clip[Ctx, Target, Delta]]],
        ctx: Ctx,
    ) -> dict[Target, Delta]:
        """Render active clips and compose their deltas per target."""
        target_deltas: dict[Target, list[Delta]] = {}

        for local_t, active_clip in local_times:
            deltas = active_clip.render(local_t, ctx)
            for target, delta in deltas.items():
                target_deltas.setdefault(target, []).append(delta)

        return {
            target: self.compose_fn(deltas) for target, deltas in target_deltas.items()
        }


@dataclass
class Timeline(_BaseTimeline[Ctx, Target, Delta]):

    @property
    def duration(self) -> float | None:
        if not self.events:
            return 0.0
        max_end = 0.0
        for start_time, clip in self.events:
            clip_dur = clip.duration
            if clip_dur is None:
                return None
            max_end = max(max_end, start_time + clip_dur)
        return max_end

    def render(self, t: float, ctx: Ctx) -> dict[Target, Delta]:
        active: list[tuple[float, Clip[Ctx, Target, Delta]]] = []
        for start_time, c in self.events:
            local_t = t - start_time
            if local_t < 0 or (c.duration is not None and local_t > c.duration):
                continue
            active.append((local_t, c))
        return self._collect_deltas(active, ctx)
