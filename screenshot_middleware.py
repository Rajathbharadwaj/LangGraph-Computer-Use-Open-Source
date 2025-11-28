"""
Screenshot Middleware for DeepAgents

Automatically injects before/after screenshots into the LLM context for action tools.
This ensures the LLM can visually verify that actions (like, comment, post) actually succeeded.

Usage:
    from screenshot_middleware import create_screenshot_middleware

    # Add to subagent middleware
    subagents = [
        {
            "name": "like_post",
            "system_prompt": "...",
            "tools": [like_post_tool],
            "middleware": [create_screenshot_middleware()]
        }
    ]
"""

from typing import Any, Callable
from langchain_core.messages import ToolMessage
from langchain.agents.middleware import wrap_tool_call
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command


@wrap_tool_call
async def screenshot_middleware(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    """Wrap tool calls with before/after screenshots for visual verification"""

    print("=" * 80)
    print("🔥 [Middleware] ENTERED screenshot_middleware!")
    print(f"🔥 [Middleware] request type: {type(request)}")
    print(f"🔥 [Middleware] request attributes: {dir(request)}")

    try:
        # Get the tool name from request
        tool_name = request.tool_call.get('name', '') if hasattr(request, 'tool_call') else ''
        print(f"🔥 [Middleware] tool_name: {tool_name}")

        # Get runtime to access Playwright client
        runtime = getattr(request, 'runtime', None)
        print(f"🔥 [Middleware] runtime exists: {runtime is not None}")
        if not runtime:
            # No runtime, just execute tool normally
            print("⚠️ [Middleware] No runtime found, passing through")
            print("=" * 80)
            return await handler(request)

        # Get config to access Playwright client info
        config = getattr(runtime, 'config', {})
        print(f"🔥 [Middleware] config type: {type(config)}")
        print(f"🔥 [Middleware] config keys: {list(config.keys())}")

        # Get configurable dict
        configurable = config.get('configurable', {})
        print(f"🔥 [Middleware] configurable type: {type(configurable)}")
        print(f"🔥 [Middleware] configurable keys: {list(configurable.keys())}")

        # Get specific values
        cua_host = configurable.get('x-cua-host')
        cua_port = configurable.get('x-cua-port')
        user_id = configurable.get('user_id')
        x_user_id = configurable.get('x-user-id')  # Clerk user ID from frontend
        cua_url = configurable.get('cua_url')

        print(f"🔥 [Middleware] cua_host: {repr(cua_host)}")
        print(f"🔥 [Middleware] cua_port: {repr(cua_port)}")
        print(f"🔥 [Middleware] user_id: {repr(user_id)}")
        print(f"🔥 [Middleware] x_user_id: {repr(x_user_id)}")
        print(f"🔥 [Middleware] cua_url: {repr(cua_url)}")
        print("=" * 80)

        # If cua_host/port not provided, try to fetch VNC URL from backend using x-user-id
        if not (cua_host and cua_port) and x_user_id:
            print(f"🔍 [Middleware] Fetching VNC URL from backend for user: {x_user_id}")
            try:
                import aiohttp
                import os

                # Get backend URL from environment
                backend_url = os.environ.get('BACKEND_URL', 'https://backend-api-644185288504.us-central1.run.app')

                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{backend_url}/api/vnc/session/{x_user_id}") as response:
                        if response.status == 200:
                            vnc_data = await response.json()
                            vnc_url = vnc_data.get('https_url') or vnc_data.get('service_url')

                            if vnc_url and "://" in vnc_url:
                                # Parse host and port
                                after_protocol = vnc_url.split("://")[1]
                                host_and_port = after_protocol.rstrip("/")
                                if ":" in host_and_port:
                                    cua_host = host_and_port.split(":")[0]
                                    cua_port = host_and_port.split(":")[1]
                                else:
                                    cua_host = host_and_port
                                    cua_port = "80" if vnc_url.startswith("http://") else "443"

                                print(f"✅ [Middleware] Fetched VNC URL: {vnc_url}")
                                print(f"✅ [Middleware] Parsed - host: {cua_host}, port: {cua_port}")
                        else:
                            print(f"⚠️ [Middleware] Backend returned status {response.status}")
            except Exception as e:
                print(f"❌ [Middleware] Error fetching VNC URL: {e}")

        if not (cua_host and cua_port):
            # No Playwright client configured, execute tool normally
            print("⚠️ [Middleware] No cua_host/cua_port found after all attempts, passing through")
            return await handler(request)

        # Import here to avoid circular dependencies
        import aiohttp
        import asyncio

        base_url = f"http://{cua_host}:{cua_port}"

        # 📸 Take screenshot BEFORE action
        print(f"📸 [Middleware] Taking BEFORE screenshot for {tool_name}")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/screenshot") as response:
                before_data = await response.json()
                before_screenshot = before_data.get("image", "")

        # Clean base64 prefix if present
        if before_screenshot.startswith("data:image/png;base64,"):
            before_screenshot = before_screenshot.replace("data:image/png;base64,", "")

        # Execute the actual tool
        tool_result = await handler(request)

        # 📸 Take screenshot AFTER action
        print(f"📸 [Middleware] Taking AFTER screenshot for {tool_name}")
        await asyncio.sleep(1)  # Wait for UI to update
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/screenshot") as response:
                after_data = await response.json()
                after_screenshot = after_data.get("image", "")

        # Clean base64 prefix if present
        if after_screenshot.startswith("data:image/png;base64,"):
            after_screenshot = after_screenshot.replace("data:image/png;base64,", "")

        # Get the tool's text result
        if isinstance(tool_result, ToolMessage):
            tool_text = tool_result.content
            tool_call_id = tool_result.tool_call_id
        else:
            tool_text = str(tool_result)
            tool_call_id = request.tool_call.get('id', '')

        # Return ToolMessage with multimodal content: text + before/after screenshots
        print(f"✅ [Middleware] Returning before/after screenshots for {tool_name}")
        return ToolMessage(
            content=[
                {
                    "type": "text",
                    "text": f"{tool_text}\n\n📸 VISUAL VERIFICATION: Compare the before/after screenshots to confirm the action succeeded."
                },
                {
                    "type": "image",
                    "source_type": "base64",
                    "data": before_screenshot,
                    "mime_type": "image/png"
                },
                {
                    "type": "text",
                    "text": "⬆️ BEFORE | AFTER ⬇️"
                },
                {
                    "type": "image",
                    "source_type": "base64",
                    "data": after_screenshot,
                    "mime_type": "image/png"
                }
            ],
            tool_call_id=tool_call_id
        )

    except Exception as e:
        print(f"❌ [Middleware] Screenshot protocol failed: {e}")
        # Fall back to normal tool execution if screenshots fail
        return await handler(request)
