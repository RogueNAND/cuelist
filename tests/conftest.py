"""Shared test fixtures."""

import asyncio
from dataclasses import dataclass

import pytest

from cuelist import BPMTimeline, TempoMap, Timeline


@dataclass
class StubClip:
    """Finite clip that renders {"ch": value * t}."""

    value: float
    clip_duration: float

    @property
    def duration(self) -> float:
        return self.clip_duration

    def render(self, t: float, ctx: object) -> dict[str, float]:
        return {"ch": self.value * t}


@dataclass
class InfiniteClip:
    """Clip with duration=None, renders constant output."""

    value: float

    @property
    def duration(self) -> None:
        return None

    def render(self, t: float, ctx: object) -> dict[str, float]:
        return {"ch": self.value}


@dataclass
class AsyncStubClip:
    """Finite clip with async render."""

    value: float
    clip_duration: float

    @property
    def duration(self) -> float:
        return self.clip_duration

    async def render(self, t: float, ctx: object) -> dict[str, float]:
        return {"ch": self.value * t}


@dataclass
class AsyncInfiniteClip:
    """Infinite clip with async render."""

    value: float

    @property
    def duration(self) -> None:
        return None

    async def render(self, t: float, ctx: object) -> dict[str, float]:
        return {"ch": self.value}


def sum_compose(deltas: list[float]) -> float:
    return sum(deltas)


@pytest.fixture
def stub_clip() -> StubClip:
    return StubClip(value=2.0, clip_duration=5.0)


@pytest.fixture
def infinite_clip() -> InfiniteClip:
    return InfiniteClip(value=1.0)


@pytest.fixture
def timeline() -> Timeline:
    return Timeline(compose_fn=sum_compose)


@pytest.fixture
def tempo_map() -> TempoMap:
    return TempoMap(120.0)


@pytest.fixture
def async_stub_clip() -> AsyncStubClip:
    return AsyncStubClip(value=2.0, clip_duration=5.0)


@pytest.fixture
def async_infinite_clip() -> AsyncInfiniteClip:
    return AsyncInfiniteClip(value=1.0)


@pytest.fixture
def bpm_timeline() -> BPMTimeline:
    return BPMTimeline(compose_fn=sum_compose)
