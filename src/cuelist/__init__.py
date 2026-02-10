"""Generic timeline library."""

from .clip import Clip, Timeline, ComposeFn
from .runner import Runner
from .tempo import TempoMap, BPMTimeline

__all__ = ["Clip", "Timeline", "ComposeFn", "Runner", "TempoMap", "BPMTimeline"]

__version__ = "0.1.0"
