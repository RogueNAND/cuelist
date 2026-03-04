"""Generic frame loop runner for timeline playback."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

from .clip import Clip, Ctx, Delta, Target

log = logging.getLogger(__name__)
_MISSING = object()  # sentinel for "not provided" (distinct from None)

Output = TypeVar("Output")


def _make_set_event() -> threading.Event:
    e = threading.Event()
    e.set()
    return e


@dataclass
class Runner(Generic[Ctx, Target, Delta, Output]):

    ctx: Ctx
    apply_fn: Callable[[dict[Target, Delta]], Output] | None = None
    output_fn: Callable[[Output], None] | None = None
    fps: float = 40.0

    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stop_event: threading.Event = field(
        default_factory=threading.Event, init=False, repr=False
    )
    _done_event: threading.Event = field(
        default_factory=_make_set_event, init=False, repr=False
    )
    _clip: Clip[Ctx, Target, Delta] | None = field(
        default=None, init=False, repr=False
    )
    _elapsed: float = field(default=0.0, init=False, repr=False)
    _paused: bool = field(default=False, init=False, repr=False)
    _time_offset: float = field(default=0.0, init=False, repr=False)
    _target_time_offset: float = field(default=0.0, init=False, repr=False)
    _loop_start: float = field(default=0.0, init=False, repr=False)
    _loops_remaining: int = field(default=0, init=False, repr=False)
    _current_loop: int = field(default=0, init=False, repr=False)
    _region_end: float | None = field(default=None, init=False, repr=False)

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def elapsed(self) -> float:
        """Current playback position in seconds."""
        return self._elapsed

    @property
    def current_loop(self) -> int:
        """Zero-based index of the current loop iteration."""
        return self._current_loop

    @property
    def loops_remaining(self) -> int:
        """Remaining loop iterations. -1 means infinite, 0 means done."""
        return self._loops_remaining

    def set_elapsed(self, t: float) -> None:
        """Set the current playback position (seconds). For use by external controllers."""
        self._elapsed = t

    def set_loop_params(
        self,
        loops_remaining: int,
        loop_start: float | None = None,
        region_end: float | None = _MISSING,
    ) -> None:
        """Update loop parameters during playback.

        Args:
            loops_remaining: New loops remaining count (-1 = infinite, 0 = stop after current).
            loop_start: New loop start position in seconds, or None to keep current.
            region_end: New region end in seconds, None to clear, or _MISSING (default) to keep current.
        """
        self._loops_remaining = loops_remaining
        if loop_start is not None:
            self._loop_start = loop_start
        if region_end is not _MISSING:
            self._region_end = region_end

    @property
    def region_end(self) -> float | None:
        """Region end position in seconds, or None if no region is active."""
        return self._region_end

    @property
    def loop_start(self) -> float:
        """Current loop start position in seconds."""
        return self._loop_start

    def nudge(self, delta: float) -> None:
        """Shift the playback clock by *delta* seconds (positive = forward).

        The offset interpolates smoothly over several frames to avoid
        visual snapping in the output.
        """
        self._target_time_offset += delta

    @property
    def state(self) -> str:
        """Current playback state: 'stopped', 'playing', or 'paused'."""
        if self._paused:
            return "paused"
        if self._thread is not None and self._thread.is_alive():
            return "playing"
        return "stopped"

    @property
    def clip(self) -> Clip[Ctx, Target, Delta] | None:
        """Currently loaded clip, or None if stopped."""
        return self._clip

    def _apply(self, deltas: dict[Target, Delta]) -> Output:
        if self.apply_fn is None:
            return deltas  # type: ignore[return-value]
        return self.apply_fn(deltas)

    def play(
        self,
        clip: Clip[Ctx, Target, Delta],
        start_at: float = 0.0,
        loops: int = 0,
        loop_start: float = 0.0,
        region_end: float | None = None,
    ) -> None:
        self.stop()
        self._clip = clip
        self._paused = False
        self._elapsed = start_at
        self._time_offset = 0.0
        self._target_time_offset = 0.0
        self._loops_remaining = loops
        self._loop_start = loop_start
        self._current_loop = 0
        self._region_end = region_end
        self._done_event.clear()
        self._start_loop(start_at)

    def pause(self) -> None:
        if self._thread is None or self._paused:
            return
        # Set _paused before _stop_event so the loop's finally block sees it.
        self._paused = True
        self._stop_event.set()
        if self._thread is not threading.current_thread():
            self._thread.join()
        self._thread = None

    def resume(self) -> None:
        if not self._paused or self._clip is None:
            return
        self._paused = False
        self._start_loop(self._elapsed)

    def swap(self, clip: Clip[Ctx, Target, Delta]) -> None:
        """Atomically replace the clip used by the running playback loop.

        The next frame will pick up the new clip.  Safe to call from any
        thread — Python's GIL guarantees the attribute write is atomic
        with respect to the loop thread's read.
        """
        self._clip = clip

    def stop(self) -> None:
        self._stop_event.set()
        if self._paused:
            self._paused = False
            self._done_event.set()
        if self._thread is not None:
            if self._thread is not threading.current_thread():
                self._thread.join()
            self._thread = None
        self._clip = None
        self._region_end = None

    def wait(self) -> None:
        self._done_event.wait()

    def play_sync(
        self, clip: Clip[Ctx, Target, Delta], start_at: float = 0.0,
        loops: int = 0, loop_start: float = 0.0,
        region_end: float | None = None,
    ) -> None:
        self.play(clip, start_at, loops=loops, loop_start=loop_start, region_end=region_end)
        try:
            self.wait()
        except KeyboardInterrupt:
            self.stop()

    @staticmethod
    def _resolve(result):
        if inspect.isawaitable(result):
            return asyncio.run(result)
        return result

    def render_frame(self, clip: Clip[Ctx, Target, Delta], t: float) -> Output:
        deltas = self._resolve(clip.render(t, self.ctx))
        return self._apply(deltas)

    def tick(self, clip: Clip[Ctx, Target, Delta], t: float) -> Output:
        """Render a single frame at time *t* and send it through the output pipeline."""
        deltas = self._resolve(clip.render(t, self.ctx))
        output = self._apply(deltas)
        if self.output_fn is not None:
            self.output_fn(output)
        return output

    async def async_tick(self, clip: Clip[Ctx, Target, Delta], t: float) -> Output:
        """Async version of tick() for callers already in an event loop."""
        result = clip.render(t, self.ctx)
        if inspect.isawaitable(result):
            result = await result
        output = self._apply(result)
        if self.output_fn is not None:
            self.output_fn(output)
        return output

    def _start_loop(self, start_at: float) -> None:
        self._stop_event.clear()
        frame_duration = 1.0 / self.fps
        loop_start = time.monotonic()
        start_time = loop_start - start_at
        self._thread = threading.Thread(
            target=self._loop,
            args=(loop_start, start_time, frame_duration),
            daemon=True,
        )
        self._thread.start()

    def _interpolate_nudge(self) -> None:
        """Smooth nudge offset toward its target (exponential ease-out)."""
        diff = self._target_time_offset - self._time_offset
        if abs(diff) < 0.001:
            self._time_offset = self._target_time_offset
        else:
            self._time_offset += diff * 0.2

    @staticmethod
    def _effective_end(clip: Clip, region_end: float | None) -> float | None:
        """Compute the effective playback endpoint, clamped to clip duration."""
        end = region_end if region_end is not None else clip.duration
        if end is not None and clip.duration is not None:
            end = min(end, clip.duration)
        return end

    def _handle_loop_boundary(self) -> tuple[float, float, int]:
        """Advance loop state and return new (loop_start, start_time, frame_count).

        Must only be called when the current iteration has reached its end
        and loops remain.
        """
        if self._loops_remaining > 0:
            self._loops_remaining -= 1
        self._current_loop += 1
        loop_start = time.monotonic()
        start_time = loop_start - self._loop_start
        self._time_offset = 0.0
        self._target_time_offset = 0.0
        return loop_start, start_time, 0

    def _loop(
        self,
        loop_start: float,
        start_time: float,
        frame_duration: float,
    ) -> None:
        frame_count = 0
        clip = self._clip  # initial snapshot
        with asyncio.Runner() as async_runner:
            try:
                while not self._stop_event.is_set():
                    # Re-read each frame so swap() takes effect on the next frame
                    clip = self._clip
                    if clip is None:
                        break

                    self._interpolate_nudge()
                    show_time = time.monotonic() - start_time + self._time_offset

                    effective_end = self._effective_end(clip, self._region_end)
                    if effective_end is not None and show_time > effective_end:
                        show_time = effective_end

                    self._elapsed = show_time

                    try:
                        result = clip.render(show_time, self.ctx)
                        if inspect.isawaitable(result):
                            deltas = async_runner.run(result)
                        else:
                            deltas = result
                        output = self._apply(deltas)
                        if self.output_fn is not None:
                            self.output_fn(output)
                    except Exception:
                        log.exception("Error rendering frame at %.3fs", show_time)

                    if effective_end is not None and show_time >= effective_end:
                        if self._loops_remaining != 0:  # -1 (infinite) or positive
                            loop_start, start_time, frame_count = self._handle_loop_boundary()
                            continue
                        break

                    frame_count += 1
                    # Pace frames from loop_start (real wall-clock), not start_time
                    # (which may be in the future when start_at is negative / pre-cue)
                    next_target = loop_start + (frame_count * frame_duration)
                    delay = max(0.0, next_target - time.monotonic())

                    if self._stop_event.wait(timeout=delay):
                        break
            finally:
                eff_end = self._effective_end(clip, self._region_end) if clip is not None else None
                clip_finished = clip is not None and eff_end is not None and self._elapsed >= eff_end
                if not self._paused or clip_finished:
                    self._paused = False
                    self._done_event.set()
