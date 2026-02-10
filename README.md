# cuelist

A generic timeline library for scheduling and playing back clips. Domain-agnostic — works with any rendering system (lighting, audio, animation, etc.).

## Installation

```bash
pip install cuelist
```

## Core Concepts

cuelist separates *what happens* from *when it happens* from *how it plays back*:

- **Clip** is the unit of content. It knows how to produce values over time, but nothing about where it sits in a sequence or how fast the clock ticks. You define clips for your domain by implementing a simple protocol — a `duration` property and a `render(t, ctx)` method. Any object that has both satisfies the protocol; no base class required.

- **Timeline** is the arrangement layer. It places clips at specific start times and handles the overlap problem: when two clips produce values for the same target at the same moment, a user-supplied `compose_fn` merges them. Timeline itself has no clock — you call `render(t, ctx)` with whatever time you want, which makes it easy to test or scrub through offline.

- **Runner** is the real-time engine. It owns the frame loop, calling `render` on a clip (or timeline) at the current wall-clock time, then passing the result through an `apply_fn` and optional `output_fn`. This is where FPS, threading, and start/stop lifecycle live — all kept out of your clip and timeline logic.

This layering means you can unit-test clips and timelines with plain function calls, swap playback strategies without touching content, and reuse the same runner across different timelines.

For music-synced work, **TempoMap** converts between beats and seconds, and **BPMTimeline** lets you schedule clips at beat positions instead of timestamps.

## Usage

### Define a clip

```python
from dataclasses import dataclass

@dataclass
class FadeClip:
    value: float
    clip_duration: float

    @property
    def duration(self) -> float:
        return self.clip_duration

    def render(self, t: float, ctx: str) -> dict[str, float]:
        return {"output": self.value * (t / self.clip_duration)}
```

### Schedule clips on a timeline

```python
from cuelist import Timeline

timeline = Timeline(compose_fn=sum)
timeline.add(0.0, FadeClip(value=1.0, clip_duration=2.0))
timeline.add(1.0, FadeClip(value=0.5, clip_duration=3.0))

# Render without a clock — useful for testing and offline work
result = timeline.render(t=1.5, ctx="my_context")
```

### Play in real-time

```python
from cuelist import Runner

runner = Runner(
    ctx="my_context",
    apply_fn=lambda deltas: deltas,
    output_fn=print,
    fps=40.0,
)

runner.play_sync(timeline)  # Blocks until complete
```

Or non-blocking:

```python
runner.play(timeline)
# ... do other things ...
runner.wait()   # Block until done
runner.stop()   # Or stop early
```

### BPM and tempo

```python
from cuelist import TempoMap, BPMTimeline

tempo = TempoMap(128)
tempo.set_tempo(64, 140)   # Speed up at beat 64

show = BPMTimeline(compose_fn=sum, tempo_map=tempo)
show.add(0, intro_clip)    # Beat 0
show.add(16, verse_clip)   # Beat 16
show.add(32, chorus_clip)  # Beat 32

# Convert between beats and seconds
tempo.time(4)    # 1.875s (4 beats at 128 BPM)
tempo.beat(3.0)  # 6.4 beats
```

## Development

```bash
pip install -e ".[dev]"
pytest -v
```
