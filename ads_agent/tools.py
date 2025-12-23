"""
Tools for Ads Deep Agent.

These wrap the ads_service/database APIs for use by subagents.
All tools are async and use the @tool decorator from langchain_core.
"""

import logging
from typing import Optional
from datetime import datetime
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# =============================================================================
# CAMPAIGN CREATION TOOLS
# =============================================================================


@tool
async def create_meta_campaign_tool(
    user_id: str,
    name: str,
    headline: str,
    description: str,
    destination_url: str,
    daily_budget_cents: int,
    targeting: dict,
    call_to_action: str = "LEARN_MORE",
) -> dict:
    """
    Create a Meta (Facebook/Instagram) campaign in DRAFT status.

    Does NOT publish to Facebook yet - just saves to database.
    Call publish_campaign_tool to push to Meta.

    Args:
        user_id: The Clerk user ID
        name: Campaign name
        headline: Ad headline (max 40 chars)
        description: Ad description/primary text (max 125 chars)
        destination_url: Landing page URL
        daily_budget_cents: Daily budget in cents (e.g., 2000 = $20)
        targeting: Targeting config dict with countries, cities, age_min, age_max, etc.
        call_to_action: CTA type (LEARN_MORE, SHOP_NOW, GET_OFFER, ORDER_NOW, etc.)

    Returns:
        dict with campaign_id, platform, status, name
    """
    from database.database import SessionLocal
    from database.models import AdsPlatform, AdsCampaign

    db = SessionLocal()
    try:
        # Get connected Meta platform for this user
        platform = (
            db.query(AdsPlatform)
            .filter(
                AdsPlatform.user_id == user_id,
                AdsPlatform.platform == "meta",
                AdsPlatform.is_connected == True,
            )
            .first()
        )

        if not platform:
            return {
                "error": "Meta Ads not connected. Please connect your Meta Ads account first.",
                "success": False,
            }

        # Store call_to_action in targeting since model doesn't have that field
        targeting_with_cta = {**targeting, "call_to_action": call_to_action}

        # Create campaign record in DRAFT status
        campaign = AdsCampaign(
            platform_id=platform.id,
            name=name,
            campaign_type="advantage_plus",
            objective="conversions",
            status="draft",
            daily_budget_cents=daily_budget_cents,
            targeting=targeting_with_cta,
            headline=headline,
            description=description,
            destination_url=destination_url,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)

        logger.info(f"Created Meta campaign draft: {campaign.id} for user {user_id}")

        return {
            "success": True,
            "campaign_id": campaign.id,
            "platform": "meta",
            "status": "draft",
            "name": name,
            "headline": headline,
            "daily_budget_cents": daily_budget_cents,
        }
    except Exception as e:
        logger.error(f"Error creating Meta campaign: {e}")
        db.rollback()
        return {"error": str(e), "success": False}
    finally:
        db.close()


@tool
async def create_google_campaign_tool(
    user_id: str,
    name: str,
    headline: str,
    description: str,
    destination_url: str,
    daily_budget_cents: int,
    targeting: dict,
) -> dict:
    """
    Create a Google Performance Max campaign in DRAFT status.

    Does NOT publish to Google yet - just saves to database.
    Call publish_campaign_tool to push to Google.

    Args:
        user_id: The Clerk user ID
        name: Campaign name
        headline: Ad headline
        description: Ad description
        destination_url: Landing page URL
        daily_budget_cents: Daily budget in cents (e.g., 2000 = $20)
        targeting: Targeting config dict

    Returns:
        dict with campaign_id, platform, status, name
    """
    from database.database import SessionLocal
    from database.models import AdsPlatform, AdsCampaign

    db = SessionLocal()
    try:
        # Get connected Google platform for this user
        platform = (
            db.query(AdsPlatform)
            .filter(
                AdsPlatform.user_id == user_id,
                AdsPlatform.platform == "google",
                AdsPlatform.is_connected == True,
            )
            .first()
        )

        if not platform:
            return {
                "error": "Google Ads not connected. Please connect your Google Ads account first.",
                "success": False,
            }

        # Create campaign record in DRAFT status
        campaign = AdsCampaign(
            platform_id=platform.id,
            name=name,
            campaign_type="performance_max",
            objective="conversions",
            status="draft",
            daily_budget_cents=daily_budget_cents,
            targeting=targeting,
            headline=headline,
            description=description,
            destination_url=destination_url,
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)

        logger.info(f"Created Google campaign draft: {campaign.id} for user {user_id}")

        return {
            "success": True,
            "campaign_id": campaign.id,
            "platform": "google",
            "status": "draft",
            "name": name,
            "headline": headline,
            "daily_budget_cents": daily_budget_cents,
        }
    except Exception as e:
        logger.error(f"Error creating Google campaign: {e}")
        db.rollback()
        return {"error": str(e), "success": False}
    finally:
        db.close()


