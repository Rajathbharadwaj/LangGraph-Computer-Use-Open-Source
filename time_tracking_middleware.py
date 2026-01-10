"""
Time Tracking Middleware for DeepAgents

Tracks elapsed time and enforces session time limits based on subscription tier.
Injects timing info into tool context to help agent manage time.

Time Limits by Tier:
- Starter: 7 minutes (420s)
- Pro: 15 minutes (900s)
- Pro Plus: 30 minutes (1800s)
- Ultimate: 41 minutes (2466s)
"""

from typing import Callable
from langchain_core.messages import ToolMessage
from langchain.agents.middleware import wrap_tool_call
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command
import time

# Time limits in seconds by subscription tier
TIME_LIMITS = {
    "starter": 420,      # 7 minutes
    "pro": 900,          # 15 minutes
    "pro_plus": 1800,    # 30 minutes
    "ultimate": 2466,    # ~41 minutes
    "default": 900,      # 15 minutes fallback
}

# Track session start times by thread_id (fallback if __request_start_time_ms__ not available)
_session_start_times: dict[str, float] = {}


@wrap_tool_call
async def time_tracking_middleware(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    """Track time and enforce limits on agent sessions.

    This middleware:
    1. Checks elapsed time since session start
    2. Warns agent when approaching time limit (40% and 20% remaining)
    3. Blocks tool execution when time limit exceeded
    """

    runtime = getattr(request, 'runtime', None)
    if not runtime:
        return await handler(request)

    config = getattr(runtime, 'config', {})
    configurable = config.get('configurable', {})

    # Get tool name for logging
    tool_name = request.tool_call.get('name', 'unknown') if hasattr(request, 'tool_call') else 'unknown'

    # Check for SUBAGENT-specific timing first (takes priority)
    # This allows subagents to have their own time budget independent of main session
    subagent_start_time_ms = configurable.get('__subagent_start_time_ms__', 0)
    subagent_budget = configurable.get('__subagent_time_budget_seconds__', 0)
    is_subagent = bool(subagent_start_time_ms and subagent_budget)

    if is_subagent:
        # SUBAGENT MODE: Use subagent-specific timing
        elapsed_ms = time.time() * 1000 - subagent_start_time_ms
        elapsed_seconds = elapsed_ms / 1000
        elapsed_minutes = elapsed_seconds / 60
        time_limit = subagent_budget
        remaining_seconds = time_limit - elapsed_seconds
        remaining_minutes = remaining_seconds / 60
        tier = "subagent"

        print(f"[TimeLimit] SUBAGENT | {tool_name} | Elapsed: {elapsed_minutes:.1f}min | Remaining: {remaining_minutes:.1f}min | Budget: {subagent_budget//60}min")
    else:
        # SESSION MODE: Use session-level timing (original behavior)
        start_time_ms = configurable.get('__request_start_time_ms__', 0)
        thread_id = configurable.get('thread_id', '')

        if not start_time_ms:
            # Fallback: track our own start time per thread
            if thread_id:
                if thread_id not in _session_start_times:
                    _session_start_times[thread_id] = time.time() * 1000
                    print(f"[TimeLimit] Started tracking time for thread {thread_id}")
                start_time_ms = _session_start_times[thread_id]
            else:
                # No way to track time, pass through
                return await handler(request)

        # Calculate elapsed time
        elapsed_ms = time.time() * 1000 - start_time_ms
        elapsed_seconds = elapsed_ms / 1000
        elapsed_minutes = elapsed_seconds / 60

        # Get user's subscription tier
        user_id = configurable.get('user_id') or configurable.get('x-user-id')
        tier = configurable.get('x-user-tier')  # Check if frontend passed tier

        if not tier:
            # Try to fetch from store
            tier = await get_user_tier(getattr(runtime, 'store', None), user_id)

        time_limit = TIME_LIMITS.get(tier, TIME_LIMITS["default"])
        remaining_seconds = time_limit - elapsed_seconds
        remaining_minutes = remaining_seconds / 60

        print(f"[TimeLimit] SESSION | {tool_name} | Elapsed: {elapsed_minutes:.1f}min | Remaining: {remaining_minutes:.1f}min | Tier: {tier} | Limit: {time_limit//60}min")

    # Check if time limit exceeded
    if elapsed_seconds >= time_limit:
        if is_subagent:
            print(f"[TimeLimit] SUBAGENT TIME LIMIT REACHED! Elapsed: {elapsed_minutes:.1f}min, Budget: {time_limit/60:.0f}min")
            return ToolMessage(
                content=f"SUBAGENT TIME BUDGET EXCEEDED\n\n"
                       f"This subagent has used its {time_limit//60}-minute budget.\n"
                       f"Elapsed: {elapsed_minutes:.1f} minutes\n\n"
                       f"Complete your current action and return results to the main agent.",
                tool_call_id=request.tool_call.get('id', '')
            )
        else:
            print(f"[TimeLimit] SESSION TIME LIMIT REACHED! Elapsed: {elapsed_minutes:.1f}min, Limit: {time_limit/60:.0f}min")

            # Clean up session tracking
            thread_id = configurable.get('thread_id', '')
            if thread_id and thread_id in _session_start_times:
                del _session_start_times[thread_id]

            return ToolMessage(
                content=f"SESSION TIME LIMIT REACHED\n\n"
                       f"You have reached the maximum session duration for your {tier} plan ({time_limit//60} minutes).\n"
                       f"Elapsed: {elapsed_minutes:.1f} minutes\n\n"
                       f"Please wrap up immediately. This will be your final action.\n"
                       f"Summarize what you accomplished and say goodbye to the user.",
                tool_call_id=request.tool_call.get('id', '')
            )

    # Execute the tool
    tool_result = await handler(request)

    # Inject timing info into response at warning thresholds
    warning = ""
    if remaining_seconds < time_limit * 0.2:  # Less than 20% remaining
        warning = f"\n\n TIME WARNING: Only {remaining_minutes:.1f} minutes remaining! Wrap up NOW."
    elif remaining_seconds < time_limit * 0.4:  # Less than 40% remaining
        warning = f"\n\n TIME CHECK: {remaining_minutes:.1f} minutes remaining. Start wrapping up."

    if warning and isinstance(tool_result, ToolMessage):
        # Append timing warning to tool result
        if isinstance(tool_result.content, str):
            return ToolMessage(
                content=tool_result.content + warning,
                tool_call_id=tool_result.tool_call_id
            )
        elif isinstance(tool_result.content, list):
            # Multimodal content - append text block
            return ToolMessage(
                content=tool_result.content + [{"type": "text", "text": warning}],
                tool_call_id=tool_result.tool_call_id
            )

    return tool_result


async def get_user_tier(store, user_id: str) -> str:
    """Fetch user's subscription tier from store.

    Args:
        store: LangGraph store instance
        user_id: User ID to look up

    Returns:
        Subscription tier name or "default"
    """
    if not store or not user_id:
        return "default"

    try:
        # Try to get subscription info from store
        sub_item = await store.aget((user_id, "subscription"), "info")
        if sub_item and sub_item.value:
            plan = sub_item.value.get("plan", "default")
            print(f"[TimeLimit] Found tier '{plan}' for user {user_id}")
            return plan
    except Exception as e:
        print(f"[TimeLimit] Could not fetch tier for {user_id}: {e}")

    return "default"


def clear_session_tracking(thread_id: str):
    """Clear session tracking for a thread (call when session ends)."""
    if thread_id in _session_start_times:
        del _session_start_times[thread_id]
        print(f"[TimeLimit] Cleared time tracking for thread {thread_id}")
