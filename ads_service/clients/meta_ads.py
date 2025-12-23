"""
Meta Ads API Client

Async wrapper around the facebook-business SDK for Meta Marketing API.
Handles campaign creation, management, and metrics fetching.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from functools import partial

from ..config import get_ads_settings, is_meta_configured
from ..models import (
    CampaignCreate,
    CampaignUpdate,
    CampaignTargeting,
    MetricsSnapshot,
    CampaignStatus,
)

logger = logging.getLogger(__name__)


class MetaAdsClient:
    """
    Client for Meta Marketing API (Facebook/Instagram Ads).

    Uses the facebook-business SDK for API calls.
    All methods are async-compatible for use with FastAPI.
    """

    def __init__(self, access_token: str, ad_account_id: str):
        """
        Initialize the Meta Ads client.

        Args:
            access_token: System User access token or user access token
            ad_account_id: Ad Account ID (without 'act_' prefix)
        """
        self.access_token = access_token
        self.ad_account_id = ad_account_id
        self._initialized = False
        self._api = None
        self._ad_account = None

    async def _ensure_initialized(self):
        """Lazily initialize the SDK (import is slow)."""
        if self._initialized:
            return

        # Import SDK lazily to avoid slow startup
        try:
            from facebook_business.api import FacebookAdsApi
            from facebook_business.adobjects.adaccount import AdAccount

            settings = get_ads_settings()

            # Initialize the API
            self._api = FacebookAdsApi.init(
                app_id=settings.meta_app_id,
                app_secret=settings.meta_app_secret,
                access_token=self.access_token,
                api_version=settings.meta_api_version,
            )

            # Get the ad account
            self._ad_account = AdAccount(f"act_{self.ad_account_id}")
            self._initialized = True

            logger.info(f"Meta Ads client initialized for account {self.ad_account_id}")

        except ImportError:
            raise RuntimeError(
                "facebook-business SDK not installed. Run: pip install facebook-business"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Meta Ads client: {e}")
            raise

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous SDK function in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    # =========================================================================
    # Account Management
    # =========================================================================

    async def get_account_info(self) -> Dict[str, Any]:
        """Get ad account information."""
        await self._ensure_initialized()

        def _get_info():
            fields = [
                "name",
                "account_id",
                "account_status",
                "currency",
                "timezone_name",
                "spend_cap",
                "amount_spent",
            ]
            return self._ad_account.api_get(fields=fields)

        result = await self._run_sync(_get_info)
        return dict(result)

    async def get_pages(self) -> List[Dict[str, Any]]:
        """Get Facebook Pages connected to this ad account."""
        await self._ensure_initialized()

        def _get_pages():
            from facebook_business.adobjects.page import Page

            pages = self._ad_account.get_promoted_objects(
                fields=["id", "name", "access_token"]
            )
            return [dict(p) for p in pages]

        return await self._run_sync(_get_pages)

    # =========================================================================
    # Campaign Management
    # =========================================================================

    async def create_campaign(
        self,
        name: str,
        objective: str = "OUTCOME_SALES",
        status: str = "PAUSED",
        special_ad_categories: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new campaign.

        Args:
            name: Campaign name
            objective: Campaign objective (OUTCOME_SALES, OUTCOME_TRAFFIC, etc.)
            status: Initial status (PAUSED, ACTIVE)
            special_ad_categories: List of special categories if applicable

        Returns:
            Campaign data including ID
        """
        await self._ensure_initialized()

        def _create_campaign():
            from facebook_business.adobjects.campaign import Campaign

            params = {
                Campaign.Field.name: name,
                Campaign.Field.objective: objective,
                Campaign.Field.status: status,
                Campaign.Field.special_ad_categories: special_ad_categories or [],
            }

            campaign = self._ad_account.create_campaign(params=params)
            return {"id": campaign.get_id(), "name": name, "status": status}

        return await self._run_sync(_create_campaign)

    async def create_ad_set(
        self,
        campaign_id: str,
        name: str,
        daily_budget_cents: int,
        targeting: CampaignTargeting,
        optimization_goal: str = "OFFSITE_CONVERSIONS",
        billing_event: str = "IMPRESSIONS",
        status: str = "PAUSED",
    ) -> Dict[str, Any]:
        """
        Create an ad set within a campaign.

        Args:
            campaign_id: Parent campaign ID
            name: Ad set name
            daily_budget_cents: Daily budget in cents
            targeting: Targeting configuration
            optimization_goal: What to optimize for
            billing_event: When to charge (IMPRESSIONS, CLICKS)
            status: Initial status

        Returns:
            Ad set data including ID
        """
        await self._ensure_initialized()

        def _create_ad_set():
            from facebook_business.adobjects.adset import AdSet

            # Build targeting spec
            targeting_spec = {}

            # Geographic targeting
            if targeting.countries:
                targeting_spec["geo_locations"] = {"countries": targeting.countries}
            elif targeting.cities:
                targeting_spec["geo_locations"] = {"cities": targeting.cities}
            elif targeting.zip_codes:
                targeting_spec["geo_locations"] = {"zips": targeting.zip_codes}

            # Age targeting
            if targeting.age_min:
                targeting_spec["age_min"] = targeting.age_min
            if targeting.age_max:
                targeting_spec["age_max"] = targeting.age_max

            # Gender targeting
            if targeting.genders:
                gender_map = {"male": 1, "female": 2}
                targeting_spec["genders"] = [
                    gender_map.get(g.lower(), 0) for g in targeting.genders if g != "all"
                ]

            params = {
                AdSet.Field.name: name,
                AdSet.Field.campaign_id: campaign_id,
                AdSet.Field.daily_budget: daily_budget_cents,  # API expects cents
                AdSet.Field.billing_event: billing_event,
                AdSet.Field.optimization_goal: optimization_goal,
                AdSet.Field.targeting: targeting_spec,
                AdSet.Field.status: status,
            }

            ad_set = self._ad_account.create_ad_set(params=params)
            return {"id": ad_set.get_id(), "name": name, "status": status}

        return await self._run_sync(_create_ad_set)

    async def create_ad_creative(
        self,
        name: str,
        page_id: str,
        headline: str,
        description: str,
        link_url: str,
        image_url: Optional[str] = None,
        video_id: Optional[str] = None,
        call_to_action: str = "LEARN_MORE",
    ) -> Dict[str, Any]:
        """
        Create an ad creative.

        Args:
            name: Creative name
            page_id: Facebook Page ID for attribution
            headline: Ad headline
            description: Ad description/primary text
            link_url: Destination URL
            image_url: Image URL (for image ads)
            video_id: Video ID (for video ads)
            call_to_action: CTA button type

        Returns:
            Creative data including ID
        """
        await self._ensure_initialized()

        def _create_creative():
            from facebook_business.adobjects.adcreative import AdCreative

            object_story_spec = {
                "page_id": page_id,
            }

            if video_id:
                object_story_spec["video_data"] = {
                    "video_id": video_id,
                    "message": description,
                    "call_to_action": {
                        "type": call_to_action,
                        "value": {"link": link_url},
                    },
                }
            elif image_url:
                object_story_spec["link_data"] = {
                    "image_hash": image_url,  # TODO: Upload image first
                    "link": link_url,
                    "message": description,
                    "name": headline,
                    "call_to_action": {
                        "type": call_to_action,
                        "value": {"link": link_url},
                    },
                }

            params = {
                AdCreative.Field.name: name,
                AdCreative.Field.object_story_spec: object_story_spec,
            }

            creative = self._ad_account.create_ad_creative(params=params)
            return {"id": creative.get_id(), "name": name}

        return await self._run_sync(_create_creative)

    async def create_ad(
        self,
        name: str,
        ad_set_id: str,
        creative_id: str,
        status: str = "PAUSED",
    ) -> Dict[str, Any]:
        """
        Create an ad.

        Args:
            name: Ad name
            ad_set_id: Parent ad set ID
            creative_id: Creative ID to use
            status: Initial status

        Returns:
            Ad data including ID
        """
        await self._ensure_initialized()

        def _create_ad():
            from facebook_business.adobjects.ad import Ad

            params = {
                Ad.Field.name: name,
                Ad.Field.adset_id: ad_set_id,
                Ad.Field.creative: {"creative_id": creative_id},
                Ad.Field.status: status,
            }

            ad = self._ad_account.create_ad(params=params)
            return {"id": ad.get_id(), "name": name, "status": status}

        return await self._run_sync(_create_ad)

    async def update_campaign_status(
        self, campaign_id: str, status: str
    ) -> Dict[str, Any]:
        """Update campaign status (ACTIVE, PAUSED, ARCHIVED)."""
        await self._ensure_initialized()

        def _update():
            from facebook_business.adobjects.campaign import Campaign

            campaign = Campaign(campaign_id)
            campaign.api_update(params={Campaign.Field.status: status})
            return {"id": campaign_id, "status": status}

        return await self._run_sync(_update)

    async def get_campaigns(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all campaigns for this ad account."""
        await self._ensure_initialized()

        def _get_campaigns():
            fields = [
                "id",
                "name",
                "status",
                "objective",
                "daily_budget",
                "lifetime_budget",
                "created_time",
            ]
            campaigns = self._ad_account.get_campaigns(fields=fields)
            return [dict(c) for c in campaigns[:limit]]

        return await self._run_sync(_get_campaigns)

    # =========================================================================
    # Metrics & Insights
    # =========================================================================

    async def get_campaign_insights(
        self,
        campaign_id: str,
        date_preset: str = "last_7d",
        time_increment: int = 1,  # Daily breakdown
    ) -> List[MetricsSnapshot]:
        """
        Get campaign performance insights.

        Args:
            campaign_id: Campaign ID
            date_preset: Date range (last_7d, last_30d, this_month, etc.)
            time_increment: Days per data point (1 for daily)

        Returns:
            List of daily metrics snapshots
        """
        await self._ensure_initialized()

        def _get_insights():
            from facebook_business.adobjects.campaign import Campaign

            campaign = Campaign(campaign_id)

            fields = [
                "date_start",
                "date_stop",
                "impressions",
                "clicks",
                "spend",
                "actions",  # Contains conversions
                "cost_per_action_type",
            ]

            params = {
                "date_preset": date_preset,
                "time_increment": time_increment,
            }

            insights = campaign.get_insights(fields=fields, params=params)

            results = []
            for insight in insights:
                data = dict(insight)

                # Extract conversions from actions
                conversions = 0
                revenue = 0
                if "actions" in data:
                    for action in data["actions"]:
                        if action["action_type"] in [
                            "purchase",
                            "omni_purchase",
                            "offsite_conversion.fb_pixel_purchase",
                        ]:
                            conversions += int(action.get("value", 0))

                # Calculate metrics
                impressions = int(data.get("impressions", 0))
                clicks = int(data.get("clicks", 0))
                spend_cents = int(float(data.get("spend", 0)) * 100)

                ctr = (clicks / impressions * 100) if impressions > 0 else None
                cpc_cents = (spend_cents // clicks) if clicks > 0 else None
                cpa_cents = (spend_cents // conversions) if conversions > 0 else None
                roas = (revenue / spend_cents) if spend_cents > 0 else None

                results.append(
                    MetricsSnapshot(
                        date=datetime.strptime(
                            data.get("date_start", data.get("date_stop")), "%Y-%m-%d"
                        ).date(),
                        impressions=impressions,
                        clicks=clicks,
                        conversions=conversions,
                        spend_cents=spend_cents,
                        revenue_cents=revenue,
                        ctr=ctr,
                        cpc_cents=cpc_cents,
                        cpa_cents=cpa_cents,
                        roas=roas,
                    )
                )

            return results

        return await self._run_sync(_get_insights)

    async def get_account_insights(
        self,
        date_preset: str = "last_7d",
    ) -> Dict[str, Any]:
        """Get account-level insights (total across all campaigns)."""
        await self._ensure_initialized()

        def _get_insights():
            fields = [
                "impressions",
                "clicks",
                "spend",
                "actions",
                "cpc",
                "cpm",
                "ctr",
            ]

            params = {"date_preset": date_preset}

            insights = self._ad_account.get_insights(fields=fields, params=params)

            if insights:
                return dict(insights[0])
            return {}

        return await self._run_sync(_get_insights)

    # =========================================================================
    # Video Upload
    # =========================================================================

    async def upload_video(
        self,
        video_path: str,
        title: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload a video to the ad account for use in ads.

        Args:
            video_path: Path to video file or URL
            title: Video title
            description: Optional description

        Returns:
            Video data including ID
        """
        await self._ensure_initialized()

        def _upload():
            from facebook_business.adobjects.advideo import AdVideo

            params = {
                AdVideo.Field.title: title,
            }

            if description:
                params[AdVideo.Field.description] = description

            # Check if it's a URL or file path
            if video_path.startswith("http"):
                params[AdVideo.Field.file_url] = video_path
            else:
                params[AdVideo.Field.filepath] = video_path

            video = self._ad_account.create_ad_video(params=params)
            return {"id": video.get_id(), "title": title}

        return await self._run_sync(_upload)


# =============================================================================
# Factory Function
# =============================================================================


def create_meta_client(access_token: str, ad_account_id: str) -> MetaAdsClient:
    """Create a Meta Ads client instance."""
    if not is_meta_configured():
        raise RuntimeError(
            "Meta Ads not configured. Set META_APP_ID and META_APP_SECRET environment variables."
        )
    return MetaAdsClient(access_token, ad_account_id)
