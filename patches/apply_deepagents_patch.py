#!/usr/bin/env python3
"""
Apply patch to deepagents to forward config to subagents.
This ensures ToolRuntime config (e.g., cua_url) is passed to subagent tools.
"""
import site
import os

def apply_patch():
    # Find deepagents installation
    for sp in site.getsitepackages():
        subagents_path = os.path.join(sp, "deepagents", "middleware", "subagents.py")
        if os.path.exists(subagents_path):
            print(f"Found deepagents at: {subagents_path}")

            with open(subagents_path, 'r') as f:
                content = f.read()

            # Check if already patched
            if "config=runtime.config" in content:
                print("Already patched, skipping...")
                return True

            # Apply patch - sync version
            old_sync = "result = subagent.invoke(subagent_state)"
            new_sync = "# Forward config to subagent so tools receive runtime context (e.g., cua_url)\n        result = subagent.invoke(subagent_state, config=runtime.config)"

            if old_sync in content:
                content = content.replace(old_sync, new_sync)
                print("Patched sync invoke")
            else:
                print("WARNING: Could not find sync invoke pattern to patch")

            # Apply patch - async version
            old_async = "result = await subagent.ainvoke(subagent_state)"
            new_async = "# Forward config to subagent so tools receive runtime context (e.g., cua_url)\n        result = await subagent.ainvoke(subagent_state, config=runtime.config)"

            if old_async in content:
                content = content.replace(old_async, new_async)
                print("Patched async ainvoke")
            else:
                print("WARNING: Could not find async ainvoke pattern to patch")

            with open(subagents_path, 'w') as f:
                f.write(content)

            print("Patch applied successfully!")
            return True

    print("ERROR: Could not find deepagents installation")
    return False

if __name__ == "__main__":
    apply_patch()
