# Automatic normal-chat Ultrawork routing contract

Status: implemented and independently reviewed
Target: Hermes Agent 0.20.6+ public plugin API
Policy id: `hermes-ultrawork-normal-chat-v1`

## 1. Decision

Enabling Hermes Ultrawork makes ordinary user turns eligible for deterministic routing without requiring `/ultrawork`. The plugin registers one `pre_llm_call` hook in addition to retaining the tool and slash command for structured dispatch and compatibility.

The manifest contract is explicit: `normal_chat_enabled` defaults to `true`; `normal_chat_dispatch` defaults to `false`; and `normal_chat_dispatch_platforms` defaults to `[]`. Thus enablement turns on context-only routing without granting a hidden write path. Hook-initiated task creation requires the operator to opt in by setting `normal_chat_dispatch=true` and listing each allowed gateway platform through the normal Hermes plugin configuration surface. The plugin validates these settings but never changes them.

The hook has only two permitted outcomes:

1. Return a bounded routing block that Hermes appends to the current user message.
2. For an explicit natural-language request to queue/delegate work, create at most one durable root Kanban task through `ctx.dispatch_tool("kanban_create", ...)`, then return a bounded receipt as routing context.

The hook never decomposes raw chat into a multi-task graph. Fan-out requires the foreground Architect to call the model-facing `ultrawork` tool with a fully specified, validated graph. This keeps automatic routing useful while preventing a hook from turning ambiguous text into many side effects.

`/ultrawork` remains a compatibility and diagnostic interface, not the primary UX.

## 2. Public Hermes behavior relied upon

Hermes documents `pre_llm_call` as firing once per user turn, after preflight compression and before the tool loop. Valid string or `{"context": ...}` returns are joined in plugin order and appended to the current turn's user message. The hook is inject-only: it does not replace history or the system prompt.

Hermes documents `ctx.dispatch_tool(name, args)` as the public plugin surface for invoking registered tools, including `kanban_*`, with parent-agent context wired when available. A successful `kanban_create` is a durable local queue write; the dispatcher runs the assigned profile in the background.

No Hermes private import, direct SQLite access, `hermes kanban` subprocess, `delegate_task`, or message injection is part of this contract.

## 3. Turn classification

The hook validates and classifies only these public callback fields: `session_id`, `task_id`, `turn_id`, `user_message`, `conversation_history`, `is_first_turn`, `model`, `platform`, `parent_session_id`, and `sender_id`. It accepts `**kwargs` for forward compatibility but ignores unrecognized values. For recursion prevention it may additionally test only the presence, never the value, of Hermes' documented `HERMES_KANBAN_TASK` worker sentinel.

Classification order is fixed and fail-closed:

1. Reject invalid types, empty text, NUL/control characters, or text above 12,000 characters.
2. Scan the current user message for secret-shaped values. A match yields generic `secret_input` context and no hash, state write, task body, or dispatch.
3. Apply negative dispatch intent before positive intent.
4. Detect protected categories with versioned token/phrase rules and word boundaries.
5. Compute the ordinary route from local facts only.
6. Check dispatch eligibility.

The hook does not call an LLM, inspect provider health, infer model price, read credentials, refresh the profile roster, inspect profile directories, or use timestamps/load counters during classification.

### 3.1 Explicit background intent

A turn has positive background intent only when its current user message contains one of these versioned, case-insensitive phrases with token boundaries, outside Markdown fenced/inline-code and quoted spans:

- `in the background`
- `delegate this` or `delegate the task`
- `use kanban`
- `queue this` or `queue the task`
- `send this to a worker` or `send this to the worker`
- `fan this out` or `fan out this task`

Any of these phrases suppresses positive intent, regardless of order:

- `do not delegate`, `don't delegate`, or `no delegation`
- `do not use kanban`, `don't use kanban`, or `no kanban`
- `do not queue`, `don't queue`, or `no background`
- `just answer`, `answer only`, `plan only`, or `do not execute`

Other wording receives automatic routing context but no hook-initiated write. The foreground agent may ask one concise question or use the structured Ultrawork tool. The rule table is data with golden tests; it is not open-ended semantic inference.

A matched phrase is treated as a mention, not intent, when the immediately preceding normalized token is `example`, `phrase`, `text`, `literal`, `quote`, `say`, or `contains`. After removing intent phrases and punctuation, a dispatchable request must have at least three tokens and contain one fixed action token: `analyze`, `build`, `create`, `document`, `fix`, `implement`, `investigate`, `migrate`, `plan`, `refactor`, `research`, `review`, `test`, `update`, `verify`, or `write`. Otherwise it is incomplete and remains context-only. The lexer and token table are policy-versioned fixtures; no probabilistic intent inference is permitted.

### 3.2 Routes

