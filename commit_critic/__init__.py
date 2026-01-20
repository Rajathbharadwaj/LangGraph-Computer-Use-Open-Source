"""
Commit Critic - AI-powered commit message analyzer using LangGraph Deep Agents.

A terminal tool that:
1. Analyzes Git commit history and scores message quality
2. Helps write better commits based on staged changes
"""

from .commit_critic_agent import create_commit_critic_agent
from .subagents import get_commit_critic_subagents
from .tools import (
    get_commits_tool,
    clone_repo_tool,
    get_staged_diff_tool,
    create_commit_tool,
    get_repo_info_tool,
)

__all__ = [
    "create_commit_critic_agent",
    "get_commit_critic_subagents",
    "get_commits_tool",
    "clone_repo_tool",
    "get_staged_diff_tool",
    "create_commit_tool",
    "get_repo_info_tool",
]

__version__ = "1.0.0"
