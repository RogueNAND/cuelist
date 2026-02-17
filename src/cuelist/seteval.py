"""Evaluate ordered set-operation lists against named object mappings."""

from __future__ import annotations

from typing import Any


_OPS = {
    "add": "__or__",
    "intersect": "__and__",
    "sub": "__sub__",
}


def evaluate_set(ops: list[list[str]], mapping: dict[str, Any]) -> Any | None:
    """Evaluate an ordered operations list against a name-to-object mapping.

    *ops* is a list of ``[operator, name]`` pairs, e.g.
    ``[["add", "front"], ["sub", "spot"]]``.

    *mapping* maps item names to set-like objects (must support ``|``, ``&``,
    ``-`` operators).

    Evaluation is left-to-right:

    - ``"add"``       — union:        ``result | item``
    - ``"intersect"`` — intersection: ``result & item``
    - ``"sub"``       — difference:   ``result - item``

    For the first item, the object is assigned directly regardless of operator.

    Returns the composed object, or ``None`` if *ops* is empty.
    """
    result: Any | None = None

    for entry in ops:
        op, name = entry[0], entry[1]

        if name not in mapping:
            raise ValueError(f"Unknown set item: {name!r}")

        dunder = _OPS.get(op)
        if dunder is None:
            raise ValueError(f"Unknown set operator: {op!r}")

        item = mapping[name]

        if result is None:
            result = item
        else:
            result = getattr(result, dunder)(item)

    return result