- Protected, ambiguous, architecture, security, release, public-API, lifecycle, or policy work: `architect_gate`.
- Large/decomposable work: one `architect` root with `decompose_allowed=true`.
- Difficult implementation/integration: configured `engineering` binding.
- QA/validation: configured `qa` binding.
- High-uncertainty research: configured `research` binding.
- Bounded routine/docs/reporting: configured free/local binding for that role.
- Unknown work: `architect_gate` with no automatic dispatch.

A route can select only an explicitly configured profile in that route's binding and the current non-stale catalog. There is no implicit fallback to the active profile, `default`, Architect, another role, or another model. Architect is selected only when the route itself is Architect-owned. Every decision keeps `allow_paid_upgrade=false`.

## 4. Context-injection contract

For every valid direct user turn, the hook returns either `None` or one canonical UTF-8 block no larger than 2,048 characters. The block uses fixed key order and contains only:

- policy id;
- route class and configured assignee, if any;
- sorted reason/risk rule ids;
- `dispatch`: `not_requested`, `blocked`, `queued`, or `ambiguous`;
- `requires_confirmation`: boolean;
- `decompose_allowed`: boolean;
- a task id only after a confirmed create result.

It does not repeat the user message, history, model, provider, local paths, profile roster, timestamps, task bodies, credentials, or exception text. Identical validated input plus identical plugin settings/catalog/receipt state produces byte-identical context.

The callback must not mutate `conversation_history`, call `ctx.inject_message`, append a synthetic message, alter a previous message, or register/change a system-prompt section mid-session. Hermes alone appends the returned block to the current user message. This preserves the cached system-prompt/history prefix and valid role alternation; the only changed bytes are the documented suffix of the current user turn.

Static policy prose stays in the bundled skill or a session-frozen, bounded system-prompt section. `pre_llm_call` carries only the per-turn decision.

## 5. Automatic root-dispatch contract

The hook may call `ctx.dispatch_tool("kanban_create", payload)` exactly once only when all conditions below hold:

1. The plugin is enabled, `normal_chat_enabled=true`, `normal_chat_dispatch=true`, and the current platform is explicitly listed in `normal_chat_dispatch_platforms` for this active profile.
2. `ctx.profile_name` is in validated `orchestrator_profiles`.
3. The callback proves a direct top-level gateway user turn: `parent_session_id` is empty, `sender_id` is non-empty, `platform` is in the configured gateway-interactive allowlist, and the documented `HERMES_KANBAN_TASK` worker sentinel is absent. Gateway-generated wakes have no authenticated sender and are ineligible; subagents have a parent and are ineligible; dispatcher workers carry the sentinel and are ineligible. Current CLI/TUI hook payloads do not expose a trusted user-origin marker, so they are context-only: the foreground agent may call the structured tool, but the hook itself performs no write. Cron, ACP, unknown platforms, and any future source that cannot prove these conditions also fail closed. This rule may be widened only in a new policy version after Hermes exposes a trusted direct-user/turn-type field.
4. Positive background intent is present and no negative intent is present.
5. The message is non-secret, unprotected, unambiguous, and complete enough to become one bounded root task.
6. The selected profile exists in a current, non-stale, versioned catalog and belongs to the exact route binding.
7. A deterministic operation/idempotency key has been derived from the policy id, active profile, session id, turn id, request revision, and root item id. Raw session/user text is not placed in the key.
8. No receipt for a conflicting request revision exists for that operation.
9. The public `kanban_create` tool is registered and returns a parseable success result with one task id.

The payload explicitly sets `title`, `assignee`, `body`, `parents=[]`, `tenant`, `workspace_kind`, and `idempotency_key`. It omits `model`, `provider`, and all profile/config mutation fields. The body deterministically contains a bounded goal/scope, source policy and revisions, acceptance/evidence requirements, safety decision, and required structured handoff. Secret-shaped input is never rendered.

A hook creates one root only. An Architect root may later decompose through ordinary Kanban lifecycle rules; lower-trust roots may not fan out. Dispatch success returns `queued` plus the confirmed task id and tells the foreground agent not to duplicate the queued implementation. Normal chat remains available to report the receipt.

`ctx.dispatch_tool` is invoked synchronously for the single local create; no plugin thread, subprocess, retry loop, polling loop, or provider call is started. The worker execution is background work owned by Hermes Kanban, not by the hook.

### 5.1 Failure and ambiguity

- Missing/stale catalog, unavailable assignee, unauthorized profile, missing tool, malformed result, or non-ambiguous create failure: no fallback; return bounded `blocked` context.
- Timeout or any result that cannot prove whether the create committed: return `ambiguous`, store only operation/request revisions and confirmed ids if any, and do not retry automatically in that turn.
- Re-entry with the same operation/request uses the same idempotency key and converges on the existing task.
- Re-entry with a different request revision returns `E_OPERATION_CONFLICT` and performs no write.
- There is no compensating delete. An operator uses normal Kanban controls if reconciliation is required.
- If `kanban_create` is unavailable, there is no shell, direct-DB, `delegate_task`, paid-model, or active-profile fallback.

