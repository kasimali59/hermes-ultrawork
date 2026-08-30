"""Hermes Ultrawork public plugin entry point."""
from __future__ import annotations

try:
    from .ultrawork.api import build_plugin, bundled_skill_path
    from .ultrawork.normal_chat import NormalChatPlugin
except ImportError:  # Direct checkout loading by Hermes/plugin tests.
    from ultrawork.api import build_plugin, bundled_skill_path
    from ultrawork.normal_chat import NormalChatPlugin


def register(ctx):
    """Register the normal-chat hook plus optional explicit compatibility interfaces."""
    plugin = build_plugin(ctx)
    ctx.register_tool(
        name="ultrawork",
        toolset="ultrawork",
        schema=plugin.tool_schema,
        handler=plugin.handle_tool,
    )
    ctx.register_command(
        "ultrawork",
        handler=plugin.handle_slash,
        description="Plan deterministic safety-first Kanban work",
        args_hint="plan <goal>",
    )
    ctx.register_cli_command(
        name="ultrawork",
        help="Validate Hermes Ultrawork requests",
        setup_fn=plugin.setup_cli,
        handler_fn=plugin.handle_cli,
    )
    ctx.register_skill("ultrawork-orchestration", bundled_skill_path())

    # Register normal-chat pre_llm_call hook
    normal_chat_plugin = NormalChatPlugin(ctx)
    ctx.register_hook(
        "pre_llm_call",
        handler=normal_chat_plugin.pre_llm_call,
    )
