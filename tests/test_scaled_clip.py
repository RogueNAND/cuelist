"""Tests for ScaledClip, fade envelope, serde round-trip, and recursive verify."""

from dataclasses import dataclass

import pytest

from cuelist.clip import NestedBPMClip, ScaledClip, Timeline, _fade_envelope, clip
from cuelist.registry import ClipRegistry
from cuelist.serde import MetadataClip, deserialize_timeline, serialize_timeline
from cuelist.tempo import BPMTimeline, TempoMap
from cuelist.verify import collect_verify_points

from conftest import sum_compose


# -- helpers ------------------------------------------------------------------

@dataclass
class DummyClip:
    duration: float

    def render(self, t, ctx):
        return {"ch": t}


def make_registry():
    reg = ClipRegistry()
    reg.register("test_clip", lambda duration=4, **kw: DummyClip(duration))
    return reg


def make_load_fn(timelines_dict):
    def load_fn(name):
        if name not in timelines_dict:
            raise KeyError(f"Timeline '{name}' not found")
        return timelines_dict[name]
    return load_fn


# -- _fade_envelope tests ----------------------------------------------------

class TestFadeEnvelope:

    def test_no_fade_returns_one(self):
        """Full output when no fade in/out."""
        assert _fade_envelope(0.5, 2.0, 0, 0) == 1.0

    def test_none_duration_returns_one(self):
        """None duration returns 1.0 regardless of fade params."""
        assert _fade_envelope(0.5, None, 0.5, 0.5) == 1.0

    def test_zero_duration_returns_one(self):
        """Zero duration returns 1.0."""
        assert _fade_envelope(0.0, 0.0, 0.5, 0.5) == 1.0

    def test_fade_in_at_zero(self):
        """t=0 with fade_in > 0 returns 0."""
        assert _fade_envelope(0.0, 2.0, 1.0, 0) == 0.0

    def test_fade_in_midpoint(self):
        """Halfway through fade_in returns 0.5."""
        assert _fade_envelope(0.5, 2.0, 1.0, 0) == pytest.approx(0.5)

    def test_fade_in_complete(self):
        """At end of fade_in period, returns 1.0."""
        assert _fade_envelope(1.0, 2.0, 1.0, 0) == pytest.approx(1.0)

    def test_fade_out_at_end(self):
        """At t=duration with fade_out > 0 returns 0."""
        assert _fade_envelope(2.0, 2.0, 0, 1.0) == pytest.approx(0.0)

    def test_fade_out_midpoint(self):
        """Halfway through fade_out returns 0.5."""
        assert _fade_envelope(1.5, 2.0, 0, 1.0) == pytest.approx(0.5)

    def test_fade_out_start(self):
        """At the start of fade_out period, returns 1.0."""
        assert _fade_envelope(1.0, 2.0, 0, 1.0) == pytest.approx(1.0)

    def test_both_fades(self):
        """Both fade_in and fade_out at their respective midpoints."""
        # 4s duration, 2s fade_in, 2s fade_out
        assert _fade_envelope(1.0, 4.0, 2.0, 2.0) == pytest.approx(0.5)  # fade_in mid
        assert _fade_envelope(2.0, 4.0, 2.0, 2.0) == pytest.approx(1.0)  # both boundaries
        assert _fade_envelope(3.0, 4.0, 2.0, 2.0) == pytest.approx(0.5)  # fade_out mid

    def test_overlapping_fades(self):
        """When fade_in + fade_out > duration, both clamp correctly."""
        # 1s duration, fade_in=1, fade_out=1 -- they overlap completely
        # At t=0.5: fade_in gives 0.5, fade_out gives (1.0-0.5)/1.0 = 0.5
        result = _fade_envelope(0.5, 1.0, 1.0, 1.0)
        assert result == pytest.approx(0.5)

    def test_clamp_never_exceeds_one(self):
        """Result is always clamped to [0, 1]."""
        assert _fade_envelope(0.5, 1.0, 0, 0) == 1.0

    def test_clamp_never_below_zero(self):
        """Result is always clamped to [0, 1] even for edge values."""
        assert _fade_envelope(0.0, 2.0, 1.0, 0) == 0.0
        assert _fade_envelope(2.0, 2.0, 0, 1.0) == pytest.approx(0.0)