# =============================================================================
# CAMPAIGN PUBLISHING TOOLS
# =============================================================================


@tool
async def publish_campaign_tool(campaign_id: int) -> dict:
    """
    Publish a draft campaign to the ad platform (Meta or Google).

    Creates the campaign on the platform in PAUSED status.
    User must call activate_campaign_tool to make it live.

    Args:
        campaign_id: The database campaign ID

    Returns:
        dict with success, external_campaign_id, status
    """
    from database.database import SessionLocal
    from database.models import AdsCampaign, AdsPlatform, AdsCredential

    db = SessionLocal()
    try:
        # Get the campaign
        campaign = db.query(AdsCampaign).filter(AdsCampaign.id == campaign_id).first()
        if not campaign:
            return {"error": f"Campaign {campaign_id} not found", "success": False}

        if campaign.status != "draft":
            return {
                "error": f"Campaign is not in draft status (current: {campaign.status})",
                "success": False,
            }

        # Get platform and credentials
        platform = (
            db.query(AdsPlatform).filter(AdsPlatform.id == campaign.platform_id).first()
        )
        if not platform:
            return {"error": "Platform not found", "success": False}

        credential = (
            db.query(AdsCredential)
            .filter(AdsCredential.platform_id == platform.id)
            .first()
        )
        if not credential:
            return {"error": "No credentials found for platform", "success": False}

        # Decrypt credentials
        from ads_service.routes import TokenEncryptionService

        encryption = TokenEncryptionService()
        access_token = encryption.decrypt_token(credential.encrypted_access_token)
        refresh_token = (
            encryption.decrypt_token(credential.encrypted_refresh_token)
            if credential.encrypted_refresh_token
            else None
        )

        external_campaign_id = None

        if platform.platform == "meta":
            # Publish to Meta
            from ads_service.clients.meta_ads import create_meta_client

            client = create_meta_client(access_token, platform.account_id)

            # Create campaign on Meta
            result = await client.create_campaign(
                name=campaign.name,
                objective="OUTCOME_SALES",
                status="PAUSED",
            )
            external_campaign_id = result.get("id")

            # Create ad set with targeting
            targeting_data = campaign.targeting or {}
            from ads_service.models import CampaignTargeting

            targeting_obj = CampaignTargeting(
                countries=targeting_data.get("countries", ["US"]),
                cities=targeting_data.get("cities"),
                age_min=targeting_data.get("age_min", 18),
                age_max=targeting_data.get("age_max", 65),
            )

            ad_set_result = await client.create_ad_set(
                campaign_id=external_campaign_id,
                name=f"{campaign.name} - Ad Set",
                daily_budget_cents=campaign.daily_budget_cents,
                targeting=targeting_obj,
                status="PAUSED",
            )
            campaign.external_ad_set_id = ad_set_result.get("id")

        elif platform.platform == "google":
            # Publish to Google
            from ads_service.clients.google_ads import create_google_client

            client = create_google_client(refresh_token, platform.account_id)

            # Create budget
            budget_resource = await client.create_campaign_budget(
                name=f"{campaign.name} Budget",
                amount_micros=campaign.daily_budget_cents * 10000,  # cents to micros
            )

            # Create Performance Max campaign
            result = await client.create_performance_max_campaign(
                name=campaign.name,
                budget_resource_name=budget_resource,
                status="PAUSED",
            )
            external_campaign_id = result.get("id")

        # Update campaign record
        campaign.external_campaign_id = external_campaign_id
        campaign.status = "paused"
        db.commit()

        logger.info(
            f"Published campaign {campaign_id} to {platform.platform}: {external_campaign_id}"
        )

        return {
            "success": True,
            "campaign_id": campaign_id,
            "external_campaign_id": external_campaign_id,
            "platform": platform.platform,
            "status": "paused",
        }

    except Exception as e:
        logger.error(f"Error publishing campaign: {e}")
        db.rollback()
        return {"error": str(e), "success": False}
    finally:
        db.close()


