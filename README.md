# cuelist

A generic timeline library for scheduling and playing back clips. Domain-agnostic -- works with any rendering system (lighting, audio, animation, etc.).

## Installation

```bash
pip install cuelist
```

## Core Concepts

cuelist separates *what happens* from *when it happens* from *how it plays back*:

- **Clip** is the unit of content. It knows how to produce values over time, but nothing about where it sits in a sequence or how fast the clock ticks. You define clips for your domain by implementing a simple protocol -- a `duration` property and a `render(t, ctx)` method. Any object that has both satisfies the protocol; no base class required.

- **Timeline** is the arrangement layer. It places clips at specific start times and handles the overlap problem: when two clips produce values for the same target at the same moment, a compose function merges them. Timeline itself has no clock -- you call `render(t, ctx)` with whatever time you want, which makes it easy to test or scrub through offline.

- **Runner** is the real-time engine. It owns the frame loop, calling `render` on a clip (or timeline) at the current wall-clock time, then passing the result through an optional `apply_fn` and `output_fn`. This is where FPS, threading, and start/stop lifecycle live -- all kept out of your clip and timeline logic.

This layering means you can unit-test clips and timelines with plain function calls, swap playback strategies without touching content, and reuse the same runner across different timelines.

For music-synced work, **TempoMap** converts between beats and seconds, and **BPMTimeline** lets you schedule clips at beat positions instead of timestamps.

## Quick Start

The fastest way to create a clip is with the `clip()` factory:

```python
from cuelist import Timeline, Runner, clip

# Create clips inline -- just a duration and a render function
fade_in = clip(2.0, lambda t, ctx: {"light": t / 2.0})
hold    = clip(3.0, lambda t, ctx: {"light": 1.0})

# Schedule on a timeline
show = Timeline()
show.add(0.0, fade_in)
show.add(2.0, hold)

# Play back
runner = Runner(ctx=None, output_fn=print, fps=40.0)
runner.play_sync(show)
```

## Defining Clips

### Option 1: `clip()` factory

For simple clips, skip the class entirely:

```python
from cuelist import clip

fade = clip(2.0, lambda t, ctx: {"light": t / 2.0})
constant = clip(None, lambda t, ctx: {"light": 1.0})  # infinite duration
```

Pass `None` for duration to create a clip that never ends -- useful for persistent states or backgrounds that run until the runner is stopped.

### Option 2: Plain class (protocol-based)

Any object with a `duration` property and `render(t, ctx)` method satisfies the `Clip` protocol:

```python
from dataclasses import dataclass

@dataclass
class FadeClip:
    target_value: float
    fade_time: float

    @property
    def duration(self) -> float:
        return self.fade_time

    def render(self, t: float, ctx) -> dict[str, float]:
        progress = t / self.fade_time
        return {"output": self.target_value * progress}
```

No base class needed. The protocol is runtime-checkable, so `isinstance(obj, Clip)` works.

## Scheduling

### Timeline (time-based)

```python
from cuelist import Timeline, clip

show = Timeline()
show.add(0.0, clip(2.0, lambda t, ctx: {"light": t / 2.0}))  # 0s-2s: fade in
show.add(2.0, clip(3.0, lambda t, ctx: {"light": 1.0}))       # 2s-5s: hold

# Render without a clock -- useful for testing and offline work
result = show.render(t=1.0, ctx=None)
```

#### Chainable API

`add()`, `remove()`, and `clear()` return `self`, so you can chain calls:

```python
show = Timeline()
show.add(0.0, intro).add(5.0, verse).add(20.0, chorus)
```

#### Managing clips

```python
show.remove(5.0, verse)   # Remove a specific clip at its position
show.clear()               # Remove all clips
```

#### Timeline duration

Timeline computes its total duration from its clips:

```python
show = Timeline()
show.add(0.0, clip(2.0, lambda t, ctx: {}))
show.add(5.0, clip(3.0, lambda t, ctx: {}))
show.duration  # 8.0 (last clip ends at 5 + 3)
```

If any clip has infinite duration (`None`), the timeline's duration is also `None`. An empty timeline has duration `0.0`.

### Compose functions

When two clips overlap and produce values for the same target, a compose function decides the outcome. Pass one when creating the timeline:

```python
from cuelist import Timeline, compose_last, compose_sum

# Last-added clip wins (default)
timeline = Timeline(compose_fn=compose_last)

# Sum all overlapping values
timeline = Timeline(compose_fn=compose_sum)
```

