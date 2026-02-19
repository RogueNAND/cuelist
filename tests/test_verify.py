"""Tests for verification point collection."""

import pytest

from cuelist import BPMTimeline, Timeline, TempoMap, clip
from cuelist.verify import VerifyPoint, collect_verify_points
from cuelist.serde import MetadataClip

from conftest import StubClip, InfiniteClip, sum_compose


class TestCollectVerifyPointsTimeline:
    """Tests for collect_verify_points with regular Timeline."""

    def test_empty_timeline(self) -> None:
        """Empty timeline returns empty list."""
        timeline = Timeline(compose_fn=sum_compose)
        points = collect_verify_points(timeline)
        assert points == []

    def test_single_clip(self) -> None:
        """Single clip produces start and end points."""
        timeline = Timeline(compose_fn=sum_compose)
        timeline.add(0.0, clip(2.0, lambda t, ctx: {"ch": t}))

        points = collect_verify_points(timeline)

        assert len(points) == 2
        assert points[0].time_seconds == 0.0
        assert points[0].label == "clip[0] (start)"
        assert points[0].event_index == 0
        assert points[0].edge == "start"

        # End should be nudged 1ms inward
        assert points[1].time_seconds == pytest.approx(1.999)
        assert points[1].label == "clip[0] (end)"
        assert points[1].event_index == 0
        assert points[1].edge == "end"

    def test_multiple_clips(self) -> None:
        """Multiple clips produce correct number of points with correct times."""
        timeline = Timeline(compose_fn=sum_compose)
        timeline.add(0.0, clip(2.0, lambda t, ctx: {"ch": t}))
        timeline.add(1.5, clip(1.0, lambda t, ctx: {"ch": t}))
        timeline.add(5.0, clip(3.0, lambda t, ctx: {"ch": t}))

        points = collect_verify_points(timeline)

        assert len(points) == 6  # 3 clips × 2 points each

        # Check first clip
        assert points[0].time_seconds == 0.0
        assert points[0].edge == "start"
        assert points[0].event_index == 0

        # Check second clip start (overlaps with first clip)
        assert points[1].time_seconds == 1.5
        assert points[1].edge == "start"
        assert points[1].event_index == 1

        # Check first clip end
        assert points[2].time_seconds == pytest.approx(1.999)
        assert points[2].edge == "end"
        assert points[2].event_index == 0

        # Check second clip end
        assert points[3].time_seconds == pytest.approx(2.499)
        assert points[3].edge == "end"
        assert points[3].event_index == 1

        # Check third clip
        assert points[4].time_seconds == 5.0
        assert points[4].edge == "start"
        assert points[4].event_index == 2

        assert points[5].time_seconds == pytest.approx(7.999)
        assert points[5].edge == "end"
        assert points[5].event_index == 2

    def test_infinite_duration_clip(self) -> None:
        """Infinite-duration clips produce only start points, no end points."""
        timeline = Timeline(compose_fn=sum_compose)
        timeline.add(0.0, clip(2.0, lambda t, ctx: {"ch": t}))
        timeline.add(3.0, clip(None, lambda t, ctx: {"ch": 1.0}))  # Infinite
        timeline.add(5.0, clip(1.0, lambda t, ctx: {"ch": t}))

        points = collect_verify_points(timeline)

        # Should have 5 points: clip0(start,end), clip1(start only), clip2(start,end)
        assert len(points) == 5

        assert points[0].event_index == 0 and points[0].edge == "start"
        assert points[1].event_index == 0 and points[1].edge == "end"
        assert points[2].event_index == 1 and points[2].edge == "start"  # Infinite
        assert points[3].event_index == 2 and points[3].edge == "start"
        assert points[4].event_index == 2 and points[4].edge == "end"

    def test_zero_duration_clip(self) -> None:
        """Zero-duration clips produce only start points."""
        timeline = Timeline(compose_fn=sum_compose)
        timeline.add(1.0, clip(0.0, lambda t, ctx: {"ch": t}))

        points = collect_verify_points(timeline)

        # Zero duration should produce only start point
        assert len(points) == 1
        assert points[0].time_seconds == 1.0
        assert points[0].edge == "start"

    def test_sort_order_start_before_end(self) -> None:
        """When start and end are at the same time, start sorts before end."""
        timeline = Timeline(compose_fn=sum_compose)
        # Create two clips where clip1's start == clip0's end (before nudge)
        timeline.add(0.0, clip(2.001, lambda t, ctx: {"ch": t}))
        timeline.add(2.0, clip(1.0, lambda t, ctx: {"ch": t}))

        points = collect_verify_points(timeline)

        # Find points around t=2.0
        points_at_2 = [p for p in points if 1.9 < p.time_seconds < 2.1]

        # Should have clip1 start and clip0 end
        # Based on the sort key (time, edge_order), at same time start (0) comes before end (1)
        assert len(points_at_2) == 2
        assert points_at_2[0].edge == "start"  # clip1 start at 2.0
        assert points_at_2[1].edge == "end"  # clip0 end nudged to 2.0

    def test_labels_fallback_to_clip_index(self) -> None:
        """Without MetadataClip, labels fall back to clip[N]."""
        timeline = Timeline(compose_fn=sum_compose)
        timeline.add(0.0, StubClip(value=1.0, clip_duration=2.0))
        timeline.add(2.0, StubClip(value=2.0, clip_duration=1.0))

        points = collect_verify_points(timeline)

        # Points are sorted by time, so order is:
        # 0.0: clip0 start, 1.999: clip0 end, 2.0: clip1 start, 2.999: clip1 end
        assert points[0].label == "clip[0] (start)"
        assert points[1].label == "clip[0] (end)"
        assert points[2].label == "clip[1] (start)"
        assert points[3].label == "clip[1] (end)"


