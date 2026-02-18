"""JSON serialization and deserialization for timelines."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .clip import Timeline
from .registry import ClipRegistry
from .seteval import evaluate_set
from .tempo import BPMTimeline, TempoMap

log = logging.getLogger(__name__)


class MetadataClip:
    """Wrapper that stores serialization metadata alongside a clip.

    Delegates ``render`` and ``duration`` to the inner clip while carrying
    ``clip_type``, ``params``, ``meta``, and optionally ``timeline_name``
    for round-trip JSON serialization.
    """

    def __init__(
        self,
        inner,
        *,
        clip_type: str | None = None,
        params: dict | None = None,
        meta: dict | None = None,
        timeline_name: str | None = None,
        template_id: str | None = None,
    ) -> None:
        self.inner = inner
        self.clip_type = clip_type
        self.params = params or {}
        self.meta = meta or {}
        self.timeline_name = timeline_name
        self.template_id = template_id

    @property
    def duration(self):
        return self.inner.duration

    def render(self, t, ctx):
        return self.inner.render(t, ctx)


def _serialize_params(params: dict, registry: ClipRegistry) -> dict:
    """Serialize clip params, replacing resource objects with their names."""
    result = {}
    for key, value in params.items():
        rname = registry.find_resource_name(value)
        if rname is not None:
            result[key] = rname
        else:
            result[key] = value
    return result


def _resolve_variables(params: dict, variables: dict) -> dict:
    """Replace ``{"$var": "name"}`` references with resolved values from *variables*.

    Works on top-level param values and inside list elements (for tuple params).
    Missing variable names are logged and passed through unchanged.
    """
    if not variables:
        return params

    def _resolve(value):
        if isinstance(value, dict) and "$var" in value:
            name = value["$var"]
            var_def = variables.get(name)
            if var_def is None:
                log.warning("Unknown variable reference %r, passing through", name)
                return value
            return var_def.get("value")
        if isinstance(value, list):
            return [_resolve(item) for item in value]
        return value

    return {key: _resolve(val) for key, val in params.items()}


def _deserialize_params(
    params: dict,
    registry: ClipRegistry,
    schema: dict | None = None,
) -> dict:
    """Deserialize clip params, resolving resource names and set operations."""
    resource_names = set(registry.list_resources())
    schema_params = (schema or {}).get("params", {})
    result = {}
    for key, value in params.items():
        field_schema = schema_params.get(key, {})

        # Set-type: resolve operations list to a composed object
        if field_schema.get("type") == "set" and isinstance(value, list):
            items_key = field_schema.get("items_key", "")
            try:
                mapping = registry.get_set(items_key)
                result[key] = evaluate_set(value, mapping)
            except (KeyError, ValueError):
                log.warning("Failed to evaluate set param %r, passing through", key)
                result[key] = value
        elif isinstance(value, str) and value in resource_names:
            result[key] = registry.get_resource(value)
        else:
            result[key] = value
    return result


def serialize_timeline(timeline: Timeline | BPMTimeline, registry: ClipRegistry) -> dict:
    """Convert a Timeline or BPMTimeline to a JSON-compatible dict.

    Note: Editor-specific fields (``templates``, ``variables``, ``audio``)
    are NOT produced here — they are managed by the cuelist-editor frontend
    and injected directly into the timeline JSON on save.
    """
    is_bpm = isinstance(timeline, BPMTimeline)

    # Find compose_fn name
    compose_fn_name = registry.find_compose_name(timeline.compose_fn)

    data: dict[str, Any] = {
        "$schema": "cuelist-timeline-v1",
        "type": "BPMTimeline" if is_bpm else "Timeline",
    }

    if compose_fn_name is not None:
        data["compose_fn"] = compose_fn_name

    if is_bpm:
        tm = timeline.tempo_map
        data["tempo"] = {
            "bpm": tm.bpm,
            "changes": [
                {"beat": beat, "bpm": bpm}
                for beat, bpm in tm.changes[1:]  # skip initial (0, base_bpm)
            ],
        }

    events = []
    for position, clip_obj in timeline.events:
        event: dict[str, Any] = {"position": position}

        if isinstance(clip_obj, MetadataClip):
            meta = clip_obj.meta
            if clip_obj.timeline_name is not None:
                event["timeline"] = {"name": clip_obj.timeline_name}
            elif clip_obj.clip_type is not None:
                event["clip"] = {
                    "type": clip_obj.clip_type,
                    "params": _serialize_params(clip_obj.params, registry),
                }
                if clip_obj.template_id:
                    event["clip"]["templateId"] = clip_obj.template_id
        else:
            meta = {}

        if meta:
            event["meta"] = meta
        events.append(event)

    data["events"] = events
    return data


def deserialize_timeline(
    data: dict,
    registry: ClipRegistry,
    load_fn: Callable[[str], dict] | None = None,
) -> Timeline | BPMTimeline:
    """Reconstruct a Timeline or BPMTimeline from a JSON dict.

    *load_fn*: optional callback that loads a sub-timeline's JSON data by name.
    Required when the timeline contains nested timeline references.

    Editor-injected fields consumed here but not produced by
    ``serialize_timeline``: ``templates`` (clip parameter presets)
    and ``variables`` (``{"$var": "name"}`` value substitution).
    The ``audio`` array is editor-only and ignored by deserialization.
    """
    tl_type = data.get("type", "Timeline")
    variables = data.get("variables", {})
    templates = data.get("templates", {})

    # Resolve compose function
    compose_fn_name = data.get("compose_fn")
    compose_fn = registry.get_compose(compose_fn_name) if compose_fn_name else None

    if tl_type == "BPMTimeline":
        tempo_data = data.get("tempo", {})
        tm = TempoMap(bpm=tempo_data.get("bpm", 120.0))
        for change in tempo_data.get("changes", []):
            tm.set_tempo(change["beat"], change["bpm"])
        kwargs: dict[str, Any] = {"tempo_map": tm}
        if compose_fn is not None:
            kwargs["compose_fn"] = compose_fn
        timeline = BPMTimeline(**kwargs)
    else:
        kwargs = {}
        if compose_fn is not None:
            kwargs["compose_fn"] = compose_fn
        timeline = Timeline(**kwargs)

    for event in data.get("events", []):
        position = event["position"]
        meta = event.get("meta", {})

        # Nested timeline reference
        if "timeline" in event:
            tl_ref = event["timeline"]
            tl_name = tl_ref.get("name")
            if not tl_name:
                log.warning("Skipping timeline event with no name at position %s", position)
                continue
            if load_fn is None:
                log.warning("Cannot load nested timeline '%s': no load_fn provided", tl_name)
                continue
            try:
                sub_data = load_fn(tl_name)
                sub_timeline = deserialize_timeline(sub_data, registry, load_fn=load_fn)
                wrapped = MetadataClip(
                    sub_timeline,
                    timeline_name=tl_name,
                    meta=meta if meta else None,
                )
                timeline.add(position, wrapped)
            except KeyError as e:
                log.warning("Skipping nested timeline '%s' at position %s: %s", tl_name, position, e)
            except Exception:
                log.exception("Failed to load nested timeline '%s'", tl_name)
            continue

        # Regular clip event
        clip_data = event.get("clip", {})
        clip_type = clip_data.get("type")
        clip_params = clip_data.get("params", {})
        template_id = clip_data.get("templateId")

        # Merge template defaults under instance overrides
        raw_instance_params = dict(clip_params)
        if template_id:
            template = templates.get(template_id)
            if template is not None:
                tpl_clip_type = template.get("clipType")
                if tpl_clip_type and tpl_clip_type != clip_type:
                    log.warning(
                        "Template '%s' clipType mismatch at position %s: expected '%s', got '%s'",
                        template_id, position, clip_type, tpl_clip_type,
                    )
                clip_params = {**template.get("params", {}), **clip_params}
            else:
                log.warning("Template '%s' not found, skipping merge at position %s", template_id, position)

        if clip_type is not None:
            try:
                clip_schema = registry.get_schema(clip_type)
                var_resolved = _resolve_variables(clip_params, variables)
                resolved_params = _deserialize_params(var_resolved, registry, schema=clip_schema)
                clip_obj = registry.create(clip_type, resolved_params)
                wrapped = MetadataClip(
                    clip_obj,
                    clip_type=clip_type,
                    params=raw_instance_params,
                    meta=meta if meta else None,
                    template_id=template_id,
                )
                timeline.add(position, wrapped)
            except KeyError as e:
                log.warning("Skipping clip '%s' at position %s: %s", clip_type, position, e)
            except Exception:
                log.exception("Failed to create clip '%s' at position %s", clip_type, position)

    return timeline
