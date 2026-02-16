"""Tests for Clip protocol and Timeline."""

import asyncio

import pytest

from cuelist import BPMTimeline, Clip, Timeline

from conftest import InfiniteClip, StubClip, resolve, sum_compose


# --- Clip protocol conformance ---


class TestClipProtocol:
    def test_stub_clip_is_clip(self, stub_clip: StubClip) -> None:
        assert isinstance(stub_clip, Clip)

    def test_infinite_clip_is_clip(self, infinite_clip: InfiniteClip) -> None:
        assert isinstance(infinite_clip, Clip)

    def test_non_clip_rejected(self) -> None:
        assert not isinstance("not a clip", Clip)

    def test_partial_clip_rejected(self) -> None:
        class HasDurationOnly:
            @property
            def duration(self) -> float:
                return 1.0

        assert not isinstance(HasDurationOnly(), Clip)


# --- Timeline duration ---


class TestTimelineDuration:
    def test_empty_timeline_duration(self, timeline: Timeline) -> None:
        assert timeline.duration == 0.0

    def test_single_clip_duration(self, timeline: Timeline, stub_clip: StubClip) -> None:
        timeline.add(0.0, stub_clip)
        assert timeline.duration == 5.0

    def test_offset_clip_duration(self, timeline: Timeline, stub_clip: StubClip) -> None:
        timeline.add(3.0, stub_clip)
        assert timeline.duration == 8.0

    def test_infinite_clip_gives_none_duration(
        self, timeline: Timeline, infinite_clip: InfiniteClip
    ) -> None:
        timeline.add(0.0, infinite_clip)
        assert timeline.duration is None


# --- Timeline render ---


class TestTimelineRender:
    def test_empty_timeline_render(self, timeline: Timeline) -> None:
        assert resolve(timeline.render(1.0, None)) == {}

    def test_render_before_clip_start(
        self, timeline: Timeline, stub_clip: StubClip
    ) -> None:
        timeline.add(5.0, stub_clip)
        assert resolve(timeline.render(2.0, None)) == {}

    def test_render_after_clip_end(
        self, timeline: Timeline, stub_clip: StubClip
    ) -> None:
        timeline.add(0.0, stub_clip)
        # clip duration is 5.0, so t=6.0 is past end
        assert resolve(timeline.render(6.0, None)) == {}

    def test_render_mid_clip(self, timeline: Timeline, stub_clip: StubClip) -> None:
        timeline.add(0.0, stub_clip)
        # StubClip renders {"ch": value * t} = {"ch": 2.0 * 2.5}
        result = resolve(timeline.render(2.5, None))
        assert result == {"ch": 5.0}

    def test_render_overlapping_clips_composed(self, timeline: Timeline) -> None:
        clip_a = StubClip(value=1.0, clip_duration=4.0)
        clip_b = StubClip(value=2.0, clip_duration=4.0)
        timeline.add(0.0, clip_a)
        timeline.add(0.0, clip_b)
        # At t=2: clip_a => 1.0*2=2.0, clip_b => 2.0*2=4.0, sum=6.0
        result = resolve(timeline.render(2.0, None))
        assert result == {"ch": 6.0}


# --- Chainable add ---


class TestChainableAdd:
    def test_add_returns_self(self, timeline: Timeline, stub_clip: StubClip) -> None:
        result = timeline.add(0.0, stub_clip)
        assert result is timeline

    def test_chained_adds(self) -> None:
        tl = (
            Timeline(compose_fn=sum_compose)
            .add(0.0, StubClip(value=1.0, clip_duration=2.0))
            .add(1.0, StubClip(value=2.0, clip_duration=3.0))
        )
        assert len(tl.events) == 2


# --- Timeline remove/clear ---


class TestTimelineRemove:
    def test_remove_existing(self, timeline: Timeline) -> None:
        clip = StubClip(value=1.0, clip_duration=2.0)
        timeline.add(0.0, clip)
        timeline.remove(0.0, clip)
        assert len(timeline.events) == 0

    def test_remove_nonexistent_raises(self, timeline: Timeline) -> None:
        clip = StubClip(value=1.0, clip_duration=2.0)
        with pytest.raises(ValueError):
            timeline.remove(0.0, clip)

    def test_remove_first_of_duplicates(self, timeline: Timeline) -> None:
        clip = StubClip(value=1.0, clip_duration=2.0)
        timeline.add(0.0, clip)
        timeline.add(0.0, clip)
        timeline.remove(0.0, clip)
        assert len(timeline.events) == 1

    def test_remove_returns_self(self, timeline: Timeline) -> None:
        clip = StubClip(value=1.0, clip_duration=2.0)
        timeline.add(0.0, clip)
        result = timeline.remove(0.0, clip)
        assert result is timeline


