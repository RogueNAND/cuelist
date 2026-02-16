"""Clip registry for mapping string names to factory functions."""

from __future__ import annotations

from typing import Any, Callable

from .schema import generate_schema


class ClipRegistry:

    def __init__(self) -> None:
        self._factories: dict[str, Callable] = {}
        self._schemas: dict[str, Any] = {}
        self._resources: dict[str, Any] = {}
        self._compose_fns: dict[str, Callable] = {}

    def register(self, name: str, factory_fn: Callable, schema: Any = None) -> None:
        """Register a clip factory by name, auto-generating schema if not provided."""
        self._factories[name] = factory_fn
        if schema is None:
            schema = generate_schema(factory_fn)
        self._schemas[name] = schema

    def create(self, name: str, params: dict) -> Any:
        """Instantiate a clip from a registered factory name and params dict."""
        if name not in self._factories:
            raise KeyError(f"No clip factory registered for {name!r}")
        return self._factories[name](**params)

    def list_factories(self) -> dict[str, Any]:
        """Return {name: schema_or_None} for all registered factories."""
        return {name: self._schemas[name] for name in self._factories}

    def list_resources(self) -> list[str]:
        """Return list of registered resource names."""
        return list(self._resources.keys())

    def register_resource(self, name: str, obj: Any) -> None:
        """Register a non-serializable resource (e.g. Scene instance) by name."""
        self._resources[name] = obj

    def get_resource(self, name: str) -> Any:
        """Retrieve a registered resource by name."""
        if name not in self._resources:
            raise KeyError(f"No resource registered for {name!r}")
        return self._resources[name]

    def register_compose(self, name: str, fn: Callable) -> None:
        """Register a compose function by name."""
        self._compose_fns[name] = fn

    def get_compose(self, name: str) -> Callable:
        """Retrieve a registered compose function by name."""
        if name not in self._compose_fns:
            raise KeyError(f"No compose function registered for {name!r}")
        return self._compose_fns[name]


registry = ClipRegistry()
