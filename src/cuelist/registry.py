"""Clip registry for mapping string names to factory functions."""

from __future__ import annotations

from typing import Any, Callable

from .schema import generate_schema


class ClipRegistry:

    def __init__(self) -> None:
        self._factories: dict[str, Callable] = {}
        self._schemas: dict[str, Any] = {}
        self._resources: dict[str, Any] = {}
        self._resource_ids: dict[int, str] = {}
        self._compose_fns: dict[str, Callable] = {}
        self._compose_ids: dict[int, str] = {}
        self._sets: dict[str, dict[str, Any]] = {}

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

    def get_schema(self, name: str) -> Any:
        """Return the schema for a registered factory, or None."""
        return self._schemas.get(name)

    def list_factories(self) -> dict[str, Any]:
        """Return {name: schema_or_None} for all registered factories."""
        return {name: self._schemas[name] for name in self._factories}

    def list_resources(self) -> list[str]:
        """Return list of registered resource names."""
        return list(self._resources.keys())

    def register_resource(self, name: str, obj: Any) -> None:
        """Register a non-serializable resource (e.g. Scene instance) by name."""
        self._resources[name] = obj
        self._resource_ids[id(obj)] = name

    def get_resource(self, name: str) -> Any:
        """Retrieve a registered resource by name."""
        if name not in self._resources:
            raise KeyError(f"No resource registered for {name!r}")
        return self._resources[name]

    def register_compose(self, name: str, fn: Callable) -> None:
        """Register a compose function by name."""
        self._compose_fns[name] = fn
        self._compose_ids[id(fn)] = name

    def get_compose(self, name: str) -> Callable:
        """Retrieve a registered compose function by name."""
        if name not in self._compose_fns:
            raise KeyError(f"No compose function registered for {name!r}")
        return self._compose_fns[name]

    def find_resource_name(self, obj: Any) -> str | None:
        """Return the registered name for a resource object, or None."""
        return self._resource_ids.get(id(obj))

    def find_compose_name(self, fn: Callable) -> str | None:
        """Return the registered name for a compose function, or None."""
        return self._compose_ids.get(id(fn))

    def register_set(self, key: str, mapping: dict[str, Any]) -> None:
        """Register a named collection of set-like objects.

        Example: ``register_set("fixture_groups", {"front": front, "bar": bar})``
        """
        self._sets[key] = mapping

    def list_sets(self) -> dict[str, list[dict[str, str]]]:
        """Return ``{key: [{name, group?}, ...]}`` for all registered set collections."""
        result: dict[str, list[dict[str, str]]] = {}
        for key, mapping in self._sets.items():
            items: list[dict[str, str]] = []
            for name, obj in mapping.items():
                item: dict[str, str] = {"name": name}
                group = getattr(obj, "group", None)
                if group is not None:
                    item["group"] = group
                items.append(item)
            result[key] = items
        return result

    def get_set(self, key: str) -> dict[str, Any]:
        """Retrieve a set collection mapping by key."""
        if key not in self._sets:
            raise KeyError(f"No set collection registered for {key!r}")
        return self._sets[key]


registry = ClipRegistry()
