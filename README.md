# Hermes Ultrawork

A standalone Hermes Agent plugin inspired by the useful workflow ideas behind OmO/LazyCodex: research before planning, explicit role routing, bounded decomposition, and evidence-oriented completion.

It is **not** LazyCodex, OmO, a model, an inference engine, or a replacement for Hermes. It does not install Codex hooks and does not patch Hermes core.

## What it does

- Routes routine, bounded work to `free-worker`.
- Routes large/decomposable work to `architect`.
- Routes difficult integration to `engineering-lead`.
- Routes QA to `qa-engineer`.
- Routes high-uncertainty research to `researcher`.
- Routes reporting to `report-writer` only after explicit health confirmation.
- Stops protected work at an Architect gate.
- Never silently upgrades a free/local task to a paid model.
- In ordinary chat, runs an automatic bounded routing pre_llm_call hook: classifies intent, suppresses negatives, and only injects a small routing context (≤2048 chars) by default. It does not write to the Kanban board unless dispatch is explicitly enabled.
- Retains a model-callable `ultrawork` tool and a `/ultrawork` planning command for explicit use; these are compatibility surfaces and not required for normal chat routing.

## Automatic behavior in normal chat

On every gateway turn, the plugin runs a pre_llm_call hook (`ultrawork/normal_chat.py`) that:

1. Classifies the user turn with a versioned phrase table (`ultrawork/intent.py`). The classifier is deterministic and fails closed.
2. Emits a bounded routing context (≤2048 chars) so the model sees a small hint about role assignment. It never inserts, rewrites, or replaces the user message.
3. May dispatch a single root Kanban card via the public `kanban_create` tool — but only when **all** of these are true:
   - `plugins.entries.hermes-ultrawork.settings.normal_chat_enabled` is true (default: true).
   - `plugins.entries.hermes-ultrawork.settings.normal_chat_dispatch` is true (default: **false**).
   - The sending platform is in `normal_chat_dispatch_platforms` (default: empty list).
   - The turn is a direct gateway turn (`parent_session_id` empty, `sender_id` non-empty, no `HERMES_KANBAN_TASK` env, no `claude-code` / `codex` / synthetic source).
   - The intent is a positive background/kanban phrase and no negative-suppression phrase matches.
   - The turn is not protected, not a secret/credential/payment/publishing/hardware/kernels request, and not ambiguous.

Otherwise the hook is context-only: zero writes, no model/provider/config/profile mutation, no direct DB or subprocess access. The Architect gate is preserved for protected work. `/ultrawork` and the `ultrawork` tool are unchanged and remain available for explicit invocation.

There is no paid-fallback path: the plugin never crosses the free/paid boundary on the host LLM call, never picks a model or provider, and never writes profile state.

## Install from Git

```bash
hermes plugins install kasimali59/hermes-ultrawork \
  --ref <FULL_40_CHARACTER_RELEASE_COMMIT_SHA> \
  --no-enable
hermes plugins enable hermes-ultrawork --no-allow-tool-override
```

This requires a Hermes release that supports the manifest version declared in `plugin.yaml`. Installation and enabling affect only the active profile's plugin metadata and plugin directory. Do not enable it in a profile that has not been reviewed.

To opt in to background Kanban dispatch from normal chat, set in the active profile's plugin settings:

```yaml
plugins:
  entries:
    hermes-ultrawork:
      settings:
        normal_chat_enabled: true        # default
        normal_chat_dispatch: true       # default false
        normal_chat_dispatch_platforms:  # default []; add platform ids you trust
          - telegram
          - discord
        tenant: your-tenant             # required for automatic dispatch; no default
        workspace_kind: scratch         # required: scratch, dir, or worktree
        orchestrator_profiles: [architect]
        role_bindings:                  # one explicit available profile per route
          architect: architect
          routine: free-worker
```

Leave `normal_chat_dispatch` at its default `false` unless you have reviewed the contract in `docs/AUTOMATIC_ROUTING_CONTRACT.md` and the per-platform trust implications.