# -- ScaledClip tests --------------------------------------------------------

class TestScaledClip:

    def test_passthrough_when_no_scaling(self):
        """Renders inner clip unchanged when amount=1.0 and no fade."""
        inner = clip(2.0, lambda t, ctx: {"ch": t * 10})
        sc = ScaledClip(inner)
        assert sc.render(1.0, None) == {"ch": 10.0}

    def test_duration_delegates(self):
        """Duration property delegates to inner clip."""
        inner = clip(5.0, lambda t, ctx: {})
        sc = ScaledClip(inner, fade_in=1.0)
        assert sc.duration == 5.0

    def test_duration_none_delegates(self):
        """None duration passes through from inner clip."""
        inner = clip(None, lambda t, ctx: {})
        sc = ScaledClip(inner)
        assert sc.duration is None

    def test_returns_empty_when_factor_zero(self):
        """Returns empty dict when amount=0."""
        inner = clip(2.0, lambda t, ctx: {"ch": 99})
        sc = ScaledClip(inner, amount=0.0)
        assert sc.render(1.0, None) == {}

    def test_returns_empty_at_start_with_fade_in(self):
        """Returns empty dict at t=0 with fade_in (factor=0)."""
        inner = clip(2.0, lambda t, ctx: {"ch": 99})
        sc = ScaledClip(inner, fade_in=1.0)
        assert sc.render(0.0, None) == {}

    def test_calls_scale_fn(self):
        """Calls scale_fn with render result and computed factor."""
        calls = []

        def mock_scale(result, factor):
            calls.append((result, factor))
            return {k: v * factor for k, v in result.items()}

        inner = clip(2.0, lambda t, ctx: {"ch": 10.0})
        sc = ScaledClip(inner, amount=0.5, scale_fn=mock_scale)
        result = sc.render(1.0, None)

        assert len(calls) == 1
        assert calls[0][0] == {"ch": 10.0}
        assert calls[0][1] == pytest.approx(0.5)
        assert result == {"ch": 5.0}

    def test_no_scale_fn_returns_unscaled(self):
        """Without scale_fn, returns raw render result when factor < 1."""
        inner = clip(2.0, lambda t, ctx: {"ch": 10.0})
        sc = ScaledClip(inner, amount=0.5)
        # No scale_fn: result passes through unscaled
        result = sc.render(1.0, None)
        assert result == {"ch": 10.0}

    def test_amount_with_fade(self):
        """Amount combines multiplicatively with fade envelope."""
        calls = []

        def mock_scale(result, factor):
            calls.append(factor)
            return result

        inner = clip(2.0, lambda t, ctx: {"ch": 1.0})
        sc = ScaledClip(inner, fade_in=2.0, amount=0.5, scale_fn=mock_scale)
        # At t=1.0: fade_in = 1.0/2.0 = 0.5, amount = 0.5, factor = 0.25
        sc.render(1.0, None)
        assert calls[0] == pytest.approx(0.25)


# -- Serde round-trip tests --------------------------------------------------

