"""Tests for ClipRegistry: set collections, decorator registration, module scanning."""

import types

from cuelist.registry import ClipRegistry


class TestListSets:
    def test_list_sets_with_group(self) -> None:
        """Items with a .group attribute include it in the output."""

        class FakeGroup:
            def __init__(self, group: str | None = None):
                self.group = group

        reg = ClipRegistry()
        reg.register_set("things", {
            "a": FakeGroup("Cat1"),
            "b": FakeGroup("Cat2"),
        })
        result = reg.list_sets()
        assert result == {
            "things": [
                {"name": "a", "group": "Cat1"},
                {"name": "b", "group": "Cat2"},
            ]
        }

    def test_list_sets_without_group(self) -> None:
        """Plain objects without .group omit the key."""
        reg = ClipRegistry()
        reg.register_set("plain", {"x": object(), "y": object()})
        result = reg.list_sets()
        assert result == {
            "plain": [
                {"name": "x"},
                {"name": "y"},
            ]
        }

    def test_list_sets_mixed(self) -> None:
        """Mix of objects with and without .group."""

        class WithGroup:
            group = "G1"

        reg = ClipRegistry()
        reg.register_set("mix", {
            "has": WithGroup(),
            "no": object(),
        })
        result = reg.list_sets()
        items = {item["name"]: item for item in result["mix"]}
        assert items["has"] == {"name": "has", "group": "G1"}
        assert items["no"] == {"name": "no"}

    def test_list_sets_group_none_omitted(self) -> None:
        """Objects with group=None should not include the group key."""

        class NoneGroup:
            group = None

        reg = ClipRegistry()
        reg.register_set("ng", {"item": NoneGroup()})
        result = reg.list_sets()
        assert result == {"ng": [{"name": "item"}]}


class TestDefaultCompose:

    def test_first_register_becomes_default(self) -> None:
        reg = ClipRegistry()
        fn = lambda deltas: sum(deltas)
        reg.register_compose("mysum", fn)
        name, default_fn = reg.get_default_compose()
        assert name == "mysum"
        assert default_fn is fn

    def test_no_default_when_empty(self) -> None:
        reg = ClipRegistry()
        name, fn = reg.get_default_compose()
        assert name is None
        assert fn is None

    def test_explicit_default_overrides(self) -> None:
        reg = ClipRegistry()
        fn_a = lambda d: d[0]
        fn_b = lambda d: d[-1]
        reg.register_compose("a", fn_a)
        reg.register_compose("b", fn_b, default=True)
        name, fn = reg.get_default_compose()
        assert name == "b"
        assert fn is fn_b

    def test_second_register_does_not_override_default(self) -> None:
        reg = ClipRegistry()
        fn_a = lambda d: d[0]
        fn_b = lambda d: d[-1]
        reg.register_compose("a", fn_a)
        reg.register_compose("b", fn_b)
        name, fn = reg.get_default_compose()
        assert name == "a"
        assert fn is fn_a


class TestRegisterDecorator:

    def test_bare_decorator_registers_by_function_name(self) -> None:
        reg = ClipRegistry()

        @reg.register
        def my_factory(duration=4, *, color=(1, 1, 1)):
            return None

        assert "my_factory" in reg.list_factories()

    def test_bare_decorator_returns_original_function(self) -> None:
        reg = ClipRegistry()

        @reg.register
        def my_factory(duration=4):
            return "hello"

        assert my_factory(4) == "hello"

    def test_direct_call_still_works(self) -> None:
        reg = ClipRegistry()
        fn = lambda duration=4: None
        reg.register("custom_name", fn)
        assert "custom_name" in reg.list_factories()

    def test_decorator_generates_schema(self) -> None:
        reg = ClipRegistry()

        @reg.register
        def my_clip(duration, *, speed=1.0):
            return None

        schema = reg.get_schema("my_clip")
        assert schema is not None
        assert "speed" in schema["params"]

    def test_decorator_with_clip_schema(self) -> None:
        """@registry.register stacked with @clip_schema picks up overrides."""
        from cuelist.schema import clip_schema

        reg = ClipRegistry()

        @reg.register
        @clip_schema({"speed": {"min": 0, "max": 10}})
        def effect(duration, *, speed=1.0):
            return None

        schema = reg.get_schema("effect")
        assert schema["params"]["speed"]["min"] == 0
        assert schema["params"]["speed"]["max"] == 10


class TestRegisterComposeDecorator:

    def test_bare_decorator_registers_by_function_name(self) -> None:
        reg = ClipRegistry()

        @reg.register_compose
        def my_compose(deltas):
            return deltas[0]

        name, fn = reg.get_default_compose()
        assert name == "my_compose"
        assert fn is my_compose

    def test_bare_decorator_returns_original_function(self) -> None:
        reg = ClipRegistry()

        @reg.register_compose
        def my_compose(deltas):
            return deltas[0]

        assert callable(my_compose)
        assert my_compose([42]) == 42

    def test_direct_call_still_works(self) -> None:
        reg = ClipRegistry()
        fn = lambda deltas: deltas[0]
        reg.register_compose("custom", fn)
        assert reg.get_compose("custom") is fn


class TestRegisterSetFromModule:

    def _make_fake_module(self) -> tuple:
        """Create a fake module with typed objects for testing."""

        class FakeGroup:
            def __init__(self, group=None):
                self.group = group

        mod = types.ModuleType("fake_rig")
        mod.front = FakeGroup("Location")
        mod.back = FakeGroup("Location")
        mod.drummer = FakeGroup("Band")
        mod.not_a_group = "a string"
        mod._private = FakeGroup("Hidden")
        return mod, FakeGroup

    def test_scans_module_for_type_instances(self) -> None:
        mod, FakeGroup = self._make_fake_module()
        reg = ClipRegistry()
        reg.register_set_from_module("groups", mod, FakeGroup)

        result = reg.get_set("groups")
        assert "front" in result
        assert "back" in result
        assert "drummer" in result
        assert "not_a_group" not in result
        assert "_private" not in result

    def test_list_sets_includes_group_attribute(self) -> None:
        mod, FakeGroup = self._make_fake_module()
        reg = ClipRegistry()
        reg.register_set_from_module("groups", mod, FakeGroup)

        result = reg.list_sets()
        items = {item["name"]: item for item in result["groups"]}
        assert items["front"]["group"] == "Location"
        assert items["drummer"]["group"] == "Band"

    def test_replaces_existing_set(self) -> None:
        mod, FakeGroup = self._make_fake_module()
        reg = ClipRegistry()
        reg.register_set("groups", {"old_item": object()})
        reg.register_set_from_module("groups", mod, FakeGroup)

        result = reg.get_set("groups")
        assert "front" in result
        assert "old_item" not in result

    def test_non_module_finds_nothing(self) -> None:
        """Passing a non-module object (e.g. a class instance) should produce an empty set."""
        _, FakeGroup = self._make_fake_module()
        reg = ClipRegistry()
        reg.register_set_from_module("groups", object(), FakeGroup)

        result = reg.get_set("groups")
        assert len(result) == 0
