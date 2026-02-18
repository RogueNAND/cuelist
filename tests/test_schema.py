"""Tests for cuelist.schema — auto-schema generation from clip factories."""

from cuelist.schema import generate_schema, clip_schema


# ---- Fixtures (test helper functions) ----

def simple_clip(duration, *, color, speed=1.0, enabled=True, label="default"):
    pass

def prefixed_colors(duration, *, color_a, color_b, speed=0.5):
    pass

@clip_schema({
    "color_a": {"type": "color", "label": "Color A"},
    "color_b": {"type": "color", "label": "Color B"},
    "selector": {"type": "set", "items_key": "groups", "label": "Fixtures"},
})
def gradient_like(duration, *, color_a, color_b, selector=None, speed=0.5):
    pass

def nullable_param(duration, *, target=None):
    pass

@clip_schema({"target": {"type": "set", "items_key": "groups"}})
def overridden_nullable(duration, *, target=None):
    pass


# ---- _is_color_name coverage ----

class TestColorNameDetection:
    def test_exact_color(self):
        schema = generate_schema(simple_clip)
        assert schema["params"]["color"]["type"] == "color"

    def test_prefixed_color(self):
        schema = generate_schema(prefixed_colors)
        assert schema["params"]["color_a"]["type"] == "color"
        assert schema["params"]["color_b"]["type"] == "color"

    def test_prefixed_color_has_default(self):
        schema = generate_schema(prefixed_colors)
        assert schema["params"]["color_a"]["default"] == [1, 1, 1]
        assert schema["params"]["color_b"]["default"] == [1, 1, 1]


# ---- Override + default interaction ----

class TestOverrideDefaults:
    def test_color_override_on_required_param_gets_default(self):
        """The original bug: color_a via @clip_schema override had default=None."""
        schema = generate_schema(gradient_like)
        assert schema["params"]["color_a"]["default"] == [1, 1, 1]
        assert schema["params"]["color_b"]["default"] == [1, 1, 1]

    def test_override_does_not_leak_tuple_keys(self):
        """When override changes type from tuple, nullable/items should be removed."""
        schema = generate_schema(overridden_nullable)
        field = schema["params"]["target"]
        assert field["type"] == "set"
        assert "nullable" not in field
        assert "items" not in field

    def test_nullable_tuple_keeps_tuple_keys(self):
        """A param that stays tuple type should keep nullable and items."""
        schema = generate_schema(nullable_param)
        field = schema["params"]["target"]
        assert field["type"] == "tuple"
        assert field["nullable"] is True
        assert "items" in field


# ---- Hidden params ----

class TestHiddenParams:
    def test_duration_hidden(self):
        schema = generate_schema(simple_clip)
        assert "duration" not in schema["params"]
        assert "duration" in schema["hidden"]


# ---- Basic type inference ----

class TestTypeInference:
    def test_number_default(self):
        schema = generate_schema(simple_clip)
        assert schema["params"]["speed"]["type"] == "number"
        assert schema["params"]["speed"]["default"] == 1.0

    def test_boolean_default(self):
        schema = generate_schema(simple_clip)
        assert schema["params"]["enabled"]["type"] == "boolean"
        assert schema["params"]["enabled"]["default"] is True

    def test_string_default(self):
        schema = generate_schema(simple_clip)
        assert schema["params"]["label"]["type"] == "string"
        assert schema["params"]["label"]["default"] == "default"
