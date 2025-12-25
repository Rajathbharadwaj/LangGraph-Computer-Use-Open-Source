"""
Ads Service API Routes

FastAPI endpoints for Meta and Google Ads platform management.
Handles OAuth flows, campaign CRUD, and metrics retrieval.
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import AdsPlatform, AdsCredential, AdsCampaign, AdsMetrics, User, UserAsset, ImageGenerationJob
from clerk_auth import get_current_user
from pydantic import BaseModel, Field

# Import encryption service directly to avoid Docker initialization
from cryptography.fernet import Fernet
import os
import json

from .config import get_ads_settings, is_meta_configured, is_google_configured
from .models import (
    AdsPlatformType,
    OAuthUrlResponse,
    OAuthCallbackRequest,
    AdsPlatformCreate,
    AdsPlatformResponse,
    AdsPlatformListResponse,
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignListResponse,
    CampaignStatus,
    CampaignMetricsResponse,
    MetricsSnapshot,
    WeeklyReportResponse,
    AdsErrorResponse,
)
from .services.oauth_manager import get_oauth_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ads", tags=["Ads"])


# =============================================================================
# Token Encryption Service (local copy to avoid Docker dependency)
# =============================================================================


class TokenEncryptionService:
    """Encrypts and decrypts OAuth tokens for secure storage."""

    def __init__(self):
        key = os.getenv("COOKIE_ENCRYPTION_KEY")
        if not key:
            logger.warning("No COOKIE_ENCRYPTION_KEY found, generating new one")
            key = Fernet.generate_key().decode()
        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt_cookies(self, data: list) -> str:
        """Encrypt data (token list) to string."""
        try:
            data_json = json.dumps(data)
            encrypted = self.cipher.encrypt(data_json.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Error encrypting data: {e}")
            raise

    def decrypt_cookies(self, encrypted_data: str) -> list:
        """Decrypt string back to data (token list)."""
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"Error decrypting data: {e}")
            raise


_encryption_service: Optional[TokenEncryptionService] = None


def get_encryption_service() -> TokenEncryptionService:
    """Get or create the encryption service singleton."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = TokenEncryptionService()
    return _encryption_service


# =============================================================================
# Health Check
# =============================================================================


@router.get("/health")
async def health_check():
    """Check ads service health and configuration status."""
    return {
        "status": "healthy",
        "meta_configured": is_meta_configured(),
        "google_configured": is_google_configured(),
    }


# =============================================================================
# OAuth Endpoints - Meta
# =============================================================================


@router.get("/oauth/meta/url", response_model=OAuthUrlResponse)
async def get_meta_oauth_url(user_id: str = Depends(get_current_user)):
    """
    Get Meta OAuth authorization URL.

    Returns a URL to redirect the user to for Meta Ads authorization.
    After authorization, Meta will redirect back to our callback endpoint.
    """
    if not is_meta_configured():
        raise HTTPException(
            status_code=400,
            detail="Meta Ads not configured. Please set META_APP_ID and META_APP_SECRET.",
        )

    oauth_manager = get_oauth_manager()
    url, state = await oauth_manager.get_meta_oauth_url(user_id)

    return OAuthUrlResponse(url=url, state=state, platform=AdsPlatformType.META)


