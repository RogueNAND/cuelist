"""Generic timeline library."""

from .clip import BaseTimeline, Clip, ComposeFn, Timeline, clip, compose_last, compose_sum
from .registry import ClipRegistry, registry
from .schema import clip_schema
from .runner import Runner
from .serde import MetadataClip, deserialize_timeline, serialize_timeline
from .seteval import evaluate_set
from .tempo import BPMTimeline, TempoMap

__all__ = [
    "BaseTimeline",
    "BPMTimeline",
    "Clip",
    "clip",
    "clip_schema",
    "ClipRegistry",
    "ComposeFn",
    "compose_last",
    "compose_sum",
    "deserialize_timeline",
    "evaluate_set",
    "MetadataClip",
    "registry",
    "Runner",
    "serialize_timeline",
    "TempoMap",
    "Timeline",
]

__version__ = "0.3.0"
