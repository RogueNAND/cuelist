"""Tests for ClipRegistry set collections."""

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
