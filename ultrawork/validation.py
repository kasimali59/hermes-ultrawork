"""Fail-closed request and settings validation; never echoes sensitive input."""
from __future__ import annotations
import re

_SECRET = re.compile(r"(?:sk-[A-Za-z0-9_-]{20,}|(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+|-----BEGIN [A-Z ]*PRIVATE KEY-----)", re.I)
_PROTECTED = re.compile(r"\b(?:credential|api key|password|payment|billing|publish|send message|external message|firmware|kernel|embedded controller|hardware controller|wmi|hid|smbus|privileged|sudo|delete all|drop table|rm -rf)\b", re.I)
_ALLOWED_CLASSES = frozenset({"architect", "routine", "qa", "research", "integration", "reporting", "unknown"})


def error(code: str, message: str, field: str | None = None) -> dict:
    result = {"ok": False, "error": {"code": code, "message": message}}
    if field:
        result["error"]["field"] = field
    return result


def validate_settings(settings: object) -> dict | None:
    if not isinstance(settings, dict):
        return error("E_CONFIG", "Plugin settings must be an object.")
    orchestrators = settings.get("orchestrator_profiles", ["architect"])
    bindings = settings.get("role_bindings")
    priorities = settings.get("profile_priority", {})
    if not isinstance(orchestrators, list) or not orchestrators or any(not isinstance(value, str) or not value for value in orchestrators):
        return error("E_CONFIG", "orchestrator_profiles must be a non-empty list of profile ids.", "orchestrator_profiles")
    if not isinstance(bindings, dict) or not bindings:
        return error("E_CONFIG", "role_bindings must be a non-empty object of ordered profile ids.", "role_bindings")
    if any(key not in _ALLOWED_CLASSES or not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value) for key, value in bindings.items()):
        return error("E_CONFIG", "role_bindings contains an invalid role or profile list.", "role_bindings")
    if not isinstance(priorities, dict) or any(not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, int) for key, value in priorities.items()):
        return error("E_CONFIG", "profile_priority must map profile ids to integers.", "profile_priority")
    return None


def validate_request(request: object) -> tuple[dict | None, dict | None]:
    if not isinstance(request, dict) or set(request) - {"mode", "goal", "items", "operation_id", "catalog_revision"}:
        return None, error("E_SCHEMA", "Request contains unsupported fields or is not an object.")
    if request.get("mode") != "plan" or not isinstance(request.get("goal"), str) or not request["goal"].strip() or len(request["goal"]) > 12000:
        return None, error("E_SCHEMA", "Only plan mode with a non-empty bounded goal is accepted.", "goal")
    items = request.get("items")
    if items is None:
        items = [{"id": "architect-root", "title": request["goal"], "task_class": "unknown"}]
    if not isinstance(items, list) or not items or len(items) > 16:
        return None, error("E_BOUNDS", "items must contain between one and sixteen items.", "items")
    validated = []
    seen = set()
    protected = bool(_PROTECTED.search(request["goal"]))
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) - {"id", "title", "task_class", "parents"}:
            return None, error("E_SCHEMA", "Each item has unsupported fields or is not an object.", f"items[{index}]")
        identifier, title, task_class = item.get("id"), item.get("title"), item.get("task_class")
        parents = item.get("parents", [])
        if not all((isinstance(identifier, str) and identifier and len(identifier) <= 64, isinstance(title, str) and title.strip() and len(title) <= 4000, task_class in _ALLOWED_CLASSES, isinstance(parents, list), all(isinstance(parent, str) and parent for parent in parents))):
            return None, error("E_SCHEMA", "Item id, title, class, or parents are invalid.", f"items[{index}]")
        if identifier in seen or len(set(parents)) != len(parents) or identifier in parents:
            return None, error("E_GRAPH", "Item ids and parents must be unique and cannot self-link.", f"items[{index}]")
        seen.add(identifier)
        protected = protected or bool(_PROTECTED.search(title))
        validated.append({"id": identifier, "title": title.strip(), "task_class": task_class, "parents": sorted(parents)})
    if any(parent not in seen for item in validated for parent in item["parents"]):
        return None, error("E_GRAPH", "Every parent must name another item.", "items")
    remaining = {item["id"]: set(item["parents"]) for item in validated}
    while remaining:
        ready = {identifier for identifier, parents in remaining.items() if not parents}
        if not ready:
            return None, error("E_GRAPH", "Item parents must form an acyclic graph.", "items")
        for identifier in ready:
            del remaining[identifier]
        for parents in remaining.values():
            parents.difference_update(ready)
    if _SECRET.search(request["goal"]) or any(_SECRET.search(item["title"]) for item in validated):
        return None, error("E_SECRET_INPUT", "Request contains secret-shaped input; remove it before planning.")
    return {"goal": request["goal"].strip(), "items": validated, "protected": protected}, None