@tool
async def activate_campaign_tool(campaign_id: int) -> dict:
    """
    Activate a published campaign (change from PAUSED to ACTIVE).

    This makes the campaign LIVE and starts spending budget.
    Only call after user explicitly approves.

    Args:
        campaign_id: The database campaign ID

    Returns:
        dict with success, status confirmation
    """
    from database.database import SessionLocal
    from database.models import AdsCampaign, AdsPlatform, AdsCredential

    db = SessionLocal()
    try:
        # Get the campaign
        campaign = db.query(AdsCampaign).filter(AdsCampaign.id == campaign_id).first()
        if not campaign:
            return {"error": f"Campaign {campaign_id} not found", "success": False}

        if campaign.status != "paused":
            return {
                "error": f"Campaign must be in paused status to activate (current: {campaign.status})",
                "success": False,
            }

        if not campaign.external_campaign_id:
            return {
                "error": "Campaign has not been published yet. Call publish_campaign first.",
                "success": False,
            }

        # Get platform and credentials
        platform = (
            db.query(AdsPlatform).filter(AdsPlatform.id == campaign.platform_id).first()
        )
        credential = (
            db.query(AdsCredential)
            .filter(AdsCredential.platform_id == platform.id)
            .first()
        )

        from ads_service.routes import TokenEncryptionService

        encryption = TokenEncryptionService()
        access_token = encryption.decrypt_token(credential.encrypted_access_token)
        refresh_token = (
            encryption.decrypt_token(credential.encrypted_refresh_token)
            if credential.encrypted_refresh_token
            else None
        )

        if platform.platform == "meta":
            from ads_service.clients.meta_ads import create_meta_client

            client = create_meta_client(access_token, platform.account_id)
            await client.update_campaign_status(
                campaign.external_campaign_id, "ACTIVE"
            )

        elif platform.platform == "google":
            from ads_service.clients.google_ads import create_google_client

            client = create_google_client(refresh_token, platform.account_id)
            # Google uses resource name format
            resource_name = f"customers/{platform.account_id}/campaigns/{campaign.external_campaign_id}"
            await client.update_campaign_status(resource_name, "ENABLED")

        # Update local status
        campaign.status = "active"
        campaign.started_at = datetime.utcnow()
        db.commit()

        logger.info(f"Activated campaign {campaign_id} on {platform.platform}")

        return {
            "success": True,
            "campaign_id": campaign_id,
            "external_campaign_id": campaign.external_campaign_id,
            "platform": platform.platform,
            "status": "active",
            "message": f"Campaign is now LIVE on {platform.platform.title()}!",
        }

    except Exception as e:
        logger.error(f"Error activating campaign: {e}")
        db.rollback()
        return {"error": str(e), "success": False}
    finally:
        db.close()


# =============================================================================
# READ-ONLY CONTEXT TOOLS
# =============================================================================


@tool
def get_user_platforms_tool(user_id: str) -> dict:
    """
    Get all connected ad platforms for a user.

    Args:
        user_id: The Clerk user ID

    Returns:
        dict with list of connected platforms
    """
    from database.database import SessionLocal
    from database.models import AdsPlatform

    db = SessionLocal()
    try:
        platforms = (
            db.query(AdsPlatform)
            .filter(AdsPlatform.user_id == user_id, AdsPlatform.is_connected == True)
            .all()
        )

        result = []
        for p in platforms:
            result.append(
                {
                    "id": p.id,
                    "platform": p.platform,
                    "account_id": p.account_id,
                    "account_name": p.account_name,
                    "is_connected": p.is_connected,
                }
            )

        return {
            "success": True,
            "platforms": result,
            "has_meta": any(p["platform"] == "meta" for p in result),
            "has_google": any(p["platform"] == "google" for p in result),
        }
    except Exception as e:
        return {"error": str(e), "success": False}
    finally:
        db.close()


