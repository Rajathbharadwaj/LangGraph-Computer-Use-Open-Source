"""
DeepAgents patch module - automatically applies patches when imported.
This patches deepagents to forward config to subagents.
"""
import site
import os
import sys

def apply_deepagents_patch():
    """Apply patch to deepagents to forward config to subagents."""
    # Find deepagents installation
    for sp in site.getsitepackages():
        subagents_path = os.path.join(sp, "deepagents", "middleware", "subagents.py")
        if os.path.exists(subagents_path):
            print(f"✅ Found deepagents at: {subagents_path}")

            with open(subagents_path, 'r') as f:
                content = f.read()

            # Check if already patched
            if "config=runtime.config" in content:
                print("✅ DeepAgents already patched, skipping...")
                return True

            # Apply patch - sync version
            old_sync = "result = subagent.invoke(subagent_state)"
            new_sync = "# Forward config to subagent so tools receive runtime context (e.g., cua_url)\n        result = subagent.invoke(subagent_state, config=runtime.config)"

            if old_sync in content:
                content = content.replace(old_sync, new_sync)
                print("✅ Patched sync invoke")
            else:
                print("⚠️  Could not find sync invoke pattern to patch")

            # Apply patch - async version
            old_async = "result = await subagent.ainvoke(subagent_state)"
            new_async = "# Forward config to subagent so tools receive runtime context (e.g., cua_url)\n        result = await subagent.ainvoke(subagent_state, config=runtime.config)"

            if old_async in content:
                content = content.replace(old_async, new_async)
                print("✅ Patched async ainvoke")
            else:
                print("⚠️  Could not find async ainvoke pattern to patch")

            # Write the patched content
            with open(subagents_path, 'w') as f:
                f.write(content)

            print("✅ DeepAgents patch applied successfully!")
            return True

    print("⚠️  Could not find deepagents installation to patch")
    return False

# Apply patch on import
try:
    apply_deepagents_patch()
except Exception as e:
    print(f"⚠️  Failed to apply deepagents patch: {e}")
    # Don't fail the import - just warn
    import traceback
    traceback.print_exc()