class TestSerdeNestedTimeline:

    def test_serialize_fade_amount(self):
        """Serializing a timeline ref with fade/amount includes those fields."""
        reg = make_registry()
        tl = Timeline(compose_fn=sum_compose)
        inner_tl = Timeline(compose_fn=sum_compose)
        wrapped = MetadataClip(
            inner_tl,
            timeline_name="sub",
            tl_fade_in=0.5,
            tl_fade_out=1.0,
            tl_amount=0.8,
        )
        tl.add(0.0, wrapped)

        data = serialize_timeline(tl, reg)
        ev = data["events"][0]
        assert ev["timeline"] == {
            "name": "sub",
            "fade_in": 0.5,
            "fade_out": 1.0,
            "amount": 0.8,
        }

    def test_serialize_no_fade_omits_fields(self):
        """When fade/amount are default, only name is included."""
        reg = make_registry()
        tl = Timeline(compose_fn=sum_compose)
        wrapped = MetadataClip(
            Timeline(compose_fn=sum_compose),
            timeline_name="sub",
        )
        tl.add(0.0, wrapped)

        data = serialize_timeline(tl, reg)
        ev = data["events"][0]
        assert ev["timeline"] == {"name": "sub"}

    def test_deserialize_creates_scaled_clip(self):
        """Deserializing a timeline ref with fade/amount wraps in ScaledClip."""
        reg = make_registry()
        sub_data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {"position": 0, "clip": {"type": "test_clip", "params": {"duration": 2}}},
            ],
        }
        load_fn = make_load_fn({"sub": sub_data})

        data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {
                    "position": 0,
                    "timeline": {"name": "sub", "fade_in": 0.5, "fade_out": 1.0, "amount": 0.8},
                },
            ],
        }
        tl = deserialize_timeline(data, reg, load_fn=load_fn)

        assert len(tl.events) == 1
        _, mc = tl.events[0]
        assert isinstance(mc, MetadataClip)
        assert mc.timeline_name == "sub"
        assert mc.tl_fade_in == 0.5
        assert mc.tl_fade_out == 1.0
        assert mc.tl_amount == 0.8
        # Inner is ScaledClip wrapping the sub-timeline
        assert isinstance(mc.inner, ScaledClip)
        assert mc.inner.fade_in == 0.5
        assert mc.inner.fade_out == 1.0
        assert mc.inner.amount == 0.8
        assert isinstance(mc.inner.inner, Timeline)

    def test_deserialize_no_fade_still_creates_scaled_clip(self):
        """Even without fade/amount, inner is ScaledClip (for duration clamping)."""
        reg = make_registry()
        sub_data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [],
        }
        load_fn = make_load_fn({"sub": sub_data})

        data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {"position": 0, "timeline": {"name": "sub"}},
            ],
        }
        tl = deserialize_timeline(data, reg, load_fn=load_fn)

        _, mc = tl.events[0]
        assert isinstance(mc, MetadataClip)
        # Always wrapped in ScaledClip for duration clamping
        assert isinstance(mc.inner, ScaledClip)
        assert mc.inner.fade_in == 0
        assert mc.inner.fade_out == 0
        assert mc.inner.amount == 1.0
        assert isinstance(mc.inner.inner, Timeline)

    def test_deserialize_uses_registry_scale_fn(self):
        """ScaledClip gets the registry's scale_fn when present."""
        reg = make_registry()
        scale_fn = lambda result, factor: result
        reg.register_scale(scale_fn)

        sub_data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [],
        }
        load_fn = make_load_fn({"sub": sub_data})

        data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {"position": 0, "timeline": {"name": "sub", "amount": 0.5}},
            ],
        }
        tl = deserialize_timeline(data, reg, load_fn=load_fn)

        _, mc = tl.events[0]
        assert isinstance(mc.inner, ScaledClip)
        assert mc.inner.scale_fn is scale_fn

    def test_round_trip(self):
        """serialize -> deserialize -> serialize produces identical JSON."""
        reg = make_registry()
        sub_data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {"position": 0, "clip": {"type": "test_clip", "params": {"duration": 2}}},
            ],
        }
        load_fn = make_load_fn({"sub": sub_data})

        original = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {
                    "position": 0,
                    "timeline": {"name": "sub", "fade_in": 0.5, "fade_out": 1.0, "amount": 0.8},
                },
            ],
        }
        tl = deserialize_timeline(original, reg, load_fn=load_fn)
        serialized = serialize_timeline(tl, reg)

        assert serialized["events"][0]["timeline"] == original["events"][0]["timeline"]

    def test_round_trip_defaults_omitted(self):
        """Round-trip with default fade/amount omits those keys."""
        reg = make_registry()
        sub_data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [],
        }
        load_fn = make_load_fn({"sub": sub_data})

        original = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {"position": 0, "timeline": {"name": "sub"}},
            ],
        }
        tl = deserialize_timeline(original, reg, load_fn=load_fn)
        serialized = serialize_timeline(tl, reg)

        assert serialized["events"][0]["timeline"] == {"name": "sub"}


# -- Recursive verify tests --------------------------------------------------

