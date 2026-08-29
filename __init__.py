"""Hermes Ultrawork plugin: explicit planning and safety-first routing."""
from __future__ import annotations
import json
from .routing import RoutingFacts, route_task


def _facts(params: dict) -> RoutingFacts:
    allowed = {field.name for field in RoutingFacts.__dataclass_fields__.values()}
    values = {key: value for key, value in params.items() if key in allowed}
    if "protected_tags" in values and isinstance(values["protected_tags"], list): values["protected_tags"] = tuple(values["protected_tags"])
    return RoutingFacts(**values)


def _result(facts: RoutingFacts) -> str:
    decision = route_task(facts)
    return json.dumps({"success": True, "policy_version": decision.policy_version, "facts": {"title": facts.title, "work_kind": facts.work_kind}, "decision": {"route_class": decision.route_class, "assignee": decision.assignee, "reason_codes": decision.reason_codes, "decompose": decision.decompose, "allow_paid_upgrade": decision.allow_paid_upgrade}, "next_step": "Do not dispatch protected work; ask the Architect for an explicit gate." if decision.assignee is None else ("Create an Architect-owned decomposition." if decision.decompose else f"Assign explicitly to {decision.assignee} without paid-model fallback.")})


def register(ctx):
    schema = {"name": "ultrawork_route", "description": "Classify a task with Hermes Ultrawork's deterministic safety-first routing policy. This plans only; it never launches workers or changes configuration.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}, "work_kind": {"type": "string", "enum": sorted(["research", "architecture", "implementation", "integration", "qa", "reporting", "docs", "operations"])}, "estimated_files": {"type": "integer", "minimum": 0}, "acceptance_checks": {"type": "integer", "minimum": 0}, "independent_units": {"type": "integer", "minimum": 0}, "integration_boundaries": {"type": "integer", "minimum": 0}, "estimated_minutes": {"type": "integer", "minimum": 0}, "requested_tokens": {"type": "integer", "minimum": 0}, "protected_tags": {"type": "array", "items": {"type": "string"}}, "architecture_ambiguity": {"type": "boolean"}, "public_api_change": {"type": "boolean"}, "security_boundary": {"type": "boolean"}, "uncertainty": {"type": "string", "enum": ["low", "high"]}}, "required": ["title"]}}
    ctx.register_tool(name="ultrawork_route", toolset="ultrawork", schema=schema, handler=lambda params, **kwargs: _result(_facts(params)))
    def slash(args=None, **kwargs):
        del kwargs
        if isinstance(args, str): args = {"title": args}
        return _result(_facts(args or {}))
    ctx.register_command("ulw", slash, description="Plan and route a task with Hermes Ultrawork; planning only, no automatic dispatch.")
