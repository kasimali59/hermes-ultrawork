---
name: ultrawork-orchestration
description: Use when planning bounded, safety-first Hermes Kanban work with the Ultrawork plugin.
version: 0.1.0
---

# Ultrawork orchestration

Use ordinary Hermes chat for automatic routing. The `pre_llm_call` hook adds bounded deterministic routing context for valid turns. It creates at most one Kanban root only when the operator explicitly enables dispatch, allowlists the platform, and the user uses a complete positive background phrase such as “queue this task” or “send this to a worker”. Without those settings, the plugin is context-only. `/ultrawork plan <goal>` and the `ultrawork` tool remain optional compatibility interfaces.

## Safe use

1. Speak normally; the hook provides a small route hint without changing the user message or system prompt.
2. Treat `architect_gate`, protected content, missing catalog, malformed settings, and unavailable bindings as stop signals. No automatic task is created.
3. Automatic dispatch is one non-protected root only. Hermes Kanban/Architect owns any later decomposition.
4. Keep secrets and credentials out of requests. Secret-shaped values are rejected and are not included in output.

## Determinism

For the same request, validated plugin settings, catalog snapshot, and receipt state, Ultrawork produces byte-identical bounded context. Intent matching uses versioned phrase boundaries and ignores quoted/code examples.

## Boundaries

The bundled plugin uses public Hermes plugin APIs only. It never mutates profiles, config, credentials, or Hermes core, never performs automatic paid-model upgrades, and never dispatches protected or ambiguous work.
