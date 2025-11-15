"""
Setup LangSmith Online Evaluators for X Growth Tools

This script creates custom code evaluators to monitor tool performance:
- comment_on_post success/failure
- create_post_on_x success/failure
- like_post success/failure
- unlike_post success/failure

Run this once to set up evaluators in your LangSmith project.
"""

import os
from langsmith import Client

# Initialize LangSmith client
client = Client()

# Your tracing project name (update if different)
PROJECT_NAME = "x_growth_deep_agent"


def create_comment_evaluator():
    """Evaluator to check if comment_on_post tool succeeded"""

    evaluator_code = """
import json

def perform_eval(run):
    '''Check if comment_on_post tool succeeded'''

    # Check if this run called the comment_on_post tool
    if run.get('run_type') != 'tool':
        return None

    if run.get('name') != 'comment_on_post' and run.get('name') != '_styled_comment_on_post':
        return None

    # Get the tool output
    outputs = run.get('outputs', {})
    output_text = str(outputs)

    # Success indicators
    success_keywords = [
        'successfully posted',
        'comment posted',
        'commented successfully',
        '✅'
    ]

    # Failure indicators
    failure_keywords = [
        'failed',
        'error',
        'could not',
        'unable to',
        '❌'
    ]

    # Check for success
    has_success = any(keyword.lower() in output_text.lower() for keyword in success_keywords)
    has_failure = any(keyword.lower() in output_text.lower() for keyword in failure_keywords)

    if has_failure:
        return {"comment_success": 0, "comment_working": False}
    elif has_success:
        return {"comment_success": 1, "comment_working": True}
    else:
        # Unclear - might need human review
        return {"comment_success": 0.5, "comment_working": None}
"""

    print("Creating comment_on_post evaluator...")
    # Note: This is pseudocode - you'll need to create this via LangSmith UI
    # or use the LangSmith SDK when available
    print(f"Evaluator code:\n{evaluator_code}")
    return evaluator_code


def create_post_evaluator():
    """Evaluator to check if create_post_on_x tool succeeded"""

    evaluator_code = """
import json

def perform_eval(run):
    '''Check if create_post_on_x tool succeeded'''

    # Check if this run called the create_post_on_x tool
    if run.get('run_type') != 'tool':
        return None

    if run.get('name') != 'create_post_on_x' and run.get('name') != '_styled_create_post_on_x':
        return None

    # Get the tool output
    outputs = run.get('outputs', {})
    output_text = str(outputs)

    # Success indicators
    success_keywords = [
        'successfully posted',
        'post created',
        'posted successfully',
        '✅'
    ]

    # Failure indicators
    failure_keywords = [
        'failed',
        'error',
        'could not',
        'unable to',
        '❌'
    ]

    # Check for success
    has_success = any(keyword.lower() in output_text.lower() for keyword in success_keywords)
    has_failure = any(keyword.lower() in output_text.lower() for keyword in failure_keywords)

    if has_failure:
        return {"post_success": 0, "post_working": False}
    elif has_success:
        return {"post_success": 1, "post_working": True}
    else:
        return {"post_success": 0.5, "post_working": None}
"""

    print("Creating create_post_on_x evaluator...")
    print(f"Evaluator code:\n{evaluator_code}")
    return evaluator_code


def create_like_evaluator():
    """Evaluator to check if like_post tool succeeded"""

    evaluator_code = """
import json

def perform_eval(run):
    '''Check if like_post tool succeeded'''

    # Check if this run called the like_post tool
    if run.get('run_type') != 'tool':
        return None

    if run.get('name') != 'like_post':
        return None

    # Get the tool output
    outputs = run.get('outputs', {})
    output_text = str(outputs)

    # Success indicators
    success_keywords = [
        'successfully liked',
        'liked post',
        'like successful',
        '✅',
        '❤️'
    ]

    # Failure indicators
    failure_keywords = [
        'failed',
        'error',
        'could not',
        'unable to',
        'already liked',
        '❌'
    ]

    # Check for success
    has_success = any(keyword.lower() in output_text.lower() for keyword in success_keywords)
    has_failure = any(keyword.lower() in output_text.lower() for keyword in failure_keywords)

    if has_failure:
        return {"like_success": 0, "like_working": False}
    elif has_success:
        return {"like_success": 1, "like_working": True}
    else:
        return {"like_success": 0.5, "like_working": None}
"""

    print("Creating like_post evaluator...")
    print(f"Evaluator code:\n{evaluator_code}")
    return evaluator_code


