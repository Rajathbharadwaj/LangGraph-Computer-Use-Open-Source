---
name: x-agent-workflow
description: Create and modify X growth workflows and subagents. Use when adding new automations, workflows, engagement flows, or extending the deep agent capabilities. Triggers on "create workflow", "add automation", "new subagent", "engagement flow".
allowed-tools: Read, Grep, Glob, Edit, Write
---

# X Growth Workflow Development

## Architecture Overview

This project uses an **atomic subagent pattern**:
- **Main Agent** (`x_growth_deep_agent.py`) - Orchestrates and plans
- **Subagents** - Execute ONE atomic action each
- **Workflows** - Deterministic sequences that delegate to subagents

## Key Files

| File | Purpose |
|------|---------|
| `x_growth_deep_agent.py` | Main orchestrator (35K+ tokens) |
| `x_growth_workflows.py` | Workflow definitions |
| `async_playwright_tools.py` | Browser automation tools (36+ tools) |
| `async_extension_tools.py` | Chrome extension tools |

## Creating a New Workflow

### Step 1: Define Workflow in `x_growth_workflows.py`

```python
class YourNewWorkflow:
    """Description of what this workflow does."""

    name = "your_workflow_name"
    description = "When to use this workflow"

    steps = [
        WorkflowStep(
            name="step_1",
            action="search_posts",
            params={"query": "{topic}"}
        ),
        WorkflowStep(
            name="step_2",
            action="engage_with_post",
            params={"post_url": "{step_1.result.url}"}
        ),
    ]
```

### Step 2: Register in AVAILABLE_WORKFLOWS

```python
AVAILABLE_WORKFLOWS = {
    # ... existing workflows
    "your_workflow": YourNewWorkflow,
}
```

### Step 3: Add Subagent if Needed

Subagents should:
- Do ONE thing only (atomic action)
- Return structured result
- Handle errors gracefully

```python
async def your_subagent(state: AgentState) -> AgentState:
    """Execute single atomic action."""
    # 1. Get required context
    # 2. Execute ONE action
    # 3. Return result in state
    return state
```

## Existing Workflows

1. **Engagement Workflow** - Like + comment on posts
2. **Reply Thread Workflow** - Reply to viral threads
3. **Profile Engagement** - Target specific user content
4. **Content Posting** - Original content creation
5. **DM Outreach** - Direct messaging strategy

## Memory Integration

Workflows can access:
- `x_user_memory.py` - User preferences and history
- `x_writing_style_learner.py` - Writing style analysis
- `competitor_content_analyzer.py` - Competitor insights

## Best Practices

1. **Atomic Actions**: Each subagent does ONE thing
2. **Deterministic**: Workflows should be predictable
3. **Monitorable**: Log all actions for activity feed
4. **Recoverable**: Handle failures gracefully
5. **Credit-Aware**: Check user credits before expensive operations
