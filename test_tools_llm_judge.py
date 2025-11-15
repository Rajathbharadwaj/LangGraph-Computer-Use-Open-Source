"""
LLM-as-a-Judge Evaluation for X Growth Tools

This script:
1. Creates a LangSmith dataset with test cases for all X tools
2. Runs the agent on each test case
3. Uses Claude as a judge to evaluate if tools executed successfully
4. Tracks results in LangSmith for analysis
"""

import asyncio
from langsmith import Client, aevaluate
from langsmith.schemas import Example, Run
from langgraph_sdk import get_client as get_langgraph_client
from langchain_anthropic import ChatAnthropic

# Configuration
LANGGRAPH_URL = "http://localhost:8124"
GRAPH_NAME = "x_growth_deep_agent"
USER_ID = "test_llm_judge"
DATASET_NAME = "x_growth_tools_test_dataset"

# Initialize clients
ls_client = Client()
judge_llm = ChatAnthropic(model="claude-sonnet-4-5-20250929")


# ============================================================================
# STEP 1: Create Dataset with Test Cases
# ============================================================================

async def create_test_dataset():
    """Create a dataset with test cases for all X automation tools"""

    # Delete existing dataset if it exists
    try:
        ls_client.delete_dataset(dataset_name=DATASET_NAME)
        print(f"Deleted existing dataset: {DATASET_NAME}")
    except:
        pass

    # Create new dataset
    dataset = ls_client.create_dataset(
        dataset_name=DATASET_NAME,
        description="Test cases for X growth automation tools"
    )

    # Define test cases
    test_cases = [
        {
            "inputs": {
                "task": "Comment 'Great insights! 🚀' on @elonmusk's latest post about AI"
            },
            "outputs": {
                "expected_tool": "comment_on_post",
                "expected_behavior": "Should call comment_on_post tool and successfully post a comment"
            }
        },
        {
            "inputs": {
                "task": "Create a post about how AI is transforming software development"
            },
            "outputs": {
                "expected_tool": "create_post_on_x",
                "expected_behavior": "Should call create_post_on_x tool and successfully create a post"
            }
        },
        {
            "inputs": {
                "task": "Like @sama's latest post"
            },
            "outputs": {
                "expected_tool": "like_post",
                "expected_behavior": "Should call like_post tool and successfully like the post"
            }
        },
        {
            "inputs": {
                "task": "Unlike @sama's post that I just liked"
            },
            "outputs": {
                "expected_tool": "unlike_post",
                "expected_behavior": "Should call unlike_post tool and successfully unlike the post"
            }
        },
        {
            "inputs": {
                "task": "Comment on @ylecun's latest post with a thoughtful response"
            },
            "outputs": {
                "expected_tool": "comment_on_post",
                "expected_behavior": "Should call comment_on_post tool and successfully post a comment"
            }
        },
        {
            "inputs": {
                "task": "Post about the benefits of open source AI models"
            },
            "outputs": {
                "expected_tool": "create_post_on_x",
                "expected_behavior": "Should call create_post_on_x tool and successfully create a post"
            }
        },
    ]

    # Add examples to dataset
    for test_case in test_cases:
        ls_client.create_example(
            dataset_id=dataset.id,
            inputs=test_case["inputs"],
            outputs=test_case["outputs"]
        )

    print(f"✅ Created dataset '{DATASET_NAME}' with {len(test_cases)} test cases")
    return dataset


# ============================================================================
# STEP 2: Define Target Function (runs the agent)
# ============================================================================

async def run_agent_on_task(inputs: dict) -> dict:
    """
    Target function that runs the agent on a task.
    This is what gets evaluated.
    """
    task = inputs["task"]

    # Get LangGraph client
    client = get_langgraph_client(url=LANGGRAPH_URL)

    # Create a thread
    thread = await client.threads.create()
    thread_id = thread["thread_id"]

    # Run the agent
    all_messages = []
    async for chunk in client.runs.stream(
        thread_id,
        GRAPH_NAME,
        input={"messages": [{"role": "user", "content": task}]},
        config={"configurable": {"user_id": USER_ID}},
        stream_mode=["messages"]
    ):
        if hasattr(chunk, 'data'):
            if isinstance(chunk.data, list):
                all_messages.extend(chunk.data)

    # Get final state to extract tool calls
    state = await client.threads.get_state(thread_id)
    messages = state.get('values', {}).get('messages', [])

    # Extract tool calls and results
    tool_calls = []
    for msg in messages:
        if isinstance(msg, dict):
            if msg.get('type') == 'tool':
                tool_calls.append({
                    'tool_name': msg.get('name'),
                    'output': str(msg.get('content', ''))
                })

    return {
        "tool_calls": tool_calls,
        "all_messages": messages
    }


