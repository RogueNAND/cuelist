"""Generic timeline library."""

from .clip import Clip, ComposeFn, Timeline, clip, compose_last, compose_sum
from .runner import Runner
from .tempo import BPMTimeline, TempoMap

__all__ = [
    "BPMTimeline",
    "Clip",
    "clip",
    "ComposeFn",
    "compose_last",
    "compose_sum",
    "Runner",
    "TempoMap",
    "Timeline",
]

__version__ = "0.2.0"