class TestTimelineClear:
    def test_clear_empties_events(self, timeline: Timeline) -> None:
        timeline.add(0.0, StubClip(value=1.0, clip_duration=2.0))
        timeline.add(1.0, StubClip(value=2.0, clip_duration=3.0))
        timeline.clear()
        assert len(timeline.events) == 0

    def test_clear_resets_duration(self, timeline: Timeline) -> None:
        timeline.add(0.0, StubClip(value=1.0, clip_duration=2.0))
        timeline.clear()
        assert timeline.duration == 0.0

    def test_clear_on_empty(self, timeline: Timeline) -> None:
        timeline.clear()
        assert len(timeline.events) == 0

    def test_clear_returns_self(self, timeline: Timeline) -> None:
        result = timeline.clear()
        assert result is timeline


# --- Nested timelines ---


class TestNestedTimelines:
    def test_timeline_is_clip(self) -> None:
        tl = Timeline(compose_fn=sum_compose)
        assert isinstance(tl, Clip)

    def test_bpm_timeline_is_clip(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        assert isinstance(bt, Clip)

    def test_nested_render(self) -> None:
        inner = Timeline(compose_fn=sum_compose)
        inner.add(0.0, StubClip(value=3.0, clip_duration=2.0))
        outer = Timeline(compose_fn=sum_compose)
        outer.add(1.0, inner)
        # At t=2.0, inner local_t=1.0 => StubClip renders {"ch": 3.0*1.0}
        result = resolve(outer.render(2.0, None))
        assert result == {"ch": pytest.approx(3.0)}

    def test_nested_duration(self) -> None:
        inner = Timeline(compose_fn=sum_compose)
        inner.add(0.0, StubClip(value=1.0, clip_duration=3.0))
        outer = Timeline(compose_fn=sum_compose)
        outer.add(2.0, inner)
        # outer duration = 2.0 + inner.duration(3.0) = 5.0
        assert outer.duration == pytest.approx(5.0)

    def test_composition_with_direct_and_nested(self) -> None:
        inner = Timeline(compose_fn=sum_compose)
        inner.add(0.0, StubClip(value=2.0, clip_duration=4.0))
        outer = Timeline(compose_fn=sum_compose)
        outer.add(0.0, StubClip(value=1.0, clip_duration=4.0))
        outer.add(0.0, inner)
        # At t=1.0: direct clip => 1.0*1.0=1.0, nested => 2.0*1.0=2.0, sum=3.0
        result = resolve(outer.render(1.0, None))
        assert result == {"ch": pytest.approx(3.0)}

    def test_infinite_duration_propagates(self) -> None:
        inner = Timeline(compose_fn=sum_compose)
        inner.add(0.0, InfiniteClip(value=1.0))
        outer = Timeline(compose_fn=sum_compose)
        outer.add(0.0, inner)
        assert outer.duration is None


# --- Negative positions ---


class TestTimelineNegativePositions:
    def test_negative_position_duration(self, timeline: Timeline) -> None:
        timeline.add(-3.0, StubClip(value=1.0, clip_duration=5.0))
        # end = -3.0 + 5.0 = 2.0
        assert timeline.duration == pytest.approx(2.0)

    def test_all_negative_duration(self, timeline: Timeline) -> None:
        timeline.add(-5.0, StubClip(value=1.0, clip_duration=2.0))
        # end = -5.0 + 2.0 = -3.0
        assert timeline.duration == pytest.approx(-3.0)

    def test_negative_position_render(self, timeline: Timeline) -> None:
        timeline.add(-2.0, StubClip(value=3.0, clip_duration=5.0))
        # At t=0.0, local_t = 0.0 - (-2.0) = 2.0
        # StubClip renders {"ch": 3.0 * 2.0} = {"ch": 6.0}
        result = resolve(timeline.render(0.0, None))
        assert result == {"ch": pytest.approx(6.0)}

    def test_start_property(self, timeline: Timeline) -> None:
        timeline.add(-3.0, StubClip(value=1.0, clip_duration=5.0))
        assert timeline.start == -3.0

    def test_start_empty(self, timeline: Timeline) -> None:
        assert timeline.start == 0.0

    def test_start_mixed_positions(self, timeline: Timeline) -> None:
        timeline.add(-3.0, StubClip(value=1.0, clip_duration=2.0))
        timeline.add(2.0, StubClip(value=1.0, clip_duration=1.0))
        assert timeline.start == -3.0