class TestRecursiveVerify:

    def test_nested_timeline_points_collected(self):
        """Points from nested timeline clips are included in output."""
        inner_tl = Timeline(compose_fn=sum_compose)
        inner_tl.add(0.0, clip(1.0, lambda t, ctx: {"ch": t}))
        inner_tl.add(2.0, clip(1.0, lambda t, ctx: {"ch": t}))

        outer_tl = Timeline(compose_fn=sum_compose)
        outer_tl.add(5.0, MetadataClip(inner_tl, timeline_name="sub"))

        points = collect_verify_points(outer_tl)

        # Outer: 1 event (inner_tl has duration 3.0) -> start + end
        # Inner: 2 clips -> 2 start + 2 end, offset by 5.0
        # Total: 6
        assert len(points) == 6

    def test_nested_points_offset_by_parent_position(self):
        """Inner clip points are offset by the outer timeline position."""
        inner_tl = Timeline(compose_fn=sum_compose)
        inner_tl.add(0.0, clip(1.0, lambda t, ctx: {"ch": t}))
        inner_tl.add(2.0, clip(1.0, lambda t, ctx: {"ch": t}))

        outer_tl = Timeline(compose_fn=sum_compose)
        outer_tl.add(10.0, MetadataClip(inner_tl, timeline_name="sub"))

        points = collect_verify_points(outer_tl)

        # Extract just the start points for inner clips (offset by 10.0)
        start_points = [p for p in points if p.edge == "start"]
        start_times = sorted(p.time_seconds for p in start_points)

        # Outer clip start at 10.0, inner clip[0] start at 10.0, inner clip[1] start at 12.0
        assert start_times == pytest.approx([10.0, 10.0, 12.0])

    def test_scaled_clip_wrapper_doesnt_prevent_recursion(self):
        """ScaledClip wrapping a timeline still allows recursion."""
        inner_tl = Timeline(compose_fn=sum_compose)
        inner_tl.add(0.0, clip(1.0, lambda t, ctx: {"ch": t}))

        scaled = ScaledClip(inner_tl, fade_in=0.5, amount=0.8)
        outer_tl = Timeline(compose_fn=sum_compose)
        outer_tl.add(5.0, MetadataClip(scaled, timeline_name="sub"))

        points = collect_verify_points(outer_tl)

        # Outer: start + end for the MetadataClip
        # Inner: start + end for the single inner clip, offset by 5.0
        assert len(points) == 4

        inner_starts = [p for p in points if p.edge == "start" and p.event_index == 0]
        # Both the outer MetadataClip (event 0) and inner clip (event 0) have start points
        assert len(inner_starts) == 2

    def test_non_nested_timeline_unchanged(self):
        """Regular clips without nested timelines still work."""
        tl = Timeline(compose_fn=sum_compose)
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": t}))
        tl.add(3.0, clip(1.0, lambda t, ctx: {"ch": t}))

        points = collect_verify_points(tl)

        assert len(points) == 4
        assert points[0].time_seconds == 0.0
        assert points[0].edge == "start"

    def test_deeply_nested(self):
        """Two levels of nesting collects all points."""
        deepest = Timeline(compose_fn=sum_compose)
        deepest.add(0.0, clip(1.0, lambda t, ctx: {"ch": t}))

        middle = Timeline(compose_fn=sum_compose)
        middle.add(0.0, MetadataClip(deepest, timeline_name="deep"))

        outer = Timeline(compose_fn=sum_compose)
        outer.add(10.0, MetadataClip(middle, timeline_name="mid"))

        points = collect_verify_points(outer)

        # outer: MetadataClip(middle) -> start + end at 10.0 / 10.999 (middle duration = 1.0)
        # middle: MetadataClip(deepest) -> start + end at 10.0 / 10.999 (deepest duration = 1.0)
        # deepest: clip -> start + end at 10.0 / 10.999
        # Total: 6
        assert len(points) == 6

        # All start points should be at 10.0 (three nested levels all starting at 0 offset)
        starts = [p for p in points if p.edge == "start"]
        assert all(p.time_seconds == pytest.approx(10.0) for p in starts)


