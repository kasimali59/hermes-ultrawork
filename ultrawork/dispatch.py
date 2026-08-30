"""Single public kanban_create invocation with explicit outcome semantics."""
from __future__ import annotations


def dispatch(ctx, payload: dict) -> dict:
    try:
        result = ctx.dispatch_tool("kanban_create", payload)
    except TimeoutError:
        return {"status": "ambiguous"}
    except Exception:
        return {"status": "blocked"}
    if not isinstance(result, dict):
        return {"status": "ambiguous"}
    task_id = result.get("task_id")
    if result.get("ok") is True and isinstance(task_id, str) and task_id:
        return {"status": "queued", "task_id": task_id}
    if result.get("ok") is False:
        return {"status": "blocked"}
    return {"status": "ambiguous"}