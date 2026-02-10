# cuelist

A generic timeline library for scheduling and playing back clips. Domain-agnostic — works with any rendering system (lighting, audio, animation, etc.).

## Installation

```bash
pip install cuelist
```

## Core Concepts

cuelist separates *what happens* from *when it happens* from *how it plays back*:

- **Clip** is the unit of content. It knows how to produce values over time, but nothing about where it sits in a sequence or how fast the clock ticks. You define clips for your domain by implementing a simple protocol — a `duration` property and a `render(t, ctx)` method. Any object that has both satisfies the protocol; no base class required.

- **Timeline** is the arrangement layer. It places clips at specific start times and handles the overlap problem: when two clips produce values for the same target at the same moment, a compose function merges them. Timeline itself has no clock — you call `render(t, ctx)` with whatever time you want, which makes it easy to test or scrub through offline.

- **Runner** is the real-time engine. It owns the frame loop, calling `render` on a clip (or timeline) at the current wall-clock time, then passing the result through an optional `apply_fn` and `output_fn`. This is where FPS, threading, and start/stop lifecycle live — all kept out of your clip and timeline logic.

This layering means you can unit-test clips and timelines with plain function calls, swap playback strategies without touching content, and reuse the same runner across different timelines.

For music-synced work, **TempoMap** converts between beats and seconds, and **BPMTimeline** lets you schedule clips at beat positions instead of timestamps.

## Quick Start

The fastest way to create a clip is with the `clip()` factory:

```python
from cuelist import Timeline, Runner, clip

# Create clips inline — just a duration and a render function
fade_in = clip(2.0, lambda t, ctx: {"light": t / 2.0})
hold    = clip(3.0, lambda t, ctx: {"light": 1.0})

# Schedule on a timeline (compose_fn defaults to compose_last)
show = Timeline()
show.add(0.0, fade_in)
show.add(2.0, hold)

# Play back (apply_fn defaults to passthrough)
runner = Runner(ctx=None, output_fn=print, fps=40.0)
runner.play_sync(show)
```

## Defining Clips

### Option 1: Plain class (protocol-based)

Any object with a `duration` property and `render(t, ctx)` method satisfies the `Clip` protocol:

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

### Option 2: `clip()` factory

For simple clips, skip the class entirely:

```python
from cuelist import clip

fade = clip(2.0, lambda t, ctx: {"light": t / 2.0})
constant = clip(None, lambda t, ctx: {"light": 1.0})  # infinite duration
```

### Option 3: `BaseClip` subclass

For clips with state or complex logic, `BaseClip` handles the `duration` boilerplate:

```python
from cuelist import BaseClip

class PulseClip(BaseClip):
    def __init__(self, rate: float, duration: float):
        super().__init__(duration=duration)
        self.rate = rate

    def render(self, t, ctx):
        import math
        return {"light": (math.sin(t * self.rate) + 1) / 2}
```

## Scheduling

### Timeline (time-based)

```python
from cuelist import Timeline, compose_sum

# compose_fn defaults to compose_last; pass compose_sum to add overlaps
timeline = Timeline(compose_fn=compose_sum)
timeline.add(0.0, FadeClip(value=1.0, clip_duration=2.0))
timeline.add(1.0, FadeClip(value=0.5, clip_duration=3.0))

# Render without a clock — useful for testing and offline work
result = timeline.render(t=1.5, ctx="my_context")
```

### BPM and tempo

```python
from cuelist import TempoMap, BPMTimeline

tempo = TempoMap(128)
tempo.set_tempo(64, 140)   # Speed up at beat 64

show = BPMTimeline(compose_fn=compose_sum, tempo_map=tempo)
show.add(0, intro_clip)    # Beat 0
show.add(16, verse_clip)   # Beat 16
show.add(32, chorus_clip)  # Beat 32

# Convert between beats and seconds
tempo.time(4)    # 1.875s (4 beats at 128 BPM)
tempo.beat(3.0)  # 6.4 beats
```

## Playback

```python
from cuelist import Runner

runner = Runner(
    ctx="my_context",
    apply_fn=lambda deltas: deltas,  # optional, defaults to passthrough
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

## Compose Functions

Built-in functions for merging overlapping clip outputs:

| Function | Behavior |
|---|---|
| `compose_last` | Last-added clip wins (default) |
| `compose_first` | First-added clip wins |
| `compose_sum` | Sum all values (numeric) |
| `compose_mean` | Average all values (numeric) |

```python
from cuelist import Timeline, compose_sum

timeline = Timeline(compose_fn=compose_sum)
```

## Development

```bash
pip install -e ".[dev]"
pytest -v
```
