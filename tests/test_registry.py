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
