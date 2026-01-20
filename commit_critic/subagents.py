"""
Atomic subagents for Commit Critic.

Each subagent executes ONE atomic action:
- fetch_commits: Get commits from a repository
- analyze_commits: Score and categorize commit messages
- get_staged_changes: Get git diff --staged
- suggest_commit_message: Generate a commit message from diff
- execute_commit: Run git commit

Following the same pattern as ads_agent/subagents.py.
"""

from .prompts import (
    FETCH_COMMITS_PROMPT,
    ANALYZE_COMMITS_PROMPT,
    GET_STAGED_PROMPT,
    SUGGEST_COMMIT_PROMPT,
    EXECUTE_COMMIT_PROMPT,
    get_date_context,
)
from .tools import (
    get_commits_tool,
    clone_repo_tool,
    get_staged_diff_tool,
    create_commit_tool,
)


def get_commit_critic_subagents():
    """
    Get atomic subagents for commit critic operations.

    Each subagent is a dict with:
    - name: Identifier for task() calls
    - description: What the subagent does (shown to main agent)
    - system_prompt: Instructions for the subagent
    - tools: List of tools the subagent can use

    Returns:
        List of subagent definitions
    """
    date_context = get_date_context()

    subagents = [
        # =====================================================================
        # FETCH COMMITS
        # =====================================================================
        {
            "name": "fetch_commits",
            "description": """Fetch recent commits from a git repository.

Input: Repository path (local) or URL (remote)
Output: JSON list of commits with hash, message, and body

For remote URLs, clones the repo first (shallow clone, depth=50).""",
            "system_prompt": FETCH_COMMITS_PROMPT + f"\n\n{date_context}",
            "tools": [get_commits_tool, clone_repo_tool],
        },
        # =====================================================================
        # ANALYZE COMMITS
        # =====================================================================
        {
            "name": "analyze_commits",
            "description": """Analyze commit messages and score them 1-10.

Input: List of commits (hash + message + body)
Output: JSON array of analysis results with:
- score (1-10)
- category (needs_work, acceptable, excellent)
- issue (what's wrong, for bad commits)
- suggestion (better message, for bad commits)
- why_good (explanation, for excellent commits)

Scoring criteria: clarity, context, format, scope.""",
            "system_prompt": ANALYZE_COMMITS_PROMPT + f"\n\n{date_context}",
            "tools": [],  # Pure LLM analysis - no tools needed
        },
        # =====================================================================
        # GET STAGED CHANGES
        # =====================================================================
        {
            "name": "get_staged_changes",
            "description": """Get staged changes (git diff --staged) for commit writing.

Input: Repository path (default: current directory)
Output: JSON with:
- has_staged: Boolean
- stat: Summary of changes
- diff: Full diff content
- files: List of changed files

Returns message if no staged changes found.""",
            "system_prompt": GET_STAGED_PROMPT + f"\n\n{date_context}",
            "tools": [get_staged_diff_tool],
        },
        # =====================================================================
        # SUGGEST COMMIT MESSAGE
        # =====================================================================
        {
            "name": "suggest_commit_message",
            "description": """Generate a well-formatted commit message from diff.

Input: Staged diff content (from get_staged_changes)
Output: JSON with:
- type: feat, fix, refactor, docs, test, chore
- scope: Affected area (api, auth, ui, etc.)
- subject: Short description (max 50 chars)
- body: Detailed explanation (optional)
- full_message: Complete formatted commit message

Follows conventional commits format.""",
            "system_prompt": SUGGEST_COMMIT_PROMPT + f"\n\n{date_context}",
            "tools": [],  # Pure LLM generation - no tools needed
        },
        # =====================================================================
        # EXECUTE COMMIT
        # =====================================================================
        {
            "name": "execute_commit",
            "description": """Execute git commit with the approved message.

CRITICAL: Only call after user has explicitly approved!

Input: Commit message (full formatted message)
Output: JSON with success status and commit output

This actually creates the commit - use with care.""",
            "system_prompt": EXECUTE_COMMIT_PROMPT + f"\n\n{date_context}",
            "tools": [create_commit_tool],
        },
    ]

    return subagents


def get_subagent_names():
    """Get list of available subagent names for documentation."""
    return [
        "fetch_commits",
        "analyze_commits",
        "get_staged_changes",
        "suggest_commit_message",
        "execute_commit",
    ]
