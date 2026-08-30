"""Black-box baseline contracts for the standalone Ultrawork plugin."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ultrawork.api import build_plugin
from ultrawork.catalog import Catalog
from ultrawork.planning import plan_request


class FakeContext:
    def __init__(self, settings: dict | None = None) -> None:
        self.settings = settings or {}
        self.profile_name = "architect"
        self.calls: list[tuple] = []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_tool(self, **kwargs):
        self.calls.append(("tool", kwargs))

    def register_command(self, name, handler, **kwargs):
        self.calls.append(("command", name, handler, kwargs))

    def register_cli_command(self, **kwargs):
        self.calls.append(("cli", kwargs))

    def register_skill(self, name, path):
        self.calls.append(("skill", name, Path(path)))

    def register_hook(self, name, handler):
        self.calls.append(("hook", name, handler))

    def dispatch_tool(self, name, args):
        self.calls.append(("dispatch", name, args))
        return {"output": json.dumps([
            {"name": "architect", "on_disk": True, "running_count": 0, "ready_count": 0, "todo_count": 0},
            {"name": "free-worker", "on_disk": True, "running_count": 0, "ready_count": 0, "todo_count": 0},
        ])}


def catalog(profiles):
    return Catalog.from_profiles(profiles, board="default")


class ManifestContractTests(unittest.TestCase):
    def test_manifest_declares_supported_standalone_plugin_contract(self):
        manifest = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
        for expected in (
            "manifest_version: 2",
            "api_version: 1",
            "kind: standalone",
            "provides_tools: [ultrawork]",
            "config_schema:",
            "role_bindings:",
        ):
            self.assertIn(expected, manifest)

    def test_register_exposes_public_tool_command_cli_and_bundled_skill(self):
        spec = importlib.util.spec_from_file_location("ultrawork_plugin", ROOT / "__init__.py")
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        ctx = FakeContext()
        module.register(ctx)
        self.assertEqual([call[0] for call in ctx.calls], ["tool", "command", "cli", "skill", "hook"])
        self.assertEqual(ctx.calls[0][1]["name"], "ultrawork")
        self.assertEqual(ctx.calls[1][1], "ultrawork")
        self.assertEqual(ctx.calls[2][1]["name"], "ultrawork")
        self.assertTrue(ctx.calls[3][2].is_file())


class PlanningContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = catalog([
            {"name": "architect", "on_disk": True, "running_count": 0, "ready_count": 0, "todo_count": 0},
            {"name": "free-worker", "on_disk": True, "running_count": 1, "ready_count": 2, "todo_count": 3},
            {"name": "qa-engineer", "on_disk": True, "running_count": 0, "ready_count": 0, "todo_count": 0},
        ])
        self.settings = {
            "orchestrator_profiles": ["architect"],
            "role_bindings": {
                "architect": ["architect"],
                "routine": ["free-worker"],
                "qa": ["qa-engineer"],
            },
            "profile_priority": {},
        }

    def test_reordered_catalog_produces_byte_identical_stable_plan(self):
        request = {
            "mode": "plan",
            "goal": "Implement a bounded feature",
            "items": [{"id": "b", "title": "Second", "task_class": "routine"}, {"id": "a", "title": "First", "task_class": "routine"}],
        }
        first = plan_request(request, self.settings, self.catalog, "architect")
        reversed_catalog = catalog(list(reversed(self.catalog.profiles)))
        second = plan_request(request, self.settings, reversed_catalog, "architect")
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual([item["id"] for item in first.payload["plan"]["items"]], ["a", "b"])
        self.assertTrue(all(item["assignee"] == "free-worker" for item in first.payload["plan"]["items"]))

    def test_protected_child_collapses_graph_to_single_architect_root(self):
        result = plan_request(
            {
                "mode": "plan",
                "goal": "Normal parent",
                "items": [
                    {"id": "root", "title": "Routine review", "task_class": "routine"},
                    {"id": "child", "title": "Rotate API key sk-live-secret", "task_class": "routine", "parents": ["root"]},
                ],
            },
            self.settings,
            self.catalog,
            "architect",
        )
        self.assertTrue(result.payload["plan"]["protected_fanout_collapsed"])
        self.assertEqual(result.payload["plan"]["items"], [{"id": "architect-root", "assignee": "architect", "parents": [], "task_class": "architect", "fanout_prohibited": True}])

    def test_protected_goal_also_collapses_fanout_before_routing_children(self):
        result = plan_request(
            {"mode": "plan", "goal": "Prepare payment workflow", "items": [{"id": "child", "title": "routine", "task_class": "routine"}]},
            self.settings,
            self.catalog,
            "architect",
        )
        self.assertTrue(result.payload["plan"]["protected_fanout_collapsed"])
        self.assertEqual(result.payload["plan"]["items"][0]["assignee"], "architect")

    def test_secret_shaped_input_is_rejected_without_echoing_value(self):
        secret = "sk-live-123456789012345678901234567890"
        result = plan_request({"mode": "plan", "goal": f"use {secret}"}, self.settings, self.catalog, "architect")
        self.assertFalse(result.payload["ok"])
        self.assertEqual(result.payload["error"]["code"], "E_SECRET_INPUT")
        self.assertNotIn(secret, result.to_json())

    def test_malformed_config_fails_closed_with_actionable_error(self):
        result = plan_request({"mode": "plan", "goal": "test"}, {"role_bindings": "not a dict"}, self.catalog, "architect")
        self.assertFalse(result.payload["ok"])
        self.assertEqual(result.payload["error"]["code"], "E_CONFIG")

    def test_unavailable_routine_role_fails_closed_to_architect(self):
        no_routine = catalog([self.catalog.profiles[0]])
        result = plan_request({"mode": "plan", "goal": "test", "items": [{"id": "one", "title": "one", "task_class": "routine"}]}, self.settings, no_routine, "architect")
        self.assertFalse(result.payload["ok"])
        self.assertEqual(result.payload["error"]["code"], "E_NO_SAFE_ROUTE")

    def test_cyclic_graph_fails_closed(self):
        result = plan_request(
            {"mode": "plan", "goal": "test", "items": [
                {"id": "a", "title": "a", "task_class": "routine", "parents": ["b"]},
                {"id": "b", "title": "b", "task_class": "routine", "parents": ["a"]},
            ]},
            self.settings, self.catalog, "architect",
        )
        self.assertFalse(result.payload["ok"])
        self.assertEqual(result.payload["error"]["code"], "E_GRAPH")

    def test_equal_candidates_use_declared_binding_order_as_stable_tie_breaker(self):
        settings = {**self.settings, "role_bindings": {**self.settings["role_bindings"], "routine": ["qa-engineer", "free-worker"]}}
        result = plan_request({"mode": "plan", "goal": "test", "items": [{"id": "one", "title": "one", "task_class": "routine"}]}, settings, self.catalog, "architect")
        self.assertTrue(result.payload["ok"])
        self.assertEqual(result.payload["plan"]["items"][0]["assignee"], "qa-engineer")

    def test_non_ascii_catalog_profile_fails_closed_instead_of_raising(self):
        with self.assertRaises(ValueError):
            catalog([self.catalog.profiles[0], {"name": "é-worker", "on_disk": True}])


class ToolContractTests(unittest.TestCase):
    def test_tool_rejects_unknown_fields_and_never_dispatches_implicitly(self):
        plugin = build_plugin(FakeContext())
        response = json.loads(plugin.handle_tool({"mode": "plan", "goal": "x", "unexpected": True}))
        self.assertEqual(response["error"]["code"], "E_SCHEMA")

    def test_tool_discovers_profiles_only_via_public_read_only_terminal_dispatch(self):
        ctx = FakeContext({
            "plugins.entries.hermes-ultrawork.settings": {
                "orchestrator_profiles": ["architect"],
                "role_bindings": {"architect": ["architect"], "routine": ["free-worker"]},
                "profile_priority": {},
            }
        })
        response = json.loads(build_plugin(ctx).handle_tool({"mode": "plan", "goal": "bounded", "items": [{"id": "one", "title": "one", "task_class": "routine"}]}))
        self.assertTrue(response["ok"])
        self.assertEqual(response["plan"]["items"][0]["assignee"], "free-worker")
        self.assertEqual(ctx.calls[-1], ("dispatch", "terminal", {"command": "hermes kanban assignees --json", "timeout": 30}))

    def test_tool_returns_stable_catalog_error_when_public_discovery_fails(self):
        class BrokenContext(FakeContext):
            def dispatch_tool(self, name, args):
                raise RuntimeError("host unavailable; token=DO_NOT_ECHO")

        response = json.loads(build_plugin(BrokenContext()).handle_tool({"mode": "plan", "goal": "bounded"}))
        self.assertEqual(response["error"]["code"], "E_CATALOG")
        self.assertNotIn("DO_NOT_ECHO", json.dumps(response))

    def test_slash_command_and_cli_are_invocable_without_implicit_side_effects(self):
        ctx = FakeContext()
        plugin = build_plugin(ctx)
        response = json.loads(plugin.handle_slash(""))
        self.assertEqual(response["error"]["code"], "E_SCHEMA")
        cli_response = plugin.handle_cli(object())
        self.assertEqual(cli_response["error"]["code"], "E_CATALOG")


if __name__ == "__main__":
    unittest.main()