# -- NestedBPMClip tests -----------------------------------------------------

class TestNestedBPMClip:

    def test_duration_returns_beats(self):
        """NestedBPMClip.duration returns max end-beat, not seconds."""
        inner = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        inner.add(0.0, clip(4.0, lambda t, ctx: {"ch": t}))  # 4 beats
        inner.add(4.0, clip(4.0, lambda t, ctx: {"ch": t}))  # ends at beat 8

        nested = NestedBPMClip(inner)
        # Duration should be 8 beats, NOT 4 seconds (which BPMTimeline.duration would return)
        assert nested.duration == 8.0
        # Verify BPMTimeline.duration would give seconds (the bug we're fixing)
        assert inner.duration == pytest.approx(4.0)  # 8 beats at 120 BPM = 4 seconds

    def test_duration_empty(self):
        """Empty nested timeline has duration 0."""
        inner = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        assert NestedBPMClip(inner).duration == 0.0

    def test_duration_none_propagates(self):
        """None duration from infinite clip passes through."""
        inner = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        inner.add(0.0, clip(None, lambda t, ctx: {}))
        assert NestedBPMClip(inner).duration is None

    def test_render_receives_beats(self):
        """NestedBPMClip.render passes t in beats directly to _render_at."""
        inner = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        # Clip at beat 0, duration 4 beats. render returns {"ch": t} where t is local beat offset
        inner.add(0.0, clip(4.0, lambda t, ctx: {"ch": t}))

        nested = NestedBPMClip(inner)
        # At beat 2.0, the clip should render with local_t = 2.0
        result = nested.render(2.0, None)
        assert result == {"ch": 2.0}

    def test_render_without_wrapper_is_wrong(self):
        """Demonstrates the bug: BPMTimeline.render interprets beats as seconds."""
        inner = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        inner.add(0.0, clip(4.0, lambda t, ctx: {"ch": t}))

        # BPMTimeline.render(2.0) treats 2.0 as seconds, converts to 4.0 beats
        # With clip at beat 0 duration 4, local_t = 4.0 which is at the boundary
        # This is the double-conversion bug
        result_buggy = inner.render(2.0, None)
        assert result_buggy == {"ch": 4.0}  # Wrong! Should be 2.0

        # NestedBPMClip.render(2.0) passes 2.0 beats directly
        nested = NestedBPMClip(inner)
        result_fixed = nested.render(2.0, None)
        assert result_fixed == {"ch": 2.0}  # Correct

    def test_nested_bpm_in_parent_bpm(self):
        """Full integration: BPMTimeline parent with nested BPMTimeline child."""
        # Inner: clip at beat 2, duration 2 beats
        inner = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        inner.add(2.0, clip(2.0, lambda t, ctx: {"ch": t + 100}))

        nested = NestedBPMClip(inner)

        # Parent: nested clip at beat 4, should span beats 4-8 (inner is 4 beats: 0+4=4 or 2+2=4)
        parent = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        parent.add(4.0, nested)

        # At 3 seconds = 6 beats at 120 BPM. Inner local_t = 6-4 = 2 beats.
        # Inner clip at beat 2, local_t = 2-2 = 0. Renders {"ch": 100}
        result = parent.render(3.0, None)
        assert result == {"ch": 100}

        # At 3.5 seconds = 7 beats. Inner local_t = 7-4 = 3 beats.
        # Inner clip at beat 2, local_t = 3-2 = 1. Renders {"ch": 101}
        result = parent.render(3.5, None)
        assert result == {"ch": 101}

    def test_with_scaled_clip(self):
        """NestedBPMClip wrapped in ScaledClip with fade works in beat-space."""
        calls = []

        def mock_scale(result, factor):
            calls.append(factor)
            return {k: v * factor for k, v in result.items()}

        inner = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        inner.add(0.0, clip(8.0, lambda t, ctx: {"ch": 10.0}))

        nested = NestedBPMClip(inner)
        # 8 beats total, 4 beat fade_in
        scaled = ScaledClip(nested, fade_in=4.0, amount=1.0, scale_fn=mock_scale)

        # At beat 2 (within 4-beat fade_in): factor = 2/4 = 0.5
        result = scaled.render(2.0, None)
        assert calls[-1] == pytest.approx(0.5)
        assert result == {"ch": 5.0}

    def test_serde_wraps_bpm_nested(self):
        """Deserialization wraps nested BPMTimeline in NestedBPMClip under ScaledClip."""
        reg = make_registry()
        sub_data = {
            "$schema": "cuelist-timeline-v1",
            "type": "BPMTimeline",
            "tempo": {"bpm": 120},
            "events": [
                {"position": 0, "clip": {"type": "test_clip", "params": {"duration": 4}}},
            ],
        }
        load_fn = make_load_fn({"sub": sub_data})

        data = {
            "$schema": "cuelist-timeline-v1",
            "type": "BPMTimeline",
            "tempo": {"bpm": 120},
            "events": [
                {"position": 0, "timeline": {"name": "sub"}},
            ],
        }
        tl = deserialize_timeline(data, reg, load_fn=load_fn)

        _, mc = tl.events[0]
        assert isinstance(mc, MetadataClip)
        # Always wrapped in ScaledClip, with NestedBPMClip inside
        assert isinstance(mc.inner, ScaledClip)
        assert isinstance(mc.inner.inner, NestedBPMClip)
        assert isinstance(mc.inner.inner.inner, BPMTimeline)

    def test_serde_wraps_bpm_with_scaled(self):
        """Deserialization: NestedBPMClip goes under ScaledClip."""
        reg = make_registry()
        sub_data = {
            "$schema": "cuelist-timeline-v1",
            "type": "BPMTimeline",
            "tempo": {"bpm": 120},
            "events": [],
        }
        load_fn = make_load_fn({"sub": sub_data})

        data = {
            "$schema": "cuelist-timeline-v1",
            "type": "BPMTimeline",
            "tempo": {"bpm": 120},
            "events": [
                {"position": 0, "timeline": {"name": "sub", "fade_in": 2, "amount": 0.8}},
            ],
        }
        tl = deserialize_timeline(data, reg, load_fn=load_fn)

        _, mc = tl.events[0]
        assert isinstance(mc.inner, ScaledClip)
        assert isinstance(mc.inner.inner, NestedBPMClip)
        assert isinstance(mc.inner.inner.inner, BPMTimeline)

    def test_verify_recurses_through_nested_bpm(self):
        """Verify collects points from nested BPMTimeline through NestedBPMClip."""
        inner = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        inner.add(0.0, clip(4.0, lambda t, ctx: {"ch": t}))
        inner.add(4.0, clip(4.0, lambda t, ctx: {"ch": t}))

        nested = NestedBPMClip(inner)
        outer = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        # Place at beat 10 = 5.0 seconds at 120 BPM
        outer.add(10.0, MetadataClip(nested, timeline_name="sub"))

        points = collect_verify_points(outer)

        # Outer: MetadataClip -> start + end
        # Inner: 2 clips -> 2 start + 2 end, offset by 5.0 seconds
        assert len(points) == 6

        starts = [p for p in points if p.edge == "start"]
        start_times = sorted(p.time_seconds for p in starts)
        # Outer starts at 5.0s (beat 10), inner clip[0] at 5.0s (beat 0+10=10), inner clip[1] at 7.0s (beat 4+10=14)
        assert start_times == pytest.approx([5.0, 5.0, 7.0])

    def test_verify_with_scaled_and_nested_bpm(self):
        """Verify recurses through ScaledClip → NestedBPMClip → BPMTimeline."""
        inner = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        inner.add(0.0, clip(2.0, lambda t, ctx: {"ch": t}))

        nested = NestedBPMClip(inner)
        scaled = ScaledClip(nested, fade_in=1.0, amount=0.8)
        outer = BPMTimeline(tempo_map=TempoMap(bpm=120.0), compose_fn=sum_compose)
        outer.add(4.0, MetadataClip(scaled, timeline_name="sub"))

        points = collect_verify_points(outer)
        # Outer: start + end for MetadataClip
        # Inner: start + end for the clip
        assert len(points) == 4