@router.get("/oauth/meta/callback")
async def handle_meta_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Handle Meta OAuth callback.

    This endpoint is called by Meta after the user authorizes our app.
    It exchanges the code for tokens and stores them in the database.
    """
    oauth_manager = get_oauth_manager()
    encryption = get_encryption_service()
    settings = get_ads_settings()

    try:
        user_id, token_data = await oauth_manager.handle_meta_callback(code, state)

        # Get or create the platform record
        platform = (
            db.query(AdsPlatform)
            .filter(
                AdsPlatform.user_id == user_id,
                AdsPlatform.platform == AdsPlatformType.META.value,
            )
            .first()
        )

        if not platform:
            platform = AdsPlatform(
                user_id=user_id,
                platform=AdsPlatformType.META.value,
            )
            db.add(platform)
            db.flush()

        # Update platform with account info
        ad_accounts = token_data.get("ad_accounts", [])
        pages = token_data.get("pages", [])

        if ad_accounts:
            # Use the first active ad account
            for acc in ad_accounts:
                if acc.get("account_status") == 1:  # Active
                    platform.account_id = acc.get("id", "").replace("act_", "")
                    platform.account_name = acc.get("name")
                    break
            else:
                # No active account, use first one
                platform.account_id = ad_accounts[0].get("id", "").replace("act_", "")
                platform.account_name = ad_accounts[0].get("name")

        if pages:
            platform.meta_page_id = pages[0].get("id")

        platform.is_connected = True
        platform.connection_error = None

        # Store encrypted tokens
        if platform.credentials:
            credentials = platform.credentials
        else:
            credentials = AdsCredential(platform_id=platform.id)
            db.add(credentials)

        credentials.encrypted_access_token = encryption.encrypt_cookies(
            [{"token": token_data.get("access_token")}]
        )

        # Calculate token expiration
        expires_in = token_data.get("expires_in", 5184000)  # Default 60 days
        credentials.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        credentials.scopes = ["ads_management", "ads_read", "business_management"]

        db.commit()

        logger.info(f"Meta OAuth completed for user {user_id}")

        # Redirect to frontend success page
        frontend_url = settings.app_base_url
        return RedirectResponse(
            url=f"{frontend_url}/ads?oauth_success=true&platform=meta"
        )

    except ValueError as e:
        logger.error(f"Meta OAuth error: {e}")
        frontend_url = settings.app_base_url
        import urllib.parse
        error_encoded = urllib.parse.quote(str(e))
        return RedirectResponse(
            url=f"{frontend_url}/ads?oauth_error={error_encoded}"
        )
    except Exception as e:
        logger.error(f"Meta OAuth unexpected error: {e}")
        import traceback
        traceback.print_exc()
        frontend_url = settings.app_base_url
        return RedirectResponse(
            url=f"{frontend_url}/ads?oauth_error=OAuth+failed"
        )


# =============================================================================
# OAuth Endpoints - Google
# =============================================================================


@router.get("/oauth/google/url", response_model=OAuthUrlResponse)
async def get_google_oauth_url(user_id: str = Depends(get_current_user)):
    """
    Get Google OAuth authorization URL.

    Returns a URL to redirect the user to for Google Ads authorization.
    After authorization, Google will redirect back to our callback endpoint.
    """
    if not is_google_configured():
        raise HTTPException(
            status_code=400,
            detail="Google Ads not configured. Please set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_DEVELOPER_TOKEN.",
        )

    oauth_manager = get_oauth_manager()
    url, state = await oauth_manager.get_google_oauth_url(user_id)

    return OAuthUrlResponse(url=url, state=state, platform=AdsPlatformType.GOOGLE)


@router.get("/oauth/google/callback")
async def handle_google_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Handle Google OAuth callback.

    This endpoint is called by Google after the user authorizes our app.
    It exchanges the code for tokens and stores them in the database.
    """
    oauth_manager = get_oauth_manager()
    encryption = get_encryption_service()
    settings = get_ads_settings()

    try:
        user_id, token_data = await oauth_manager.handle_google_callback(code, state)

        # Get or create the platform record
        platform = (
            db.query(AdsPlatform)
            .filter(
                AdsPlatform.user_id == user_id,
                AdsPlatform.platform == AdsPlatformType.GOOGLE.value,
            )
            .first()
        )

        if not platform:
            platform = AdsPlatform(
                user_id=user_id,
                platform=AdsPlatformType.GOOGLE.value,
            )
            db.add(platform)
            db.flush()

        platform.is_connected = True
        platform.connection_error = None

        # Store encrypted tokens
        if platform.credentials:
            credentials = platform.credentials
        else:
            credentials = AdsCredential(platform_id=platform.id)
            db.add(credentials)

        credentials.encrypted_access_token = encryption.encrypt_cookies(
            [{"token": token_data.get("access_token")}]
        )

        if token_data.get("refresh_token"):
            credentials.encrypted_refresh_token = encryption.encrypt_cookies(
                [{"token": token_data.get("refresh_token")}]
            )

        # Calculate token expiration
        expires_in = token_data.get("expires_in", 3600)
        credentials.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        credentials.scopes = ["https://www.googleapis.com/auth/adwords"]

        db.commit()

        logger.info(f"Google OAuth completed for user {user_id}")

        # Redirect to frontend success page
        frontend_url = settings.app_base_url
        return RedirectResponse(
            url=f"{frontend_url}/ads?oauth_success=true&platform=google"
        )

    except ValueError as e:
        logger.error(f"Google OAuth error: {e}")
        frontend_url = settings.app_base_url
        import urllib.parse
        error_encoded = urllib.parse.quote(str(e))
        return RedirectResponse(
            url=f"{frontend_url}/ads?oauth_error={error_encoded}"
        )
    except Exception as e:
        logger.error(f"Google OAuth unexpected error: {e}")
        import traceback
        traceback.print_exc()
        frontend_url = settings.app_base_url
        return RedirectResponse(
            url=f"{frontend_url}/ads?oauth_error=OAuth+failed"
        )


# =============================================================================
# Platform Management
# =============================================================================


