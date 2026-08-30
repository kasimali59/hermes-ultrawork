"""Disposable-profile integration coverage for automatic normal-chat routing."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ultrawork.normal_chat import NormalChatPlugin


class DisposableProfileContext:
    """Small public-API-only Hermes context with isolated disposable state."""

    def __init__(self, root: Path, profile_name: str, *, dispatch_enabled: bool = False) -> None:
        self.root = root
        self.profile_name = profile_name
        self.platform = "telegram"
        self.sender_id = f"sender-{profile_name}"
        self.parent_session_id = ""
        self.HERMES_KANBAN_TASK = None
        self.settings = {
            "normal_chat_enabled": True,
            "normal_chat_dispatch": dispatch_enabled,
            "normal_chat_dispatch_platforms": ["telegram"],
            "orchestrator_profiles": [profile_name],
            "role_bindings": {"architect": "architect", "routine": "free-worker", "integration": "engineering-lead", "qa": "qa-engineer", "research": "researcher"},
            "tenant": "test-tenant",
            "workspace_kind": "scratch",
        }
        self.history = []
        self.calls = []
        self.state = {"normal_chat_catalog": {"version": 1, "revision": "catalog-r1", "stale": False, "profiles": [
            {"name": "architect", "available": True}, {"name": "free-worker", "available": True},
            {"name": "engineering-lead", "available": True}, {"name": "qa-engineer", "available": True},
            {"name": "researcher", "available": True},
        ]}}
        root.mkdir(parents=True)
        (root / "profile.yaml").write_text(f"profile: {profile_name}\n", encoding="utf-8")
        (root / "memory.txt").write_text(f"memory-{profile_name}\n", encoding="utf-8")

    def get_config(self, key, default=None):
        return self.settings if key == "plugins.entries.hermes-ultrawork.settings" else default

    def dispatch_tool(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == "kanban_create":
            task_id = f"task-{self.profile_name}-{len(self.calls)}"
            return {"ok": True, "task_id": task_id}
        raise AssertionError(f"unexpected tool: {name}")


class DisposableProfileRoutingIntegrationTests(unittest.TestCase):
    def test_profiles_are_isolated_across_normal_turns_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            left = DisposableProfileContext(root / "left", "left")
            right = DisposableProfileContext(root / "right", "right")
            left_plugin = NormalChatPlugin(left)
            right_plugin = NormalChatPlugin(right)
            left_history = [{"role": "user", "content": "private-left"}]
            right_history = [{"role": "user", "content": "private-right"}]

            left_context = left_plugin.pre_llm_call(session_id="s", turn_id="1", user_message="Fix a typo", conversation_history=left_history)
            right_context = right_plugin.pre_llm_call(session_id="s", turn_id="1", user_message="Fix a typo", conversation_history=right_history)

            self.assertIsInstance(left_context, str)
            self.assertIsInstance(right_context, str)
            self.assertEqual(left_context, right_context)
            self.assertEqual(left_history, [{"role": "user", "content": "private-left"}])
            self.assertEqual(right_history, [{"role": "user", "content": "private-right"}])
            self.assertEqual(left.calls, [])
            self.assertEqual(right.calls, [])
            self.assertNotIn("left", right_context)
            self.assertNotIn("right", left_context)

            self.assertEqual({path.name for path in left.root.iterdir()}, {"profile.yaml", "memory.txt"})
            self.assertEqual({path.name for path in right.root.iterdir()}, {"profile.yaml", "memory.txt"})
            del left_plugin, right_plugin, left, right

    def test_multiple_turns_cache_suffix_and_role_alternation_remain_stable(self):
        with tempfile.TemporaryDirectory() as temp:
            ctx = DisposableProfileContext(Path(temp) / "profile", "cache")
            plugin = NormalChatPlugin(ctx)
            history = [{"role": "user", "content": "Fix a typo"}, {"role": "assistant", "content": "Done"}]
            first = plugin.pre_llm_call(session_id="s", turn_id="2", user_message="Run regression tests", conversation_history=history)
            second = plugin.pre_llm_call(session_id="s", turn_id="2", user_message="Run regression tests", conversation_history=history)
            alternate = plugin.pre_llm_call(session_id="s", turn_id="3", user_message="Build a feature", conversation_history=history)
            self.assertIsInstance(first, str)
            self.assertIsInstance(alternate, str)
            self.assertEqual(first, second)
            self.assertTrue(alternate)
            self.assertEqual([entry["role"] for entry in history], ["user", "assistant"])
            self.assertLessEqual(len(first.encode()), 2048)
            self.assertNotIn("Run regression tests", first)

    def test_explicit_background_dispatch_is_one_root_and_receipt_is_profile_local(self):
        with tempfile.TemporaryDirectory() as temp:
            ctx = DisposableProfileContext(Path(temp) / "profile", "dispatch", dispatch_enabled=True)
            plugin = NormalChatPlugin(ctx)
            message = "Please fix the typo in the README in the background"
            with mock.patch.dict(os.environ, {}, clear=True):
                result = plugin.pre_llm_call(session_id="s", turn_id="7", user_message=message, platform=ctx.platform, sender_id=ctx.sender_id, parent_session_id=ctx.parent_session_id)
            creates = [args for name, args in ctx.calls if name == "kanban_create"]
            self.assertEqual(len(creates), 1)
            self.assertEqual(creates[0]["parents"], [])
            self.assertEqual(creates[0]["assignee"], "free-worker")
            self.assertNotIn("model", creates[0])
            self.assertNotIn("provider", creates[0])
            self.assertIn("dispatch:queued", result)
            self.assertIn("task_id:task-dispatch-1", result)
            with mock.patch.dict(os.environ, {}, clear=True):
                replay = plugin.pre_llm_call(session_id="s", turn_id="7", user_message=message, platform=ctx.platform, sender_id=ctx.sender_id, parent_session_id=ctx.parent_session_id)
            self.assertEqual(len([name for name, _ in ctx.calls if name == "kanban_create"]), 1)
            self.assertEqual(result, replay)

    def test_protected_and_paid_fallback_requests_are_confirmation_gated(self):
        with tempfile.TemporaryDirectory() as temp:
            ctx = DisposableProfileContext(Path(temp) / "profile", "guarded", dispatch_enabled=True)
            plugin = NormalChatPlugin(ctx)
            for message in (
                "Please rotate the API key in the background",
                "Please send this external message in the background",
                "Please use a paid fallback to fix the typo in the background",
            ):
                result = plugin.pre_llm_call(session_id="s", turn_id="1", user_message=message)
                self.assertIsInstance(result, str)
                self.assertIn("route:architect_gate", result)
                self.assertIn("requires_confirmation:True", result)
            self.assertEqual([name for name, _ in ctx.calls if name == "kanban_create"], [])


if __name__ == "__main__":
    unittest.main()