def create_unlike_evaluator():
    """Evaluator to check if unlike_post tool succeeded"""

    evaluator_code = """
import json

def perform_eval(run):
    '''Check if unlike_post tool succeeded'''

    # Check if this run called the unlike_post tool
    if run.get('run_type') != 'tool':
        return None

    if run.get('name') != 'unlike_post':
        return None

    # Get the tool output
    outputs = run.get('outputs', {})
    output_text = str(outputs)

    # Success indicators
    success_keywords = [
        'successfully unliked',
        'unliked post',
        'unlike successful',
        '✅'
    ]

    # Failure indicators
    failure_keywords = [
        'failed',
        'error',
        'could not',
        'unable to',
        'not liked',
        '❌'
    ]

    # Check for success
    has_success = any(keyword.lower() in output_text.lower() for keyword in success_keywords)
    has_failure = any(keyword.lower() in output_text.lower() for keyword in failure_keywords)

    if has_failure:
        return {"unlike_success": 0, "unlike_working": False}
    elif has_success:
        return {"unlike_success": 1, "unlike_working": True}
    else:
        return {"unlike_success": 0.5, "unlike_working": None}
"""

    print("Creating unlike_post evaluator...")
    print(f"Evaluator code:\n{evaluator_code}")
    return evaluator_code


def print_setup_instructions():
    """Print instructions for setting up evaluators in LangSmith UI"""

    print("\n" + "="*80)
    print("SETUP INSTRUCTIONS FOR LANGSMITH ONLINE EVALUATORS")
    print("="*80)
    print()
    print("To set up these evaluators in LangSmith:")
    print()
    print("1. Go to https://smith.langchain.com/")
    print(f"2. Navigate to your '{PROJECT_NAME}' tracing project")
    print("3. Click '+ New' → 'New Evaluator'")
    print("4. Select 'Custom Code' evaluator")
    print()
    print("For each evaluator (comment, post, like, unlike):")
    print()
    print("5. Name the evaluator (e.g., 'comment_on_post_success')")
    print()
    print("6. Add a filter to only evaluate that specific tool:")
    print("   - Click 'Add filter'")
    print("   - Select 'Name' (or 'Run Type')")
    print("   - Set to 'equals' and enter the tool name")
    print("   Examples:")
    print("     • comment_on_post or _styled_comment_on_post")
    print("     • create_post_on_x or _styled_create_post_on_x")
    print("     • like_post")
    print("     • unlike_post")
    print()
    print("7. Copy the evaluator code from above")
    print()
    print("8. (Optional) Set sampling rate to 1.0 to evaluate all tool calls")
    print()
    print("9. (Optional) Enable 'Apply to past runs' to backfill")
    print()
    print("10. Click 'Test Code' on a recent run to verify")
    print()
    print("11. Click 'Save' to activate the evaluator")
    print()
    print("="*80)
    print()
    print("MONITORING YOUR TOOLS:")
    print("="*80)
    print()
    print("After setup, you can monitor tool performance by:")
    print()
    print("• Viewing feedback in the 'Feedback' tab of each run")
    print("• Creating dashboards to track success rates over time")
    print("• Setting up alerts when success rates drop below threshold")
    print()
    print("Example queries:")
    print("  - Filter by 'Feedback: comment_success = 1' to see successful comments")
    print("  - Filter by 'Feedback: post_working = false' to debug failures")
    print()
    print("="*80)


if __name__ == "__main__":
    print("Setting up X Growth Tool Evaluators for LangSmith...\n")

    # Generate evaluator code
    evaluators = {
        "comment_on_post": create_comment_evaluator(),
        "create_post_on_x": create_post_evaluator(),
        "like_post": create_like_evaluator(),
        "unlike_post": create_unlike_evaluator(),
    }

    # Print setup instructions
    print_setup_instructions()

    # Save evaluator code to files for reference
    for name, code in evaluators.items():
        filename = f"evaluator_{name}.py"
        with open(filename, 'w') as f:
            f.write(code)
        print(f"✅ Saved {filename}")

    print()
    print("Next steps:")
    print("1. Go to LangSmith UI at https://smith.langchain.com/")
    print("2. Follow the instructions above to create each evaluator")
    print("3. Test your tools and watch the feedback appear in real-time!")
