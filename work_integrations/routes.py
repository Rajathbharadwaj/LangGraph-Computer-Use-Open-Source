"""
FastAPI routes for Work Integrations.

Handles:
- OAuth flows for all platforms
- Integration management (list, create, update, delete)
- Activity queries
- Draft management (list, approve, reject)
- Webhook receivers
"""

import logging
import secrets
from typing import Optional, List
from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Header
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.database import get_db_session
from database.models import (
    WorkIntegration,
    WorkIntegrationCredential,
    WorkActivity,
    ActivityDraft,
    ScheduledPost,
    XAccount,
)
from services.cookie_encryption import encrypt_data, decrypt_data
from clerk_auth import get_current_user as get_current_user_id

from .config import get_work_integrations_settings, INTEGRATION_CREDITS
from services.billing_service import BillingService
from services.stripe_service import PLAN_LIMITS
from .models import (
    WorkPlatform,
    DraftStatus,
    ActivityCategory,
    OAuthURLResponse,
    IntegrationResponse,
    IntegrationListResponse,
    IntegrationSettings,
    ActivityResponse,
    ActivityListResponse,
    ActivityFilters,
    DraftResponse,
    DraftListResponse,
    DraftApproveRequest,
    DraftRejectRequest,
    WebhookResponse,
    IntegrationStats,
    WorkIntegrationsOverview,
    GitHubRepoListResponse,
    GitHubRepo,
)
from .services.oauth_manager import get_work_oauth_manager
from .clients.github_client import get_github_client
from .webhooks.github_webhook import process_github_webhook
from .webhooks.slack_webhook import get_slack_webhook_handler
from .webhooks.linear_webhook import get_linear_webhook_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/work-integrations", tags=["work-integrations"])


# =============================================================================
# OAuth Routes
# =============================================================================

