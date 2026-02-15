"""JSON serialization and deserialization for timelines."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .clip import Timeline
from .registry import ClipRegistry
from .tempo import BPMTimeline, TempoMap

log = logging.getLogger(__name__)


def _serialize_params(params: dict, registry: ClipRegistry) -> dict:
    """Serialize clip params, replacing resource objects with their names."""
    result = {}
    for key, value in params.items():
        # Check if the value is a registered resource — replace with name
        found = False
        for rname, robj in registry._resources.items():
            if value is robj:
                result[key] = rname
                found = True
                break
        if not found:
            result[key] = value
    return result


def _deserialize_params(params: dict, registry: ClipRegistry) -> dict:
    """Deserialize clip params, resolving resource name strings."""
    result = {}
    for key, value in params.items():
        if isinstance(value, str) and value in registry._resources:
            result[key] = registry.get_resource(value)
        else:
            result[key] = value
    return result


def serialize_timeline(timeline: Timeline | BPMTimeline, registry: ClipRegistry) -> dict:
    """Convert a Timeline or BPMTimeline to a JSON-compatible dict."""
    is_bpm = isinstance(timeline, BPMTimeline)

    # Find compose_fn name
    compose_fn_name = None
    for name, fn in registry._compose_fns.items():
        if fn is timeline.compose_fn:
            compose_fn_name = name
            break

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
                for beat, bpm in tm._changes[1:]  # skip initial (0, base_bpm)
            ],
        }

    events = []
    for position, clip_obj in timeline.events:
        meta = getattr(clip_obj, "_cuelist_meta", {})
        event: dict[str, Any] = {"position": position}

        # Check if this is a nested timeline reference
        tl_name = getattr(clip_obj, "_cuelist_timeline_name", None)
        if tl_name is not None:
            event["timeline"] = {"name": tl_name}
        else:
            # Regular clip serialization
            clip_type = getattr(clip_obj, "_cuelist_type", None)
            clip_params = getattr(clip_obj, "_cuelist_params", {})
            if clip_type is not None:
                event["clip"] = {
                    "type": clip_type,
                    "params": _serialize_params(clip_params, registry),
                }

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
                sub_timeline._cuelist_timeline_name = tl_name
                if meta:
                    sub_timeline._cuelist_meta = meta
                timeline.add(position, sub_timeline)
            except Exception:
                log.exception("Failed to load nested timeline '%s'", tl_name)
            continue

        # Regular clip event
        clip_data = event.get("clip", {})
        clip_type = clip_data.get("type")
        clip_params = clip_data.get("params", {})

        if clip_type is not None:
            resolved_params = _deserialize_params(clip_params, registry)
            clip_obj = registry.create(clip_type, resolved_params)
            # Stash metadata for round-trip serialization
            clip_obj._cuelist_type = clip_type
            clip_obj._cuelist_params = clip_params
            if meta:
                clip_obj._cuelist_meta = meta
            timeline.add(position, clip_obj)

    return timeline
