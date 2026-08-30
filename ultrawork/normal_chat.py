"""Public, fail-closed pre_llm_call adapter for normal-chat routing."""
from __future__ import annotations

import hashlib
import os
from typing import Literal

from .dispatch import dispatch
from .intent import POLICY_VERSION, classify_intent
from .validation import _PROTECTED, _SECRET

RouteClass = Literal["architect_gate", "difficult_integration", "qa", "high_uncertainty_research", "ordinary_low_risk"]
_WORKSPACE_KINDS = frozenset({"scratch", "dir", "worktree"})
_ROUTE_BINDING_ROLES = frozenset({"architect", "routine", "integration", "qa", "research"})


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


class NormalChatPlugin:
    POLICY_VERSION = POLICY_VERSION

    def __init__(self, ctx):
        self.ctx = ctx

    def _settings(self) -> dict | None:
        settings = self.ctx.get_config("plugins.entries.hermes-ultrawork.settings", {})
        if not isinstance(settings, dict):
            return None
        required = ("normal_chat_enabled", "normal_chat_dispatch", "normal_chat_dispatch_platforms", "orchestrator_profiles", "role_bindings", "tenant", "workspace_kind")
        if any(name not in settings for name in required):
            return None
        if not isinstance(settings["normal_chat_enabled"], bool) or not isinstance(settings["normal_chat_dispatch"], bool):
            return None
        if not isinstance(settings["normal_chat_dispatch_platforms"], list) or any(not isinstance(item, str) or not item for item in settings["normal_chat_dispatch_platforms"]):
            return None
        if not isinstance(settings["orchestrator_profiles"], list) or not settings["orchestrator_profiles"] or any(not isinstance(item, str) or not item for item in settings["orchestrator_profiles"]):
            return None
        bindings = settings["role_bindings"]
        if (
            not isinstance(bindings, dict)
            or set(bindings) != _ROUTE_BINDING_ROLES
            or any(not isinstance(profile, str) or not profile or not profile.isascii() for profile in bindings.values())
        ):
            return None
        if not isinstance(settings["tenant"], str) or not settings["tenant"] or not isinstance(settings["workspace_kind"], str) or settings["workspace_kind"] not in _WORKSPACE_KINDS:
            return None
        return settings

    def _catalog(self) -> dict[str, bool] | None:
        state = getattr(self.ctx, "state", None)
        if not isinstance(state, dict):
            return None
        snapshot = state.get("normal_chat_catalog")
        if not isinstance(snapshot, dict) or set(snapshot) != {"version", "revision", "stale", "profiles"}:
            return None
        if snapshot["version"] != 1 or not isinstance(snapshot["revision"], str) or not snapshot["revision"] or snapshot["stale"] is not False or not isinstance(snapshot["profiles"], list):
            return None
        result: dict[str, bool] = {}
        for profile in snapshot["profiles"]:
            if not isinstance(profile, dict) or set(profile) != {"name", "available"}:
                return None
            name, available = profile["name"], profile["available"]
            if not isinstance(name, str) or not name or not name.isascii() or not isinstance(available, bool) or name in result:
                return None
            result[name] = available
        return result

    @staticmethod
    def _route(text: str, intent: dict[str, object]) -> tuple[RouteClass, str, bool]:
        words = set(text.casefold().split())
        if "fan" in words or "architecture" in words or "architect" in words or "lifecycle" in words or "policy" in words:
            return "architect_gate", "architect", True
        if "qa" in words or "test" in words or "verify" in words:
            return "qa", "qa", False
        if "research" in words or "investigate" in words:
            return "high_uncertainty_research", "research", False
        if "integration" in words or "implement" in words or "migrate" in words or "refactor" in words:
            return "difficult_integration", "integration", False
        return "ordinary_low_risk", "routine", False

    @staticmethod
    def _binding(settings: dict, role: str, catalog: dict[str, bool]) -> str | None:
        binding = settings["role_bindings"].get(role)
        if not isinstance(binding, str) or not binding or catalog.get(binding) is not True:
            return None
        return binding

    @staticmethod
    def _render(route: str, assignee: str | None, reasons: tuple[str, ...], status: str, confirmation: bool, decompose: bool, task_id: str | None = None) -> str:
        fields = [
            f"policy_id:{POLICY_VERSION}", f"route:{route}",
        ]
        if assignee:
            fields.append(f"assignee:{assignee}")
        fields.extend((f"reasons:{','.join(sorted(set(reasons)))}", f"dispatch:{status}", f"requires_confirmation:{confirmation}", f"decompose_allowed:{decompose}"))
        if task_id:
            fields.append(f"task_id:{task_id}")
        return "\n".join(fields)

    def _blocked(self, reason: str, route: str = "architect_gate", confirmation: bool = False) -> str:
        return self._render(route, None, (reason,), "blocked", confirmation, False)

    def pre_llm_call(self, session_id: str | None = None, task_id: str | None = None, turn_id: str | None = None, user_message: str | None = None, conversation_history: list | None = None, is_first_turn: bool = False, model: str | None = None, platform: str | None = None, parent_session_id: str | None = None, sender_id: str | None = None, **kwargs) -> str | None:
        del task_id, conversation_history, is_first_turn, model, kwargs
        settings = self._settings()
        if settings is None:
            return self._blocked("E_CONFIG")
        if settings["normal_chat_enabled"] is not True:
            return None
        if not isinstance(user_message, str) or not user_message.strip() or len(user_message) > 12000 or any(ord(char) < 32 and char not in "\t\n\r" for char in user_message):
            return self._blocked("E_INPUT")
        if _SECRET.search(user_message):
            return self._blocked("secret_input", confirmation=True)
        if _PROTECTED.search(user_message) or "paid fallback" in user_message.casefold():
            return self._blocked("protected_content", confirmation=True)
        intent = classify_intent(user_message)
        route, role, decompose = self._route(user_message, intent)
        catalog = self._catalog()
        if catalog is None:
            return self._blocked("E_CATALOG", route)
        assignee = self._binding(settings, role, catalog)
        if assignee is None:
            return self._blocked("E_NO_SAFE_ROUTE", route)
        if intent["negative"]:
            return self._render(route, assignee, tuple(intent["negative"]), "blocked", False, decompose)
        if not intent["positive"]:
            return self._render(route, assignee, ("not_requested",), "not_requested", False, decompose)
        if not intent["complete"]:
            return self._render(route, assignee, ("incomplete_intent",), "blocked", False, decompose)
        direct = not parent_session_id and bool(sender_id) and platform in settings["normal_chat_dispatch_platforms"] and "HERMES_KANBAN_TASK" not in os.environ
        if settings["normal_chat_dispatch"] is not True or not direct or getattr(self.ctx, "profile_name", None) not in settings["orchestrator_profiles"]:
            return self._render(route, assignee, ("dispatch_ineligible",), "blocked", False, decompose)
        if not isinstance(session_id, str) or not session_id or not isinstance(turn_id, str) or not turn_id:
            return self._render(route, assignee, ("E_OPERATION" ,), "blocked", False, decompose)
        state = self.ctx.state
        operations = state.setdefault("normal_chat_operations", {})
        if not isinstance(operations, dict):
            return self._blocked("E_STATE", route)
        operation = _digest(POLICY_VERSION, self.ctx.profile_name, session_id, turn_id, "root")
        revision = _digest(user_message)
        previous = operations.get(operation)
        if isinstance(previous, dict):
            if previous.get("revision") != revision:
                return self._render(route, assignee, ("E_OPERATION_CONFLICT",), "blocked", False, decompose)
            confirmed = previous.get("confirmed_id")
            if isinstance(confirmed, str) and confirmed:
                return self._render(route, assignee, ("normal_chat_dispatch",), "queued", False, decompose, confirmed)
            status = previous.get("status")
            if status in {"blocked", "ambiguous"}:
                return self._render(route, assignee, ("E_CREATE",), status, False, decompose)
            return self._render(route, assignee, ("E_OPERATION_AMBIGUOUS",), "ambiguous", False, decompose)
        idempotency_key = _digest(POLICY_VERSION, self.ctx.profile_name, session_id, turn_id, revision, "root")
        body = ("Goal/scope:\n" + user_message[:1000] + "\n\nSource policy/revision:\n" + POLICY_VERSION + "/" + revision + "\n\nAcceptance/evidence:\nRun focused tests and report evidence.\n\nSafety decision:\nNon-protected single root; no automatic fan-out.\n\nStructured handoff:\nsummary: ...\nmetadata: {...}")
        payload = {"title": user_message[:160], "assignee": assignee, "body": body[:1800], "parents": [], "tenant": settings["tenant"], "workspace_kind": settings["workspace_kind"], "idempotency_key": idempotency_key}
        result = dispatch(self.ctx, payload)
        record = {"revision": revision, "idempotency_key": idempotency_key}
        if result["status"] == "queued":
            record["confirmed_id"] = result["task_id"]
            operations[operation] = record
            return self._render(route, assignee, ("normal_chat_dispatch",), "queued", False, decompose, result["task_id"])
        record["status"] = result["status"]
        operations[operation] = record
        return self._render(route, assignee, ("E_CREATE",), result["status"], False, decompose)


def build_plugin(ctx):
    return NormalChatPlugin(ctx)