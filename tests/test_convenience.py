"""Tests for boilerplate-reduction convenience APIs."""

import pytest

from cuelist import (
    BaseClip,
    BPMTimeline,
    Clip,
    Runner,
    Timeline,
    clip,
    compose_first,
    compose_last,
    compose_mean,
    compose_sum,
)


# ---------------------------------------------------------------------------
# clip() factory
# ---------------------------------------------------------------------------


class TestClipFactory:
    def test_satisfies_protocol(self) -> None:
        c = clip(2.0, lambda t, ctx: {"ch": t})
        assert isinstance(c, Clip)

    def test_duration(self) -> None:
        c = clip(3.5, lambda t, ctx: {})
        assert c.duration == 3.5

    def test_none_duration(self) -> None:
        c = clip(None, lambda t, ctx: {"ch": 1.0})
        assert c.duration is None

    def test_render(self) -> None:
        c = clip(2.0, lambda t, ctx: {"ch": t * 2})
        assert c.render(1.0, None) == {"ch": 2.0}

    def test_ctx_passed_through(self) -> None:
        c = clip(1.0, lambda t, ctx: {"val": ctx})
        assert c.render(0.5, "hello") == {"val": "hello"}

    def test_works_on_timeline(self) -> None:
        tl = Timeline(compose_fn=compose_sum)
        c = clip(2.0, lambda t, ctx: {"ch": t})
        tl.add(0.0, c)
        assert tl.render(1.0, None) == {"ch": 1.0}

    def test_works_on_runner(self) -> None:
        c = clip(1.0, lambda t, ctx: {"ch": t * 3})
        runner = Runner(ctx=None)
        result = runner.render_frame(c, t=0.5)
        assert result == {"ch": 1.5}


# ---------------------------------------------------------------------------
# BaseClip
# ---------------------------------------------------------------------------


class TestBaseClip:
    def test_satisfies_protocol(self) -> None:
        class MyClip(BaseClip):
            def render(self, t, ctx):
                return {"ch": t}

        c = MyClip(duration=2.0)
        assert isinstance(c, Clip)

    def test_duration_via_init(self) -> None:
        class MyClip(BaseClip):
            def render(self, t, ctx):
                return {}

        c = MyClip(duration=5.0)
        assert c.duration == 5.0

    def test_none_duration(self) -> None:
        class InfClip(BaseClip):
            def render(self, t, ctx):
                return {"ch": 1.0}

        c = InfClip()
        assert c.duration is None

    def test_render_works(self) -> None:
        class FadeClip(BaseClip):
            def __init__(self, value: float, dur: float):
                super().__init__(duration=dur)
                self.value = value

            def render(self, t, ctx):
                return {"ch": self.value * t}

        c = FadeClip(value=2.0, dur=3.0)
        assert c.render(1.5, None) == {"ch": 3.0}

    def test_unimplemented_render_raises(self) -> None:
        c = BaseClip(duration=1.0)
        with pytest.raises(NotImplementedError):
            c.render(0.0, None)

    def test_works_on_timeline(self) -> None:
        class SimpleClip(BaseClip):
            def render(self, t, ctx):
                return {"ch": t}

        tl = Timeline(compose_fn=compose_sum)
        tl.add(0.0, SimpleClip(duration=2.0))
        assert tl.render(1.0, None) == {"ch": 1.0}


# ---------------------------------------------------------------------------
# compose functions
# ---------------------------------------------------------------------------


class TestComposeFunctions:
    def test_compose_last(self) -> None:
        assert compose_last([1, 2, 3]) == 3

    def test_compose_first(self) -> None:
        assert compose_first([1, 2, 3]) == 1

    def test_compose_sum(self) -> None:
        assert compose_sum([1.0, 2.0, 3.0]) == 6.0

    def test_compose_mean(self) -> None:
        assert compose_mean([2.0, 4.0, 6.0]) == pytest.approx(4.0)

    def test_compose_sum_single(self) -> None:
        assert compose_sum([5.0]) == 5.0

    def test_compose_mean_single(self) -> None:
        assert compose_mean([7.0]) == 7.0

    def test_compose_last_single(self) -> None:
        assert compose_last([42]) == 42

    def test_compose_first_single(self) -> None:
        assert compose_first([42]) == 42

    def test_compose_last_on_timeline(self) -> None:
        tl = Timeline(compose_fn=compose_last)
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert tl.render(1.0, None) == {"ch": 20.0}

    def test_compose_first_on_timeline(self) -> None:
        tl = Timeline(compose_fn=compose_first)
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert tl.render(1.0, None) == {"ch": 10.0}


# ---------------------------------------------------------------------------
# Default compose_fn on Timeline/BPMTimeline
# ---------------------------------------------------------------------------


class TestDefaultComposeFn:
    def test_timeline_default_compose_is_last(self) -> None:
        tl = Timeline()
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert tl.render(1.0, None) == {"ch": 20.0}

    def test_bpm_timeline_default_compose_is_last(self) -> None:
        bt = BPMTimeline()
        bt.add(0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        bt.add(0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert bt.render(0.5, None) == {"ch": 20.0}

    def test_timeline_explicit_compose_overrides(self) -> None:
        tl = Timeline(compose_fn=compose_sum)
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert tl.render(1.0, None) == {"ch": 30.0}

    def test_bpm_timeline_explicit_compose_overrides(self) -> None:
        bt = BPMTimeline(compose_fn=compose_sum)
        bt.add(0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        bt.add(0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert bt.render(0.5, None) == {"ch": 30.0}

    def test_timeline_no_args(self) -> None:
        """Timeline() with no arguments is valid."""
        tl = Timeline()
        assert tl.duration == 0.0
        assert tl.render(0.0, None) == {}


# ---------------------------------------------------------------------------
# Default apply_fn on Runner
# ---------------------------------------------------------------------------


class TestDefaultApplyFn:
    def test_runner_no_apply_fn_passthrough(self) -> None:
        c = clip(1.0, lambda t, ctx: {"ch": t * 3})
        runner = Runner(ctx=None)
        result = runner.render_frame(c, t=2.0)
        assert result == {"ch": 6.0}

    def test_runner_explicit_apply_fn_still_works(self) -> None:
        c = clip(1.0, lambda t, ctx: {"ch": t})
        runner = Runner(ctx=None, apply_fn=lambda d: sum(d.values()))
        result = runner.render_frame(c, t=3.0)
        assert result == 3.0

    def test_runner_no_apply_fn_with_tick(self) -> None:
        c = clip(1.0, lambda t, ctx: {"ch": 5.0})
        outputs: list = []
        runner = Runner(ctx=None, output_fn=outputs.append)
        runner.tick(c, t=0.5)
        assert outputs == [{"ch": 5.0}]

    def test_runner_no_apply_fn_play_sync(self) -> None:
        c = clip(0.05, lambda t, ctx: {"ch": t})
        outputs: list = []
        runner = Runner(ctx=None, output_fn=outputs.append, fps=40.0)
        runner.play_sync(c)
        assert len(outputs) >= 1