@tool
def get_user_campaigns_tool(user_id: str, status: Optional[str] = None) -> dict:
    """
    Get campaigns for a user, optionally filtered by status.

    Args:
        user_id: The Clerk user ID
        status: Optional filter (draft, active, paused, archived)

    Returns:
        dict with list of campaigns
    """
    from database.database import SessionLocal
    from database.models import AdsPlatform, AdsCampaign

    db = SessionLocal()
    try:
        # Get user's platforms
        platform_ids = (
            db.query(AdsPlatform.id)
            .filter(AdsPlatform.user_id == user_id)
            .subquery()
        )

        # Query campaigns
        query = db.query(AdsCampaign).filter(
            AdsCampaign.platform_id.in_(platform_ids)
        )

        if status:
            query = query.filter(AdsCampaign.status == status)

        campaigns = query.order_by(AdsCampaign.created_at.desc()).limit(50).all()

        result = []
        for c in campaigns:
            platform = db.query(AdsPlatform).filter(AdsPlatform.id == c.platform_id).first()
            result.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "platform": platform.platform if platform else "unknown",
                    "status": c.status,
                    "headline": c.headline,
                    "daily_budget_cents": c.daily_budget_cents,
                    "external_campaign_id": c.external_campaign_id,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
            )

        return {"success": True, "campaigns": result, "count": len(result)}
    except Exception as e:
        return {"error": str(e), "success": False}
    finally:
        db.close()


# =============================================================================
# TOOL FACTORY FUNCTIONS (for runtime binding)
# =============================================================================


def create_business_context_tool(user_id: str):
    """Create a tool that returns the user's business context from memory."""

    @tool
    def get_business_context() -> dict:
        """
        Get the business context and preferences for ad targeting.

        Returns business name, type, location, default budget, and targeting defaults.
        """
        # This will be called at runtime with access to the store
        # For now, return a placeholder - the actual implementation
        # will use runtime.store in the subagent
        return {
            "message": "Use the AdsUserMemory class with runtime.store to get preferences",
            "user_id": user_id,
        }

    return get_business_context


def create_connected_platforms_tool(user_id: str):
    """Create a tool that returns connected platforms for a specific user."""

    @tool
    def get_connected_platforms() -> dict:
        """
        Get connected ad platforms for this user.

        Returns which platforms (Meta, Google) are connected and ready for campaigns.
        """
        return get_user_platforms_tool.invoke({"user_id": user_id})

    return get_connected_platforms


# =============================================================================
# ASSET & IMAGE GENERATION TOOLS
# =============================================================================


@tool
def get_user_assets_tool(user_id: str, asset_type: Optional[str] = None) -> dict:
    """
    Get all brand assets for a user.

    Brand assets include logos, product photos, and background images
    that can be used as inputs for AI image generation.

    Args:
        user_id: The Clerk user ID
        asset_type: Optional filter by type (logo, product, background, other)

    Returns:
        dict with list of assets including URLs and metadata
    """
    from database.database import SessionLocal
    from database.models import UserAsset

    db = SessionLocal()
    try:
        query = db.query(UserAsset).filter(
            UserAsset.user_id == user_id,
            UserAsset.is_active == True,
        )

        if asset_type:
            query = query.filter(UserAsset.asset_type == asset_type)

        assets = query.order_by(UserAsset.created_at.desc()).all()

        result = []
        for a in assets:
            result.append({
                "id": a.id,
                "name": a.name,
                "asset_type": a.asset_type,
                "file_url": a.file_url,
                "thumbnail_url": a.thumbnail_url,
                "width": a.width,
                "height": a.height,
                "description": a.description,
            })

        # Group by type for easier reference
        logos = [a for a in result if a["asset_type"] == "logo"]
        products = [a for a in result if a["asset_type"] == "product"]
        backgrounds = [a for a in result if a["asset_type"] == "background"]
        other = [a for a in result if a["asset_type"] == "other"]

        return {
            "success": True,
            "assets": result,
            "count": len(result),
            "logos": logos,
            "products": products,
            "backgrounds": backgrounds,
            "other": other,
        }
    except Exception as e:
        logger.error(f"Error getting user assets: {e}")
        return {"error": str(e), "success": False}
    finally:
        db.close()