# -- Duration override tests -------------------------------------------------

class TestDurationOverride:

    def test_duration_override_returns_override(self):
        """ScaledClip with duration_override returns override, not inner duration."""
        inner = clip(32.0, lambda t, ctx: {"ch": t})
        sc = ScaledClip(inner, duration_override=16.0)
        assert sc.duration == 16.0

    def test_duration_override_none_delegates(self):
        """ScaledClip without duration_override delegates to inner."""
        inner = clip(32.0, lambda t, ctx: {"ch": t})
        sc = ScaledClip(inner)
        assert sc.duration == 32.0

    def test_fade_uses_overridden_duration(self):
        """Fade envelope uses the overridden duration, not the inner duration."""
        calls = []

        def mock_scale(result, factor):
            calls.append(factor)
            return result

        inner = clip(32.0, lambda t, ctx: {"ch": 1.0})
        sc = ScaledClip(inner, fade_out=4.0, scale_fn=mock_scale, duration_override=16.0)

        # At t=14: fade_out with duration=16, fade_out=4 → starts at t=12
        # factor = (16-14)/4 = 0.5
        sc.render(14.0, None)
        assert calls[-1] == pytest.approx(0.5)

        # At t=16: fade_out → factor = 0.0 → returns {}
        result = sc.render(16.0, None)
        assert result == {}

    def test_parent_stops_rendering_at_clamped_duration(self):
        """Parent timeline stops rendering sub-clip at the clamped duration."""
        inner_tl = Timeline(compose_fn=sum_compose)
        inner_tl.add(0.0, clip(32.0, lambda t, ctx: {"ch": 1.0}))

        sc = ScaledClip(inner_tl, duration_override=8.0)
        parent = Timeline(compose_fn=sum_compose)
        parent.add(0.0, sc)

        # At t=4 (within clamped duration), renders
        result = parent.render(4.0, None)
        assert result == {"ch": 1.0}

        # At t=9 (past clamped duration of 8), not rendered
        result = parent.render(9.0, None)
        assert result == {}

    def test_serde_duration_override_from_meta(self):
        """Deserialization reads meta.durationBeats as duration_override."""
        reg = make_registry()
        sub_data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {"position": 0, "clip": {"type": "test_clip", "params": {"duration": 32}}},
            ],
        }
        load_fn = make_load_fn({"sub": sub_data})

        data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {
                    "position": 0,
                    "timeline": {"name": "sub"},
                    "meta": {"durationBeats": 16},
                },
            ],
        }
        tl = deserialize_timeline(data, reg, load_fn=load_fn)

        _, mc = tl.events[0]
        assert isinstance(mc.inner, ScaledClip)
        assert mc.inner.duration_override == 16
        assert mc.inner.duration == 16

    def test_serde_no_meta_duration_falls_back(self):
        """Without meta.durationBeats, ScaledClip uses inner duration."""
        reg = make_registry()
        sub_data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {"position": 0, "clip": {"type": "test_clip", "params": {"duration": 32}}},
            ],
        }
        load_fn = make_load_fn({"sub": sub_data})

        data = {
            "$schema": "cuelist-timeline-v1",
            "type": "Timeline",
            "events": [
                {"position": 0, "timeline": {"name": "sub"}},
            ],
        }
        tl = deserialize_timeline(data, reg, load_fn=load_fn)

        _, mc = tl.events[0]
        assert isinstance(mc.inner, ScaledClip)
        assert mc.inner.duration_override is None
        # Falls back to inner timeline duration
        assert mc.inner.duration == 32

    def test_amount_with_duration_override(self):
        """Amount scaling works with clamped duration."""
        calls = []

        def mock_scale(result, factor):
            calls.append(factor)
            return {k: v * factor for k, v in result.items()}

        inner = clip(32.0, lambda t, ctx: {"ch": 10.0})
        sc = ScaledClip(inner, amount=0.5, scale_fn=mock_scale, duration_override=16.0)

        # Mid-clip: factor = 0.5 * 1.0 (no fade) = 0.5
        result = sc.render(8.0, None)
        assert calls[-1] == pytest.approx(0.5)
        assert result == {"ch": 5.0}
