"""Pure deterministic planning from validated inputs and catalog snapshots."""
from __future__ import annotations
import json
from dataclasses import dataclass
from .catalog import Catalog
from .validation import error, validate_request, validate_settings


@dataclass(frozen=True, slots=True)
class PlanResult:
    payload: dict
    def to_json(self) -> str:
        return json.dumps(self.payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _candidate(role: str, settings: dict, catalog: Catalog) -> str | None:
    bindings = settings["role_bindings"]
    names = bindings.get(role, bindings.get("architect", []))
    records = {profile["name"]: profile for profile in catalog.profiles if profile["on_disk"]}
    candidates = [records[name] for name in names if name in records]
    if not candidates:
        return None
    priorities = settings["profile_priority"]
    return min(candidates, key=lambda p: (names.index(p["name"]), priorities.get(p["name"], 100), p["running_count"], p["ready_count"] + p["todo_count"], p["name"].encode("ascii", "strict")))["name"]


def plan_request(request: object, settings: object, catalog: Catalog, active_profile: str) -> PlanResult:
    validated, problem = validate_request(request)
    if problem:
        return PlanResult(problem)
    problem = validate_settings(settings)
    if problem:
        return PlanResult(problem)
    assert isinstance(settings, dict)
    if not isinstance(catalog, Catalog) or not isinstance(active_profile, str) or active_profile not in settings["orchestrator_profiles"]:
        return PlanResult(error("E_CONFIG", "Active profile is not authorized to create Ultrawork plans.", "orchestrator_profiles"))
    assert validated is not None
    architect = _candidate("architect", settings, catalog)
    if not architect:
        return PlanResult(error("E_NO_SAFE_ROUTE", "No configured on-disk Architect profile is available."))
    if validated["protected"]:
        items = [{"id": "architect-root", "assignee": architect, "parents": [], "task_class": "architect", "fanout_prohibited": True}]
        return PlanResult({"ok": True, "policy_version": "hermes-ultrawork-plan-v1", "catalog_revision": catalog.revision, "plan": {"protected_fanout_collapsed": True, "items": items}})
    planned = []
    for item in sorted(validated["items"], key=lambda entry: entry["id"].encode("ascii", "strict")):
        role = item["task_class"]
        if role in {"unknown", "architect"}:
            role = "architect"
        assignee = _candidate(role, settings, catalog)
        if not assignee:
            return PlanResult(error("E_NO_SAFE_ROUTE", f"No configured on-disk profile is available for role {role}."))
        planned.append({"id": item["id"], "assignee": assignee, "parents": item["parents"], "task_class": item["task_class"], "fanout_prohibited": False})
    return PlanResult({"ok": True, "policy_version": "hermes-ultrawork-plan-v1", "catalog_revision": catalog.revision, "plan": {"protected_fanout_collapsed": False, "items": planned}})
