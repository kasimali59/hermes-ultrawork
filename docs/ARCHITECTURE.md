# Hermes Ultrawork architecture

Status: implemented and independently reviewed
Target: Hermes Agent 0.20.6+ general Python plugin API

## Purpose

Hermes Ultrawork adapts useful OmO/LazyCodex workflow ideas to Hermes without installing either project or patching Hermes core. The user continues to use ordinary Hermes chat. The plugin adds a deterministic `pre_llm_call` hook that supplies a small routing hint and, only when separately enabled and allowlisted, creates one non-protected Kanban root through the public plugin dispatcher.

## Normal-chat flow

```text
ordinary user turn
        |
        v
versioned lexical intent + protected-content checks
        |
        +--> invalid/secret/protected/ambiguous -> bounded Architect gate, zero writes
        |
        +--> ordinary work -> bounded route context, zero writes
        |
        +--> explicit background intent + all dispatch gates
                    |
                    v
             one public kanban_create call
                    |
                    v
             Hermes dispatcher / Architect-owned lifecycle
```

The hook never calls an LLM, changes the active model, edits configuration, reads credentials, scans profile directories, uses private Hermes imports, shells out, or fans out raw chat into multiple tasks.

## Routing behavior

The route is derived from fixed local rules:

- architecture, policy, security, lifecycle, release, hardware, credentials, publishing, payments, messaging, privilege, or destructive work: Architect gate;
- large or decomposable work: Architect route with decomposition allowed after the root exists;
- difficult integration: configured engineering binding;
- QA/verification: configured QA binding;
- high-uncertainty research: configured research binding;
- routine work: configured routine/free/local binding.

Only profile ids present in the validated, non-stale `ctx.state` catalog and exact role bindings are eligible. Missing or malformed configuration/catalog data fails closed. There is no active-profile, default-profile, Architect, paid-model, or provider fallback unless that profile is the route's explicit configured binding.

## Dispatch gates

Automatic task creation requires every gate below:

1. plugin normal-chat routing is enabled;
2. hook dispatch is explicitly enabled;
3. the platform is explicitly allowlisted;
4. the callback proves a direct gateway turn with a sender and no parent/worker sentinel;
5. the message contains a complete positive background phrase such as `queue this task` or `send this to a worker`;
6. no negative suppression phrase, secret-shaped input, protected content, or ambiguity is present;
7. the active profile is an authorized orchestrator;
8. the exact selected assignee is configured and catalog-confirmed;
9. operation and request revisions do not conflict;
10. the public `kanban_create` result is parseable.

The payload explicitly supplies title, bounded body, assignee, empty parents, tenant, workspace kind, and idempotency key. It omits model/provider overrides. A timeout or malformed result is recorded as ambiguous and is never retried automatically in the same turn. A replay with the same revision converges; a changed revision is blocked.

## Cache and conversation safety

`pre_llm_call` returns a bounded deterministic suffix only. Hermes appends it to the current user turn. The plugin does not mutate conversation history, inject messages, alter the system prompt, change tool schemas/toolsets, or create additional user/assistant messages. This preserves prompt-cache prefixes and role alternation.

## State and privacy

Plugin state may contain only catalog revision/snapshot, operation/request revisions, idempotency keys, statuses, and confirmed task ids. It never stores raw prompts, task bodies, credentials, exception text, provider/model values, profile paths, or message bodies. The only environment check is presence of the documented `HERMES_KANBAN_TASK` worker sentinel; its value is not read or stored.

## Public API surfaces

- `ctx.register_tool`: optional structured planning interface;
- `ctx.register_command`: optional `/ultrawork` compatibility command;
- `ctx.register_cli_command`: validation/status compatibility surface;
- `ctx.register_skill`: bundled workflow guidance;
- `ctx.register_hook("pre_llm_call", ...)`: automatic normal-chat routing;
- `ctx.dispatch_tool("kanban_create", payload)`: the sole automatic write path.

The plugin deliberately does not use `ctx.llm`, `ctx.set_config`, direct SQLite, subprocesses, network clients, private Hermes modules, or profile-home traversal.

## Testing and rollout

The repository contains deterministic unit/contract tests and disposable-profile integration tests. Release gates require the full pytest suite, compileall, whitespace checks, source safety scan, independent QA approval, and GitHub Actions success. Installation remains explicit and profile-scoped; rollback is performed by disabling/removing the plugin or reinstalling a pinned earlier commit.

For the full acceptance matrix, see [`AUTOMATIC_ROUTING_CONTRACT.md`](AUTOMATIC_ROUTING_CONTRACT.md).
