"""BPM and tempo mapping for timeline scheduling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Self

from .clip import Clip, ComposeFn, _resolve_render, compose_last


@dataclass
class TempoMap:

    bpm: float = 120.0
    _changes: list[tuple[float, float]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self._changes = [(0.0, self.bpm)]

    def set_tempo(self, beat: float, bpm: float) -> TempoMap:
        if beat <= 0:
            self._changes[0] = (0.0, bpm)
        else:
            self._changes = [(b, t) for b, t in self._changes if b != beat]
            self._changes.append((beat, bpm))
            self._changes.sort()
        return self

    def time(self, beats: float) -> float:
        """Convert beat position to seconds."""
        total_seconds = 0.0
        prev_beat = 0.0
        prev_bpm = self._changes[0][1]

        for change_beat, change_bpm in self._changes[1:]:
            if beats <= change_beat:
                break
            segment_beats = change_beat - prev_beat
            total_seconds += segment_beats * (60.0 / prev_bpm)
            prev_beat = change_beat
            prev_bpm = change_bpm

        remaining_beats = beats - prev_beat
        total_seconds += remaining_beats * (60.0 / prev_bpm)
        return total_seconds

    def beat(self, seconds: float) -> float:
        """Convert seconds to beat position."""
        total_beats = 0.0
        prev_beat = 0.0
        prev_bpm = self._changes[0][1]
        elapsed_seconds = 0.0

        for change_beat, change_bpm in self._changes[1:]:
            segment_beats = change_beat - prev_beat
            segment_seconds = segment_beats * (60.0 / prev_bpm)

            if elapsed_seconds + segment_seconds >= seconds:
                break

            elapsed_seconds += segment_seconds
            total_beats = change_beat
            prev_beat = change_beat
            prev_bpm = change_bpm

        remaining_seconds = seconds - elapsed_seconds
        total_beats += remaining_seconds * (prev_bpm / 60.0)
        return total_beats


@dataclass
class BPMTimeline:

    compose_fn: ComposeFn = field(default=compose_last)
    events: list[tuple[float, Clip]] = field(default_factory=list)
    tempo_map: TempoMap = field(default_factory=TempoMap)

    def add(self, position: float, clip: Clip) -> Self:
        self.events.append((position, clip))
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
        return self.tempo_map.time(min(start_beat for start_beat, _ in self.events))

    @property
    def duration(self) -> float | None:
        if not self.events:
            return 0.0
        max_end = None
        for start_beat, c in self.events:
            clip_dur = c.duration
            if clip_dur is None:
                return None
            end_beat = start_beat + clip_dur
            end_time = self.tempo_map.time(end_beat)
            if max_end is None or end_time > max_end:
                max_end = end_time
        return max_end

    async def render(self, t: float, ctx) -> dict:
        current_beat = self.tempo_map.beat(t)
        active = []
        for start_beat, c in self.events:
            local_beat = current_beat - start_beat
            if local_beat < 0 or (c.duration is not None and local_beat > c.duration):
                continue
            active.append((local_beat, c))
        if not active:
            return {}
        results = await asyncio.gather(
            *(_resolve_render(c, lb, ctx) for lb, c in active)
        )
        target_deltas: dict = {}
        for deltas in results:
            for target, delta in deltas.items():
                target_deltas.setdefault(target, []).append(delta)
        return {
            target: self.compose_fn(deltas)
            for target, deltas in target_deltas.items()
        }
