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

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def elapsed(self) -> float:
        """Current playback position in seconds."""
        return self._elapsed

    def set_elapsed(self, t: float) -> None:
        """Set the current playback position (seconds). For use by external controllers."""
        self._elapsed = t

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
    ) -> None:
        self.stop()
        self._clip = clip
        self._paused = False
        self._elapsed = start_at
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

    def wait(self) -> None:
        self._done_event.wait()

    def play_sync(self, clip: Clip[Ctx, Target, Delta], start_at: float = 0.0) -> None:
        self.play(clip, start_at)
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
        start_time = time.monotonic() - start_at
        self._thread = threading.Thread(
            target=self._loop,
            args=(start_time, frame_duration),
            daemon=True,
        )
        self._thread.start()

    def _loop(
        self,
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

                    show_time = time.monotonic() - start_time

                    if clip.duration is not None and show_time > clip.duration:
                        show_time = clip.duration

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

                    if clip.duration is not None and show_time >= clip.duration:
                        break

                    frame_count += 1
                    next_target = start_time + (frame_count * frame_duration)
                    delay = max(0.0, next_target - time.monotonic())

                    if self._stop_event.wait(timeout=delay):
                        break
            finally:
                clip_finished = clip is not None and clip.duration is not None and self._elapsed >= clip.duration
                if not self._paused or clip_finished:
                    self._paused = False
                    self._done_event.set()