Built-in compose functions:

| Function | Behavior |
|---|---|
| `compose_last` | Last-added clip wins (default) |
| `compose_sum` | Sum all values (numeric) |

You can write your own -- a compose function takes a list of deltas and returns a single merged delta:

```python
def compose_max(deltas):
    return max(deltas)

def compose_average(deltas):
    return sum(deltas) / len(deltas)

timeline = Timeline(compose_fn=compose_max)
```

### BPM and tempo

`BPMTimeline` works like `Timeline` but positions and clip durations are measured in **beats** instead of seconds. A `TempoMap` handles the conversion.

```python
from cuelist import TempoMap, BPMTimeline, clip

# Create a tempo map (default is 120 BPM)
tempo = TempoMap(128)

# Schedule clips at beat positions
show = BPMTimeline(tempo_map=tempo)
show.add(0, clip(16, lambda t, ctx: {"light": t / 16}))   # 16-beat fade
show.add(16, clip(16, lambda t, ctx: {"light": 1.0}))      # 16-beat hold
```

When a clip renders inside a `BPMTimeline`, the `t` value passed to `render()` is in beats, not seconds. So a clip with `duration=16` lasts 16 beats, and its `t` counts from `0` to `16`.

#### Tempo changes

Use `set_tempo()` to change BPM at a specific beat. The tempo map handles the math of variable-speed sections:

```python
tempo = TempoMap(128)
tempo.set_tempo(64, 140)    # Speed up to 140 BPM at beat 64
tempo.set_tempo(128, 100)   # Slow down at beat 128
```

Calls to `set_tempo()` are also chainable:

```python
tempo = TempoMap(128).set_tempo(64, 140).set_tempo(128, 100)
```

#### Converting between beats and seconds

```python
tempo = TempoMap(128)
tempo.time(4)    # 1.875 -- beat 4 falls at 1.875 seconds
tempo.beat(3.0)  # 6.4   -- 3 seconds in is beat 6.4
```

These conversions account for any tempo changes in the map.

### Nesting timelines

Since `Timeline` and `BPMTimeline` both have `duration` and `render()`, they satisfy the `Clip` protocol. This means you can nest one timeline inside another:

```python
from cuelist import Timeline, clip

# Build sections as individual timelines
intro = Timeline()
intro.add(0.0, clip(2.0, lambda t, ctx: {"light": t / 2.0}))
intro.add(2.0, clip(2.0, lambda t, ctx: {"light": 1.0}))

chorus = Timeline()
chorus.add(0.0, clip(4.0, lambda t, ctx: {"light": 0.5 + 0.5 * (t / 4.0)}))

# Compose into a master timeline
master = Timeline()
master.add(0.0, intro)     # intro.duration is 4.0
master.add(4.0, chorus)    # chorus starts at 4s
```

## Playback

### Basic playback

```python
from cuelist import Runner

runner = Runner(
    ctx=None,               # passed to every clip's render()
    output_fn=print,        # receives each frame's output
    fps=40.0,               # frames per second
)

runner.play_sync(show)  # Blocks until the timeline finishes
```

### Async playback

```python
runner.play(show)
# ... do other things ...
runner.wait()   # Block until done
runner.stop()   # Or stop early
```

### Pause and resume

```python
runner.play(show)
# ... later ...
runner.pause()           # Freezes playback, remembers position
runner.is_paused         # True
runner.resume()          # Continues from where it left off
```

### Starting mid-timeline

Both `play()` and `play_sync()` accept a `start_at` parameter to jump ahead:

```python
runner.play_sync(show, start_at=5.0)   # Start 5 seconds in
```

### apply_fn

An optional `apply_fn` transforms the raw clip output before it reaches `output_fn`. This is where you'd map abstract deltas to concrete hardware commands:

```python
def to_dmx(deltas):
    return {k: int(v * 255) for k, v in deltas.items()}

runner = Runner(ctx=None, apply_fn=to_dmx, output_fn=send_dmx, fps=40.0)
```

If omitted, the raw dict from `render()` passes straight through.

### Single-frame rendering

For testing or manual stepping, render individual frames without the frame loop:

```python
runner = Runner(ctx=None)

# render_frame: renders a frame and returns the result (no output_fn call)
result = runner.render_frame(show, t=1.5)

# tick: renders a frame, calls output_fn, and returns the result
result = runner.tick(show, t=1.5)
```

## Development

```bash
pip install -e ".[dev]"
pytest -v
```