class TestCollectVerifyPointsBPMTimeline:
    """Tests for collect_verify_points with BPMTimeline."""

    def test_bpm_timeline_beat_to_seconds_conversion(self) -> None:
        """BPMTimeline converts beat positions to seconds correctly."""
        tempo_map = TempoMap(120.0)  # 120 BPM = 2 beats/second
        timeline = BPMTimeline(tempo_map=tempo_map, compose_fn=sum_compose)

        timeline.add(0.0, clip(2.0, lambda t, ctx: {"ch": t}))  # Beat 0-2
        timeline.add(4.0, clip(2.0, lambda t, ctx: {"ch": t}))  # Beat 4-6

        points = collect_verify_points(timeline)

        # At 120 BPM: beat 0 = 0s, beat 2 = 1s, beat 4 = 2s, beat 6 = 3s
        assert len(points) == 4

        assert points[0].time_seconds == pytest.approx(0.0)  # Beat 0
        assert points[0].edge == "start"

        assert points[1].time_seconds == pytest.approx(0.999)  # Beat 2 - 1ms
        assert points[1].edge == "end"

        assert points[2].time_seconds == pytest.approx(2.0)  # Beat 4
        assert points[2].edge == "start"

        assert points[3].time_seconds == pytest.approx(2.999)  # Beat 6 - 1ms
        assert points[3].edge == "end"

    def test_bpm_timeline_variable_tempo(self) -> None:
        """BPMTimeline handles tempo changes correctly."""
        tempo_map = TempoMap(120.0)  # Start at 120 BPM
        tempo_map.set_tempo(4.0, 60.0)  # Change to 60 BPM at beat 4
        timeline = BPMTimeline(tempo_map=tempo_map, compose_fn=sum_compose)

        timeline.add(0.0, clip(2.0, lambda t, ctx: {"ch": t}))  # Beat 0-2
        timeline.add(4.0, clip(2.0, lambda t, ctx: {"ch": t}))  # Beat 4-6

        points = collect_verify_points(timeline)

        # At 120 BPM: beat 0-4 takes 2 seconds
        # At 60 BPM: beat 4-6 takes 2 seconds
        assert points[0].time_seconds == pytest.approx(0.0)  # Beat 0
        assert points[1].time_seconds == pytest.approx(0.999)  # Beat 2
        assert points[2].time_seconds == pytest.approx(2.0)  # Beat 4
        assert points[3].time_seconds == pytest.approx(3.999)  # Beat 6 (2s + 2s - 1ms)

    def test_bpm_timeline_infinite_clip(self) -> None:
        """BPMTimeline handles infinite clips correctly."""
        tempo_map = TempoMap(120.0)
        timeline = BPMTimeline(tempo_map=tempo_map, compose_fn=sum_compose)

        timeline.add(0.0, clip(None, lambda t, ctx: {"ch": 1.0}))

        points = collect_verify_points(timeline)

        assert len(points) == 1
        assert points[0].time_seconds == 0.0
        assert points[0].edge == "start"

    def test_bpm_timeline_empty(self) -> None:
        """Empty BPMTimeline returns empty list."""
        tempo_map = TempoMap(120.0)
        timeline = BPMTimeline(tempo_map=tempo_map, compose_fn=sum_compose)

        points = collect_verify_points(timeline)

        assert points == []


