"""Generic timeline library."""

from .clip import BaseTimeline, Clip, ComposeFn, ScaledClip, Timeline, clip, compose_last, compose_sum
from .clip import _fade_envelope as fade_envelope
from .registry import ClipRegistry, registry
from .schema import clip_schema
from .runner import Runner
from .serde import MetadataClip, deserialize_timeline, serialize_timeline
from .seteval import evaluate_set
from .tempo import BPMTimeline, TempoMap
from .verify import VerifyPoint, collect_verify_points

__all__ = [
    "BaseTimeline",
    "BPMTimeline",
    "Clip",
    "clip",
    "clip_schema",
    "ClipRegistry",
    "collect_verify_points",
    "ComposeFn",
    "compose_last",
    "compose_sum",
    "deserialize_timeline",
    "fade_envelope",
    "evaluate_set",
    "MetadataClip",
    "registry",
    "Runner",
    "ScaledClip",
    "serialize_timeline",
    "TempoMap",
    "Timeline",
    "VerifyPoint",
]

__version__ = "0.3.0"