@router.get("/oauth/{platform}/url", response_model=OAuthURLResponse)
async def get_oauth_url(
    platform: WorkPlatform,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get OAuth authorization URL for a platform.

    Starts the OAuth flow by generating an authorization URL with state.
    Checks billing limits before allowing new connections.
    """
    oauth_manager = get_work_oauth_manager()
    settings = get_work_integrations_settings()

    # Check billing limits for work integrations
    from sqlalchemy.orm import Session as SyncSession
    from database.database import SessionLocal
    sync_db: SyncSession = SessionLocal()
    try:
        billing = BillingService(sync_db)
        subscription = billing.get_subscription(user_id)
        plan = subscription.plan if subscription else "free"

        limits = PLAN_LIMITS.get(plan, {})
        max_integrations = limits.get("work_integrations", 0)

        if max_integrations == 0:
            raise HTTPException(
                403,
                "Work integrations require a paid subscription. Please upgrade to Starter or higher."
            )

        # Count existing integrations
        if max_integrations != -1:  # -1 means unlimited
            result = await db.execute(
                select(func.count()).where(
                    WorkIntegration.user_id == user_id,
                    WorkIntegration.is_connected == True,
                )
            )
            current_count = result.scalar() or 0

            if current_count >= max_integrations:
                raise HTTPException(
                    403,
                    f"Your {plan} plan allows {max_integrations} work integration(s). "
                    f"Please upgrade to connect more platforms."
                )
    finally:
        sync_db.close()

    # Check if credentials are configured
    if platform == WorkPlatform.GITHUB and not settings.github_client_id:
        raise HTTPException(400, "GitHub OAuth not configured")
    elif platform == WorkPlatform.SLACK and not settings.slack_client_id:
        raise HTTPException(400, "Slack OAuth not configured")
    elif platform == WorkPlatform.NOTION and not settings.notion_client_id:
        raise HTTPException(400, "Notion OAuth not configured")
    elif platform == WorkPlatform.LINEAR and not settings.linear_client_id:
        raise HTTPException(400, "Linear OAuth not configured")
    elif platform == WorkPlatform.FIGMA and not settings.figma_client_id:
        raise HTTPException(400, "Figma OAuth not configured")

    # Generate OAuth URL
    if platform == WorkPlatform.GITHUB:
        url, state = await oauth_manager.get_github_oauth_url(user_id)
    elif platform == WorkPlatform.SLACK:
        url, state = await oauth_manager.get_slack_oauth_url(user_id)
    elif platform == WorkPlatform.NOTION:
        url, state = await oauth_manager.get_notion_oauth_url(user_id)
    elif platform == WorkPlatform.LINEAR:
        url, state = await oauth_manager.get_linear_oauth_url(user_id)
    elif platform == WorkPlatform.FIGMA:
        url, state = await oauth_manager.get_figma_oauth_url(user_id)
    else:
        raise HTTPException(400, f"Unsupported platform: {platform}")

    return OAuthURLResponse(url=url, state=state)


@router.get("/oauth/{platform}/callback")
async def oauth_callback(
    platform: WorkPlatform,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Handle OAuth callback from platform.

    Exchanges the authorization code for tokens and creates the integration.
    """
    oauth_manager = get_work_oauth_manager()
    settings = get_work_integrations_settings()

    try:
        # Handle callback based on platform
        if platform == WorkPlatform.GITHUB:
            user_id, token_data = await oauth_manager.handle_github_callback(code, state)
            account_id = str(token_data.get("user", {}).get("id", ""))
            account_name = token_data.get("user", {}).get("login", "")
        elif platform == WorkPlatform.SLACK:
            user_id, token_data = await oauth_manager.handle_slack_callback(code, state)
            account_id = token_data.get("workspace", {}).get("id", "")
            account_name = token_data.get("workspace", {}).get("name", "")
        elif platform == WorkPlatform.NOTION:
            user_id, token_data = await oauth_manager.handle_notion_callback(code, state)
            account_id = token_data.get("workspace_id", "")
            account_name = token_data.get("workspace_name", "")
        elif platform == WorkPlatform.LINEAR:
            user_id, token_data = await oauth_manager.handle_linear_callback(code, state)
            account_id = token_data.get("organization", {}).get("id", "")
            account_name = token_data.get("organization", {}).get("name", "")
        elif platform == WorkPlatform.FIGMA:
            user_id, token_data = await oauth_manager.handle_figma_callback(code, state)
            account_id = token_data.get("user", {}).get("id", "")
            account_name = token_data.get("user", {}).get("handle", "")
        else:
            raise HTTPException(400, f"Unsupported platform: {platform}")

        # Check if integration already exists
        existing = await db.execute(
            select(WorkIntegration).where(
                and_(
                    WorkIntegration.user_id == user_id,
                    WorkIntegration.platform == platform.value,
                )
            )
        )
        integration = existing.scalar_one_or_none()

        if integration:
            # Update existing integration
            integration.external_account_id = account_id
            integration.external_account_name = account_name
            integration.is_connected = True
            integration.connection_error = None
            integration.updated_at = datetime.utcnow()
        else:
            # Create new integration
            integration = WorkIntegration(
                user_id=user_id,
                platform=platform.value,
                external_account_id=account_id,
                external_account_name=account_name,
                is_connected=True,
                webhook_secret=secrets.token_hex(32),
                credits_per_month=INTEGRATION_CREDITS.get(platform.value, 100),
            )
            db.add(integration)

        await db.flush()

        # Store encrypted credentials
        cred_result = await db.execute(
            select(WorkIntegrationCredential).where(
                WorkIntegrationCredential.integration_id == integration.id
            )
        )
        credential = cred_result.scalar_one_or_none()

        encrypted_access = encrypt_data(token_data.get("access_token", ""))
        encrypted_refresh = encrypt_data(token_data.get("refresh_token", "")) if token_data.get("refresh_token") else None

        if credential:
            credential.encrypted_access_token = encrypted_access
            credential.encrypted_refresh_token = encrypted_refresh
            credential.token_expires_at = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 0)) if token_data.get("expires_in") else None
            credential.updated_at = datetime.utcnow()
        else:
            credential = WorkIntegrationCredential(
                integration_id=integration.id,
                encrypted_access_token=encrypted_access,
                encrypted_refresh_token=encrypted_refresh,
                token_expires_at=datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 0)) if token_data.get("expires_in") else None,
                scopes=token_data.get("scope", "").split(",") if token_data.get("scope") else [],
            )
            db.add(credential)

        await db.commit()

        # Redirect to frontend integrations page with success
        redirect_url = f"{settings.frontend_url}/integrations?connected={platform.value}"
        return {"redirect_url": redirect_url, "success": True}

    except ValueError as e:
        logger.error(f"OAuth callback error: {e}")
        redirect_url = f"{settings.frontend_url}/integrations?error={str(e)}"
        return {"redirect_url": redirect_url, "success": False, "error": str(e)}

    except Exception as e:
        logger.error(f"Unexpected OAuth error: {e}")
        await db.rollback()
        raise HTTPException(500, f"OAuth failed: {str(e)}")


