"""
X Growth Workflows - Deterministic Action Sequences

Each workflow is a pre-defined sequence of atomic actions for a specific goal.
The DeepAgent selects the workflow and orchestrates execution via subagents.

Available Workflows:
1. engagement_workflow - Find and engage with posts (likes + comments)
2. reply_to_thread_workflow - Find a viral thread and reply to comments
3. profile_engagement_workflow - Engage with a specific user's content
4. content_posting_workflow - Create and post original content
5. dm_outreach_workflow - Send DMs to potential connections
"""

from typing import Dict, List, Any
from dataclasses import dataclass


@dataclass
class WorkflowStep:
    """A single step in a workflow"""
    subagent: str  # Which subagent to call
    action: str  # What to tell the subagent
    description: str  # Human-readable description
    check_memory: bool = False  # Should check action_history.json first?
    update_memory: bool = False  # Should update action_history.json after?


class Workflow:
    """Base class for all workflows"""
    
    def __init__(self, name: str, goal: str, steps: List[WorkflowStep]):
        self.name = name
        self.goal = goal
        self.steps = steps
    
    def to_prompt(self) -> str:
        """Convert workflow to a prompt for the DeepAgent"""
        prompt = f"""
WORKFLOW: {self.name}
GOAL: {self.goal}

STEPS TO EXECUTE:
"""
        for i, step in enumerate(self.steps, 1):
            prompt += f"\n{i}. {step.description}"
            prompt += f"\n   → Delegate to: task('{step.subagent}', '{step.action}')"
            if step.check_memory:
                prompt += "\n   → Check action_history.json BEFORE this step"
            if step.update_memory:
                prompt += "\n   → Update action_history.json AFTER this step"
        
        return prompt


# ============================================================================
# WORKFLOW 1: ENGAGEMENT (Like + Comment on Posts)
# ============================================================================

ENGAGEMENT_WORKFLOW = Workflow(
    name="engagement_workflow",
    goal="Engage with posts from the home timeline. X's algorithm already shows relevant content from your network.",
    steps=[
        WorkflowStep(
            subagent="navigate",
            action="Go to https://x.com/home",
            description="Navigate to home timeline (X's algorithm shows relevant content)"
        ),
        WorkflowStep(
            subagent="analyze_page",
            action="Analyze the home timeline to see what posts are visible",
            description="Get comprehensive context of home timeline posts"
        ),
        WorkflowStep(
            subagent="scroll",
            action="Scroll down to load more posts",
            description="Load additional posts from timeline"
        ),
        WorkflowStep(
            subagent="analyze_page",
            action="Analyze updated timeline with more posts",
            description="Get comprehensive context after scrolling",
            check_memory=True  # Check what we've already engaged with
        ),
        # Now engage with posts - ONLY like posts that are comment-worthy
        # Analyze tone/intent DEEPLY using extended thinking, then engage ONLY if truly worthwhile
        WorkflowStep(
            subagent="like_and_comment",
            action="Analyze post tone/intent deeply using extended thinking, then engage ONLY if truly worthwhile",
            description="Analyze + Engage post #1 (tone-aware, skips spam/sarcasm)",
            check_memory=True,
            update_memory=True
        ),
        WorkflowStep(
            subagent="like_and_comment",
            action="Analyze post tone/intent deeply using extended thinking, then engage ONLY if truly worthwhile",
            description="Analyze + Engage post #2 (tone-aware, skips spam/sarcasm)",
            check_memory=True,
            update_memory=True
        ),
        WorkflowStep(
            subagent="like_and_comment",
            action="Analyze post tone/intent deeply using extended thinking, then engage ONLY if truly worthwhile",
            description="Analyze + Engage post #3 (tone-aware, skips spam/sarcasm)",
            check_memory=True,
            update_memory=True
        ),
        WorkflowStep(
            subagent="like_and_comment",
            action="Analyze post tone/intent deeply using extended thinking, then engage ONLY if truly worthwhile",
            description="Analyze + Engage post #4 (tone-aware, skips spam/sarcasm)",
            check_memory=True,
            update_memory=True
        ),
        WorkflowStep(
            subagent="like_and_comment",
            action="Analyze post tone/intent deeply using extended thinking, then engage ONLY if truly worthwhile",
            description="Analyze + Engage post #5 (tone-aware, skips spam/sarcasm)",
            check_memory=True,
            update_memory=True
        ),
    ]
)


