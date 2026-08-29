# Architecture

Hermes Ultrawork is intentionally a thin policy plugin.

```text
request + explicit facts
          |
          v
  deterministic routing policy
          |
          +--> architect_gate (protected)
          +--> architect (large / architectural)
          +--> engineering-lead (integration)
          +--> qa-engineer (verification)
          +--> researcher (uncertain research)
          +--> free-worker (bounded routine work)
```

## Boundaries

The plugin owns classification only. Hermes owns profiles, authentication, Kanban persistence, dispatch, worktrees, and review lifecycle. Keeping those responsibilities separate avoids private imports and makes updates safer.

The policy is pure and deterministic. No provider health request, pricing lookup, profile mutation, subprocess, network call, hardware operation, or credential read occurs during classification.

## Why this is different from the earlier core patch

The earlier prototype wired routing into Hermes' internal Kanban decomposition. That can be useful for upstream work but is not a stable community plugin boundary. This repository instead exposes the tested policy through public plugin registration APIs and leaves task creation/dispatch explicit to the user or an approved future integration.

## Future work

Automatic Kanban creation should be a separate opt-in slice using `ctx.dispatch_tool("kanban_create", ...)`, with explicit confirmation, profile existence checks, idempotency keys, and independent review. It must not silently change the user's model routing or cross protected-action boundaries.
