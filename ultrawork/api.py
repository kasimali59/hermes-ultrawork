"""Public plugin adapter: registration is side-effect free."""
from __future__ import annotations
import json
from pathlib import Path
from .catalog import Catalog
from .planning import plan_request
from .validation import error, validate_request

TOOL_SCHEMA = {"name": "ultrawork", "description": "Validate and plan deterministic safety-first Kanban work; never dispatches automatically.", "parameters": {"type": "object", "additionalProperties": False, "required": ["mode", "goal"], "properties": {"mode": {"type": "string", "enum": ["plan"]}, "goal": {"type": "string", "minLength": 1, "maxLength": 12000}, "items": {"type": "array", "maxItems": 16}, "operation_id": {"type": "string"}, "catalog_revision": {"type": "string"}}}}


class Plugin:
    def __init__(self, ctx):
        self.ctx = ctx
        self.tool_schema = TOOL_SCHEMA

    def _settings(self):
        return self.ctx.get_config("plugins.entries.hermes-ultrawork.settings", {})

    def _discover_catalog(self):
        """Use only Hermes' public tool dispatcher and a fixed read-only command."""
        try:
            result = self.ctx.dispatch_tool(
                "terminal", {"command": "hermes kanban assignees --json", "timeout": 30}
            )
            output = result.get("output") if isinstance(result, dict) else None
            profiles = json.loads(output) if isinstance(output, str) else None
            return Catalog.from_profiles(profiles, "default"), None
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError, RuntimeError):
            return None, error("E_CATALOG", "Could not validate the public Hermes profile roster.")

    def handle_tool(self, params, **kwargs):
        del kwargs
        _, problem = validate_request(params)
        if problem:
            return json.dumps(problem, sort_keys=True, separators=(",", ":"))
        catalog, problem = self._discover_catalog()
        assert catalog is not None or problem is not None
        payload = problem if problem else plan_request(params, self._settings(), catalog, self.ctx.profile_name).payload
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def handle_slash(self, args=None, **kwargs):
        del kwargs
        goal = args.strip() if isinstance(args, str) else ""
        return self.handle_tool({"mode": "plan", "goal": goal})

    def setup_cli(self, parser):
        parser.add_argument("action", choices=("validate",))
        parser.add_argument("request")

    def handle_cli(self, args):
        return error("E_CATALOG", "CLI validation requires a synced public profile catalog; no dispatch command is registered.")


def build_plugin(ctx):
    return Plugin(ctx)


def bundled_skill_path() -> Path:
    return Path(__file__).resolve().parents[1] / "skills" / "ultrawork-orchestration" / "SKILL.md"
