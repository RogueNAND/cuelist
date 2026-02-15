"""Generic timeline library."""

from .clip import Clip, ComposeFn, Timeline, clip, compose_last, compose_sum
from .registry import ClipRegistry, registry
from .runner import Runner
from .serde import deserialize_timeline, serialize_timeline
from .tempo import BPMTimeline, TempoMap

__all__ = [
    "BPMTimeline",
    "Clip",
    "clip",
    "ClipRegistry",
    "ComposeFn",
    "compose_last",
    "compose_sum",
    "deserialize_timeline",
    "registry",
    "Runner",
    "serialize_timeline",
    "TempoMap",
    "Timeline",
]

__version__ = "0.3.0"
