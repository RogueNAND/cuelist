"""JSON serialization and deserialization for timelines."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .clip import Timeline
from .registry import ClipRegistry
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
    ) -> None:
        self.inner = inner
        self.clip_type = clip_type
        self.params = params or {}
        self.meta = meta or {}
        self.timeline_name = timeline_name

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


def _deserialize_params(params: dict, registry: ClipRegistry) -> dict:
    """Deserialize clip params, resolving resource name strings."""
    resource_names = set(registry.list_resources())
    result = {}
    for key, value in params.items():
        if isinstance(value, str) and value in resource_names:
            result[key] = registry.get_resource(value)
        else:
            result[key] = value
    return result


def serialize_timeline(timeline: Timeline | BPMTimeline, registry: ClipRegistry) -> dict:
    """Convert a Timeline or BPMTimeline to a JSON-compatible dict."""
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

    load_fn: optional callback that loads a sub-timeline's JSON data by name.
    Required when the timeline contains nested timeline references.
    """
    tl_type = data.get("type", "Timeline")

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
            except Exception:
                log.exception("Failed to load nested timeline '%s'", tl_name)
            continue

        # Regular clip event
        clip_data = event.get("clip", {})
        clip_type = clip_data.get("type")
        clip_params = clip_data.get("params", {})

        if clip_type is not None:
            try:
                resolved_params = _deserialize_params(clip_params, registry)
                clip_obj = registry.create(clip_type, resolved_params)
                wrapped = MetadataClip(
                    clip_obj,
                    clip_type=clip_type,
                    params=clip_params,
                    meta=meta if meta else None,
                )
                timeline.add(position, wrapped)
            except Exception:
                log.exception("Failed to create clip '%s' at position %s", clip_type, position)

    return timeline
