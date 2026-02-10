"""Generic timeline library."""

from .clip import BaseClip, Clip, ComposeFn, Timeline, clip
from .compose import compose_first, compose_last, compose_mean, compose_sum
from .runner import Runner
from .tempo import BPMTimeline, TempoMap

__all__ = [
    "BaseClip",
    "BPMTimeline",
    "Clip",
    "clip",
    "ComposeFn",
    "compose_first",
    "compose_last",
    "compose_mean",
    "compose_sum",
    "Runner",
    "TempoMap",
    "Timeline",
]

__version__ = "0.1.0"
