"""Tests for boilerplate-reduction convenience APIs."""

import asyncio
import inspect

import pytest

from cuelist import (
    BPMTimeline,
    Clip,
    Runner,
    Timeline,
    clip,
    compose_last,
    compose_sum,
)

from conftest import resolve


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
        assert resolve(tl.render(1.0, None)) == {"ch": 1.0}

    def test_works_on_runner(self) -> None:
        c = clip(1.0, lambda t, ctx: {"ch": t * 3})
        runner = Runner(ctx=None)
        result = runner.render_frame(c, t=0.5)
        assert result == {"ch": 1.5}


# ---------------------------------------------------------------------------
# compose functions
# ---------------------------------------------------------------------------


class TestComposeFunctions:
    def test_compose_last(self) -> None:
        assert compose_last([1, 2, 3]) == 3

    def test_compose_sum(self) -> None:
        assert compose_sum([1.0, 2.0, 3.0]) == 6.0

    def test_compose_sum_single(self) -> None:
        assert compose_sum([5.0]) == 5.0

    def test_compose_last_single(self) -> None:
        assert compose_last([42]) == 42

    def test_compose_last_on_timeline(self) -> None:
        tl = Timeline(compose_fn=compose_last)
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert resolve(tl.render(1.0, None)) == {"ch": 20.0}


# ---------------------------------------------------------------------------
# Default compose_fn on Timeline/BPMTimeline
# ---------------------------------------------------------------------------


class TestDefaultComposeFn:
    def test_timeline_default_compose_is_last(self) -> None:
        tl = Timeline()
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert resolve(tl.render(1.0, None)) == {"ch": 20.0}

    def test_bpm_timeline_default_compose_is_last(self) -> None:
        bt = BPMTimeline()
        bt.add(0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        bt.add(0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert resolve(bt.render(0.5, None)) == {"ch": 20.0}

    def test_timeline_explicit_compose_overrides(self) -> None:
        tl = Timeline(compose_fn=compose_sum)
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        tl.add(0.0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert resolve(tl.render(1.0, None)) == {"ch": 30.0}

    def test_bpm_timeline_explicit_compose_overrides(self) -> None:
        bt = BPMTimeline(compose_fn=compose_sum)
        bt.add(0, clip(2.0, lambda t, ctx: {"ch": 10.0}))
        bt.add(0, clip(2.0, lambda t, ctx: {"ch": 20.0}))
        assert resolve(bt.render(0.5, None)) == {"ch": 30.0}

    def test_timeline_no_args(self) -> None:
        """Timeline() with no arguments is valid."""
        tl = Timeline()
        assert tl.duration == 0.0
        assert resolve(tl.render(0.0, None)) == {}


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