## 6. Protected-work and confirmation gate

Credential handling, destructive operations, payment, publishing/release, external messaging, privilege changes, and hardware/firmware/kernel/EC/WMI/HID/SMBus writes always produce `architect_gate`, `requires_confirmation=true`, and no hook-initiated dispatch.

The foreground Architect must state the exact proposed action, target, and material consequence and obtain explicit user confirmation before any such action. A generic earlier `yes`, plugin enablement, background-intent phrase, or approval of unrelated work is not confirmation. The hook does not persist or consume confirmation state.

After confirmation, the foreground Architect may submit a fully structured request through the explicit `ultrawork` tool. That request is revalidated and may create only an Architect-owned review/root task. The plugin still does not perform the protected action itself. Credential values remain out of plugin inputs and Kanban bodies even after confirmation.

## 7. Hard invariants

### Prompt/cache and conversation

- No past message, cached system prompt, tool schema, or toolset changes after session start.
- No message insertion; Hermes appends one bounded suffix to the current user message.
- No two consecutive user/assistant roles are created.
- Hook output ordering and serialization are deterministic.

### Profile and state isolation

- All identity decisions use `ctx.profile_name`; all plugin state uses `ctx.state`.
- State contains catalog revisions, operation/request revisions, idempotency keys, and confirmed task ids only; never prompts, task bodies, secrets, model/provider values, or cross-profile paths.
- No direct traversal or mutation of any profile home, `profile.yaml`, config, memory, skills, sessions, cron, or auth stores.
- Board and tenant are explicit validated inputs; no cross-board or cross-tenant fallback.
- The only environment access is a boolean presence check for documented `HERMES_KANBAN_TASK`; its value is never read, logged, hashed, or stored.

### Model/cost/config safety

- Routing selects a configured profile, never a model/provider.
- `model` and `provider` are omitted from `kanban_create`.
- No `ctx.llm`, provider probe, fallback-chain edit, `ctx.set_config`, `hermes config`, or model/config mutation.
- A missing free/local binding fails closed; it never upgrades to a paid profile.

### Side-effect safety

- Automatic dispatch is limited to one non-protected root task after explicit positive background intent.
- Protected actions require scoped confirmation in the foreground Architect session.
- The plugin never publishes, sends messages, handles payment, uses credentials, or controls hardware.

## 8. Affected modules

Implementation should remain focused:

- `__init__.py`: register the `pre_llm_call` hook; retain tool/slash/CLI/skill compatibility.
- `plugin.yaml`: declare `normal_chat_enabled` (default `true`), `normal_chat_dispatch` (default `false`), `normal_chat_dispatch_platforms` (default `[]`), bounded hard maxima, and no capabilities or environment requirements.
- `ultrawork/normal_chat.py` (new): callback adapter, source eligibility, canonical context/receipt rendering.
- `ultrawork/intent.py` (new): versioned positive/negative phrase tables and deterministic intent classifier.
- `ultrawork/validation.py`: shared text/secret/protected validation with word-boundary rules.
- `ultrawork/planning.py`: single-root route construction and no cross-role fallback.
- `ultrawork/catalog.py`: current/stale snapshot validation; no roster refresh on the hook hot path.
- `ultrawork/dispatch.py` (new): exact `kanban_create` payload, result validation, idempotent receipts, ambiguity handling.
- `ultrawork/api.py`: structured `plan|dispatch` remains the only multi-item dispatch path.
- `skills/ultrawork-orchestration/SKILL.md`, `README.md`, and `docs/ARCHITECTURE.md`: make normal chat primary and `/ultrawork` compatibility-only.
- `tests/`: focused contract tests plus disposable-profile/plugin integration tests.

Do not retain the duplicate top-level `routing.py` policy as a second source of truth. Migrate callers to the package policy or delete it only after parity tests prove no behavior was lost.

## 9. Contract-test scenarios

### Hook and cache behavior

1. Registration exposes one hook plus the existing public interfaces; registration performs no I/O or dispatch.
2. Ordinary `"Fix a typo"` returns deterministic free/local routing context and zero host-tool calls.
3. The same callback input/settings/catalog/receipt produces byte-identical output across repeated runs.
4. Output is at most 2,048 characters and contains no copied user text/history/model/provider/path.
5. The callback leaves the supplied history deeply equal and never calls message/system-prompt mutation APIs.
6. A simulated API message list has unchanged role sequence and only the current user content receives a suffix.
7. Multiple plugin contexts remain valid when Hermes joins them with double newlines.

