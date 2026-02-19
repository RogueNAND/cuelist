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
        self._default_compose_name: str | None = None
        self._default_compose_fn: Callable | None = None
        self._sets: dict[str, dict[str, Any]] = {}
        self._scale_fn: Callable | None = None

    def register(self, name_or_fn=None, factory_fn=None, *, schema=None):
        """Register a clip factory, auto-generating schema if not provided.

        Can be used as a bare decorator (``@registry.register``) or as a
        direct call (``registry.register("name", fn)``).
        """
        if callable(name_or_fn) and factory_fn is None:
            # Bare decorator: @registry.register
            fn = name_or_fn
            name = fn.__name__
            self._factories[name] = fn
            self._schemas[name] = schema or generate_schema(fn)
            return fn

        # Direct call: registry.register("name", fn)
        name = name_or_fn
        fn = factory_fn
        self._factories[name] = fn
        self._schemas[name] = schema or generate_schema(fn)

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

    def register_compose(self, name_or_fn=None, fn=None, *, default=False):
        """Register a compose function by name.

        Can be used as a bare decorator (``@registry.register_compose``) or
        as a direct call (``registry.register_compose("name", fn)``).

        The first registered function (or any with ``default=True``)
        becomes the fallback used by ``deserialize_timeline`` when the
        JSON data does not specify a ``compose_fn``.
        """
        if callable(name_or_fn) and fn is None:
            func, name = name_or_fn, name_or_fn.__name__
        else:
            func, name = fn, name_or_fn

        self._compose_fns[name] = func
        self._compose_ids[id(func)] = name
        if default or self._default_compose_fn is None:
            self._default_compose_name = name
            self._default_compose_fn = func

        if fn is None and callable(name_or_fn):
            return func  # decorator mode: return the function

    def get_compose(self, name: str) -> Callable:
        """Retrieve a registered compose function by name."""
        if name not in self._compose_fns:
            raise KeyError(f"No compose function registered for {name!r}")
        return self._compose_fns[name]

    def find_resource_name(self, obj: Any) -> str | None:
        """Return the registered name for a resource object, or None."""
        return self._resource_ids.get(id(obj))

    def get_default_compose(self) -> tuple[str | None, Callable | None]:
        """Return *(name, fn)* for the default compose function, or *(None, None)*."""
        return self._default_compose_name, self._default_compose_fn

    def find_compose_name(self, fn: Callable) -> str | None:
        """Return the registered name for a compose function, or None."""
        return self._compose_ids.get(id(fn))

    def register_set(self, key: str, mapping: dict[str, Any]) -> None:
        """Register a named collection of set-like objects.

        Example: ``register_set("fixture_groups", {"front": front, "bar": bar})``
        """
        self._sets[key] = mapping

    def register_set_from_module(self, key: str, module: Any, type_filter: type) -> None:
        """Scan a module's namespace and register all instances of *type_filter*.

        Uses module-level variable names as keys.  Names starting with
        ``_`` are skipped.

        Example::

            import my_rig
            registry.register_set_from_module("fixture_groups", my_rig, FixtureGroup)
        """
        mapping: dict[str, Any] = {}
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if isinstance(obj, type_filter):
                mapping[name] = obj
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

    def register_scale(self, fn):
        """Register a domain-specific delta scale function: (dict, float) -> dict."""
        self._scale_fn = fn

    def get_scale(self):
        """Return the registered scale function, or None."""
        return self._scale_fn

    def get_set(self, key: str) -> dict[str, Any]:
        """Retrieve a set collection mapping by key."""
        if key not in self._sets:
            raise KeyError(f"No set collection registered for {key!r}")
        return self._sets[key]


registry = ClipRegistry()
