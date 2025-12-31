"""
GitHub Webhook Handler for Work Integrations.

Processes GitHub webhook events and creates WorkActivity records.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WorkIntegration, WorkActivity
from ..config import SIGNIFICANCE_SCORES, CATEGORY_MULTIPLIERS
from ..models import WorkPlatform, ActivityCategory

logger = logging.getLogger(__name__)


def determine_category(activity_type: str) -> ActivityCategory:
    """Determine activity category based on type."""
    code_shipped = ["release_published", "pr_merged", "commit_pushed"]
    collaboration = ["review_submitted", "issue_commented", "pr_commented"]

    if activity_type in code_shipped:
        return ActivityCategory.CODE_SHIPPED
    elif activity_type in collaboration:
        return ActivityCategory.COLLABORATION
    else:
        return ActivityCategory.PROGRESS


def calculate_significance(
    activity_type: str,
    category: ActivityCategory,
    lines_added: int = 0,
    lines_removed: int = 0,
    files_changed: int = 0,
    comments_count: int = 0,
) -> float:
    """
    Calculate significance score for an activity.

    Score = base_score * category_multiplier + metric_bonuses
    """
    base_score = SIGNIFICANCE_SCORES.get(activity_type, 0.3)
    category_mult = CATEGORY_MULTIPLIERS.get(category.value, 1.0)

    # Metric bonuses (capped)
    lines_bonus = min((lines_added + lines_removed) * 0.001, 0.2)
    files_bonus = min(files_changed * 0.02, 0.1)
    comments_bonus = min(comments_count * 0.05, 0.1)

    score = (base_score * category_mult) + lines_bonus + files_bonus + comments_bonus

    # Cap at 1.0
    return min(score, 1.0)


async def process_github_webhook(
    db: AsyncSession,
    integration: WorkIntegration,
    event_type: str,
    payload: Dict[str, Any],
) -> List[WorkActivity]:
    """
    Process a GitHub webhook event and create WorkActivity records.

    Args:
        db: Database session
        integration: The WorkIntegration receiving the webhook
        event_type: GitHub event type (X-GitHub-Event header)
        payload: Webhook payload

    Returns:
        List of created WorkActivity records
    """
    activities = []

    try:
        if event_type == "push":
            activities = await _process_push_event(db, integration, payload)
        elif event_type == "pull_request":
            activities = await _process_pull_request_event(db, integration, payload)
        elif event_type == "release":
            activities = await _process_release_event(db, integration, payload)
        elif event_type == "issues":
            activities = await _process_issues_event(db, integration, payload)
        elif event_type == "issue_comment":
            activities = await _process_comment_event(db, integration, payload)
        elif event_type == "pull_request_review":
            activities = await _process_review_event(db, integration, payload)
        else:
            logger.debug(f"Ignoring GitHub event type: {event_type}")

    except Exception as e:
        logger.error(f"Error processing GitHub webhook: {e}")
        raise

    return activities


async def _process_push_event(
    db: AsyncSession,
    integration: WorkIntegration,
    payload: Dict[str, Any],
) -> List[WorkActivity]:
    """Process push event - create activity for commits."""
    if not integration.capture_commits:
        return []

    commits = payload.get("commits", [])
    if not commits:
        return []

    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "")

    # Create one activity for the push (aggregating commits)
    commit_count = len(commits)
    first_commit = commits[0] if commits else {}

    # Calculate total changes
    total_added = sum(c.get("stats", {}).get("additions", 0) for c in commits)
    total_removed = sum(c.get("stats", {}).get("deletions", 0) for c in commits)

    activity_type = "commit_pushed"
    category = determine_category(activity_type)

    # Build title
    if commit_count == 1:
        title = f"Pushed commit: {first_commit.get('message', '').split(chr(10))[0][:100]}"
    else:
        title = f"Pushed {commit_count} commits to {repo_name}"

    # Build description
    messages = [c.get("message", "").split("\n")[0] for c in commits[:5]]
    description = "\n".join(f"- {m}" for m in messages)
    if commit_count > 5:
        description += f"\n... and {commit_count - 5} more"

    activity = WorkActivity(
        integration_id=integration.id,
        user_id=integration.user_id,
        platform=WorkPlatform.GITHUB.value,
        external_id=payload.get("after"),  # SHA of head commit
        activity_type=activity_type,
        category=category.value,
        title=title,
        description=description,
        url=payload.get("compare"),  # Compare URL
        repo_or_project=repo_name,
        lines_added=total_added,
        lines_removed=total_removed,
        files_changed=len(set(f for c in commits for f in c.get("modified", []) + c.get("added", []) + c.get("removed", []))),
        significance_score=calculate_significance(
            activity_type, category, total_added, total_removed
        ),
        raw_payload=payload,
        activity_at=datetime.fromisoformat(payload.get("head_commit", {}).get("timestamp", datetime.utcnow().isoformat()).replace("Z", "+00:00")),
    )

    db.add(activity)
    await db.flush()

    logger.info(f"Created push activity for {repo_name}: {commit_count} commits")
    return [activity]


async def _process_pull_request_event(
    db: AsyncSession,
    integration: WorkIntegration,
    payload: Dict[str, Any],
) -> List[WorkActivity]:
    """Process pull_request event."""
    if not integration.capture_prs:
        return []

    action = payload.get("action")
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    # Only track significant PR events
    if action not in ["opened", "closed", "merged"]:
        return []

    # Determine activity type
    if action == "opened":
        activity_type = "pr_opened"
    elif pr.get("merged"):
        activity_type = "pr_merged"
    else:
        activity_type = "pr_closed"

    category = determine_category(activity_type)

    activity = WorkActivity(
        integration_id=integration.id,
        user_id=integration.user_id,
        platform=WorkPlatform.GITHUB.value,
        external_id=str(pr.get("id")),
        activity_type=activity_type,
        category=category.value,
        title=f"PR #{pr.get('number')}: {pr.get('title', '')[:100]}",
        description=pr.get("body", "")[:500] if pr.get("body") else None,
        url=pr.get("html_url"),
        repo_or_project=repo.get("full_name", ""),
        lines_added=pr.get("additions", 0),
        lines_removed=pr.get("deletions", 0),
        files_changed=pr.get("changed_files", 0),
        comments_count=pr.get("comments", 0) + pr.get("review_comments", 0),
        significance_score=calculate_significance(
            activity_type,
            category,
            pr.get("additions", 0),
            pr.get("deletions", 0),
            pr.get("changed_files", 0),
            pr.get("comments", 0),
        ),
        raw_payload=payload,
        activity_at=datetime.fromisoformat(
            (pr.get("merged_at") or pr.get("closed_at") or pr.get("created_at") or datetime.utcnow().isoformat()).replace("Z", "+00:00")
        ),
    )

    db.add(activity)
    await db.flush()

    logger.info(f"Created PR activity: {activity_type} #{pr.get('number')}")
    return [activity]


async def _process_release_event(
    db: AsyncSession,
    integration: WorkIntegration,
    payload: Dict[str, Any],
) -> List[WorkActivity]:
    """Process release event."""
    if not integration.capture_releases:
        return []

    action = payload.get("action")
    if action != "published":
        return []

    release = payload.get("release", {})
    repo = payload.get("repository", {})

    activity_type = "release_published"
    category = determine_category(activity_type)

    activity = WorkActivity(
        integration_id=integration.id,
        user_id=integration.user_id,
        platform=WorkPlatform.GITHUB.value,
        external_id=str(release.get("id")),
        activity_type=activity_type,
        category=category.value,
        title=f"Released {release.get('tag_name', '')} - {release.get('name', '')}",
        description=release.get("body", "")[:500] if release.get("body") else None,
        url=release.get("html_url"),
        repo_or_project=repo.get("full_name", ""),
        significance_score=calculate_significance(activity_type, category),
        raw_payload=payload,
        activity_at=datetime.fromisoformat(release.get("published_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")),
    )

    db.add(activity)
    await db.flush()

    logger.info(f"Created release activity: {release.get('tag_name')}")
    return [activity]


async def _process_issues_event(
    db: AsyncSession,
    integration: WorkIntegration,
    payload: Dict[str, Any],
) -> List[WorkActivity]:
    """Process issues event."""
    if not integration.capture_issues:
        return []

    action = payload.get("action")
    issue = payload.get("issue", {})
    repo = payload.get("repository", {})

    # Only track open and close
    if action not in ["opened", "closed"]:
        return []

    activity_type = "issue_opened" if action == "opened" else "issue_closed"
    category = determine_category(activity_type)

    activity = WorkActivity(
        integration_id=integration.id,
        user_id=integration.user_id,
        platform=WorkPlatform.GITHUB.value,
        external_id=str(issue.get("id")),
        activity_type=activity_type,
        category=category.value,
        title=f"Issue #{issue.get('number')}: {issue.get('title', '')[:100]}",
        description=issue.get("body", "")[:500] if issue.get("body") else None,
        url=issue.get("html_url"),
        repo_or_project=repo.get("full_name", ""),
        comments_count=issue.get("comments", 0),
        significance_score=calculate_significance(
            activity_type, category, comments_count=issue.get("comments", 0)
        ),
        raw_payload=payload,
        activity_at=datetime.fromisoformat(
            (issue.get("closed_at") or issue.get("created_at") or datetime.utcnow().isoformat()).replace("Z", "+00:00")
        ),
    )

    db.add(activity)
    await db.flush()

    logger.info(f"Created issue activity: {activity_type} #{issue.get('number')}")
    return [activity]


async def _process_comment_event(
    db: AsyncSession,
    integration: WorkIntegration,
    payload: Dict[str, Any],
) -> List[WorkActivity]:
    """Process issue_comment event."""
    if not integration.capture_comments:
        return []

    action = payload.get("action")
    if action != "created":
        return []

    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    repo = payload.get("repository", {})

    activity_type = "issue_commented"
    category = ActivityCategory.COLLABORATION

    activity = WorkActivity(
        integration_id=integration.id,
        user_id=integration.user_id,
        platform=WorkPlatform.GITHUB.value,
        external_id=str(comment.get("id")),
        activity_type=activity_type,
        category=category.value,
        title=f"Commented on #{issue.get('number')}: {issue.get('title', '')[:80]}",
        description=comment.get("body", "")[:500] if comment.get("body") else None,
        url=comment.get("html_url"),
        repo_or_project=repo.get("full_name", ""),
        reactions_count=sum(comment.get("reactions", {}).values()) if isinstance(comment.get("reactions"), dict) else 0,
        significance_score=calculate_significance(activity_type, category),
        raw_payload=payload,
        activity_at=datetime.fromisoformat(comment.get("created_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")),
    )

    db.add(activity)
    await db.flush()

    logger.info(f"Created comment activity on #{issue.get('number')}")
    return [activity]


async def _process_review_event(
    db: AsyncSession,
    integration: WorkIntegration,
    payload: Dict[str, Any],
) -> List[WorkActivity]:
    """Process pull_request_review event."""
    if not integration.capture_comments:
        return []

    action = payload.get("action")
    if action != "submitted":
        return []

    review = payload.get("review", {})
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    activity_type = "review_submitted"
    category = ActivityCategory.COLLABORATION

    # Get review state for title
    state = review.get("state", "").lower()
    state_text = {
        "approved": "Approved",
        "changes_requested": "Requested changes on",
        "commented": "Reviewed",
    }.get(state, "Reviewed")

    activity = WorkActivity(
        integration_id=integration.id,
        user_id=integration.user_id,
        platform=WorkPlatform.GITHUB.value,
        external_id=str(review.get("id")),
        activity_type=activity_type,
        category=category.value,
        title=f"{state_text} PR #{pr.get('number')}: {pr.get('title', '')[:80]}",
        description=review.get("body", "")[:500] if review.get("body") else None,
        url=review.get("html_url"),
        repo_or_project=repo.get("full_name", ""),
        significance_score=calculate_significance(activity_type, category),
        raw_payload=payload,
        activity_at=datetime.fromisoformat(review.get("submitted_at", datetime.utcnow().isoformat()).replace("Z", "+00:00")),
    )

    db.add(activity)
    await db.flush()

    logger.info(f"Created review activity on PR #{pr.get('number')}")
    return [activity]
