from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from app.services.story_runtime_support import (
    DEFAULT_SERIAL_DELIVERY_MODE,
    _empty_long_term_state,
    _ensure_serial_runtime,
    ensure_story_bible_v2_structure,
)


WorkflowFactory = Callable[[dict[str, Any] | None], dict[str, Any]]



def clone_story_state_domains(
    story_bible: dict[str, Any] | None,
    *,
    workflow_factory: WorkflowFactory | None = None,
    active_arc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ensure_story_state_domains(
        deepcopy(story_bible or {}),
        workflow_factory=workflow_factory,
        active_arc=active_arc,
    )



def ensure_story_state_domains(
    story_bible: dict[str, Any] | None,
    *,
    workflow_factory: WorkflowFactory | None = None,
    active_arc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = ensure_story_bible_v2_structure(story_bible if isinstance(story_bible, dict) else {})
    payload.setdefault("control_console", {})
    payload.setdefault("planning_layers", {})
    payload.setdefault("story_state", {})
    runtime = _ensure_serial_runtime(payload)
    release_mode = runtime.get("delivery_mode", DEFAULT_SERIAL_DELIVERY_MODE)
    payload.setdefault("long_term_state", _empty_long_term_state(release_mode))
    if workflow_factory is not None:
        payload.setdefault("workflow_state", workflow_factory(active_arc or payload.get("active_arc")))
    else:
        payload.setdefault("workflow_state", {})
    return payload



def ensure_workflow_state(
    story_bible: dict[str, Any],
    *,
    workflow_factory: WorkflowFactory | None = None,
    active_arc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = ensure_story_state_domains(
        story_bible,
        workflow_factory=workflow_factory,
        active_arc=active_arc,
    )
    return payload.setdefault("workflow_state", {})



def ensure_control_console(story_bible: dict[str, Any]) -> dict[str, Any]:
    payload = ensure_story_state_domains(story_bible)
    return payload.setdefault("control_console", {})



def ensure_planning_layers(story_bible: dict[str, Any]) -> dict[str, Any]:
    payload = ensure_story_state_domains(story_bible)
    return payload.setdefault("planning_layers", {})



def ensure_serial_runtime(story_bible: dict[str, Any]) -> dict[str, Any]:
    payload = ensure_story_state_domains(story_bible)
    return _ensure_serial_runtime(payload)



def ensure_long_term_state(story_bible: dict[str, Any]) -> dict[str, Any]:
    payload = ensure_story_state_domains(story_bible)
    return payload.setdefault("long_term_state", _empty_long_term_state())



def ensure_story_state_bucket(story_bible: dict[str, Any]) -> dict[str, Any]:
    payload = ensure_story_state_domains(story_bible)
    return payload.setdefault("story_state", {})



def get_live_runtime(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    workflow_state = (story_bible or {}).get("workflow_state") or {}
    return workflow_state.get("live_runtime") or {}



def set_live_runtime(story_bible: dict[str, Any], value: dict[str, Any] | None) -> dict[str, Any]:
    workflow_state = ensure_workflow_state(story_bible)
    workflow_state["live_runtime"] = value or {}
    return story_bible



def get_current_pipeline(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    workflow_state = (story_bible or {}).get("workflow_state") or {}
    return workflow_state.get("current_pipeline") or {}



def get_planning_status(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    console = (story_bible or {}).get("control_console") or {}
    return console.get("planning_status") or {}



def get_chapter_card_queue(story_bible: dict[str, Any] | None, *, limit: int | None = None) -> list[dict[str, Any]]:
    console = (story_bible or {}).get("control_console") or {}
    queue = console.get("chapter_card_queue") or []
    queue = [item for item in queue if isinstance(item, dict)]
    return queue[:limit] if isinstance(limit, int) and limit >= 0 else queue



def get_story_state_bucket(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    return (story_bible or {}).get("story_state") or {}



def update_story_state_bucket(story_bible: dict[str, Any], **updates: Any) -> dict[str, Any]:
    bucket = ensure_story_state_bucket(story_bible)
    bucket.update(updates)
    return story_bible



def workflow_bootstrap_view(story_bible: dict[str, Any] | None) -> dict[str, Any]:
    workflow = (story_bible or {}).get("workflow_state") or {}
    return {
        "bootstrap_state": workflow.get("bootstrap_state"),
        "bootstrap_error": workflow.get("bootstrap_error"),
        "bootstrap_retry_count": int(workflow.get("bootstrap_retry_count", 0) or 0),
        "bootstrap_completed": bool(workflow.get("bootstrap_completed", False)),
    }
