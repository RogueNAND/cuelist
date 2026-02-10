"""Generic clip protocol and timeline scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, Protocol, TypeVar, runtime_checkable

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


@dataclass
class Timeline(Generic[Ctx, Target, Delta]):

    compose_fn: ComposeFn[Delta]
    events: list[tuple[float, Clip[Ctx, Target, Delta]]] = field(default_factory=list)

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

    def add(
        self, start_time: float, clip: Clip[Ctx, Target, Delta]
    ) -> Timeline[Ctx, Target, Delta]:
        self.events.append((start_time, clip))
        return self

    def remove(
        self, start_time: float, clip: Clip[Ctx, Target, Delta]
    ) -> Timeline[Ctx, Target, Delta]:
        self.events.remove((start_time, clip))
        return self

    def clear(self) -> Timeline[Ctx, Target, Delta]:
        self.events.clear()
        return self

    def render(self, t: float, ctx: Ctx) -> dict[Target, Delta]:
        target_deltas: dict[Target, list[Delta]] = {}

        for start_time, clip in self.events:
            local_t = t - start_time
            if local_t < 0 or (clip.duration is not None and local_t > clip.duration):
                continue

            deltas = clip.render(local_t, ctx)
            for target, delta in deltas.items():
                target_deltas.setdefault(target, []).append(delta)

        return {
            target: self.compose_fn(deltas) for target, deltas in target_deltas.items()
        }