@tool
async def generate_ad_image_tool(
    user_id: str,
    prompt: str,
    asset_ids: Optional[list] = None,
    aspect_ratio: str = "1:1",
    resolution: str = "1k",
    campaign_id: Optional[int] = None,
) -> dict:
    """
    Generate an AI-powered ad image using Nano Banana Pro.

    Uses the user's brand assets (logo, product photos) as reference
    to create a cohesive, branded ad image.

    Args:
        user_id: The Clerk user ID
        prompt: Text description of the image to generate
        asset_ids: Optional list of UserAsset IDs to use as references
        aspect_ratio: Output aspect ratio (1:1, 16:9, 9:16, 4:3, 3:4, 4:5, 5:4, 21:9, 9:21)
        resolution: Output resolution (1k or 2k)
        campaign_id: Optional campaign ID to link the generated image to

    Returns:
        dict with job_id, status, result_url (when complete), or error
    """
    from database.database import SessionLocal
    from database.models import UserAsset, ImageGenerationJob, AdsCampaign
    from ads_service.clients.nano_banana import is_nano_banana_configured, get_nano_banana_client

    if not is_nano_banana_configured():
        return {
            "success": False,
            "error": "Image generation not configured. Please set KIE_API_KEY environment variable.",
        }

    db = SessionLocal()
    try:
        # Validate asset IDs belong to user
        image_inputs = []
        if asset_ids:
            assets = (
                db.query(UserAsset)
                .filter(
                    UserAsset.id.in_(asset_ids),
                    UserAsset.user_id == user_id,
                    UserAsset.is_active == True,
                )
                .all()
            )
            if len(assets) != len(asset_ids):
                return {
                    "success": False,
                    "error": "Some asset IDs not found or not owned by user",
                }
            image_inputs = [a.file_url for a in assets]

        # Create the job record
        job = ImageGenerationJob(
            user_id=user_id,
            campaign_id=campaign_id,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            input_asset_ids=asset_ids or [],
            status="pending",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        logger.info(f"Created image generation job {job.id} for user {user_id}")

        # Call the API
        try:
            client = get_nano_banana_client()

            # Generate and wait for completion
            result = await client.generate_and_wait(
                prompt=prompt,
                image_inputs=image_inputs if image_inputs else None,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                max_wait_seconds=120,
            )

            await client.close()

            # Update job with result
            job.external_task_id = result.get("taskId")
            job.status = "completed"
            job.result_url = result.get("result") or result.get("imageUrl")
            from datetime import datetime
            job.completed_at = datetime.utcnow()

            # Update campaign media_url if linked
            if campaign_id and job.result_url:
                campaign = db.query(AdsCampaign).filter(AdsCampaign.id == campaign_id).first()
                if campaign:
                    campaign.media_url = job.result_url
                    logger.info(f"Updated campaign {campaign_id} with generated image")

            db.commit()

            return {
                "success": True,
                "job_id": job.id,
                "status": "completed",
                "result_url": job.result_url,
                "prompt": prompt,
                "message": "Image generated successfully!",
            }

        except TimeoutError as e:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
            return {
                "success": False,
                "job_id": job.id,
                "error": f"Image generation timed out: {e}",
            }

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
            logger.error(f"Image generation failed for job {job.id}: {e}")
            return {
                "success": False,
                "job_id": job.id,
                "error": str(e),
            }

    except Exception as e:
        logger.error(f"Error creating image generation job: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def create_user_assets_tool(user_id: str):
    """Create a tool that returns assets for a specific user."""

    @tool
    def get_my_assets(asset_type: Optional[str] = None) -> dict:
        """
        Get my brand assets for ad image generation.

        Returns logos, product photos, and other assets that can be used
        as references for AI-generated ad images.

        Args:
            asset_type: Optional filter (logo, product, background, other)
        """
        return get_user_assets_tool.invoke({"user_id": user_id, "asset_type": asset_type})

    return get_my_assets
