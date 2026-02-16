"""Tests for async clip support."""

import asyncio
import time

import pytest

from cuelist import Clip, Runner, Timeline, clip, compose_sum

from conftest import AsyncInfiniteClip, AsyncStubClip, StubClip, resolve, sum_compose


# --- Protocol conformance ---


class TestAsyncProtocol:
    def test_async_stub_clip_is_clip(self) -> None:
        c = AsyncStubClip(value=1.0, clip_duration=2.0)
        assert isinstance(c, Clip)

    def test_async_infinite_clip_is_clip(self) -> None:
        c = AsyncInfiniteClip(value=1.0)
        assert isinstance(c, Clip)


# --- Async clips on Timeline ---


class TestAsyncTimeline:
    def test_async_clip_renders(self) -> None:
        tl = Timeline(compose_fn=sum_compose)
        tl.add(0.0, AsyncStubClip(value=2.0, clip_duration=5.0))
        result = resolve(tl.render(2.5, None))
        assert result == {"ch": 5.0}

    def test_mixed_sync_async(self) -> None:
        tl = Timeline(compose_fn=sum_compose)
        tl.add(0.0, StubClip(value=1.0, clip_duration=4.0))
        tl.add(0.0, AsyncStubClip(value=2.0, clip_duration=4.0))
        # At t=2: sync => 1.0*2=2.0, async => 2.0*2=4.0, sum=6.0
        result = resolve(tl.render(2.0, None))
        assert result == {"ch": 6.0}

    def test_async_clips_run_concurrently(self) -> None:
        """Three async clips each sleeping 0.1s should complete in ~0.1s, not ~0.3s."""

        class SlowAsyncClip:
            @property
            def duration(self):
                return 1.0

            async def render(self, t, ctx):
                await asyncio.sleep(0.1)
                return {"ch": 1.0}

        tl = Timeline(compose_fn=sum_compose)
        tl.add(0.0, SlowAsyncClip())
        tl.add(0.0, SlowAsyncClip())
        tl.add(0.0, SlowAsyncClip())

        start = time.monotonic()
        result = resolve(tl.render(0.5, None))
        elapsed = time.monotonic() - start

        assert result == {"ch": 3.0}
        assert elapsed < 0.25  # concurrent, not sequential


# --- clip() factory with async function ---


class TestAsyncClipFactory:
    def test_async_fn_clip(self) -> None:
        async def render_fn(t, ctx):
            return {"ch": t * 3}

        c = clip(2.0, render_fn)
        assert isinstance(c, Clip)
        # render returns a coroutine, which Timeline handles
        tl = Timeline()
        tl.add(0.0, c)
        result = resolve(tl.render(1.0, None))
        assert result == {"ch": 3.0}


# --- Runner with async clips ---


class TestAsyncRunner:
    def test_render_frame_with_async_clip(self) -> None:
        tl = Timeline(compose_fn=sum_compose)
        tl.add(0.0, AsyncStubClip(value=3.0, clip_duration=5.0))
        runner = Runner(ctx=None)
        result = runner.render_frame(tl, t=2.0)
        assert result == {"ch": 6.0}

    def test_tick_with_async_clip(self) -> None:
        tl = Timeline(compose_fn=sum_compose)
        tl.add(0.0, AsyncStubClip(value=1.0, clip_duration=5.0))
        outputs: list = []
        runner = Runner(ctx=None, output_fn=outputs.append)
        runner.tick(tl, t=3.0)
        assert outputs == [{"ch": 3.0}]

    def test_play_sync_with_async_clip(self) -> None:
        tl = Timeline(compose_fn=sum_compose)
        tl.add(0.0, AsyncStubClip(value=1.0, clip_duration=0.05))
        outputs: list = []
        runner = Runner(ctx=None, output_fn=outputs.append, fps=40.0)
        runner.play_sync(tl)
        assert len(outputs) >= 1

    def test_mixed_timeline_through_runner(self) -> None:
        tl = Timeline(compose_fn=sum_compose)
        tl.add(0.0, StubClip(value=1.0, clip_duration=0.05))
        tl.add(0.0, AsyncStubClip(value=2.0, clip_duration=0.05))
        outputs: list = []
        runner = Runner(ctx=None, output_fn=outputs.append, fps=40.0)
        runner.play_sync(tl)
        assert len(outputs) >= 1


# --- Nested async timelines ---


class TestNestedAsyncTimelines:
    def test_nested_async_render(self) -> None:
        inner = Timeline(compose_fn=sum_compose)
        inner.add(0.0, AsyncStubClip(value=3.0, clip_duration=2.0))
        outer = Timeline(compose_fn=sum_compose)
        outer.add(1.0, inner)
        # At t=2.0, inner local_t=1.0 => AsyncStubClip renders {"ch": 3.0*1.0}
        result = asyncio.run(outer.render(2.0, None))
        assert result == {"ch": pytest.approx(3.0)}

    def test_nested_mixed_sync_async(self) -> None:
        inner = Timeline(compose_fn=sum_compose)
        inner.add(0.0, AsyncStubClip(value=2.0, clip_duration=4.0))
        outer = Timeline(compose_fn=sum_compose)
        outer.add(0.0, StubClip(value=1.0, clip_duration=4.0))
        outer.add(0.0, inner)
        # At t=1.0: direct sync => 1.0, nested async => 2.0, sum=3.0
        result = asyncio.run(outer.render(1.0, None))
        assert result == {"ch": pytest.approx(3.0)}