## Usage

Inside a conversation, just talk normally — the pre_llm_call hook runs automatically and (when dispatch is enabled) may schedule a single root Kanban card for explicit background work. You do not need to remember any command.

For explicit planning, the `/ultrawork` command and `ultrawork` model-callable tool are retained for compatibility:

```text
/ultrawork Build a feature that touches six files and needs tests
```

Or ask the model to call `ultrawork` with a plan request. A result looks like:

```json
{"ok":true,"plan":{"protected_fanout_collapsed":false,"items":[{"id":"architect-root","assignee":"architect","parents":[],"task_class":"unknown","fanout_prohibited":false}]}}
```

The active profile must be listed in `orchestrator_profiles`, and settings must supply non-empty `role_bindings` for the planned task classes. Use the returned decision to create or assign a Kanban task explicitly. The plugin does not infer credentials, probe providers, or fall back across paid/free boundaries.

## Safety model

Protected terms and tags include credentials, secrets, payment, publishing, external messaging, privileged operations, firmware, kernel, WMI/HID/SMBus, and destructive actions. These return `architect_gate` with no assignee. Missing or malformed facts fail closed. `allow_paid_upgrade` is always false in this release.

The pre_llm_call hook is bounded and fail-closed: it injects at most 2048 chars of routing context, never mutates the user message, never writes to model/provider/config/profile state, never imports private Hermes internals, and only calls the public `kanban_create` wrapper when every gate above passes. Profile state is isolated — Ultrawork never reads or writes another profile's settings, memory, skills, cron, or sessions.

This plugin is not a hardware-control plugin and has no hardware, subprocess, network, filesystem, credential, or configuration-write capability beyond Hermes loading the plugin itself.

## Troubleshooting

- **No routing context appears in the model output.** Every valid direct turn receives canonical bounded routing context, even without a background-intent phrase. Check `normal_chat_enabled`, the explicit role bindings, and the current catalog snapshot supplied in plugin state.
- **No Kanban card is created from chat.** By design: `normal_chat_dispatch` defaults to `false` and `normal_chat_dispatch_platforms` is empty. Opt in only after reading `docs/AUTOMATIC_ROUTING_CONTRACT.md`.
- **A card was blocked from dispatch.** The hook treats the turn as protected, secret-bearing, ambiguous, or ineligible (e.g. CLI, TUI, synthetic source, `HERMES_KANBAN_TASK` already set). The hook never blocks the user message — the model still sees the original turn; only the side-effect is skipped.
- **`/ultrawork` no longer needed.** It is retained for compatibility. The automatic hook covers the common case; you can keep using `/ultrawork` for explicit planning without changing behavior.
- **Multiple cards in one turn.** Not supported. The hook is bounded to at most one root per turn and never fans out from chat.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q .
```

The test suite covers the pre_llm_call hook, intent classifier, dispatch adapter, plugin contract, disposable-profile integration, and CLI; 47 tests and 47 subtests pass on the current implementation.

## Uninstall / rollback

1. Disable the plugin: `hermes plugins disable hermes-ultrawork`.
2. Remove only its active-profile directory and metadata: `hermes plugins remove hermes-ultrawork`.
3. To roll back, repeat the install command with `--force --ref <PREVIOUS_FULL_40_CHARACTER_COMMIT_SHA> --no-enable`, then enable it explicitly.

No Hermes core files or global model settings are modified by installation.

## Compatibility

Targets Hermes Agent's general Python plugin API (`plugin.yaml`, `register(ctx)`, `ctx.register_tool`, `ctx.register_command`, and `ctx.register_hook` for `pre_llm_call`). The automatic chat hook requires a Hermes release that supports the `pre_llm_call` hook and a `kanban_create` dispatch tool exposed via `ctx.dispatch_tool`. Pin a release tag when deploying in a team. Check the Hermes plugin documentation before upgrading Hermes because plugin APIs can evolve.

## License

MIT. See `LICENSE`.