# ============================================================================
# WORKFLOW 2: REPLY TO THREAD (Engage in Conversations)
# ============================================================================

REPLY_TO_THREAD_WORKFLOW = Workflow(
    name="reply_to_thread_workflow",
    goal="Find a viral thread and reply to interesting comments",
    steps=[
        WorkflowStep(
            subagent="navigate",
            action="Go to X home feed",
            description="Navigate to home feed to find viral threads"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot to see trending posts",
            description="Capture home feed"
        ),
        WorkflowStep(
            subagent="scroll",
            action="Scroll to find viral threads (high engagement)",
            description="Find viral content"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot of viral thread",
            description="Capture viral thread"
        ),
        WorkflowStep(
            subagent="click",
            action="Click on the viral thread to open it",
            description="Open thread"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot of thread replies",
            description="See all replies"
        ),
        WorkflowStep(
            subagent="scroll",
            action="Scroll through replies to find good ones",
            description="Browse replies"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot of interesting replies",
            description="Identify reply targets",
            check_memory=True
        ),
        # Reply to 3 interesting comments
        WorkflowStep(
            subagent="comment_on_post",
            action="Reply to first interesting comment with value-add insight",
            description="Reply to comment #1",
            check_memory=True,
            update_memory=True
        ),
        WorkflowStep(
            subagent="comment_on_post",
            action="Reply to second interesting comment with value-add insight",
            description="Reply to comment #2",
            check_memory=True,
            update_memory=True
        ),
        WorkflowStep(
            subagent="comment_on_post",
            action="Reply to third interesting comment with value-add insight",
            description="Reply to comment #3",
            check_memory=True,
            update_memory=True
        ),
    ]
)


# ============================================================================
# WORKFLOW 3: PROFILE ENGAGEMENT (Build Relationships)
# ============================================================================

PROFILE_ENGAGEMENT_WORKFLOW = Workflow(
    name="profile_engagement_workflow",
    goal="Visit a specific user's profile and engage with their content",
    steps=[
        WorkflowStep(
            subagent="navigate",
            action="Go to the user's profile URL",
            description="Navigate to target profile"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot of profile",
            description="See profile overview",
            check_memory=True  # Check if we've engaged with this user before
        ),
        WorkflowStep(
            subagent="scroll",
            action="Scroll to see recent posts",
            description="Load recent posts"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot of recent posts",
            description="Analyze recent content"
        ),
        # Engage with 3 best posts
        WorkflowStep(
            subagent="like_post",
            action="Like the most relevant/insightful post",
            description="Like best post",
            check_memory=True,
            update_memory=True
        ),
        WorkflowStep(
            subagent="like_post",
            action="Like the second most relevant post",
            description="Like second best post",
            check_memory=True,
            update_memory=True
        ),
        WorkflowStep(
            subagent="comment_on_post",
            action="Comment on the best post with thoughtful insight",
            description="Comment on best post",
            check_memory=True,
            update_memory=True
        ),
    ]
)


# ============================================================================
# WORKFLOW 4: CONTENT POSTING (Create Original Posts)
# ============================================================================

CONTENT_POSTING_WORKFLOW = Workflow(
    name="content_posting_workflow",
    goal="Create and post original content",
    steps=[
        WorkflowStep(
            subagent="navigate",
            action="Go to X home page",
            description="Navigate to home"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot to see compose box",
            description="Locate compose area"
        ),
        WorkflowStep(
            subagent="click",
            action="Click on 'What's happening?' compose box",
            description="Open compose box"
        ),
        WorkflowStep(
            subagent="type_text",
            action="Type the post content (generated by LLM)",
            description="Write post content"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot to verify post looks good",
            description="Preview post"
        ),
        WorkflowStep(
            subagent="click",
            action="Click 'Post' button",
            description="Publish post",
            update_memory=True
        ),
    ]
)