class TestCollectVerifyPointsMetadataClip:
    """Tests for label generation from MetadataClip."""

    def test_metadata_clip_with_clip_type(self) -> None:
        """MetadataClip with clip_type uses it for the label."""
        timeline = Timeline(compose_fn=sum_compose)
        inner = clip(2.0, lambda t, ctx: {"ch": t})
        metadata_clip = MetadataClip(
            inner,
            clip_type="MyEffect",
            meta={},
        )
        timeline.add(0.0, metadata_clip)

        points = collect_verify_points(timeline)

        assert points[0].label == "MyEffect (start)"
        assert points[1].label == "MyEffect (end)"

    def test_metadata_clip_with_meta_label(self) -> None:
        """MetadataClip with meta.label uses it when clip_type is None."""
        timeline = Timeline(compose_fn=sum_compose)
        inner = clip(2.0, lambda t, ctx: {"ch": t})
        metadata_clip = MetadataClip(
            inner,
            clip_type=None,
            meta={"label": "Custom Label"},
        )
        timeline.add(0.0, metadata_clip)

        points = collect_verify_points(timeline)

        assert points[0].label == "Custom Label (start)"
        assert points[1].label == "Custom Label (end)"

    def test_metadata_clip_with_timeline_name(self) -> None:
        """MetadataClip with timeline_name uses it as fallback."""
        timeline = Timeline(compose_fn=sum_compose)
        inner = clip(2.0, lambda t, ctx: {"ch": t})
        metadata_clip = MetadataClip(
            inner,
            clip_type=None,
            meta={},
            timeline_name="MyTimeline",
        )
        timeline.add(0.0, metadata_clip)

        points = collect_verify_points(timeline)

        assert points[0].label == "MyTimeline (start)"
        assert points[1].label == "MyTimeline (end)"

    def test_metadata_clip_priority_clip_type_over_label(self) -> None:
        """When both clip_type and meta.label exist, clip_type takes priority."""
        timeline = Timeline(compose_fn=sum_compose)
        inner = clip(2.0, lambda t, ctx: {"ch": t})
        metadata_clip = MetadataClip(
            inner,
            clip_type="Effect",
            meta={"label": "Should not use this"},
        )
        timeline.add(0.0, metadata_clip)

        points = collect_verify_points(timeline)

        assert points[0].label == "Effect (start)"

    def test_metadata_clip_fallback_to_index(self) -> None:
        """MetadataClip with no names falls back to clip[N]."""
        timeline = Timeline(compose_fn=sum_compose)
        inner = clip(2.0, lambda t, ctx: {"ch": t})
        metadata_clip = MetadataClip(
            inner,
            clip_type=None,
            meta={},
        )
        timeline.add(0.0, metadata_clip)

        points = collect_verify_points(timeline)

        assert points[0].label == "clip[0] (start)"
        assert points[1].label == "clip[0] (end)"


class TestCollectVerifyPointsEdgeCases:
    """Edge cases and boundary conditions."""

    def test_very_short_clip_nudge_not_below_start(self) -> None:
        """End nudge doesn't go below start time for very short clips."""
        timeline = Timeline(compose_fn=sum_compose)
        # 0.0005s duration (0.5ms) - nudging 1ms would go negative
        timeline.add(1.0, clip(0.0005, lambda t, ctx: {"ch": t}))

        points = collect_verify_points(timeline)

        # End should be clamped to start
        assert points[1].time_seconds == pytest.approx(1.0)
        assert points[1].edge == "end"

    def test_negative_position_timeline(self) -> None:
        """Timeline with negative positions works correctly."""
        timeline = Timeline(compose_fn=sum_compose)
        timeline.add(-2.0, clip(1.0, lambda t, ctx: {"ch": t}))
        timeline.add(0.0, clip(1.0, lambda t, ctx: {"ch": t}))

        points = collect_verify_points(timeline)

        assert len(points) == 4
        assert points[0].time_seconds == pytest.approx(-2.0)
        assert points[1].time_seconds == pytest.approx(-1.001)
        assert points[2].time_seconds == pytest.approx(0.0)
        assert points[3].time_seconds == pytest.approx(0.999)

    def test_many_clips_sort_stable(self) -> None:
        """Many overlapping clips sort correctly."""
        timeline = Timeline(compose_fn=sum_compose)

        # Add 10 clips all starting at different times
        for i in range(10):
            timeline.add(i * 0.5, clip(1.0, lambda t, ctx: {"ch": t}))

        points = collect_verify_points(timeline)

        # Should have 20 points, all sorted by time
        assert len(points) == 20

        # Verify monotonic time order (allowing for start/end at same time)
        for i in range(len(points) - 1):
            assert points[i].time_seconds <= points[i + 1].time_seconds

        # Verify start before end at same timestamp
        for i in range(len(points) - 1):
            if points[i].time_seconds == points[i + 1].time_seconds:
                if points[i].edge == "end":
                    assert points[i + 1].edge == "start"