# =============================================================================
# Integration Management Routes
# =============================================================================

@router.get("", response_model=IntegrationListResponse)
async def list_integrations(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """List all work integrations for the user."""
    result = await db.execute(
        select(WorkIntegration)
        .where(WorkIntegration.user_id == user_id)
        .order_by(WorkIntegration.created_at.desc())
    )
    integrations = result.scalars().all()

    return IntegrationListResponse(
        integrations=[IntegrationResponse.model_validate(i) for i in integrations],
        total=len(integrations),
    )


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(
    integration_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a specific integration."""
    result = await db.execute(
        select(WorkIntegration).where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Integration not found")

    return IntegrationResponse.model_validate(integration)


@router.put("/{integration_id}/settings", response_model=IntegrationResponse)
async def update_integration_settings(
    integration_id: int,
    settings: IntegrationSettings,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Update settings for an integration."""
    result = await db.execute(
        select(WorkIntegration).where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Integration not found")

    # Update fields if provided
    if settings.github_repos is not None:
        integration.github_repos = settings.github_repos
    if settings.github_org is not None:
        integration.github_org = settings.github_org
    if settings.slack_channels is not None:
        integration.slack_channels = settings.slack_channels
    if settings.notion_database_ids is not None:
        integration.notion_database_ids = settings.notion_database_ids
    if settings.linear_team_id is not None:
        integration.linear_team_id = settings.linear_team_id
    if settings.figma_project_ids is not None:
        integration.figma_project_ids = settings.figma_project_ids
    if settings.capture_commits is not None:
        integration.capture_commits = settings.capture_commits
    if settings.capture_prs is not None:
        integration.capture_prs = settings.capture_prs
    if settings.capture_releases is not None:
        integration.capture_releases = settings.capture_releases
    if settings.capture_issues is not None:
        integration.capture_issues = settings.capture_issues
    if settings.capture_comments is not None:
        integration.capture_comments = settings.capture_comments

    integration.updated_at = datetime.utcnow()
    await db.commit()

    return IntegrationResponse.model_validate(integration)


@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Disconnect and delete an integration."""
    result = await db.execute(
        select(WorkIntegration).where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Integration not found")

    await db.delete(integration)
    await db.commit()

    return {"success": True, "message": "Integration deleted"}


@router.post("/{integration_id}/pause")
async def pause_integration(
    integration_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Pause an integration without disconnecting."""
    result = await db.execute(
        select(WorkIntegration).where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Integration not found")

    integration.is_active = False
    integration.updated_at = datetime.utcnow()
    await db.commit()

    return {"success": True, "message": "Integration paused"}


@router.post("/{integration_id}/resume")
async def resume_integration(
    integration_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Resume a paused integration."""
    result = await db.execute(
        select(WorkIntegration).where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Integration not found")

    integration.is_active = True
    integration.updated_at = datetime.utcnow()
    await db.commit()

    return {"success": True, "message": "Integration resumed"}


# =============================================================================
# GitHub-specific Routes
# =============================================================================

@router.get("/{integration_id}/github/repos", response_model=GitHubRepoListResponse)
async def list_github_repos(
    integration_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """List available GitHub repositories for selection."""
    result = await db.execute(
        select(WorkIntegration)
        .options(selectinload(WorkIntegration.credentials))
        .where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
                WorkIntegration.platform == "github",
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "GitHub integration not found")

    if not integration.credentials:
        raise HTTPException(400, "No credentials found for integration")

    access_token = decrypt_data(integration.credentials.encrypted_access_token)
    client = get_github_client(access_token)

    repos = await client.list_repos()

    return GitHubRepoListResponse(
        repos=[
            GitHubRepo(
                id=r["id"],
                name=r["name"],
                full_name=r["full_name"],
                private=r["private"],
                description=r.get("description"),
                html_url=r["html_url"],
                default_branch=r.get("default_branch", "main"),
            )
            for r in repos
        ],
        total=len(repos),
    )


@router.post("/{integration_id}/github/webhook")
async def setup_github_webhook(
    integration_id: int,
    repo_full_name: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Set up webhook for a GitHub repository."""
    settings = get_work_integrations_settings()

    result = await db.execute(
        select(WorkIntegration)
        .options(selectinload(WorkIntegration.credentials))
        .where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
                WorkIntegration.platform == "github",
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "GitHub integration not found")

    access_token = decrypt_data(integration.credentials.encrypted_access_token)
    client = get_github_client(access_token)

    owner, repo = repo_full_name.split("/")
    webhook_url = f"{settings.backend_url}/api/work-integrations/webhooks/github"

    webhook = await client.create_webhook(
        owner=owner,
        repo=repo,
        webhook_url=webhook_url,
        secret=integration.webhook_secret,
    )

    # Add repo to tracked repos
    if repo_full_name not in integration.github_repos:
        integration.github_repos = integration.github_repos + [repo_full_name]

    integration.webhook_registered = True
    integration.updated_at = datetime.utcnow()
    await db.commit()

    return {"success": True, "webhook_id": webhook.get("id")}


# =============================================================================
# Slack-specific Routes
# =============================================================================

@router.get("/{integration_id}/slack/channels")
async def list_slack_channels(
    integration_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """List available Slack channels for selection."""
    from .clients.slack_client import get_slack_client

    result = await db.execute(
        select(WorkIntegration)
        .options(selectinload(WorkIntegration.credentials))
        .where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
                WorkIntegration.platform == "slack",
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Slack integration not found")

    if not integration.credentials:
        raise HTTPException(400, "No credentials found for integration")

    access_token = decrypt_data(integration.credentials.encrypted_access_token)
    client = get_slack_client(access_token)

    channels = await client.list_channels()

    return {
        "channels": [
            {
                "id": c["id"],
                "name": c["name"],
                "is_private": c.get("is_private", False),
                "num_members": c.get("num_members", 0),
            }
            for c in channels
        ],
        "total": len(channels),
    }


# =============================================================================
# Linear-specific Routes
# =============================================================================

@router.get("/{integration_id}/linear/teams")
async def list_linear_teams(
    integration_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """List available Linear teams for selection."""
    from .clients.linear_client import get_linear_client

    result = await db.execute(
        select(WorkIntegration)
        .options(selectinload(WorkIntegration.credentials))
        .where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
                WorkIntegration.platform == "linear",
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Linear integration not found")

    if not integration.credentials:
        raise HTTPException(400, "No credentials found for integration")

    access_token = decrypt_data(integration.credentials.encrypted_access_token)
    client = get_linear_client(access_token)

    teams = await client.list_teams()

    return {
        "teams": [
            {
                "id": t["id"],
                "name": t["name"],
                "key": t["key"],
                "description": t.get("description"),
            }
            for t in teams
        ],
        "total": len(teams),
    }


@router.post("/{integration_id}/linear/webhook")
async def setup_linear_webhook(
    integration_id: int,
    team_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Set up webhook for Linear organization."""
    from .clients.linear_client import get_linear_client

    settings = get_work_integrations_settings()

    result = await db.execute(
        select(WorkIntegration)
        .options(selectinload(WorkIntegration.credentials))
        .where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
                WorkIntegration.platform == "linear",
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Linear integration not found")

    access_token = decrypt_data(integration.credentials.encrypted_access_token)
    client = get_linear_client(access_token)

    webhook_url = f"{settings.backend_url}/api/work-integrations/webhooks/linear"

    webhook = await client.create_webhook(
        url=webhook_url,
        team_id=team_id,
        label="Parallel Universe",
    )

    integration.webhook_registered = True
    if team_id:
        integration.linear_team_id = team_id
    integration.updated_at = datetime.utcnow()
    await db.commit()

    return {"success": True, "webhook_id": webhook.get("id")}


# =============================================================================
# Notion-specific Routes
# =============================================================================

@router.get("/{integration_id}/notion/databases")
async def list_notion_databases(
    integration_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """List available Notion databases for selection."""
    from .clients.notion_client import get_notion_client

    result = await db.execute(
        select(WorkIntegration)
        .options(selectinload(WorkIntegration.credentials))
        .where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
                WorkIntegration.platform == "notion",
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Notion integration not found")

    if not integration.credentials:
        raise HTTPException(400, "No credentials found for integration")

    access_token = decrypt_data(integration.credentials.encrypted_access_token)
    client = get_notion_client(access_token)

    databases = await client.list_databases()

    return {
        "databases": [
            {
                "id": d["id"],
                "title": d.get("title", [{}])[0].get("plain_text", "Untitled") if d.get("title") else "Untitled",
                "url": d.get("url"),
                "icon": d.get("icon", {}).get("emoji") if d.get("icon") else None,
            }
            for d in databases
        ],
        "total": len(databases),
    }


# =============================================================================
# Figma-specific Routes
# =============================================================================

@router.get("/{integration_id}/figma/projects")
async def list_figma_projects(
    integration_id: int,
    team_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """List available Figma projects for a team."""
    from .clients.figma_client import get_figma_client

    result = await db.execute(
        select(WorkIntegration)
        .options(selectinload(WorkIntegration.credentials))
        .where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
                WorkIntegration.platform == "figma",
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Figma integration not found")

    if not integration.credentials:
        raise HTTPException(400, "No credentials found for integration")

    access_token = decrypt_data(integration.credentials.encrypted_access_token)
    client = get_figma_client(access_token)

    projects = await client.list_team_projects(team_id)

    return {
        "projects": [
            {
                "id": p["id"],
                "name": p["name"],
            }
            for p in projects
        ],
        "total": len(projects),
    }


# =============================================================================
# Activity Routes
# =============================================================================

@router.get("/activities", response_model=ActivityListResponse)
async def list_activities(
    platform: Optional[WorkPlatform] = None,
    category: Optional[ActivityCategory] = None,
    processed: Optional[bool] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """List work activities with filtering."""
    query = select(WorkActivity).where(WorkActivity.user_id == user_id)

    if platform:
        query = query.where(WorkActivity.platform == platform.value)
    if category:
        query = query.where(WorkActivity.category == category.value)
    if processed is not None:
        query = query.where(WorkActivity.processed == processed)
    if start_date:
        query = query.where(WorkActivity.activity_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.where(WorkActivity.activity_at <= datetime.combine(end_date, datetime.max.time()))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Apply pagination
    query = query.order_by(WorkActivity.activity_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    activities = result.scalars().all()

    return ActivityListResponse(
        activities=[ActivityResponse.model_validate(a) for a in activities],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# Draft Routes
# =============================================================================

@router.get("/drafts", response_model=DraftListResponse)
async def list_drafts(
    status: Optional[DraftStatus] = None,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """List activity drafts."""
    query = select(ActivityDraft).where(ActivityDraft.user_id == user_id)

    if status:
        query = query.where(ActivityDraft.status == status.value)

    query = query.order_by(ActivityDraft.created_at.desc())

    result = await db.execute(query)
    drafts = result.scalars().all()

    # Count pending
    pending_count = sum(1 for d in drafts if d.status == DraftStatus.PENDING.value)

    return DraftListResponse(
        drafts=[DraftResponse.model_validate(d) for d in drafts],
        total=len(drafts),
        pending_count=pending_count,
    )


@router.get("/drafts/{draft_id}", response_model=DraftResponse)
async def get_draft(
    draft_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a specific draft."""
    result = await db.execute(
        select(ActivityDraft).where(
            and_(
                ActivityDraft.id == draft_id,
                ActivityDraft.user_id == user_id,
            )
        )
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(404, "Draft not found")

    return DraftResponse.model_validate(draft)


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: int,
    request: DraftApproveRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Approve a draft and schedule it for posting."""
    result = await db.execute(
        select(ActivityDraft).where(
            and_(
                ActivityDraft.id == draft_id,
                ActivityDraft.user_id == user_id,
            )
        )
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(404, "Draft not found")

    if draft.status != DraftStatus.PENDING.value:
        raise HTTPException(400, f"Cannot approve draft with status: {draft.status}")

    # Determine content and status
    content = request.edited_content or draft.content
    new_status = DraftStatus.EDITED.value if request.edited_content else DraftStatus.APPROVED.value

    # Create scheduled post
    scheduled_at = request.schedule_at or (datetime.utcnow() + timedelta(hours=1))

    scheduled_post = ScheduledPost(
        x_account_id=draft.x_account_id,
        content=content,
        status="scheduled",
        scheduled_at=scheduled_at,
        ai_generated=True,
        ai_metadata={"source": "activity_draft", "draft_id": draft_id},
    )
    db.add(scheduled_post)
    await db.flush()

    # Update draft
    draft.status = new_status
    draft.user_edited_content = request.edited_content
    draft.scheduled_post_id = scheduled_post.id
    draft.scheduled_at = scheduled_at
    draft.reviewed_at = datetime.utcnow()
    draft.updated_at = datetime.utcnow()

    await db.commit()

    return {
        "success": True,
        "message": "Draft approved and scheduled",
        "scheduled_post_id": scheduled_post.id,
        "scheduled_at": scheduled_at.isoformat(),
    }


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: int,
    request: DraftRejectRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Reject a draft."""
    result = await db.execute(
        select(ActivityDraft).where(
            and_(
                ActivityDraft.id == draft_id,
                ActivityDraft.user_id == user_id,
            )
        )
    )
    draft = result.scalar_one_or_none()

    if not draft:
        raise HTTPException(404, "Draft not found")

    if draft.status != DraftStatus.PENDING.value:
        raise HTTPException(400, f"Cannot reject draft with status: {draft.status}")

    draft.status = DraftStatus.REJECTED.value
    draft.feedback_rating = request.feedback_rating
    draft.feedback_text = request.reason
    draft.reviewed_at = datetime.utcnow()
    draft.updated_at = datetime.utcnow()

    await db.commit()

    return {"success": True, "message": "Draft rejected"}


# =============================================================================
# Webhook Routes
# =============================================================================

@router.post("/webhooks/github", response_model=WebhookResponse)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Receive GitHub webhook events.

    Events are verified using the webhook secret and processed
    to create WorkActivity records.
    """
    body = await request.body()
    payload = await request.json()

    # Get repository info to find integration
    repo = payload.get("repository", {})
    repo_full_name = repo.get("full_name", "")

    if not repo_full_name:
        return WebhookResponse(success=False, message="No repository in payload")

    # Find integration by repo
    result = await db.execute(
        select(WorkIntegration).where(
            and_(
                WorkIntegration.platform == "github",
                WorkIntegration.is_connected == True,
                WorkIntegration.is_active == True,
            )
        )
    )
    integrations = result.scalars().all()

    # Find integration that tracks this repo
    integration = None
    for i in integrations:
        if repo_full_name in (i.github_repos or []):
            integration = i
            break

    if not integration:
        logger.debug(f"No integration found for repo {repo_full_name}")
        return WebhookResponse(success=True, message="No integration for this repo")

    # Verify webhook signature
    oauth_manager = get_work_oauth_manager()
    if x_hub_signature_256 and integration.webhook_secret:
        if not oauth_manager.verify_github_webhook(body, x_hub_signature_256):
            raise HTTPException(401, "Invalid webhook signature")

    # Process the webhook
    try:
        activities = await process_github_webhook(db, integration, x_github_event, payload)
        await db.commit()

        return WebhookResponse(
            success=True,
            message=f"Processed {x_github_event} event",
            activities_created=len(activities),
        )

    except Exception as e:
        logger.error(f"Error processing GitHub webhook: {e}")
        await db.rollback()
        raise HTTPException(500, f"Webhook processing failed: {str(e)}")


@router.post("/webhooks/slack", response_model=WebhookResponse)
async def slack_webhook(
    request: Request,
    x_slack_request_timestamp: str = Header(None, alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str = Header(None, alias="X-Slack-Signature"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Receive Slack Events API callbacks.

    Handles URL verification challenges and event callbacks.
    """
    body = await request.body()
    payload = await request.json()

    # Handle URL verification challenge (required for Slack app setup)
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    # Get team/workspace ID
    team_id = payload.get("team_id")
    if not team_id:
        return WebhookResponse(success=False, message="No team_id in payload")

    # Find integration
    result = await db.execute(
        select(WorkIntegration).where(
            and_(
                WorkIntegration.platform == "slack",
                WorkIntegration.external_account_id == team_id,
                WorkIntegration.is_active == True,
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        logger.debug(f"No Slack integration found for team {team_id}")
        return WebhookResponse(success=True, message="No integration for this workspace")

    # Verify signature if we have credentials
    settings = get_work_integrations_settings()
    handler = get_slack_webhook_handler()

    if x_slack_signature and settings.slack_signing_secret:
        if not handler.verify_signature(
            body,
            x_slack_request_timestamp,
            x_slack_signature,
            settings.slack_signing_secret,
        ):
            raise HTTPException(401, "Invalid Slack signature")

    # Process the event
    try:
        result = await handler.handle_event(payload, db)

        # If it's a challenge response, return it
        if isinstance(result, dict) and "challenge" in result:
            return result

        await db.commit()

        return WebhookResponse(
            success=True,
            message="Slack event processed",
            activities_created=1 if result else 0,
        )

    except Exception as e:
        logger.error(f"Error processing Slack webhook: {e}")
        await db.rollback()
        raise HTTPException(500, f"Webhook processing failed: {str(e)}")


@router.post("/webhooks/linear", response_model=WebhookResponse)
async def linear_webhook(
    request: Request,
    linear_signature: str = Header(None, alias="Linear-Signature"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Receive Linear webhook events.

    Processes issue, comment, project, and cycle events.
    """
    body = await request.body()
    payload = await request.json()

    organization_id = payload.get("organizationId")
    if not organization_id:
        return WebhookResponse(success=False, message="No organizationId in payload")

    # Find integration
    result = await db.execute(
        select(WorkIntegration).where(
            and_(
                WorkIntegration.platform == "linear",
                WorkIntegration.external_account_id == organization_id,
                WorkIntegration.is_active == True,
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        logger.debug(f"No Linear integration found for org {organization_id}")
        return WebhookResponse(success=True, message="No integration for this organization")

    # Verify signature if we have a webhook secret
    handler = get_linear_webhook_handler()

    if linear_signature and integration.webhook_secret:
        if not handler.verify_signature(
            body,
            linear_signature,
            integration.webhook_secret,
        ):
            raise HTTPException(401, "Invalid Linear signature")

    # Process the event
    try:
        activity = await handler.handle_event(payload, db)
        await db.commit()

        event_type = payload.get("type", "unknown")
        action = payload.get("action", "unknown")

        return WebhookResponse(
            success=True,
            message=f"Processed Linear {event_type}.{action}",
            activities_created=1 if activity else 0,
        )

    except Exception as e:
        logger.error(f"Error processing Linear webhook: {e}")
        await db.rollback()
        raise HTTPException(500, f"Webhook processing failed: {str(e)}")


# =============================================================================
# Stats Routes
# =============================================================================

@router.get("/stats", response_model=WorkIntegrationsOverview)
async def get_overview_stats(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Get overview statistics for work integrations."""
    # Count integrations
    integrations_result = await db.execute(
        select(WorkIntegration).where(WorkIntegration.user_id == user_id)
    )
    integrations = integrations_result.scalars().all()

    active_count = sum(1 for i in integrations if i.is_active)
    platforms = list(set(i.platform for i in integrations))

    # Count activities
    activities_count = await db.scalar(
        select(func.count()).where(WorkActivity.user_id == user_id)
    )

    # Count pending drafts
    pending_drafts = await db.scalar(
        select(func.count()).where(
            and_(
                ActivityDraft.user_id == user_id,
                ActivityDraft.status == DraftStatus.PENDING.value,
            )
        )
    )

    # Count approved drafts this month
    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    approved_this_month = await db.scalar(
        select(func.count()).where(
            and_(
                ActivityDraft.user_id == user_id,
                ActivityDraft.status.in_([DraftStatus.APPROVED.value, DraftStatus.EDITED.value]),
                ActivityDraft.reviewed_at >= start_of_month,
            )
        )
    )

    return WorkIntegrationsOverview(
        total_integrations=len(integrations),
        active_integrations=active_count,
        total_activities_captured=activities_count or 0,
        pending_drafts=pending_drafts or 0,
        drafts_approved_this_month=approved_this_month or 0,
        platforms_connected=[WorkPlatform(p) for p in platforms],
    )


@router.get("/stats/{integration_id}", response_model=IntegrationStats)
async def get_integration_stats(
    integration_id: int,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Get statistics for a specific integration."""
    # Verify ownership
    result = await db.execute(
        select(WorkIntegration).where(
            and_(
                WorkIntegration.id == integration_id,
                WorkIntegration.user_id == user_id,
            )
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(404, "Integration not found")

    # Count activities
    total = await db.scalar(
        select(func.count()).where(WorkActivity.integration_id == integration_id)
    )

    # Today's activities
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = await db.scalar(
        select(func.count()).where(
            and_(
                WorkActivity.integration_id == integration_id,
                WorkActivity.activity_at >= today,
            )
        )
    )

    # This week's activities
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_count = await db.scalar(
        select(func.count()).where(
            and_(
                WorkActivity.integration_id == integration_id,
                WorkActivity.activity_at >= week_ago,
            )
        )
    )

    # Drafts from this integration
    drafts_result = await db.execute(
        select(func.count(), func.count(ActivityDraft.id).filter(
            ActivityDraft.status.in_([DraftStatus.APPROVED.value, DraftStatus.EDITED.value])
        )).select_from(ActivityDraft).where(
            and_(
                ActivityDraft.user_id == user_id,
                # Would need to join with activities - simplified for now
            )
        )
    )

    return IntegrationStats(
        integration_id=integration_id,
        platform=WorkPlatform(integration.platform),
        total_activities=total or 0,
        activities_today=today_count or 0,
        activities_this_week=week_count or 0,
        last_activity_at=integration.last_activity_at,
        drafts_generated=0,  # TODO: Track properly
        drafts_approved=0,
    )


# =============================================================================
# Manual Digest Trigger (for testing)
# =============================================================================

@router.post("/digest/trigger")
async def trigger_digest(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Manually trigger digest generation for the current user.

    Useful for testing without waiting for the scheduled job.
    """
    from .services.activity_aggregator import ActivityAggregator
    from .services.draft_generator import DraftGenerator

    # Create aggregator and generator
    aggregator = ActivityAggregator(db)
    generator = DraftGenerator(db)

    # Prepare digest
    digest = await aggregator.prepare_digest(user_id)

    if not digest:
        return {
            "success": False,
            "message": "No activities to aggregate or insufficient activity",
        }

    # Generate drafts
    drafts = await generator.generate_and_save_drafts(digest, num_drafts=1)

    await db.commit()

    return {
        "success": True,
        "message": f"Generated {len(drafts)} draft(s)",
        "drafts": [
            {
                "id": d.id,
                "content": d.content,
                "theme": d.digest_theme,
            }
            for d in drafts
        ],
        "activities_used": len(digest["activity_ids"]),
        "theme": digest["theme"],
    }
