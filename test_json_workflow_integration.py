"""
Test JSON Workflow Integration with Deep Agent

This script tests that the deep agent can properly load and execute JSON workflows.
"""

import asyncio
from x_growth_workflows import get_workflow_prompt


def test_json_workflow_loading():
    """Test loading a JSON workflow"""
    print("🧪 Test 1: Loading JSON workflow 'reply_guy_strategy'")
    print("="*80)

    prompt = get_workflow_prompt("reply_guy_strategy")

    assert prompt is not None, "Prompt should not be None"
    assert "Reply Guy Strategy" in prompt, "Prompt should contain workflow name"
    assert "engagement" in prompt, "Prompt should contain category"
    assert "viral threads" in prompt, "Prompt should contain description"
    assert "Configuration Parameters" in prompt, "Prompt should have config section"
    assert "Max Replies Per Session:** 5" in prompt, "Prompt should have config values"
    assert "Execution Strategy" in prompt, "Prompt should have strategy section"
    assert "Navigate:**" in prompt, "Prompt should have navigation step"
    assert "Execution Rules" in prompt, "Prompt should have execution rules"

    print("✅ JSON workflow loaded successfully!")
    print(f"\nPrompt preview (first 500 chars):\n{prompt[:500]}...")
    print("="*80)
    print()


def test_python_workflow_fallback():
    """Test that Python workflows still work as fallback"""
    print("🧪 Test 2: Loading Python workflow 'engagement' (fallback)")
    print("="*80)

    prompt = get_workflow_prompt("engagement")

    assert prompt is not None, "Prompt should not be None"
    assert "engagement_workflow" in prompt, "Prompt should contain workflow name"
    assert "EXECUTE WORKFLOW" in prompt, "Prompt should have workflow header"
    assert "STEPS TO EXECUTE" in prompt, "Prompt should have steps section"

    print("✅ Python workflow fallback works!")
    print(f"\nPrompt preview (first 500 chars):\n{prompt[:500]}...")
    print("="*80)
    print()


def test_all_json_workflows():
    """Test loading all JSON workflows"""
    print("🧪 Test 3: Loading ALL JSON workflows")
    print("="*80)

    workflow_ids = [
        "reply_guy_strategy",
        "follower_farming",
        "early_bird_special",
        "reciprocal_engagement",
        "learning_workflow"
    ]

    for workflow_id in workflow_ids:
        print(f"\n📋 Loading: {workflow_id}")
        prompt = get_workflow_prompt(workflow_id)
        assert prompt is not None, f"Failed to load {workflow_id}"
        assert len(prompt) > 100, f"Prompt for {workflow_id} is too short"
        print(f"   ✅ Loaded ({len(prompt)} chars)")

    print("\n✅ All JSON workflows loaded successfully!")
    print("="*80)
    print()


def test_workflow_with_params():
    """Test loading workflow with additional parameters"""
    print("🧪 Test 4: Loading JSON workflow with parameters")
    print("="*80)

    prompt = get_workflow_prompt("reply_guy_strategy", max_posts=10, target_topic="AI")

    assert "Additional Parameters" in prompt, "Should have parameters section"
    assert "Max Posts" in prompt or "max_posts" in prompt, "Should include max_posts"
    assert "Target Topic" in prompt or "target_topic" in prompt, "Should include target_topic"

    print("✅ Workflow with parameters works!")
    print(f"\nPrompt preview (showing parameters section):")
    # Find and show the parameters section
    lines = prompt.split('\n')
    for i, line in enumerate(lines):
        if 'Additional Parameters' in line:
            print('\n'.join(lines[i:i+5]))
            break
    print("="*80)
    print()


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print(" JSON WORKFLOW INTEGRATION TESTS ")
    print("="*80 + "\n")

    try:
        test_json_workflow_loading()
        test_python_workflow_fallback()
        test_all_json_workflows()
        test_workflow_with_params()

        print("\n" + "="*80)
        print(" ✅ ALL TESTS PASSED! ")
        print("="*80)
        print("\n🎉 JSON workflows are now integrated with the deep agent!")
        print("\nWhat this means:")
        print("- Frontend can send workflow IDs like 'reply_guy_strategy'")
        print("- Agent will load JSON workflow file and convert to prompt")
        print("- Agent will execute based on the natural language guidance")
        print("- Python workflows still work as fallback")
        print("\n" + "="*80 + "\n")

        return True

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