@router.get("/platforms", response_model=AdsPlatformListResponse)
async def list_platforms(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all connected ads platforms for the current user.
    """
    platforms = (
        db.query(AdsPlatform)
        .filter(AdsPlatform.user_id == user_id)
        .all()
    )

    return AdsPlatformListResponse(
        platforms=[
            AdsPlatformResponse(
                id=p.id,
                platform=AdsPlatformType(p.platform),
                account_id=p.account_id,
                account_name=p.account_name,
                is_connected=p.is_connected,
                connection_error=p.connection_error,
                created_at=p.created_at,
                last_synced_at=p.last_synced_at,
            )
            for p in platforms
        ],
        meta_configured=is_meta_configured(),
        google_configured=is_google_configured(),
    )


@router.get("/platforms/{platform_id}", response_model=AdsPlatformResponse)
async def get_platform(
    platform_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific platform by ID."""
    platform = (
        db.query(AdsPlatform)
        .filter(AdsPlatform.id == platform_id, AdsPlatform.user_id == user_id)
        .first()
    )

    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")

    return AdsPlatformResponse(
        id=platform.id,
        platform=AdsPlatformType(platform.platform),
        account_id=platform.account_id,
        account_name=platform.account_name,
        is_connected=platform.is_connected,
        connection_error=platform.connection_error,
        created_at=platform.created_at,
        last_synced_at=platform.last_synced_at,
    )


@router.delete("/platforms/{platform_id}")
async def disconnect_platform(
    platform_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Disconnect an ads platform.

    This removes the stored credentials but preserves campaign history.
    """
    platform = (
        db.query(AdsPlatform)
        .filter(AdsPlatform.id == platform_id, AdsPlatform.user_id == user_id)
        .first()
    )

    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")

    # Delete credentials
    if platform.credentials:
        db.delete(platform.credentials)

    # Mark as disconnected (keep for history)
    platform.is_connected = False
    platform.connection_error = "Disconnected by user"

    db.commit()

    return {"success": True, "message": f"Disconnected {platform.platform} ads platform"}


@router.put("/platforms/{platform_id}/account")
async def update_platform_account(
    platform_id: int,
    account_id: str = Query(..., description="New account ID to use"),
    account_name: Optional[str] = Query(None, description="Account display name"),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update the account ID for a platform.

    Use this when a user has multiple ad accounts and wants to switch.
    """
    platform = (
        db.query(AdsPlatform)
        .filter(AdsPlatform.id == platform_id, AdsPlatform.user_id == user_id)
        .first()
    )

    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")

    platform.account_id = account_id
    if account_name:
        platform.account_name = account_name

    db.commit()

    return {"success": True, "account_id": account_id}


# =============================================================================
# Campaign Management
# =============================================================================


@router.get("/campaigns", response_model=CampaignListResponse)
async def list_campaigns(
    platform_id: Optional[int] = Query(None, description="Filter by platform"),
    status: Optional[CampaignStatus] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all campaigns for the current user."""
    query = (
        db.query(AdsCampaign)
        .join(AdsPlatform)
        .filter(AdsPlatform.user_id == user_id)
    )

    if platform_id:
        query = query.filter(AdsCampaign.platform_id == platform_id)

    if status:
        query = query.filter(AdsCampaign.status == status.value)

    total = query.count()
    campaigns = query.offset(offset).limit(limit).all()

    return CampaignListResponse(
        campaigns=[
            CampaignResponse(
                id=c.id,
                platform_id=c.platform_id,
                platform=AdsPlatformType(c.platform.platform),
                external_campaign_id=c.external_campaign_id,
                name=c.name,
                campaign_type=c.campaign_type,
                objective=c.objective,
                status=CampaignStatus(c.status) if c.status else CampaignStatus.DRAFT,
                daily_budget_cents=c.daily_budget_cents,
                total_spend_cents=c.total_spend_cents or 0,
                targeting=c.targeting,
                headline=c.headline,
                description=c.description,
                destination_url=c.destination_url,
                created_at=c.created_at,
                last_synced_at=c.last_synced_at,
            )
            for c in campaigns
        ],
        total=total,
    )


@router.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(
    campaign_data: CampaignCreate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new ad campaign.

    The campaign will be created in DRAFT status locally.
    Use the /campaigns/{id}/publish endpoint to push it to the ad platform.
    """
    # Verify platform ownership
    platform = (
        db.query(AdsPlatform)
        .filter(
            AdsPlatform.id == campaign_data.platform_id,
            AdsPlatform.user_id == user_id,
        )
        .first()
    )

    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")

    if not platform.is_connected:
        raise HTTPException(status_code=400, detail="Platform is not connected")

    # Create campaign record
    campaign = AdsCampaign(
        platform_id=platform.id,
        name=campaign_data.name,
        campaign_type=campaign_data.campaign_type.value,
        objective=campaign_data.objective.value,
        status=CampaignStatus.DRAFT.value,
        daily_budget_cents=campaign_data.daily_budget_cents,
        lifetime_budget_cents=campaign_data.lifetime_budget_cents,
        targeting=campaign_data.targeting.model_dump() if campaign_data.targeting else None,
        headline=campaign_data.creative.headline,
        description=campaign_data.creative.description,
        destination_url=campaign_data.creative.destination_url,
        media_url=campaign_data.creative.media_url,
        call_to_action=campaign_data.creative.call_to_action,
    )

    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    return CampaignResponse(
        id=campaign.id,
        platform_id=campaign.platform_id,
        platform=AdsPlatformType(platform.platform),
        external_campaign_id=campaign.external_campaign_id,
        name=campaign.name,
        campaign_type=campaign.campaign_type,
        objective=campaign.objective,
        status=CampaignStatus(campaign.status),
        daily_budget_cents=campaign.daily_budget_cents,
        total_spend_cents=campaign.total_spend_cents or 0,
        targeting=campaign.targeting,
        headline=campaign.headline,
        description=campaign.description,
        destination_url=campaign.destination_url,
        created_at=campaign.created_at,
        last_synced_at=campaign.last_synced_at,
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific campaign by ID."""
    campaign = (
        db.query(AdsCampaign)
        .join(AdsPlatform)
        .filter(
            AdsCampaign.id == campaign_id,
            AdsPlatform.user_id == user_id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return CampaignResponse(
        id=campaign.id,
        platform_id=campaign.platform_id,
        platform=AdsPlatformType(campaign.platform.platform),
        external_campaign_id=campaign.external_campaign_id,
        name=campaign.name,
        campaign_type=campaign.campaign_type,
        objective=campaign.objective,
        status=CampaignStatus(campaign.status) if campaign.status else CampaignStatus.DRAFT,
        daily_budget_cents=campaign.daily_budget_cents,
        total_spend_cents=campaign.total_spend_cents or 0,
        targeting=campaign.targeting,
        headline=campaign.headline,
        description=campaign.description,
        destination_url=campaign.destination_url,
        created_at=campaign.created_at,
        last_synced_at=campaign.last_synced_at,
    )


@router.put("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    updates: CampaignUpdate,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a campaign."""
    campaign = (
        db.query(AdsCampaign)
        .join(AdsPlatform)
        .filter(
            AdsCampaign.id == campaign_id,
            AdsPlatform.user_id == user_id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Apply updates
    if updates.name is not None:
        campaign.name = updates.name
    if updates.status is not None:
        campaign.status = updates.status.value
    if updates.daily_budget_cents is not None:
        campaign.daily_budget_cents = updates.daily_budget_cents
    if updates.targeting is not None:
        campaign.targeting = updates.targeting.model_dump()

    db.commit()
    db.refresh(campaign)

    return CampaignResponse(
        id=campaign.id,
        platform_id=campaign.platform_id,
        platform=AdsPlatformType(campaign.platform.platform),
        external_campaign_id=campaign.external_campaign_id,
        name=campaign.name,
        campaign_type=campaign.campaign_type,
        objective=campaign.objective,
        status=CampaignStatus(campaign.status) if campaign.status else CampaignStatus.DRAFT,
        daily_budget_cents=campaign.daily_budget_cents,
        total_spend_cents=campaign.total_spend_cents or 0,
        targeting=campaign.targeting,
        headline=campaign.headline,
        description=campaign.description,
        destination_url=campaign.destination_url,
        created_at=campaign.created_at,
        last_synced_at=campaign.last_synced_at,
    )


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Archive a campaign.

    If the campaign is live on the platform, it will be paused first.
    """
    campaign = (
        db.query(AdsCampaign)
        .join(AdsPlatform)
        .filter(
            AdsCampaign.id == campaign_id,
            AdsPlatform.user_id == user_id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # TODO: If campaign is live, pause it on the platform first

    campaign.status = CampaignStatus.ARCHIVED.value
    db.commit()

    return {"success": True, "message": "Campaign archived"}


@router.post("/campaigns/{campaign_id}/publish")
async def publish_campaign(
    campaign_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Publish a draft campaign to the ad platform.

    This creates the campaign on Meta or Google Ads.
    The campaign will be created in PAUSED status on the platform.
    """
    campaign = (
        db.query(AdsCampaign)
        .join(AdsPlatform)
        .filter(
            AdsCampaign.id == campaign_id,
            AdsPlatform.user_id == user_id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != CampaignStatus.DRAFT.value:
        raise HTTPException(
            status_code=400,
            detail=f"Campaign is not in draft status (current: {campaign.status})",
        )

    platform = campaign.platform

    if not platform.is_connected:
        raise HTTPException(status_code=400, detail="Platform is not connected")

    if not platform.credentials:
        raise HTTPException(status_code=400, detail="Platform credentials not found")

    # Get decrypted tokens
    encryption = get_encryption_service()
    access_token_data = encryption.decrypt_cookies(
        platform.credentials.encrypted_access_token
    )
    access_token = access_token_data[0]["token"]

    try:
        if platform.platform == AdsPlatformType.META.value:
            from .clients.meta_ads import create_meta_client

            client = create_meta_client(access_token, platform.account_id)

            # Create campaign on Meta
            meta_campaign = await client.create_campaign(
                name=campaign.name,
                objective=_map_objective_to_meta(campaign.objective),
                status="PAUSED",
            )

            campaign.external_campaign_id = meta_campaign["id"]
            campaign.status = CampaignStatus.PAUSED.value

            # TODO: Create ad set and ads

        elif platform.platform == AdsPlatformType.GOOGLE.value:
            from .clients.google_ads import create_google_client

            # Get refresh token for Google
            refresh_token_data = encryption.decrypt_cookies(
                platform.credentials.encrypted_refresh_token
            )
            refresh_token = refresh_token_data[0]["token"]

            client = create_google_client(refresh_token, platform.account_id)

            # Create budget
            budget_micros = campaign.daily_budget_cents * 10000  # cents to micros
            budget_name = f"Budget - {campaign.name}"
            budget_resource = await client.create_campaign_budget(
                name=budget_name,
                amount_micros=budget_micros,
            )

            # Create Performance Max campaign
            google_campaign = await client.create_performance_max_campaign(
                name=campaign.name,
                budget_resource_name=budget_resource,
                status="PAUSED",
            )

            campaign.external_campaign_id = google_campaign["id"]
            campaign.status = CampaignStatus.PAUSED.value

            # TODO: Create asset group

        campaign.last_synced_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "external_campaign_id": campaign.external_campaign_id,
            "status": campaign.status,
        }

    except Exception as e:
        logger.error(f"Failed to publish campaign: {e}")
        import traceback
        traceback.print_exc()
        campaign.status = CampaignStatus.ERROR.value
        campaign.connection_error = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to publish campaign: {e}")


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pause an active campaign on the ad platform."""
    campaign = (
        db.query(AdsCampaign)
        .join(AdsPlatform)
        .filter(
            AdsCampaign.id == campaign_id,
            AdsPlatform.user_id == user_id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not campaign.external_campaign_id:
        raise HTTPException(status_code=400, detail="Campaign not published yet")

    platform = campaign.platform
    encryption = get_encryption_service()
    access_token_data = encryption.decrypt_cookies(
        platform.credentials.encrypted_access_token
    )
    access_token = access_token_data[0]["token"]

    try:
        if platform.platform == AdsPlatformType.META.value:
            from .clients.meta_ads import create_meta_client
            client = create_meta_client(access_token, platform.account_id)
            await client.update_campaign_status(campaign.external_campaign_id, "PAUSED")

        elif platform.platform == AdsPlatformType.GOOGLE.value:
            from .clients.google_ads import create_google_client
            refresh_token_data = encryption.decrypt_cookies(
                platform.credentials.encrypted_refresh_token
            )
            refresh_token = refresh_token_data[0]["token"]
            client = create_google_client(refresh_token, platform.account_id)

            # Build resource name
            resource_name = f"customers/{platform.account_id}/campaigns/{campaign.external_campaign_id}"
            await client.update_campaign_status(resource_name, "PAUSED")

        campaign.status = CampaignStatus.PAUSED.value
        campaign.last_synced_at = datetime.utcnow()
        db.commit()

        return {"success": True, "status": "paused"}

    except Exception as e:
        logger.error(f"Failed to pause campaign: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to pause campaign: {e}")


@router.post("/campaigns/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activate a paused campaign on the ad platform."""
    campaign = (
        db.query(AdsCampaign)
        .join(AdsPlatform)
        .filter(
            AdsCampaign.id == campaign_id,
            AdsPlatform.user_id == user_id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not campaign.external_campaign_id:
        raise HTTPException(status_code=400, detail="Campaign not published yet")

    platform = campaign.platform
    encryption = get_encryption_service()
    access_token_data = encryption.decrypt_cookies(
        platform.credentials.encrypted_access_token
    )
    access_token = access_token_data[0]["token"]

    try:
        if platform.platform == AdsPlatformType.META.value:
            from .clients.meta_ads import create_meta_client
            client = create_meta_client(access_token, platform.account_id)
            await client.update_campaign_status(campaign.external_campaign_id, "ACTIVE")

        elif platform.platform == AdsPlatformType.GOOGLE.value:
            from .clients.google_ads import create_google_client
            refresh_token_data = encryption.decrypt_cookies(
                platform.credentials.encrypted_refresh_token
            )
            refresh_token = refresh_token_data[0]["token"]
            client = create_google_client(refresh_token, platform.account_id)

            resource_name = f"customers/{platform.account_id}/campaigns/{campaign.external_campaign_id}"
            await client.update_campaign_status(resource_name, "ENABLED")

        campaign.status = CampaignStatus.ACTIVE.value
        campaign.last_synced_at = datetime.utcnow()
        db.commit()

        return {"success": True, "status": "active"}

    except Exception as e:
        logger.error(f"Failed to activate campaign: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to activate campaign: {e}")


# =============================================================================
# Metrics & Reporting
# =============================================================================


@router.get("/campaigns/{campaign_id}/metrics", response_model=CampaignMetricsResponse)
async def get_campaign_metrics(
    campaign_id: int,
    days: int = Query(7, ge=1, le=90, description="Number of days of metrics"),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get performance metrics for a campaign."""
    campaign = (
        db.query(AdsCampaign)
        .join(AdsPlatform)
        .filter(
            AdsCampaign.id == campaign_id,
            AdsPlatform.user_id == user_id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Get metrics from database
    start_date = datetime.utcnow().date() - timedelta(days=days)
    metrics = (
        db.query(AdsMetrics)
        .filter(
            AdsMetrics.campaign_id == campaign_id,
            AdsMetrics.date >= start_date,
        )
        .order_by(AdsMetrics.date)
        .all()
    )

    # Calculate totals
    total_spend = sum(m.spend_cents for m in metrics)
    total_revenue = sum(m.revenue_cents for m in metrics)
    total_impressions = sum(m.impressions for m in metrics)
    total_clicks = sum(m.clicks for m in metrics)
    total_conversions = sum(m.conversions for m in metrics)
    overall_roas = (total_revenue / total_spend) if total_spend > 0 else None

    return CampaignMetricsResponse(
        campaign_id=campaign.id,
        campaign_name=campaign.name,
        platform=AdsPlatformType(campaign.platform.platform),
        total_spend_cents=total_spend,
        total_revenue_cents=total_revenue,
        total_impressions=total_impressions,
        total_clicks=total_clicks,
        total_conversions=total_conversions,
        overall_roas=overall_roas,
        daily_metrics=[
            MetricsSnapshot(
                date=m.date,
                impressions=m.impressions,
                clicks=m.clicks,
                conversions=m.conversions,
                spend_cents=m.spend_cents,
                revenue_cents=m.revenue_cents,
                ctr=m.ctr,
                cpc_cents=m.cpc_cents,
                cpa_cents=m.cpa_cents,
                roas=m.roas,
            )
            for m in metrics
        ],
    )


@router.post("/campaigns/{campaign_id}/sync")
async def sync_campaign_metrics(
    campaign_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sync metrics from the ad platform for a campaign.

    Fetches the latest performance data and stores it locally.
    """
    campaign = (
        db.query(AdsCampaign)
        .join(AdsPlatform)
        .filter(
            AdsCampaign.id == campaign_id,
            AdsPlatform.user_id == user_id,
        )
        .first()
    )

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not campaign.external_campaign_id:
        raise HTTPException(status_code=400, detail="Campaign not published yet")

    platform = campaign.platform
    encryption = get_encryption_service()

    try:
        if platform.platform == AdsPlatformType.META.value:
            access_token_data = encryption.decrypt_cookies(
                platform.credentials.encrypted_access_token
            )
            access_token = access_token_data[0]["token"]

            from .clients.meta_ads import create_meta_client
            client = create_meta_client(access_token, platform.account_id)

            metrics = await client.get_campaign_insights(
                campaign.external_campaign_id,
                date_preset="last_7d",
            )

        elif platform.platform == AdsPlatformType.GOOGLE.value:
            refresh_token_data = encryption.decrypt_cookies(
                platform.credentials.encrypted_refresh_token
            )
            refresh_token = refresh_token_data[0]["token"]

            from .clients.google_ads import create_google_client
            client = create_google_client(refresh_token, platform.account_id)

            end_date = datetime.utcnow().strftime("%Y-%m-%d")
            start_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

            metrics = await client.get_campaign_metrics(
                campaign.external_campaign_id,
                start_date,
                end_date,
            )
        else:
            metrics = []

        # Store metrics in database
        for m in metrics:
            existing = (
                db.query(AdsMetrics)
                .filter(
                    AdsMetrics.campaign_id == campaign_id,
                    AdsMetrics.date == m.date,
                )
                .first()
            )

            if existing:
                # Update existing record
                existing.impressions = m.impressions
                existing.clicks = m.clicks
                existing.conversions = m.conversions
                existing.spend_cents = m.spend_cents
                existing.revenue_cents = m.revenue_cents
                existing.ctr = m.ctr
                existing.cpc_cents = m.cpc_cents
                existing.cpa_cents = m.cpa_cents
                existing.roas = m.roas
            else:
                # Create new record
                new_metric = AdsMetrics(
                    campaign_id=campaign_id,
                    date=m.date,
                    impressions=m.impressions,
                    clicks=m.clicks,
                    conversions=m.conversions,
                    spend_cents=m.spend_cents,
                    revenue_cents=m.revenue_cents,
                    ctr=m.ctr,
                    cpc_cents=m.cpc_cents,
                    cpa_cents=m.cpa_cents,
                    roas=m.roas,
                )
                db.add(new_metric)

        # Update total spend on campaign
        total_spend = sum(m.spend_cents for m in metrics)
        campaign.total_spend_cents = (campaign.total_spend_cents or 0) + total_spend
        campaign.last_synced_at = datetime.utcnow()

        db.commit()

        return {
            "success": True,
            "synced_days": len(metrics),
            "last_synced_at": campaign.last_synced_at.isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to sync metrics: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to sync metrics: {e}")


@router.get("/reports/weekly", response_model=WeeklyReportResponse)
async def get_weekly_report(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a plain-language weekly performance report.

    Aggregates data from all campaigns across all platforms.
    """
    # Get date range
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=7)

    # Get all metrics for this user's campaigns in the date range
    metrics = (
        db.query(AdsMetrics)
        .join(AdsCampaign)
        .join(AdsPlatform)
        .filter(
            AdsPlatform.user_id == user_id,
            AdsMetrics.date >= start_date,
            AdsMetrics.date <= end_date,
        )
        .all()
    )

    # Aggregate metrics
    total_spend_cents = sum(m.spend_cents for m in metrics)
    total_revenue_cents = sum(m.revenue_cents for m in metrics)
    total_impressions = sum(m.impressions for m in metrics)
    total_conversions = sum(m.conversions for m in metrics)

    total_spend = total_spend_cents / 100
    total_revenue = total_revenue_cents / 100
    roas = (total_revenue / total_spend) if total_spend > 0 else None

    # Find best performing platform
    platform_spend = {}
    platform_revenue = {}
    for m in metrics:
        platform = m.campaign.platform.platform
        platform_spend[platform] = platform_spend.get(platform, 0) + m.spend_cents
        platform_revenue[platform] = platform_revenue.get(platform, 0) + m.revenue_cents

    best_platform = None
    best_roas = 0
    for platform, spend in platform_spend.items():
        if spend > 0:
            platform_roas = platform_revenue.get(platform, 0) / spend
            if platform_roas > best_roas:
                best_roas = platform_roas
                best_platform = platform

    # Generate plain language summary
    if total_spend == 0:
        summary = "No ad spend this week. Consider activating your campaigns!"
    elif roas and roas >= 2:
        summary = f"Great week! You spent ${total_spend:.2f} and made ${total_revenue:.2f} - that's ${roas:.2f} back for every dollar spent."
    elif roas and roas >= 1:
        summary = f"Solid week. You spent ${total_spend:.2f} and made ${total_revenue:.2f}. You're profitable but there's room to optimize."
    else:
        summary = f"This week cost ${total_spend:.2f} with ${total_revenue:.2f} in revenue. Let's review your targeting and creatives to improve performance."

    # AI insight (placeholder - would use Claude in production)
    ai_insight = None
    if total_conversions > 0 and total_spend > 0:
        cpa = total_spend / total_conversions
        if cpa < 50:
            ai_insight = f"Your cost per customer (${cpa:.2f}) is excellent. Consider increasing your budget to acquire more customers."
        elif cpa < 100:
            ai_insight = f"Your cost per customer (${cpa:.2f}) is reasonable. Try testing new ad creatives to bring it down."
        else:
            ai_insight = f"Your cost per customer (${cpa:.2f}) is high. Consider narrowing your targeting or refreshing your ad creative."

    return WeeklyReportResponse(
        period_start=start_date,
        period_end=end_date,
        total_spend=total_spend,
        total_revenue=total_revenue,
        new_customers=total_conversions,
        impressions=total_impressions,
        roas=roas,
        best_platform=best_platform,
        best_campaign=None,  # TODO: Calculate best campaign
        ai_insight=ai_insight,
        plain_language_summary=summary,
    )


# =============================================================================
# Asset Management - Pydantic Models
# =============================================================================


class AssetUploadRequest(BaseModel):
    """Request to create a new asset."""
    name: str = Field(..., min_length=1, max_length=100)
    file_url: str = Field(..., description="URL of the uploaded file")
    asset_type: str = Field("other", description="Type: logo, product, background, other")
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class AssetResponse(BaseModel):
    """Response for a single asset."""
    id: int
    name: str
    asset_type: str
    description: Optional[str] = None
    file_url: str
    thumbnail_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    is_active: bool
    created_at: datetime


class AssetListResponse(BaseModel):
    """Response for listing assets."""
    assets: List[AssetResponse]
    total: int


class ImageGenerateRequest(BaseModel):
    """Request to generate an AI image."""
    prompt: str = Field(..., min_length=1)
    asset_ids: Optional[List[int]] = Field(None, description="Asset IDs to use as input")
    aspect_ratio: str = Field("1:1", description="1:1, 16:9, 9:16, 4:3, 3:4, 4:5, 5:4, 21:9, 9:21")
    resolution: str = Field("1k", description="1k or 2k")
    campaign_id: Optional[int] = Field(None, description="Campaign to link to")
    wait_for_completion: bool = Field(True, description="Wait for generation to complete")


class ImageJobResponse(BaseModel):
    """Response for an image generation job."""
    id: int
    prompt: str
    aspect_ratio: str
    resolution: str
    input_asset_ids: List[int]
    status: str
    result_url: Optional[str] = None
    error_message: Optional[str] = None
    campaign_id: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class ImageJobListResponse(BaseModel):
    """Response for listing image jobs."""
    jobs: List[ImageJobResponse]
    total: int


# =============================================================================
# Asset Management Endpoints
# =============================================================================


@router.post("/assets", response_model=AssetResponse)
async def create_asset(
    asset_data: AssetUploadRequest,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new brand asset record.

    The file should already be uploaded to cloud storage.
    This creates the database record linking the user to the asset.
    """
    asset = UserAsset(
        user_id=user_id,
        name=asset_data.name,
        asset_type=asset_data.asset_type,
        description=asset_data.description,
        file_url=asset_data.file_url,
        thumbnail_url=asset_data.thumbnail_url,
        file_size_bytes=asset_data.file_size_bytes,
        mime_type=asset_data.mime_type,
        width=asset_data.width,
        height=asset_data.height,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    logger.info(f"Created asset {asset.id} ({asset.name}) for user {user_id}")

    return AssetResponse(
        id=asset.id,
        name=asset.name,
        asset_type=asset.asset_type,
        description=asset.description,
        file_url=asset.file_url,
        thumbnail_url=asset.thumbnail_url,
        file_size_bytes=asset.file_size_bytes,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        is_active=asset.is_active,
        created_at=asset.created_at,
    )


@router.get("/assets", response_model=AssetListResponse)
async def list_assets(
    asset_type: Optional[str] = Query(None, description="Filter by type: logo, product, background, other"),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all brand assets for the current user.
    """
    query = db.query(UserAsset).filter(
        UserAsset.user_id == user_id,
        UserAsset.is_active == True,
    )

    if asset_type:
        query = query.filter(UserAsset.asset_type == asset_type)

    assets = query.order_by(UserAsset.created_at.desc()).all()

    return AssetListResponse(
        assets=[
            AssetResponse(
                id=a.id,
                name=a.name,
                asset_type=a.asset_type,
                description=a.description,
                file_url=a.file_url,
                thumbnail_url=a.thumbnail_url,
                file_size_bytes=a.file_size_bytes,
                mime_type=a.mime_type,
                width=a.width,
                height=a.height,
                is_active=a.is_active,
                created_at=a.created_at,
            )
            for a in assets
        ],
        total=len(assets),
    )


@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific asset by ID."""
    asset = (
        db.query(UserAsset)
        .filter(UserAsset.id == asset_id, UserAsset.user_id == user_id)
        .first()
    )

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    return AssetResponse(
        id=asset.id,
        name=asset.name,
        asset_type=asset.asset_type,
        description=asset.description,
        file_url=asset.file_url,
        thumbnail_url=asset.thumbnail_url,
        file_size_bytes=asset.file_size_bytes,
        mime_type=asset.mime_type,
        width=asset.width,
        height=asset.height,
        is_active=asset.is_active,
        created_at=asset.created_at,
    )


@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete an asset (soft delete - marks as inactive).
    """
    asset = (
        db.query(UserAsset)
        .filter(UserAsset.id == asset_id, UserAsset.user_id == user_id)
        .first()
    )

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset.is_active = False
    db.commit()

    logger.info(f"Deleted asset {asset_id} for user {user_id}")
    return {"success": True, "message": "Asset deleted"}


# =============================================================================
# Image Generation Endpoints
# =============================================================================


@router.post("/generate-image", response_model=ImageJobResponse)
async def generate_image(
    request: ImageGenerateRequest,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate an AI image using Nano Banana Pro.

    Optionally provide asset IDs to use as reference images.
    Set wait_for_completion=false to return immediately with a pending job.
    """
    from .clients.nano_banana import is_nano_banana_configured
    from .services.image_generation import get_image_generation_service

    if not is_nano_banana_configured():
        raise HTTPException(
            status_code=400,
            detail="Image generation not configured. Please set KIE_API_KEY.",
        )

    # Validate aspect ratio
    valid_ratios = ["1:1", "16:9", "9:16", "4:3", "3:4", "4:5", "5:4", "21:9", "9:21"]
    if request.aspect_ratio not in valid_ratios:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid aspect_ratio. Must be one of: {valid_ratios}",
        )

    # Validate resolution
    if request.resolution not in ["1k", "2k"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid resolution. Must be '1k' or '2k'",
        )

    # Validate asset IDs belong to user
    if request.asset_ids:
        assets = (
            db.query(UserAsset)
            .filter(
                UserAsset.id.in_(request.asset_ids),
                UserAsset.user_id == user_id,
                UserAsset.is_active == True,
            )
            .all()
        )
        if len(assets) != len(request.asset_ids):
            raise HTTPException(
                status_code=400,
                detail="Some asset IDs not found or not owned by user",
            )

    # Validate campaign belongs to user
    if request.campaign_id:
        campaign = (
            db.query(AdsCampaign)
            .join(AdsPlatform)
            .filter(
                AdsCampaign.id == request.campaign_id,
                AdsPlatform.user_id == user_id,
            )
            .first()
        )
        if not campaign:
            raise HTTPException(
                status_code=400,
                detail="Campaign not found or not owned by user",
            )

    try:
        service = get_image_generation_service(db=db)
        job = await service.generate_image(
            user_id=user_id,
            prompt=request.prompt,
            asset_ids=request.asset_ids,
            aspect_ratio=request.aspect_ratio,
            resolution=request.resolution,
            campaign_id=request.campaign_id,
            wait_for_completion=request.wait_for_completion,
        )
        await service.close()

        return ImageJobResponse(
            id=job.id,
            prompt=job.prompt,
            aspect_ratio=job.aspect_ratio,
            resolution=job.resolution,
            input_asset_ids=job.input_asset_ids or [],
            status=job.status,
            result_url=job.result_url,
            error_message=job.error_message,
            campaign_id=job.campaign_id,
            created_at=job.created_at,
            completed_at=job.completed_at,
        )

    except TimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e))
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Image generation failed: {e}")


@router.get("/image-jobs", response_model=ImageJobListResponse)
async def list_image_jobs(
    status: Optional[str] = Query(None, description="Filter by status: pending, processing, completed, failed"),
    limit: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List image generation jobs for the current user.
    """
    query = db.query(ImageGenerationJob).filter(ImageGenerationJob.user_id == user_id)

    if status:
        query = query.filter(ImageGenerationJob.status == status)

    jobs = query.order_by(ImageGenerationJob.created_at.desc()).limit(limit).all()

    return ImageJobListResponse(
        jobs=[
            ImageJobResponse(
                id=j.id,
                prompt=j.prompt,
                aspect_ratio=j.aspect_ratio,
                resolution=j.resolution,
                input_asset_ids=j.input_asset_ids or [],
                status=j.status,
                result_url=j.result_url,
                error_message=j.error_message,
                campaign_id=j.campaign_id,
                created_at=j.created_at,
                completed_at=j.completed_at,
            )
            for j in jobs
        ],
        total=len(jobs),
    )


@router.get("/image-jobs/{job_id}", response_model=ImageJobResponse)
async def get_image_job(
    job_id: int,
    refresh: bool = Query(False, description="Check with API for status update"),
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a specific image generation job.

    Use refresh=true to check the Kie.ai API for status updates.
    """
    job = (
        db.query(ImageGenerationJob)
        .filter(ImageGenerationJob.id == job_id, ImageGenerationJob.user_id == user_id)
        .first()
    )

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Refresh status from API if requested and job is still processing
    if refresh and job.status in ["pending", "processing"]:
        from .services.image_generation import get_image_generation_service

        service = get_image_generation_service(db=db)
        job = await service.check_job_status(job_id, user_id)
        await service.close()

    return ImageJobResponse(
        id=job.id,
        prompt=job.prompt,
        aspect_ratio=job.aspect_ratio,
        resolution=job.resolution,
        input_asset_ids=job.input_asset_ids or [],
        status=job.status,
        result_url=job.result_url,
        error_message=job.error_message,
        campaign_id=job.campaign_id,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _map_objective_to_meta(objective: str) -> str:
    """Map internal objective to Meta campaign objective."""
    mapping = {
        "conversions": "OUTCOME_SALES",
        "traffic": "OUTCOME_TRAFFIC",
        "awareness": "OUTCOME_AWARENESS",
        "engagement": "OUTCOME_ENGAGEMENT",
        "leads": "OUTCOME_LEADS",
    }
    return mapping.get(objective, "OUTCOME_SALES")


def _map_objective_to_google(objective: str) -> str:
    """Map internal objective to Google bidding strategy."""
    # For Performance Max, we primarily use conversions-based bidding
    return "MAXIMIZE_CONVERSIONS"
