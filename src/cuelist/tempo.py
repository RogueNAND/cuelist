"""BPM and tempo mapping for timeline scheduling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic

from .clip import Clip, ComposeFn, Ctx, Delta, Target


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
        if beats <= 0:
            return 0.0

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
        if seconds <= 0:
            return 0.0

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
class BPMTimeline(Generic[Ctx, Target, Delta]):

    compose_fn: ComposeFn[Delta]
    tempo_map: TempoMap = field(default_factory=TempoMap)
    events: list[tuple[float, Clip[Ctx, Target, Delta]]] = field(default_factory=list)

    @property
    def duration(self) -> float | None:
        if not self.events:
            return 0.0
        max_end = 0.0
        for start_beat, clip in self.events:
            clip_dur = clip.duration
            if clip_dur is None:
                return None
            end_beat = start_beat + clip_dur
            max_end = max(max_end, self.tempo_map.time(end_beat))
        return max_end

    def add(
        self, beat: float, clip: Clip[Ctx, Target, Delta]
    ) -> BPMTimeline[Ctx, Target, Delta]:
        self.events.append((beat, clip))
        return self

    def remove(
        self, beat: float, clip: Clip[Ctx, Target, Delta]
    ) -> BPMTimeline[Ctx, Target, Delta]:
        self.events.remove((beat, clip))
        return self

    def clear(self) -> BPMTimeline[Ctx, Target, Delta]:
        self.events.clear()
        return self

    def render(self, t: float, ctx: Ctx) -> dict[Target, Delta]:
        current_beat = self.tempo_map.beat(t)
        target_deltas: dict[Target, list[Delta]] = {}

        for start_beat, clip in self.events:
            local_beat = current_beat - start_beat
            if local_beat < 0 or (clip.duration is not None and local_beat > clip.duration):
                continue

            deltas = clip.render(local_beat, ctx)
            for target, delta in deltas.items():
                target_deltas.setdefault(target, []).append(delta)

        return {
            target: self.compose_fn(deltas) for target, deltas in target_deltas.items()
        }
