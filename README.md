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
- Exposes a model-callable `ultrawork_route` tool and `/ulw` planning command.

The first release is deliberately **planning-only**: it returns a structured decision and never launches a worker, changes model settings, edits configuration, touches credentials, or controls hardware. This makes it safe to evaluate before enabling any dispatch integration.

## Install from Git

```bash
mkdir -p ~/.hermes/plugins
cd ~/.hermes/plugins
git clone https://github.com/kasimali59/hermes-ultrawork.git hermes-ultrawork
```

Restart Hermes. Third-party plugins are disabled by default; explicitly enable `hermes-ultrawork` in your profile's `plugins.enabled` configuration using Hermes' supported configuration command. Do not enable it in a profile that has not been reviewed.

## Usage

Inside a conversation:

```text
/ulw Build a feature that touches six files and needs tests
```

Or ask the model to call `ultrawork_route` with explicit facts. A result looks like:

```json
{"route_class":"large_decomposable","assignee":"architect","decompose":true}
```

Use the returned decision to create or assign a Kanban task explicitly. The plugin does not infer credentials, probe providers, or fall back across paid/free boundaries.

## Safety model

Protected terms and tags include credentials, secrets, payment, publishing, external messaging, privileged operations, firmware, kernel, WMI/HID/SMBus, and destructive actions. These return `architect_gate` with no assignee. Missing or malformed facts fail closed. `allow_paid_upgrade` is always false in this release.

This plugin is not a hardware-control plugin and has no hardware, subprocess, network, filesystem, credential, or configuration-write capability beyond Hermes loading the plugin itself.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q .
```

## Uninstall / rollback

1. Disable `hermes-ultrawork` in the profile configuration.
2. Remove `~/.hermes/plugins/hermes-ultrawork` or delete only the cloned directory.
3. Restart Hermes.

No Hermes core files or global model settings are modified by installation.

## Compatibility

Targets Hermes Agent's general Python plugin API (`plugin.yaml`, `register(ctx)`, `ctx.register_tool`, and `ctx.register_command`). Pin a release tag when deploying in a team. Check the Hermes plugin documentation before upgrading Hermes because plugin APIs can evolve.

## License

MIT. See `LICENSE`.
