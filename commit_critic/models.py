"""
Pydantic models for Commit Critic structured output.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class CommitAnalysis(BaseModel):
    """Analysis result for a single commit message."""

    hash: str = Field(description="Short commit hash (8 chars)")
    message: str = Field(description="The commit message (first line)")
    body: Optional[str] = Field(default=None, description="Commit body (additional lines)")
    score: int = Field(ge=1, le=10, description="Quality score from 1-10")
    category: Literal["needs_work", "acceptable", "excellent"] = Field(
        description="Category based on score: needs_work (1-3), acceptable (4-6), excellent (7-10)"
    )
    issue: Optional[str] = Field(
        default=None,
        description="What's wrong with this commit message (for needs_work/acceptable)"
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="Suggested better commit message (for needs_work/acceptable)"
    )
    why_good: Optional[str] = Field(
        default=None,
        description="Why this commit message is good (for excellent)"
    )


class AnalysisReport(BaseModel):
    """Aggregated analysis report for multiple commits."""

    total_commits: int = Field(description="Total number of commits analyzed")
    average_score: float = Field(description="Average quality score")

    # Categorized counts
    needs_work_count: int = Field(description="Number of commits scoring 1-3")
    acceptable_count: int = Field(description="Number of commits scoring 4-6")
    excellent_count: int = Field(description="Number of commits scoring 7-10")

    # Specific issue counts
    vague_count: int = Field(description="Number of vague/unclear commits")
    one_word_count: int = Field(description="Number of one-word commits (e.g., 'fix', 'wip')")
    no_scope_count: int = Field(description="Number of commits without clear scope")

    # Lists of commits by category
    needs_work: list[CommitAnalysis] = Field(default_factory=list)
    acceptable: list[CommitAnalysis] = Field(default_factory=list)
    excellent: list[CommitAnalysis] = Field(default_factory=list)


class StagedChanges(BaseModel):
    """Information about staged changes for commit writing."""

    has_staged: bool = Field(description="Whether there are staged changes")
    stat: Optional[str] = Field(default=None, description="git diff --staged --stat output")
    diff: Optional[str] = Field(default=None, description="git diff --staged output (truncated)")
    files: list[str] = Field(default_factory=list, description="List of staged file paths")
    file_count: int = Field(default=0, description="Number of staged files")
    message: Optional[str] = Field(default=None, description="Status message")


class SuggestedCommit(BaseModel):
    """Suggested commit message from the AI."""

    type: str = Field(description="Commit type (feat, fix, refactor, docs, test, chore)")
    scope: Optional[str] = Field(default=None, description="Scope/area of change")
    subject: str = Field(description="Short description (max 50 chars)")
    body: Optional[str] = Field(default=None, description="Detailed explanation")

    @property
    def full_message(self) -> str:
        """Format as conventional commit message."""
        header = f"{self.type}"
        if self.scope:
            header += f"({self.scope})"
        header += f": {self.subject}"

        if self.body:
            return f"{header}\n\n{self.body}"
        return header


class RepoInfo(BaseModel):
    """Basic repository information."""

    repo_path: str = Field(description="Absolute path to repository")
    branch: str = Field(description="Current branch name")
    remote: str = Field(description="Remote origin URL")
    has_staged_changes: bool = Field(description="Whether there are staged changes")
