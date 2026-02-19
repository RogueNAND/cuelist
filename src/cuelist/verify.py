"""Verification point collection for timeline preview rendering."""

from __future__ import annotations

from dataclasses import dataclass

from .clip import Timeline
from .serde import MetadataClip
from .tempo import BPMTimeline


@dataclass
class VerifyPoint:
    time_seconds: float
    label: str
    event_index: int
    edge: str  # "start" or "end"


def _build_label(index: int, clip) -> str:
    """Build a human-readable label from a clip, using MetadataClip attributes if available."""
    if isinstance(clip, MetadataClip):
        name = clip.clip_type or clip.meta.get("label") or clip.timeline_name
        if name:
            return name
    return f"clip[{index}]"


def collect_verify_points(timeline: Timeline | BPMTimeline) -> list[VerifyPoint]:
    """Collect start/end verification points from a timeline's events.

    Returns points sorted by (time_seconds, edge) where start sorts before end.
    """
    is_bpm = isinstance(timeline, BPMTimeline)
    points: list[tuple[float, int, VerifyPoint]] = []

    for i, (position, clip) in enumerate(timeline.events):
        label = _build_label(i, clip)

        if is_bpm:
            start_seconds = timeline.tempo_map.time(position)
        else:
            start_seconds = position

        points.append((start_seconds, 0, VerifyPoint(
            time_seconds=start_seconds,
            label=f"{label} (start)",
            event_index=i,
            edge="start",
        )))

        if clip.duration is not None and clip.duration > 0:
            if is_bpm:
                end_seconds = timeline.tempo_map.time(position + clip.duration)
            else:
                end_seconds = position + clip.duration

            # Nudge 1ms inward, but not below start
            end_seconds = max(start_seconds, end_seconds - 0.001)

            points.append((end_seconds, 1, VerifyPoint(
                time_seconds=end_seconds,
                label=f"{label} (end)",
                event_index=i,
                edge="end",
            )))

    points.sort(key=lambda p: (p[0], p[1]))
    return [vp for _, _, vp in points]