# ============================================================================
# WORKFLOW 5: DM OUTREACH (Build Connections)
# ============================================================================

DM_OUTREACH_WORKFLOW = Workflow(
    name="dm_outreach_workflow",
    goal="Send personalized DMs to potential connections",
    steps=[
        WorkflowStep(
            subagent="navigate",
            action="Go to target user's profile",
            description="Navigate to profile",
            check_memory=True  # Check if we've already DM'd this user
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot of profile",
            description="Analyze profile for personalization"
        ),
        WorkflowStep(
            subagent="click",
            action="Click 'Message' button",
            description="Open DM composer"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot of DM composer",
            description="See DM interface"
        ),
        WorkflowStep(
            subagent="type_text",
            action="Type personalized DM message",
            description="Write DM"
        ),
        WorkflowStep(
            subagent="screenshot",
            action="Take screenshot to verify message",
            description="Preview DM"
        ),
        WorkflowStep(
            subagent="click",
            action="Click 'Send' button",
            description="Send DM",
            update_memory=True
        ),
    ]
)


# ============================================================================
# WORKFLOW REGISTRY
# ============================================================================

WORKFLOWS: Dict[str, Workflow] = {
    "engagement": ENGAGEMENT_WORKFLOW,
    "reply_to_thread": REPLY_TO_THREAD_WORKFLOW,
    "profile_engagement": PROFILE_ENGAGEMENT_WORKFLOW,
    "content_posting": CONTENT_POSTING_WORKFLOW,
    "dm_outreach": DM_OUTREACH_WORKFLOW,
}


def get_workflow(goal: str) -> Workflow:
    """Get a workflow by goal name"""
    if goal not in WORKFLOWS:
        raise ValueError(f"Unknown workflow: {goal}. Available: {list(WORKFLOWS.keys())}")
    return WORKFLOWS[goal]


def list_workflows() -> List[str]:
    """List all available workflows"""
    return list(WORKFLOWS.keys())


def get_workflow_prompt(goal: str, **kwargs) -> str:
    """
    Get the full prompt for a workflow with parameters
    
    Args:
        goal: The workflow goal (e.g., 'engagement')
        **kwargs: Parameters for the workflow (e.g., keywords='AI agents', target_user='@elonmusk')
    
    Returns:
        Full prompt for the DeepAgent
    """
    workflow = get_workflow(goal)
    
    prompt = f"""
🎯 EXECUTE WORKFLOW: {workflow.name}

GOAL: {workflow.goal}

PARAMETERS:
"""
    for key, value in kwargs.items():
        prompt += f"- {key}: {value}\n"
    
    prompt += workflow.to_prompt()
    
    prompt += """

EXECUTION RULES:
1. Execute steps IN ORDER (do NOT skip or reorder)
2. Use task() to delegate each step to the appropriate subagent
3. Wait for subagent result before proceeding to next step
4. If check_memory=True, read action_history.json BEFORE the step
5. If update_memory=True, write to action_history.json AFTER the step
6. If a step fails, retry ONCE, then skip and continue
7. Take screenshots frequently to see what's on the page
8. Analyze screenshots before deciding on coordinates or actions

MEMORY CHECKS:
- ALWAYS check action_history.json before engaging (like/comment)
- NEVER engage with same post/user twice in 24 hours
- Track daily limits: 50 likes, 20 comments, 10 DMs

START EXECUTION NOW.
"""
    
    return prompt


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("📋 Available X Growth Workflows")
    print("=" * 60)
    
    for goal, workflow in WORKFLOWS.items():
        print(f"\n🎯 {goal}")
        print(f"   Goal: {workflow.goal}")
        print(f"   Steps: {len(workflow.steps)}")
    
    print("\n" + "=" * 60)
    print("📝 Example: Engagement Workflow Prompt")
    print("=" * 60)
    
    prompt = get_workflow_prompt(
        "engagement",
        keywords="AI agents",
        num_likes=5,
        num_comments=2
    )
    print(prompt)