### Intent and single-root dispatch

8. Every positive phrase on an otherwise eligible, complete gateway turn queues exactly one root; casing and punctuation variants match.
9. Every negative phrase suppresses dispatch, including when a positive phrase is also present.
10. Similar substrings and quoted/example phrases do not dispatch; Unicode/control/oversized inputs fail closed.
11. Direct authenticated gateway turn may dispatch; CLI/TUI, subagent, cron, worker, synthetic wake, unsupported platform, empty-sender, or unidentifiable source may not.
12. The exact `kanban_create` payload has explicit fields, no model/provider override, stable idempotency key, and bounded body.
13. Replaying the same turn converges on one task; conflicting request revision performs no write.
14. The hook makes at most one host-tool call and never fans out raw chat.
15. Missing/malformed/timeout/ambiguous create results stop without retry or delete.

### Routing, profile, and cost safety

16. Routine work with unavailable free/local binding fails closed; it never selects Architect/default/active profile.
17. Architecture/large work selects Architect only because its route class requires Architect.
18. QA, research, and engineering routes select only their configured on-disk bindings.
19. Stale/malformed/duplicate/non-ASCII catalogs dispatch nothing.
20. Unauthorized `ctx.profile_name`, other profile homes, boards, and tenants cannot receive state or tasks.
21. Static/AST checks reject `ctx.llm`, `ctx.set_config`, model/provider payload keys, direct DB/private Hermes imports, shell Kanban, profile traversal, network, subprocess, and credential/environment reads, allowing only the exact boolean `HERMES_KANBAN_TASK` presence check.

### Protected work

22. Each protected category returns Architect gate, confirmation required, and zero dispatch calls.
23. A protected child hidden under benign parent text cannot be auto-fanned-out.
24. Secret-shaped values yield generic error/context with no echo, hash, state write, or task write.
25. `hid` does not match inside `children`; `publish` does not match an allowed negative fixture unless the token/phrase rule says so.
26. A generic `yes` does not clear the gate or auto-dispatch protected work.

### Disposable-profile integration

27. Install/enable in a temporary `HERMES_HOME`; normal chat receives routing without invoking `/ultrawork`.
28. Fake public `kanban_create` records one durable root and the returned receipt is injected into only the current user turn.
29. Existing profile/config/auth/memory/skill/session sentinels remain unchanged outside allowed active-profile plugin metadata/state.
30. Disabling/removing the plugin restores normal chat with no hook output and no core/config edits.

## 10. Implementation sequence

1. Consolidate validation/routing into one package policy and land the golden contract tests first.
2. Add pure intent/source-eligibility/context-rendering functions; prove zero host calls.
3. Register `pre_llm_call` in context-only mode and pass cache/alternation/disposable-profile tests.
4. Add the one-root dispatch adapter with fake `kanban_create`, stable receipts, and ambiguity tests.
5. Enable explicit natural-language background intent; keep protected and unidentifiable turns context-only.
6. Update normal-chat-first docs while preserving `/ultrawork` compatibility.
7. Run focused tests, full `pytest`, compile/static/security checks, disposable-profile integration, independent QA, then the existing release gates.

## 11. Acceptance checklist

- [ ] A user can type an ordinary task without remembering `/ultrawork` and receives the deterministic Ultrawork route.
- [ ] Context-only normal-chat routing is on when the plugin is enabled, while hook writes remain off by default.
- [ ] Only an operator-enabled, platform-allowlisted, explicit positive natural-language background intent can cause a hook write.
- [ ] One hook invocation creates at most one non-protected root through public `ctx.dispatch_tool("kanban_create", ...)`.
- [ ] Raw chat is never automatically decomposed or fanned out.
- [ ] Protected/secret/ambiguous/ineligible turns perform zero writes and retain the Architect/confirmation gate.
- [ ] Same validated inputs and receipt state produce byte-identical bounded context and stable idempotency keys.
- [ ] System prompt, past messages, tool schemas/toolsets, and role alternation remain unchanged.
- [ ] Profile/board/tenant state stays isolated and no profile/config/auth files are read or changed.
- [ ] Missing free/local routes fail closed with no paid/default/Architect fallback.
- [ ] No model/provider override, provider call, config mutation, shell Kanban, direct DB, or private Hermes API is used.
- [ ] `/ultrawork` remains compatible but normal chat is the documented primary path.
- [ ] Focused contract tests, full tests, disposable-profile integration, QA, and release gates pass with real evidence.

## Sources

- https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks
- https://hermes-agent.nousresearch.com/docs/developer-guide/prompt-assembly
- https://hermes-agent.nousresearch.com/docs/guides/build-a-hermes-plugin
- https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins
- https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
