# LLM-as-a-Judge Evaluation Guide

## Overview

This guide explains how to use the LLM-as-a-judge evaluation system to test your X growth automation tools.

## What is LLM-as-a-Judge?

Instead of hardcoding success/failure checks, we use Claude (Sonnet 4.5) to intelligently evaluate whether each tool executed successfully by analyzing:
- Tool outputs
- Success/failure indicators
- Expected behavior vs actual behavior

## Files

- `test_tools_llm_judge.py` - Main evaluation script with LLM judge
- Dataset: `x_growth_tools_test_dataset` (created automatically)
- Results tracked in LangSmith

## How to Run

```bash
python test_tools_llm_judge.py
```

This will:
1. Create a dataset with 6 test cases (2 comments, 2 posts, 1 like, 1 unlike)
2. Run your agent on each test case
3. Use Claude to judge if tools executed successfully
4. Track everything in LangSmith

## Evaluation Criteria

### 1. Correct Tool Called (Deterministic)
- Checks if the agent called the expected tool
- Score: 1 (correct) or 0 (wrong tool)
- Handles both `comment_on_post` and `_styled_comment_on_post`

### 2. Tool Execution Success (LLM Judge)
- Claude analyzes the tool output
- Looks for success indicators:
  - "successfully"
  - "✅"
  - Specific confirmation messages
- Looks for failure indicators:
  - "failed"
  - "error"
  - "unable to"
  - "❌"
- Score: 1 (success) or 0 (failed)
- Provides explanation for each score

## Viewing Results

After running the evaluation:

1. **LangSmith UI**: Go to https://smith.langchain.com/
2. **Navigate to**: Datasets → `x_growth_tools_test_dataset`
3. **View experiments**: Click on the latest `x-tools-llm-judge` experiment
4. **Analyze**:
   - Overall pass/fail rates
   - Individual test case results
   - Judge explanations for each evaluation
   - Tool execution traces

## Adding More Test Cases

Edit `test_tools_llm_judge.py` and add to the `test_cases` list:

```python
{
    "inputs": {
        "task": "Your test task here"
    },
    "outputs": {
        "expected_tool": "tool_name",
        "expected_behavior": "Description of expected behavior"
    }
}
```

## Benefits of LLM-as-Judge

1. **Flexible**: Adapts to different output formats
2. **Intelligent**: Understands context and nuance
3. **Explainable**: Provides reasoning for each score
4. **No hardcoding**: Works even if output format changes
5. **Tracked**: All evaluations logged in LangSmith for analysis

## Next Steps

1. Review the evaluation results in LangSmith
2. Fix any failing tools
3. Re-run evaluation to verify fixes
4. Set up CI/CD to run evaluations automatically
5. Add more test cases to improve coverage

## Online Evaluators

You already have online evaluators set up that run in real-time on production traces. The LLM-as-judge system complements these by providing:
- Batch evaluation across test datasets
- More detailed analysis with LLM reasoning
- Systematic testing before production deployment
