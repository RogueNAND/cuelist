"""Tests for TempoMap and BPMTimeline."""

import asyncio

import pytest

from cuelist import BPMTimeline, TempoMap

from conftest import InfiniteClip, StubClip, resolve, sum_compose


# --- TempoMap basics ---


class TestTempoMapBasics:
    def test_default_bpm(self) -> None:
        tm = TempoMap()
        # 120 BPM => 1 beat = 0.5s
        assert tm.time(1.0) == pytest.approx(0.5)

    def test_custom_bpm(self) -> None:
        tm = TempoMap(60.0)
        # 60 BPM => 1 beat = 1.0s
        assert tm.time(1.0) == pytest.approx(1.0)

    def test_zero_beats_returns_zero(self) -> None:
        tm = TempoMap(120.0)
        assert tm.time(0.0) == 0.0

    def test_negative_beats_extrapolates(self) -> None:
        tm = TempoMap(120.0)
        # -1 beat at 120 BPM = -0.5s
        assert tm.time(-1.0) == pytest.approx(-0.5)

    def test_zero_seconds_returns_zero_beat(self) -> None:
        tm = TempoMap(120.0)
        assert tm.beat(0.0) == 0.0

    def test_negative_seconds_extrapolates(self) -> None:
        tm = TempoMap(120.0)
        # -1s at 120 BPM = -2 beats
        assert tm.beat(-1.0) == pytest.approx(-2.0)


# --- Beat/time roundtrips ---


