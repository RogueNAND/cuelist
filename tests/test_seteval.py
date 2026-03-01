"""Tests for seteval.evaluate_set()."""

import pytest

from cuelist.seteval import evaluate_set


class TestEvaluateSet:

    def test_empty_ops_returns_none(self):
        """Empty operations list returns None."""
        assert evaluate_set([], {"a": {1, 2}}) is None

    def test_single_add_returns_item(self):
        """Single 'add' op returns the item directly."""
        items = {"front": {1, 2, 3}}
        result = evaluate_set([["add", "front"]], items)
        assert result == {1, 2, 3}

    def test_union_two_sets(self):
        """Two 'add' ops produce a union."""
        items = {"a": {1, 2}, "b": {3, 4}}
        result = evaluate_set([["add", "a"], ["add", "b"]], items)
        assert result == {1, 2, 3, 4}

    def test_intersection(self):
        """'add' then 'intersect' produces an intersection."""
        items = {"a": {1, 2, 3}, "b": {2, 3, 4}}
        result = evaluate_set([["add", "a"], ["intersect", "b"]], items)
        assert result == {2, 3}

    def test_difference(self):
        """'add' then 'sub' produces a difference."""
        items = {"a": {1, 2, 3}, "b": {2}}
        result = evaluate_set([["add", "a"], ["sub", "b"]], items)
        assert result == {1, 3}

    def test_multi_step_chain(self):
        """Multi-step: add + intersect + sub."""
        items = {"a": {1, 2, 3, 4}, "b": {2, 3, 4, 5}, "c": {3}}
        result = evaluate_set(
            [["add", "a"], ["intersect", "b"], ["sub", "c"]],
            items,
        )
        # a & b = {2, 3, 4}, then - c = {2, 4}
        assert result == {2, 4}

    def test_unknown_name_raises(self):
        """Unknown item name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown set item"):
            evaluate_set([["add", "missing"]], {})

    def test_unknown_operator_raises(self):
        """Unknown operator raises ValueError."""
        items = {"a": {1}}
        with pytest.raises(ValueError, match="Unknown set operator"):
            evaluate_set([["xor", "a"]], items)
