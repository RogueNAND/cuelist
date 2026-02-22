"""Tests for Runner."""

import threading
import time

from cuelist import Runner

from conftest import InfiniteClip, StubClip


# --- render_frame ---


class TestRenderFrame:
    def test_render_frame_output(self) -> None:
        clip = StubClip(value=3.0, clip_duration=5.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d)
        result = runner.render_frame(clip, t=2.0)
        assert result == {"ch": 6.0}

    def test_render_frame_apply_fn(self) -> None:
        clip = StubClip(value=1.0, clip_duration=5.0)
        runner = Runner(ctx=None, apply_fn=lambda d: sum(d.values()))
        result = runner.render_frame(clip, t=3.0)
        assert result == 3.0

    def test_render_frame_ctx_propagation(self) -> None:
        """Ctx is passed through to clip.render."""

        class CtxClip:
            @property
            def duration(self) -> float:
                return 1.0

            def render(self, t: float, ctx: str) -> dict[str, str]:
                return {"ctx_val": ctx}

        runner = Runner(ctx="hello", apply_fn=lambda d: d)
        result = runner.render_frame(CtxClip(), t=0.0)
        assert result == {"ctx_val": "hello"}


# --- play_sync ---


class TestPlaySync:
    def test_play_sync_completes_for_finite_clip(self) -> None:
        clip = StubClip(value=1.0, clip_duration=0.05)
        outputs: list = []
        runner = Runner(
            ctx=None,
            apply_fn=lambda d: d,
            output_fn=outputs.append,
            fps=40.0,
        )
        runner.play_sync(clip)
        assert len(outputs) >= 1

    def test_play_sync_handles_zero_duration(self) -> None:
        clip = StubClip(value=1.0, clip_duration=0.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        # Should complete quickly without hanging
        runner.play_sync(clip)


# --- stop ---


class TestStop:
    def test_stop_halts_infinite_clip(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.1)
        runner.stop()
        runner.wait()

    def test_stop_safe_when_idle(self) -> None:
        runner = Runner(ctx=None, apply_fn=lambda d: d)
        runner.stop()  # Should not raise


# --- play + wait ---


class TestPlayWait:
    def test_async_cycle_completes(self) -> None:
        clip = StubClip(value=1.0, clip_duration=0.05)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        runner.wait()

    def test_wait_returns_after_stop(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.stop()
        runner.wait()

    def test_play_replaces_previous_playback(self) -> None:
        outputs: list = []
        runner = Runner(
            ctx=None,
            apply_fn=lambda d: d,
            output_fn=outputs.append,
            fps=40.0,
        )
        clip1 = InfiniteClip(value=1.0)
        runner.play(clip1)
        time.sleep(0.05)
        clip2 = StubClip(value=2.0, clip_duration=0.05)
        runner.play(clip2)
        runner.wait()


# --- Timing drift ---


class TestTimingDrift:
    def test_total_elapsed_within_tolerance(self) -> None:
        clip_duration = 0.2
        clip = StubClip(value=1.0, clip_duration=clip_duration)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        start = time.monotonic()
        runner.play(clip)
        runner.wait()
        elapsed = time.monotonic() - start
        # Should complete within a reasonable tolerance of the clip duration
        # Allow up to 100ms overhead for timer scheduling
        assert elapsed < clip_duration + 0.1


# --- Final frame render ---


class TestFinalFrame:
    def test_last_output_matches_render_at_duration(self) -> None:
        clip = StubClip(value=3.0, clip_duration=0.05)
        outputs: list = []
        runner = Runner(
            ctx=None,
            apply_fn=lambda d: d,
            output_fn=outputs.append,
            fps=40.0,
        )
        runner.play(clip)
        runner.wait()
        # Last output should be render at t=duration => {"ch": 3.0 * 0.05}
        assert len(outputs) >= 1
        expected = clip.render(clip.duration, None)
        assert outputs[-1] == expected

    def test_final_frame_fires_for_short_clip(self) -> None:
        """Even if the clip is shorter than a frame, we get a final frame."""
        clip = StubClip(value=5.0, clip_duration=0.001)
        outputs: list = []
        runner = Runner(
            ctx=None,
            apply_fn=lambda d: d,
            output_fn=outputs.append,
            fps=40.0,
        )
        runner.play(clip)
        runner.wait()
        assert len(outputs) >= 1
        expected = clip.render(clip.duration, None)
        assert outputs[-1] == expected


# --- pause ---


class TestPause:
    def test_pause_stops_output(self) -> None:
        outputs: list = []
        runner = Runner(
            ctx=None,
            apply_fn=lambda d: d,
            output_fn=outputs.append,
            fps=40.0,
        )
        clip = InfiniteClip(value=1.0)
        runner.play(clip)
        time.sleep(0.1)
        runner.pause()
        count_at_pause = len(outputs)
        time.sleep(0.1)
        assert len(outputs) == count_at_pause

    def test_pause_when_idle_is_noop(self) -> None:
        runner = Runner(ctx=None, apply_fn=lambda d: d)
        runner.pause()  # Should not raise

    def test_double_pause_is_noop(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.pause()
        runner.pause()  # Should not raise
        runner.stop()

    def test_wait_blocks_while_paused(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.pause()
        # wait() should not return while paused — use a timeout to verify
        done = threading.Event()
        threading.Thread(target=lambda: (runner.wait(), done.set()), daemon=True).start()
        assert not done.wait(timeout=0.15)
        runner.stop()


# --- resume ---


class TestResume:
    def test_resume_continues_playback(self) -> None:
        outputs: list = []
        runner = Runner(
            ctx=None,
            apply_fn=lambda d: d,
            output_fn=outputs.append,
            fps=40.0,
        )
        clip = InfiniteClip(value=1.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.pause()
        count_at_pause = len(outputs)
        runner.resume()
        time.sleep(0.1)
        assert len(outputs) > count_at_pause
        runner.stop()

    def test_resume_when_not_paused_is_noop(self) -> None:
        runner = Runner(ctx=None, apply_fn=lambda d: d)
        runner.resume()  # Should not raise

    def test_resume_clip_completes(self) -> None:
        clip = StubClip(value=1.0, clip_duration=0.15)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.pause()
        runner.resume()
        runner.wait()  # Should return when clip finishes


# --- pause/stop interaction ---


class TestPauseStopInteraction:
    def test_stop_while_paused(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.pause()
        runner.stop()
        runner.wait()  # Should return immediately

    def test_play_while_paused_starts_fresh(self) -> None:
        outputs: list = []
        runner = Runner(
            ctx=None,
            apply_fn=lambda d: d,
            output_fn=outputs.append,
            fps=40.0,
        )
        clip1 = InfiniteClip(value=1.0)
        runner.play(clip1)
        time.sleep(0.05)
        runner.pause()
        clip2 = StubClip(value=2.0, clip_duration=0.05)
        runner.play(clip2)
        runner.wait()  # clip2 should complete

    def test_is_paused_property(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        assert not runner.is_paused
        runner.play(clip)
        time.sleep(0.05)
        assert not runner.is_paused
        runner.pause()
        assert runner.is_paused
        runner.resume()
        time.sleep(0.05)
        assert not runner.is_paused
        runner.stop()
        assert not runner.is_paused


# --- pause/resume timing ---


class TestPauseResumeTiming:
    def test_resume_elapsed_continuity(self) -> None:
        """show_time after resume should be >= show_time at pause."""
        times: list[float] = []

        class TimingClip:
            @property
            def duration(self) -> None:
                return None

            def render(self, t: float, ctx: object) -> dict[str, float]:
                times.append(t)
                return {"ch": t}

        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        clip = TimingClip()
        runner.play(clip)
        time.sleep(0.1)
        runner.pause()
        last_before_pause = times[-1]
        runner.resume()
        time.sleep(0.1)
        runner.stop()
        first_after_resume = next(t for t in times if t > last_before_pause)
        assert first_after_resume >= last_before_pause

    def test_pause_resume_cycle(self) -> None:
        """Multiple pause/resume cycles, clip still finishes."""
        clip = StubClip(value=1.0, clip_duration=0.3)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.pause()
        time.sleep(0.05)
        runner.resume()
        time.sleep(0.05)
        runner.pause()
        time.sleep(0.05)
        runner.resume()
        runner.wait()  # Should still complete


# --- tick ---


class TestTick:
    def test_tick_returns_output(self) -> None:
        clip = StubClip(value=3.0, clip_duration=5.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d)
        result = runner.tick(clip, t=2.0)
        assert result == {"ch": 6.0}

    def test_tick_calls_output_fn(self) -> None:
        clip = StubClip(value=1.0, clip_duration=5.0)
        outputs: list = []
        runner = Runner(ctx=None, apply_fn=lambda d: d, output_fn=outputs.append)
        runner.tick(clip, t=3.0)
        assert len(outputs) == 1
        assert outputs[0] == {"ch": 3.0}

    def test_tick_without_output_fn(self) -> None:
        clip = StubClip(value=2.0, clip_duration=5.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, output_fn=None)
        result = runner.tick(clip, t=1.0)
        assert result == {"ch": 2.0}


# --- Negative start_at ---


class TestNegativeStartAt:
    def test_play_with_negative_start_at(self) -> None:
        clip = StubClip(value=1.0, clip_duration=0.05)
        outputs: list = []
        runner = Runner(
            ctx=None,
            apply_fn=lambda d: d,
            output_fn=outputs.append,
            fps=40.0,
        )
        runner.play(clip, start_at=-0.1)
        runner.wait()
        assert len(outputs) >= 1


# --- nudge ---


class TestNudge:
    def test_nudge_sets_target_offset(self) -> None:
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.nudge(0.5)
        assert runner._target_time_offset == 0.5
        runner.nudge(0.3)
        assert runner._target_time_offset == 0.8

    def test_nudge_forward_advances_elapsed(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.nudge(0.5)
        # Wait long enough for interpolation to mostly converge (~500ms)
        time.sleep(0.5)
        # Elapsed should include most of the 0.5s offset
        assert runner.elapsed >= 0.8
        runner.stop()

    def test_nudge_backward_reduces_elapsed(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.15)
        elapsed_before = runner.elapsed
        runner.nudge(-0.1)
        time.sleep(0.15)
        # Elapsed should be less than it would be without the nudge
        assert runner.elapsed < elapsed_before + 0.2
        assert runner.elapsed >= 0.0
        runner.stop()

    def test_nudge_clamps_to_zero(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.nudge(-10.0)
        time.sleep(0.1)
        assert runner.elapsed >= 0.0
        runner.stop()

    def test_play_resets_offset(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.nudge(1.0)
        runner.stop()
        assert runner._target_time_offset == 1.0
        clip2 = InfiniteClip(value=1.0)
        runner.play(clip2)
        # play() resets both offsets
        assert runner._time_offset == 0.0
        assert runner._target_time_offset == 0.0
        time.sleep(0.05)
        assert runner.elapsed < 0.2
        runner.stop()

    def test_nudge_when_stopped_is_safe(self) -> None:
        runner = Runner(ctx=None, apply_fn=lambda d: d)
        runner.nudge(1.0)  # Should not raise
        assert runner._target_time_offset == 1.0

    def test_nudge_interpolates_gradually(self) -> None:
        clip = InfiniteClip(value=1.0)
        runner = Runner(ctx=None, apply_fn=lambda d: d, fps=40.0)
        runner.play(clip)
        time.sleep(0.05)
        runner.nudge(1.0)
        # After one frame (~25ms), offset should have moved partially, not fully
        time.sleep(0.03)
        assert runner._time_offset < 0.5  # should not have jumped to 1.0 yet
        assert runner._time_offset > 0.0  # but should have started moving
        runner.stop()
