"""
Monkey-patch deepagents to forward config to subagents.

This module patches the deepagents.middleware.subagents module at import time
to ensure that runtime config (containing cua_url for per-user VNC sessions)
is forwarded to subagent tools.

Import this module early in your application to apply the patch.
"""
import sys


def _apply_patch():
    """Apply the config forwarding patch to deepagents subagents middleware."""
    try:
        from deepagents.middleware import subagents
        from langchain.tools import ToolRuntime
        from langchain_core.messages import HumanMessage
        from langgraph.types import Command

        # Check if already patched
        if hasattr(subagents, '_CONFIG_PATCH_APPLIED'):
            return

        # Get references to the original functions we need
        _EXCLUDED_STATE_KEYS = subagents._EXCLUDED_STATE_KEYS

        def _return_command_with_state_update(result: dict, tool_call_id: str) -> Command:
            state_update = {k: v for k, v in result.items() if k not in _EXCLUDED_STATE_KEYS}
            from langchain_core.messages import ToolMessage
            return Command(
                update={
                    **state_update,
                    "messages": [ToolMessage(result["messages"][-1].text, tool_call_id=tool_call_id)],
                }
            )

        # Store original _create_task_tool
        original_create_task_tool = subagents._create_task_tool

        def patched_create_task_tool(**kwargs):
            """Wrapper that patches the task tool to forward config."""
            tool = original_create_task_tool(**kwargs)

            # Get the subagent graphs from closure
            subagent_graphs, _ = subagents._get_subagents(
                default_model=kwargs['default_model'],
                default_tools=kwargs['default_tools'],
                default_middleware=kwargs['default_middleware'],
                default_interrupt_on=kwargs['default_interrupt_on'],
                subagents=kwargs['subagents'],
                general_purpose_agent=kwargs['general_purpose_agent'],
            )

            def _validate_and_prepare_state(subagent_type: str, description: str, runtime: ToolRuntime):
                if subagent_type not in subagent_graphs:
                    msg = f"Error: invoked agent of type {subagent_type}, the only allowed types are {[f'`{k}`' for k in subagent_graphs]}"
                    raise ValueError(msg)
                subagent = subagent_graphs[subagent_type]
                subagent_state = {k: v for k, v in runtime.state.items() if k not in _EXCLUDED_STATE_KEYS}
                subagent_state["messages"] = [HumanMessage(content=description)]
                return subagent, subagent_state

            # Create patched task functions
            def patched_task(description: str, subagent_type: str, runtime: ToolRuntime):
                subagent, subagent_state = _validate_and_prepare_state(subagent_type, description, runtime)
                # PATCHED: Forward config to subagent
                result = subagent.invoke(subagent_state, config=runtime.config)
                if not runtime.tool_call_id:
                    raise ValueError("Tool call ID is required for subagent invocation")
                return _return_command_with_state_update(result, runtime.tool_call_id)

            async def patched_atask(description: str, subagent_type: str, runtime: ToolRuntime):
                subagent, subagent_state = _validate_and_prepare_state(subagent_type, description, runtime)
                # PATCHED: Forward config to subagent
                result = await subagent.ainvoke(subagent_state, config=runtime.config)
                if not runtime.tool_call_id:
                    raise ValueError("Tool call ID is required for subagent invocation")
                return _return_command_with_state_update(result, runtime.tool_call_id)

            # Replace the tool's functions
            tool.func = patched_task
            tool.coroutine = patched_atask

            return tool

        # Apply the patch
        subagents._create_task_tool = patched_create_task_tool
        subagents._CONFIG_PATCH_APPLIED = True
        print("✅ Applied deepagents config forwarding patch")

    except ImportError as e:
        print(f"⚠️ Could not apply deepagents patch: {e}")
    except Exception as e:
        print(f"⚠️ Error applying deepagents patch: {e}")
        import traceback
        traceback.print_exc()


# Apply patch on import
_apply_patch()