# ============================================================================
# STEP 3: Define LLM-as-Judge Evaluators
# ============================================================================

async def tool_execution_judge(run: Run, example: Example) -> dict:
    """
    LLM-as-a-judge evaluator that checks if the tool executed successfully.

    Returns:
        - score: 1 if tool executed successfully, 0 if failed
        - comment: Explanation from the judge
    """

    # Get the expected tool from the example
    expected_tool = example.outputs.get("expected_tool")
    expected_behavior = example.outputs.get("expected_behavior")

    # Get the actual outputs from the run
    tool_calls = run.outputs.get("tool_calls", [])

    # Prepare context for the judge
    tool_calls_summary = "\n".join([
        f"- Tool: {tc['tool_name']}\n  Output: {tc['output'][:500]}"
        for tc in tool_calls
    ])

    if not tool_calls_summary:
        tool_calls_summary = "No tool calls found"

    # Judge prompt
    judge_instructions = f"""You are evaluating an AI agent's tool execution.

EXPECTED BEHAVIOR:
{expected_behavior}

EXPECTED TOOL:
{expected_tool}

ACTUAL TOOL CALLS:
{tool_calls_summary}

EVALUATION CRITERIA:
1. Did the agent call the expected tool ({expected_tool})?
2. Did the tool execution appear successful based on the output?
3. Look for success indicators: "successfully", "✅", specific confirmation messages
4. Look for failure indicators: "failed", "error", "unable to", "❌"

Respond with ONLY:
- "1" if the tool executed successfully
- "0" if the tool failed or wasn't called
- Then on a new line, provide a brief explanation
"""

    # Run the judge
    response = await judge_llm.ainvoke([
        {"role": "user", "content": judge_instructions}
    ])

    # Parse response
    response_text = response.content.strip()
    lines = response_text.split('\n', 1)

    try:
        score = int(lines[0].strip())
        comment = lines[1].strip() if len(lines) > 1 else "No explanation provided"
    except:
        score = 0
        comment = f"Failed to parse judge response: {response_text}"

    return {
        "key": "tool_execution_success",
        "score": score,
        "comment": comment
    }


async def correct_tool_called_judge(run: Run, example: Example) -> dict:
    """
    LLM-as-a-judge evaluator that checks if the correct tool was called.
    """

    expected_tool = example.outputs.get("expected_tool")
    tool_calls = run.outputs.get("tool_calls", [])

    # Check if the expected tool was called
    called_tools = [tc['tool_name'] for tc in tool_calls]

    # Handle styled versions of tools
    expected_tools_variants = [
        expected_tool,
        f"_styled_{expected_tool}"
    ]

    correct_tool_called = any(
        tool in called_tools for tool in expected_tools_variants
    )

    if correct_tool_called:
        score = 1
        comment = f"✅ Correct tool called: {expected_tool}"
    else:
        score = 0
        comment = f"❌ Expected {expected_tool}, but got: {', '.join(called_tools) if called_tools else 'no tools'}"

    return {
        "key": "correct_tool_called",
        "score": score,
        "comment": comment
    }


# ============================================================================
# STEP 4: Run Evaluation
# ============================================================================

async def run_evaluation():
    """Run the LLM-as-judge evaluation on all test cases"""

    print("\n" + "="*80)
    print("LLM-AS-A-JUDGE EVALUATION FOR X GROWTH TOOLS")
    print("="*80)

    # Create dataset
    print("\n📊 Creating test dataset...")
    dataset = await create_test_dataset()

    # Run evaluation
    print("\n🧪 Running evaluation with LLM-as-judge...")
    print("This will:")
    print("  1. Run the agent on each test case")
    print("  2. Use Claude as a judge to evaluate tool execution")
    print("  3. Track all results in LangSmith")
    print("\nThis may take a few minutes...\n")

    results = await aevaluate(
        run_agent_on_task,  # Target function
        data=DATASET_NAME,  # Dataset to evaluate on
        evaluators=[
            correct_tool_called_judge,  # Check if correct tool was called
            tool_execution_judge,  # Check if tool executed successfully (LLM judge)
        ],
        experiment_prefix="x-tools-llm-judge",  # Experiment name prefix
        max_concurrency=1,  # Run one at a time to avoid conflicts
    )

    print("\n" + "="*80)
    print("✅ EVALUATION COMPLETE!")
    print("="*80)
    print(f"\n📊 Results available in LangSmith:")
    print(f"   https://smith.langchain.com/")
    print(f"\n📁 Dataset: {DATASET_NAME}")
    print(f"🧪 Experiment: x-tools-llm-judge")

    # Print summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    return results


# ============================================================================
# Main
# ============================================================================

async def main():
    """Main entry point"""
    try:
        results = await run_evaluation()
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
