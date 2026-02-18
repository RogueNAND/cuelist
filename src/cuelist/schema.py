"""Auto-schema generation for clip factory functions."""

from __future__ import annotations

import inspect
import typing
from typing import Any, Callable


ALWAYS_HIDDEN = {"duration", "fade_in", "fade_out"}


def _label(name: str) -> str:
    """Convert snake_case parameter name to Title Case label."""
    return name.replace("_", " ").title()


def _is_color_name(name: str) -> bool:
    return (
        name == "color"
        or name.startswith("color_") or name.startswith("colour_")
        or name.endswith("_color") or name.endswith("_colour")
    )


def _is_scene_name(name: str) -> bool:
    return name == "scene" or name.endswith("_scene")


def _infer_field(name: str, default: Any, annotation: Any) -> dict:
    """Infer a schema field from parameter name, default, and type annotation."""
    # Name-based heuristics
    if _is_color_name(name):
        return {"type": "color", "default": [1, 1, 1]}
    if _is_scene_name(name):
        return {"type": "resource"}

    # Default-value based
    if isinstance(default, bool):
        return {"type": "boolean", "default": default}
    if isinstance(default, (int, float)):
        return {"type": "number", "default": default}
    if isinstance(default, str):
        return {"type": "string", "default": default}
    if default is None:
        return {"type": "tuple", "nullable": True, "default": None, "items": []}

    # Fallback
    return {"type": "string"}


def generate_schema(fn: Callable, overrides: dict | None = None) -> dict:
    """Generate a UI schema dict from a clip factory function's signature.

    Returns ``{"params": {...}, "hidden": [...]}``.
    Automatically picks up ``fn._cuelist_schema_overrides`` if no explicit overrides given.
    """
    if overrides is None:
        overrides = getattr(fn, "_cuelist_schema_overrides", None) or {}
    else:
        overrides = overrides or {}
    sig = inspect.signature(fn)

    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}

    params: dict[str, Any] = {}
    hidden: list[str] = []

    for name, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue

        if name in ALWAYS_HIDDEN:
            hidden.append(name)
            continue

        default = param.default if param.default is not param.empty else None
        annotation = hints.get(name)

        field = _infer_field(name, default, annotation)
        field["label"] = _label(name)

        if "default" not in field and default is not None:
            field["default"] = default

        # Apply overrides (merged on top of inferred base)
        if name in overrides:
            field.update(overrides[name])

        # Ensure color fields always have a usable default
        if field.get("type") == "color" and field.get("default") is None:
            field["default"] = [1, 1, 1]

        # Clean up tuple-specific keys that leak when overrides change the type
        if field.get("type") != "tuple":
            field.pop("nullable", None)
            field.pop("items", None)

        params[name] = field

    return {"params": params, "hidden": hidden}


def clip_schema(overrides: dict) -> Callable:
    """Decorator that attaches schema overrides to a clip factory function."""
    def decorator(fn: Callable) -> Callable:
        fn._cuelist_schema_overrides = overrides
        return fn
    return decorator