class TestNegativeTimeExtrapolation:
    def test_negative_beat_roundtrip(self) -> None:
        tm = TempoMap(120.0)
        assert tm.beat(tm.time(-2.0)) == pytest.approx(-2.0)

    def test_negative_second_roundtrip(self) -> None:
        tm = TempoMap(120.0)
        assert tm.time(tm.beat(-3.0)) == pytest.approx(-3.0)

    def test_negative_beat_with_tempo_change(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(4, 60.0)
        # Negative beats use the initial tempo (120 BPM) regardless of later changes
        assert tm.time(-2.0) == pytest.approx(-1.0)


class TestBeatTimeRoundtrip:
    def test_roundtrip_simple(self) -> None:
        tm = TempoMap(120.0)
        assert tm.beat(tm.time(4.0)) == pytest.approx(4.0)

    def test_roundtrip_reverse(self) -> None:
        tm = TempoMap(120.0)
        assert tm.time(tm.beat(3.0)) == pytest.approx(3.0)

    def test_roundtrip_with_tempo_change(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(4, 60.0)
        for beats in [1.0, 4.0, 6.0, 10.0]:
            assert tm.beat(tm.time(beats)) == pytest.approx(beats)


# --- Tempo changes ---


class TestTempoChanges:
    def test_single_change(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(4, 60.0)
        # First 4 beats at 120 BPM = 2.0s
        assert tm.time(4.0) == pytest.approx(2.0)
        # Beat 5: 2.0s + 1 beat at 60 BPM = 2.0 + 1.0 = 3.0s
        assert tm.time(5.0) == pytest.approx(3.0)

    def test_multiple_changes(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(4, 60.0)
        tm.set_tempo(8, 240.0)
        # 4 beats @ 120 = 2.0s, 4 beats @ 60 = 4.0s, total to beat 8 = 6.0s
        assert tm.time(8.0) == pytest.approx(6.0)
        # Beat 9: 6.0s + 1 beat at 240 BPM = 6.0 + 0.25 = 6.25s
        assert tm.time(9.0) == pytest.approx(6.25)

    def test_override_at_beat_zero(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(0, 60.0)
        # Should now be 60 BPM from the start
        assert tm.time(1.0) == pytest.approx(1.0)

    def test_set_tempo_chainable(self) -> None:
        tm = TempoMap(120.0)
        result = tm.set_tempo(4, 60.0)
        assert result is tm

    def test_negative_beat_overrides_zero(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(-5, 60.0)
        assert tm.time(1.0) == pytest.approx(1.0)


# --- Beat conversion ---


class TestBeatConversion:
    def test_beat_at_120bpm(self) -> None:
        tm = TempoMap(120.0)
        # 120 BPM = 2 beats/sec
        assert tm.beat(1.0) == pytest.approx(2.0)
        assert tm.beat(3.0) == pytest.approx(6.0)

    def test_beat_with_tempo_change(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(4, 60.0)
        # At 2.0s we should be at beat 4.0
        assert tm.beat(2.0) == pytest.approx(4.0)
        # At 3.0s: beat 4 + 1 beat at 60 BPM = beat 5
        assert tm.beat(3.0) == pytest.approx(5.0)


# --- BPMTimeline ---


class TestBPMTimeline:
    def test_empty_duration(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        assert bt.duration == 0.0

    def test_duration_with_clip(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose, tempo_map=TempoMap(120.0))
        clip = StubClip(value=1.0, clip_duration=2.0)
        bt.add(0, clip)
        # clip starts at beat 0, duration 2.0 beats => end beat 2.0
        # At 120 BPM, beat 2.0 = 1.0s
        assert bt.duration == pytest.approx(1.0)

    def test_duration_offset_clip(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose, tempo_map=TempoMap(120.0))
        clip = StubClip(value=1.0, clip_duration=1.0)
        bt.add(4, clip)
        # end beat = 4 + 1.0 = 5.0, at 120 BPM = 2.5s
        assert bt.duration == pytest.approx(2.5)

    def test_infinite_clip_duration_none(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        bt.add(0, InfiniteClip(value=1.0))
        assert bt.duration is None

    def test_render_timing(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose, tempo_map=TempoMap(120.0))
        clip = StubClip(value=2.0, clip_duration=5.0)
        bt.add(4, clip)  # starts at beat 4 (2.0s at 120 BPM)
        # At t=1.0s, current_beat=2.0, clip hasn't started (beat 4)
        assert resolve(bt.render(1.0, None)) == {}
        # At t=3.0s, current_beat=6.0, local_beat=6.0-4.0=2.0
        # StubClip renders {"ch": 2.0 * 2.0} = {"ch": 4.0}
        assert resolve(bt.render(3.0, None)) == {"ch": pytest.approx(4.0)}

    def test_render_composition(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose, tempo_map=TempoMap(120.0))
        clip_a = StubClip(value=1.0, clip_duration=5.0)
        clip_b = StubClip(value=3.0, clip_duration=5.0)
        bt.add(0, clip_a)
        bt.add(0, clip_b)
        # At t=1.0s, current_beat=2.0, local_beat=2.0
        # clip_a => 1.0*2.0=2.0, clip_b => 3.0*2.0=6.0, sum=8.0
        assert resolve(bt.render(1.0, None)) == {"ch": pytest.approx(8.0)}

    def test_add_chainable(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        clip = StubClip(value=1.0, clip_duration=1.0)
        result = bt.add(0, clip)
        assert result is bt

    def test_duration_with_tempo_change(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(4, 60.0)
        bt = BPMTimeline(compose_fn=sum_compose, tempo_map=tm)
        clip = StubClip(value=1.0, clip_duration=4.0)  # 4 beats
        bt.add(2, clip)
        # end_beat = 2 + 4 = 6
        # tempo_map.time(6): 4 beats@120=2.0s + 2 beats@60=2.0s = 4.0s
        assert bt.duration == pytest.approx(4.0)

    def test_render_with_tempo_change(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(4, 60.0)
        bt = BPMTimeline(compose_fn=sum_compose, tempo_map=tm)
        clip = StubClip(value=1.0, clip_duration=4.0)  # 4 beats
        bt.add(4, clip)  # starts at beat 4 (= 2.0s)
        # At t=3.0s: beat(3.0) = 4 + (3.0-2.0)*(60/60) = 5.0
        # local_beat = 5.0 - 4.0 = 1.0
        # StubClip renders {"ch": 1.0 * 1.0} = {"ch": 1.0}
        assert resolve(bt.render(3.0, None)) == {"ch": pytest.approx(1.0)}


# --- set_tempo deduplication ---


class TestSetTempoDedup:
    def test_override_same_beat_keeps_one_entry(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(4, 60.0)
        tm.set_tempo(4, 90.0)
        # Only beat-0 and beat-4 entries
        assert len(tm._changes) == 2
        assert tm._changes[1] == (4, 90.0)

    def test_override_same_beat_correct_bpm(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(4, 60.0)
        tm.set_tempo(4, 180.0)
        # Beat 5: 4 beats @ 120 BPM = 2.0s + 1 beat @ 180 BPM = 2.333...s
        assert tm.time(5.0) == pytest.approx(2.0 + 60.0 / 180.0)

    def test_override_preserves_other_entries(self) -> None:
        tm = TempoMap(120.0)
        tm.set_tempo(4, 60.0)
        tm.set_tempo(8, 240.0)
        tm.set_tempo(4, 90.0)
        assert len(tm._changes) == 3
        assert tm._changes[1] == (4, 90.0)
        assert tm._changes[2] == (8, 240.0)


# --- BPMTimeline remove/clear ---


class TestBPMTimelineRemove:
    def test_remove_existing(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        clip = StubClip(value=1.0, clip_duration=2.0)
        bt.add(0, clip)
        bt.remove(0, clip)
        assert len(bt.events) == 0

    def test_remove_nonexistent_raises(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        clip = StubClip(value=1.0, clip_duration=2.0)
        with pytest.raises(ValueError):
            bt.remove(0, clip)

    def test_remove_first_of_duplicates(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        clip = StubClip(value=1.0, clip_duration=2.0)
        bt.add(0, clip)
        bt.add(0, clip)
        bt.remove(0, clip)
        assert len(bt.events) == 1

    def test_remove_returns_self(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        clip = StubClip(value=1.0, clip_duration=2.0)
        bt.add(0, clip)
        result = bt.remove(0, clip)
        assert result is bt


class TestBPMTimelineClear:
    def test_clear_empties_events(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        bt.add(0, StubClip(value=1.0, clip_duration=2.0))
        bt.add(4, StubClip(value=2.0, clip_duration=3.0))
        bt.clear()
        assert len(bt.events) == 0

    def test_clear_resets_duration(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        bt.add(0, StubClip(value=1.0, clip_duration=2.0))
        bt.clear()
        assert bt.duration == 0.0

    def test_clear_on_empty(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        bt.clear()
        assert len(bt.events) == 0

    def test_clear_returns_self(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        result = bt.clear()
        assert result is bt


# --- BPMTimeline negative positions ---


class TestBPMTimelineNegative:
    def test_negative_position_duration(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose, tempo_map=TempoMap(120.0))
        clip = StubClip(value=1.0, clip_duration=6.0)
        bt.add(-4, clip)
        # end beat = -4 + 6 = 2, at 120 BPM = 1.0s
        assert bt.duration == pytest.approx(1.0)

    def test_all_negative_duration(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose, tempo_map=TempoMap(120.0))
        clip = StubClip(value=1.0, clip_duration=2.0)
        bt.add(-4, clip)
        # end beat = -4 + 2 = -2, at 120 BPM = -1.0s
        assert bt.duration == pytest.approx(-1.0)

    def test_start_property(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose, tempo_map=TempoMap(120.0))
        bt.add(-4, StubClip(value=1.0, clip_duration=6.0))
        # beat -4 at 120 BPM = -2.0s
        assert bt.start == pytest.approx(-2.0)

    def test_start_empty(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose)
        assert bt.start == 0.0

    def test_render_at_negative_time(self) -> None:
        bt = BPMTimeline(compose_fn=sum_compose, tempo_map=TempoMap(120.0))
        clip = StubClip(value=1.0, clip_duration=6.0)
        bt.add(-4, clip)  # starts at beat -4 (-2.0s)
        # At t=-1.0s, current_beat = -2.0, local_beat = -2.0 - (-4.0) = 2.0
        # StubClip renders {"ch": 1.0 * 2.0} = {"ch": 2.0}
        assert resolve(bt.render(-1.0, None)) == {"ch": pytest.approx(2.0)}
