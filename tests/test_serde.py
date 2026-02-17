"""Tests for serde variable resolution and round-trip serialization."""

from dataclasses import dataclass

import pytest

from cuelist.registry import ClipRegistry
from cuelist.serde import (
    MetadataClip,
    _resolve_variables,
    deserialize_timeline,
    serialize_timeline,
)


# -- helpers ------------------------------------------------------------------

@dataclass
class DummyClip:
    duration: float

    def render(self, t, ctx):
        return {}


def make_registry():
    reg = ClipRegistry()
    reg.register("test_clip", lambda duration=4, color=(1, 1, 1), level=1.0: DummyClip(duration))
    return reg


# -- _resolve_variables -------------------------------------------------------

class TestResolveVariables:

    def test_no_variables_passthrough(self):
        params = {"a": 1, "b": "hello"}
        assert _resolve_variables(params, {}) == params

    def test_number_variable(self):
        variables = {"x": {"type": "number", "value": 42}}
        params = {"level": {"$var": "x"}}
        assert _resolve_variables(params, variables) == {"level": 42}

    def test_color_variable(self):
        variables = {"red": {"type": "color", "value": [1, 0, 0]}}
        params = {"color": {"$var": "red"}}
        assert _resolve_variables(params, variables) == {"color": [1, 0, 0]}

    def test_string_variable(self):
        variables = {"name": {"type": "string", "value": "hello"}}
        params = {"label": {"$var": "name"}}
        assert _resolve_variables(params, variables) == {"label": "hello"}

    def test_boolean_variable(self):
        variables = {"flag": {"type": "boolean", "value": True}}
        params = {"enabled": {"$var": "flag"}}
        assert _resolve_variables(params, variables) == {"enabled": True}

    def test_tuple_mixed_literal_and_var(self):
        variables = {"red": {"type": "color", "value": [1, 0, 0]}}
        params = {"wash": [{"$var": "red"}, 0.5]}
        result = _resolve_variables(params, variables)
        assert result == {"wash": [[1, 0, 0], 0.5]}

    def test_tuple_all_vars(self):
        variables = {
            "c": {"type": "color", "value": [0, 1, 0]},
            "d": {"type": "number", "value": 0.8},
        }
        params = {"wash": [{"$var": "c"}, {"$var": "d"}]}
        result = _resolve_variables(params, variables)
        assert result == {"wash": [[0, 1, 0], 0.8]}

    def test_tuple_no_vars(self):
        params = {"wash": [[1, 1, 1], 0.5]}
        result = _resolve_variables(params, {})
        assert result == {"wash": [[1, 1, 1], 0.5]}

    def test_missing_variable_passthrough(self):
        params = {"level": {"$var": "nonexistent"}}
        result = _resolve_variables(params, {})
        assert result == {"level": {"$var": "nonexistent"}}

    def test_mixed_literal_and_var_params(self):
        variables = {"x": {"type": "number", "value": 10}}
        params = {"a": {"$var": "x"}, "b": "literal", "c": 3.14}
        result = _resolve_variables(params, variables)
        assert result == {"a": 10, "b": "literal", "c": 3.14}


# -- deserialize_timeline with variables --------------------------------------

class TestDeserializeWithVariables:

    def test_basic_variable_resolution(self):
        reg = make_registry()
        data = {
            "$schema": "cuelist-timeline-v1",
            "type": "BPMTimeline",
            "tempo": {"bpm": 120},
            "variables": {
                "my_color": {"type": "color", "value": [1, 0, 0]},
                "my_level": {"type": "number", "value": 0.7},
            },
            "events": [
                {
                    "position": 0,
                    "clip": {
                        "type": "test_clip",
                        "params": {
                            "duration": 8,
                            "color": {"$var": "my_color"},
                            "level": {"$var": "my_level"},
                        },
                    },
                },
            ],
        }
        tl = deserialize_timeline(data, reg)
        assert len(tl.events) == 1

        # MetadataClip.params preserves raw $var refs
        pos, clip = tl.events[0]
        assert isinstance(clip, MetadataClip)
        assert clip.params["color"] == {"$var": "my_color"}
        assert clip.params["level"] == {"$var": "my_level"}

    def test_no_variables_still_works(self):
        reg = make_registry()
        data = {
            "$schema": "cuelist-timeline-v1",
            "type": "BPMTimeline",
            "tempo": {"bpm": 120},
            "events": [
                {
                    "position": 0,
                    "clip": {
                        "type": "test_clip",
                        "params": {"duration": 4, "color": [1, 1, 1], "level": 1.0},
                    },
                },
            ],
        }
        tl = deserialize_timeline(data, reg)
        assert len(tl.events) == 1

    def test_round_trip_preserves_variables(self):
        """serialize → deserialize round-trip keeps $var refs in MetadataClip.params."""
        reg = make_registry()
        data = {
            "$schema": "cuelist-timeline-v1",
            "type": "BPMTimeline",
            "tempo": {"bpm": 120},
            "variables": {
                "c": {"type": "color", "value": [0.5, 0, 1]},
            },
            "events": [
                {
                    "position": 4,
                    "clip": {
                        "type": "test_clip",
                        "params": {"duration": 8, "color": {"$var": "c"}},
                    },
                },
            ],
        }
        tl = deserialize_timeline(data, reg)
        serialized = serialize_timeline(tl, reg)

        # Serialized events keep the $var reference
        assert serialized["events"][0]["clip"]["params"]["color"] == {"$var": "c"}
