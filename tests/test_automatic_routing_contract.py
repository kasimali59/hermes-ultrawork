"""Deterministic black-box contract tests for normal-chat routing."""
from __future__ import annotations

import copy
import inspect
import os
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ultrawork.normal_chat import NormalChatPlugin
from ultrawork.intent import NEGATIVE, POSITIVE, classify_intent


class NormalChatContext:
    def __init__(self, settings=None, *, platform="telegram", sender_id="user-1", parent_session_id=""):
        self.settings = {
            "normal_chat_enabled": True,
            "normal_chat_dispatch": False,
            "normal_chat_dispatch_platforms": [],
            "orchestrator_profiles": ["architect"],
            "role_bindings": {"architect": "architect", "routine": "free-worker", "integration": "engineering-lead", "qa": "qa-engineer", "research": "researcher"},
            "tenant": "test-tenant",
            "workspace_kind": "scratch",
        }
        if settings:
            self.settings.update(settings)
        self.profile_name = "architect"
        self.platform = platform
        self.sender_id = sender_id
        self.parent_session_id = parent_session_id
        self.HERMES_KANBAN_TASK = None
        self.calls = []
        self.created = []
        self.create_exception = None
        self.create_result = None
        self.state = {"normal_chat_catalog": {"version": 1, "revision": "catalog-r1", "stale": False, "profiles": [
            {"name": "architect", "available": True}, {"name": "free-worker", "available": True},
            {"name": "engineering-lead", "available": True}, {"name": "qa-engineer", "available": True},
            {"name": "researcher", "available": True},
        ]}}

    def get_config(self, key, default=None):
        return self.settings if key == "plugins.entries.hermes-ultrawork.settings" else default

    def dispatch_tool(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == "kanban_create":
            if self.create_exception is not None:
                raise self.create_exception
            if self.create_result is not None:
                return self.create_result
            task_id = f"task-{len(self.created) + 1}"
            self.created.append((task_id, args))
            return {"ok": True, "task_id": task_id}
        raise AssertionError(f"unexpected tool: {name}")


class AutomaticRoutingContractTests(unittest.TestCase):
    def invoke(self, ctx, text, history=None, **kwargs):
        with mock.patch.dict(os.environ, {}, clear=True):
            return NormalChatPlugin(ctx).pre_llm_call(
                session_id="session-1", turn_id="turn-1", user_message=text,
                conversation_history=history, model="configured-model", platform=ctx.platform,
                sender_id=ctx.sender_id, parent_session_id=ctx.parent_session_id, **kwargs,
            )

    def test_ordinary_chat_automatically_returns_bounded_stable_context_without_write(self):
        ctx = NormalChatContext()
        first = self.invoke(ctx, "Fix a typo")
        second = self.invoke(ctx, "Fix a typo")
        self.assertIsInstance(first, str)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first.encode("utf-8")), 2048)
        self.assertIn("policy_id:hermes-ultrawork-normal-chat-v1", first)
        self.assertIn("dispatch:not_requested", first)
        self.assertEqual(ctx.calls, [])

    def test_context_does_not_mutate_history_or_add_messages_and_roles_stay_valid(self):
        history = [{"role": "user", "content": "Earlier"}, {"role": "assistant", "content": "Done"}]
        before = copy.deepcopy(history)
        ctx = NormalChatContext()
        suffix = self.invoke(ctx, "Review this change", history)
        self.assertEqual(history, before)
        assembled = history + [{"role": "user", "content": "Review this change\n\n" + suffix}]
        self.assertEqual([message["role"] for message in assembled], ["user", "assistant", "user"])
        self.assertNotIn("configured-model", suffix)
        self.assertNotIn("Earlier", suffix)

    def test_explicit_background_dispatch_is_opt_in_and_creates_one_root(self):
        ctx = NormalChatContext({"normal_chat_dispatch": True, "normal_chat_dispatch_platforms": ["telegram"]})
        result = self.invoke(ctx, "Build the report in the background")
        writes = [call for call in ctx.calls if call[0] == "kanban_create"]
        self.assertEqual(len(writes), 1)
        self.assertIn("dispatch:queued", result)
        payload = writes[0][1]
        self.assertEqual(payload["parents"], [])
        self.assertNotIn("model", payload)
        self.assertNotIn("provider", payload)
        self.assertEqual(payload["assignee"], "free-worker")

    def test_every_negative_phrase_suppresses_background_dispatch(self):
        for phrase in ("do not delegate", "do not use kanban", "do not queue", "just answer", "plan only"):
            with self.subTest(phrase=phrase):
                ctx = NormalChatContext({"normal_chat_dispatch": True, "normal_chat_dispatch_platforms": ["telegram"]})
                result = self.invoke(ctx, f"Build this in the background; {phrase}")
                self.assertEqual([call for call in ctx.calls if call[0] == "kanban_create"], [])
                self.assertIn("dispatch:blocked", result)

    def test_quoted_or_example_intent_and_incomplete_requests_do_not_dispatch(self):
        cases = [
            'The phrase "in the background" is an example; answer this',
            "Use the phrase 'delegate this' in documentation",
            "in the background",
            "Please queue this",
        ]
        for text in cases:
            with self.subTest(text=text):
                ctx = NormalChatContext({"normal_chat_dispatch": True, "normal_chat_dispatch_platforms": ["telegram"]})
                self.invoke(ctx, text)
                self.assertEqual([call for call in ctx.calls if call[0] == "kanban_create"], [])

    def test_protected_categories_require_confirmation_and_never_dispatch(self):
        cases = {
            "credential": "Rotate the credential in the background",
            "destructive": "Delete all records in the background",
            "payment": "Approve the payment in the background",
            "publishing": "Publish the release in the background",
            "external_message": "Send message to customers in the background",
            "privilege": "Run this with sudo in the background",
            "hardware": "Write firmware in the background",
        }
        for category, text in cases.items():
            with self.subTest(category=category):
                ctx = NormalChatContext({"normal_chat_dispatch": True, "normal_chat_dispatch_platforms": ["telegram"]})
                result = self.invoke(ctx, text)
                self.assertIn("route:architect_gate", result)
                self.assertIn("requires_confirmation:True", result)
                self.assertEqual([call for call in ctx.calls if call[0] == "kanban_create"], [])

    def test_ineligible_sources_never_dispatch(self):
        settings = {"normal_chat_dispatch": True, "normal_chat_dispatch_platforms": ["telegram"]}
        cases = [
            NormalChatContext(settings, platform="cli"),
            NormalChatContext(settings, sender_id=""),
            NormalChatContext(settings, parent_session_id="parent"),
        ]
        for ctx in cases:
            self.invoke(ctx, "Build this in the background")
            self.assertEqual([call for call in ctx.calls if call[0] == "kanban_create"], [])

    def test_replay_is_idempotent_and_conflicting_revision_does_not_write_twice(self):
        ctx = NormalChatContext({"normal_chat_dispatch": True, "normal_chat_dispatch_platforms": ["telegram"]})
        plugin = NormalChatPlugin(ctx)
        kwargs = dict(session_id="session-1", turn_id="turn-1", user_message="Build this report in the background", platform="telegram", sender_id="user-1", parent_session_id="")
        with mock.patch.dict(os.environ, {}, clear=True):
            first = plugin.pre_llm_call(**kwargs)
            replay = plugin.pre_llm_call(**kwargs)
            conflict = plugin.pre_llm_call(**{**kwargs, "user_message": "Build a different report in the background"})
        self.assertEqual(first, replay)
        self.assertIn("dispatch:queued", first)
        self.assertIn("reasons:E_OPERATION_CONFLICT", conflict)
        self.assertIn("dispatch:blocked", conflict)
        self.assertEqual(len([call for call in ctx.calls if call[0] == "kanban_create"]), 1)
        records = ctx.state["normal_chat_operations"]
        self.assertEqual(len(records), 1)
        record = next(iter(records.values()))
        self.assertEqual(set(record), {"revision", "idempotency_key", "confirmed_id"})
        self.assertNotIn("Build this report", repr(ctx.state))
        self.assertNotIn("model", repr(ctx.state).casefold())
        self.assertNotIn("provider", repr(ctx.state).casefold())

    def test_hook_path_has_no_direct_host_tool_and_dispatch_adapter_only_creates_kanban_tasks(self):
        hook_source = inspect.getsource(NormalChatPlugin.pre_llm_call)
        dispatch_source = (ROOT / "ultrawork" / "dispatch.py").read_text(encoding="utf-8")
        self.assertNotIn("dispatch_tool", hook_source)
        self.assertNotIn("subprocess", hook_source)
        self.assertEqual(dispatch_source.count("ctx.dispatch_tool("), 1)
        self.assertIn('ctx.dispatch_tool("kanban_create", payload)', dispatch_source)

    def test_definite_create_exception_replays_blocked_without_retry_and_stores_metadata_only(self):
        ctx = NormalChatContext({"normal_chat_dispatch": True, "normal_chat_dispatch_platforms": ["telegram"]})
        ctx.create_exception = RuntimeError("unavailable")
        kwargs = dict(session_id="session-1", turn_id="turn-1", user_message="Build this report in the background", platform="telegram", sender_id="user-1", parent_session_id="")
        with mock.patch.dict(os.environ, {}, clear=True):
            first = NormalChatPlugin(ctx).pre_llm_call(**kwargs)
            replay = NormalChatPlugin(ctx).pre_llm_call(**kwargs)
        self.assertIn("dispatch:blocked", first)
        self.assertIn("dispatch:blocked", replay)
        self.assertEqual(len([call for call in ctx.calls if call[0] == "kanban_create"]), 1)
        records = ctx.state["normal_chat_operations"]
        self.assertEqual(len(records), 1)
        record = next(iter(records.values()))
        self.assertEqual(set(record), {"revision", "idempotency_key", "status"})
        self.assertNotIn("body", repr(ctx.state))
        self.assertNotIn("super-secret", repr(ctx.state))

    def test_create_result_outcomes_replay_without_retry(self):
        cases = (
            ("explicit_failure", {"ok": False}, "blocked"),
            ("malformed_result", {"ok": True}, "ambiguous"),
            ("timeout", TimeoutError(), "ambiguous"),
        )
        kwargs = dict(session_id="session-1", turn_id="turn-1", user_message="Build this report in the background", platform="telegram", sender_id="user-1", parent_session_id="")
        for name, outcome, status in cases:
            with self.subTest(outcome=name):
                ctx = NormalChatContext({"normal_chat_dispatch": True, "normal_chat_dispatch_platforms": ["telegram"]})
                if isinstance(outcome, Exception):
                    ctx.create_exception = outcome
                else:
                    ctx.create_result = outcome
                with mock.patch.dict(os.environ, {}, clear=True):
                    first = NormalChatPlugin(ctx).pre_llm_call(**kwargs)
                    replay = NormalChatPlugin(ctx).pre_llm_call(**kwargs)
                self.assertIn(f"dispatch:{status}", first)
                self.assertEqual(replay, first)
                self.assertEqual(len([call for call in ctx.calls if call[0] == "kanban_create"]), 1)
                record = next(iter(ctx.state["normal_chat_operations"].values()))
                self.assertEqual(record["status"], status)

    def test_no_paid_fallback_or_model_config_mutation(self):
        ctx = NormalChatContext({"role_bindings": {"routine": []}})
        before = copy.deepcopy(ctx.settings)
        result = self.invoke(ctx, "Fix a typo")
        self.assertEqual(ctx.settings, before)
        self.assertNotIn("paid", result.casefold())
        self.assertNotIn("provider", result.casefold())
        self.assertNotIn("model", result.casefold())

    def test_context_state_isolated_by_profile_and_no_secret_is_echoed(self):
        secret = "api_key=super-secret-value"
        ctx = NormalChatContext()
        before = copy.deepcopy(ctx.__dict__)
        result = self.invoke(ctx, f"Review {secret}")
        self.assertNotIn("super-secret-value", result)
        self.assertEqual(ctx.profile_name, "architect")
        self.assertEqual(ctx.settings, before["settings"])
        self.assertEqual([call for call in ctx.calls if call[0] == "kanban_create"], [])

    def test_idempotency_key_is_stable_across_processes(self):
        script = """from tests.test_automatic_routing_contract import NormalChatContext\nfrom ultrawork.normal_chat import NormalChatPlugin\nc=NormalChatContext({'normal_chat_dispatch': True, 'normal_chat_dispatch_platforms':['telegram']})\nNormalChatPlugin(c).pre_llm_call(session_id='s', turn_id='t', platform='telegram', sender_id='user-1', parent_session_id='', user_message='Build this report in the background')\nprint([a['idempotency_key'] for n,a in c.calls if n == 'kanban_create'][0])\n"""
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        env.pop("HERMES_KANBAN_TASK", None)
        outputs = [subprocess.check_output([sys.executable, "-c", script], cwd=ROOT, env=env, text=True).strip() for _ in range(2)]
        self.assertEqual(outputs[0], outputs[1])

    def test_missing_state_catalog_fails_closed_without_terminal_or_create(self):
        ctx = NormalChatContext({"normal_chat_dispatch": True, "normal_chat_dispatch_platforms": ["telegram"]})
        ctx.state.pop("normal_chat_catalog")
        result = self.invoke(ctx, "Build the report in the background")
        self.assertIn("dispatch:blocked", result)
        self.assertEqual(ctx.calls, [])

    def test_malformed_non_selected_role_binding_fails_closed_without_create(self):
        ctx = NormalChatContext({
            "normal_chat_dispatch": True,
            "normal_chat_dispatch_platforms": ["telegram"],
            "role_bindings": {
                "architect": "architect",
                "routine": "free-worker",
                "integration": "engineering-lead",
                "qa": [],
                "research": "researcher",
            },
        })
        result = self.invoke(ctx, "Build the report in the background")
        self.assertIn("dispatch:blocked", result)
        self.assertEqual(ctx.calls, [])

    def test_versioned_lexer_handles_full_phrase_tables_boundaries_and_protected_spans(self):
        for phrase in POSITIVE:
            with self.subTest(positive=phrase):
                result = classify_intent(f"Build a report; {phrase}!")
                self.assertIn(phrase, result["positive"])
                self.assertTrue(result["complete"])
        for phrase in NEGATIVE:
            with self.subTest(negative=phrase):
                self.assertIn(phrase, classify_intent(f"Build a report; {phrase}.")["negative"])
        for text in (
            "Build a report; delegate thisx",
            'Build a report; "delegate this"',
            "Build a report; `delegate this`",
            "Build a report; ```delegate this```",
            "Build a report; example delegate this",
        ):
            with self.subTest(suppressed=text):
                self.assertEqual(classify_intent(text)["positive"], ())


if __name__ == "__main__":
    unittest.main()
