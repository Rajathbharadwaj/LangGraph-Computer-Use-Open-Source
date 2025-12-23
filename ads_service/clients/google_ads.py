"""
Google Ads API Client

Async wrapper around the google-ads SDK for Google Ads API.
Handles Performance Max campaign creation, management, and metrics fetching.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from functools import partial

from ..config import get_ads_settings, is_google_configured
from ..models import (
    CampaignCreate,
    CampaignUpdate,
    CampaignTargeting,
    MetricsSnapshot,
    CampaignStatus,
)

logger = logging.getLogger(__name__)


class GoogleAdsClient:
    """
    Client for Google Ads API.

    Uses the google-ads SDK for API calls.
    All methods are async-compatible for use with FastAPI.
    """

    def __init__(self, refresh_token: str, customer_id: str):
        """
        Initialize the Google Ads client.

        Args:
            refresh_token: OAuth2 refresh token for the customer
            customer_id: Google Ads Customer ID (10 digits, no dashes)
        """
        self.refresh_token = refresh_token
        self.customer_id = customer_id.replace("-", "")  # Remove dashes if present
        self._initialized = False
        self._client = None

    async def _ensure_initialized(self):
        """Lazily initialize the SDK."""
        if self._initialized:
            return

        try:
            from google.ads.googleads.client import GoogleAdsClient as GAClient
            from google.ads.googleads.errors import GoogleAdsException

            settings = get_ads_settings()

            # Build credentials dict
            credentials = {
                "developer_token": settings.google_developer_token,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": self.refresh_token,
                "use_proto_plus": True,
            }

            # Add login customer ID if managing through MCC
            if settings.google_login_customer_id:
                credentials["login_customer_id"] = settings.google_login_customer_id

            self._client = GAClient.load_from_dict(credentials)
            self._initialized = True

            logger.info(f"Google Ads client initialized for customer {self.customer_id}")

        except ImportError:
            raise RuntimeError(
                "google-ads SDK not installed. Run: pip install google-ads"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Google Ads client: {e}")
            raise

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous SDK function in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    # =========================================================================
    # Account Management
    # =========================================================================

    async def get_account_info(self) -> Dict[str, Any]:
        """Get Google Ads account information."""
        await self._ensure_initialized()

        def _get_info():
            ga_service = self._client.get_service("GoogleAdsService")

            query = """
                SELECT
                    customer.id,
                    customer.descriptive_name,
                    customer.currency_code,
                    customer.time_zone,
                    customer.status
                FROM customer
                LIMIT 1
            """

            response = ga_service.search(customer_id=self.customer_id, query=query)

            for row in response:
                return {
                    "id": row.customer.id,
                    "name": row.customer.descriptive_name,
                    "currency": row.customer.currency_code,
                    "timezone": row.customer.time_zone,
                    "status": row.customer.status.name,
                }
            return {}

        return await self._run_sync(_get_info)

    # =========================================================================
    # Campaign Management
    # =========================================================================

    async def create_campaign_budget(
        self,
        name: str,
        amount_micros: int,
        delivery_method: str = "STANDARD",
    ) -> str:
        """
        Create a campaign budget.

        Args:
            name: Budget name
            amount_micros: Daily budget in micros ($1 = 1,000,000 micros)
            delivery_method: STANDARD or ACCELERATED

        Returns:
            Budget resource name
        """
        await self._ensure_initialized()

        def _create_budget():
            campaign_budget_service = self._client.get_service("CampaignBudgetService")

            operation = self._client.get_type("CampaignBudgetOperation")
            budget = operation.create

            budget.name = name
            budget.amount_micros = amount_micros
            budget.delivery_method = self._client.enums.BudgetDeliveryMethodEnum[
                delivery_method
            ]

            response = campaign_budget_service.mutate_campaign_budgets(
                customer_id=self.customer_id, operations=[operation]
            )

            return response.results[0].resource_name

        return await self._run_sync(_create_budget)

    async def create_performance_max_campaign(
        self,
        name: str,
        budget_resource_name: str,
        status: str = "PAUSED",
        target_roas: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Create a Performance Max campaign.

        Args:
            name: Campaign name
            budget_resource_name: Resource name of the budget
            status: Initial status (PAUSED, ENABLED)
            target_roas: Optional target ROAS for bidding

        Returns:
            Campaign data including resource name
        """
        await self._ensure_initialized()

        def _create_campaign():
            campaign_service = self._client.get_service("CampaignService")

            operation = self._client.get_type("CampaignOperation")
            campaign = operation.create

            campaign.name = name
            campaign.campaign_budget = budget_resource_name
            campaign.advertising_channel_type = (
                self._client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
            )
            campaign.status = self._client.enums.CampaignStatusEnum[status]

            # Set bidding strategy
            if target_roas:
                campaign.maximize_conversion_value.target_roas = target_roas
            else:
                campaign.maximize_conversions.target_cpa_micros = 0  # Let Google optimize

            response = campaign_service.mutate_campaigns(
                customer_id=self.customer_id, operations=[operation]
            )

            resource_name = response.results[0].resource_name
            campaign_id = resource_name.split("/")[-1]

            return {
                "resource_name": resource_name,
                "id": campaign_id,
                "name": name,
                "status": status,
            }

        return await self._run_sync(_create_campaign)

    async def create_asset_group(
        self,
        campaign_resource_name: str,
        name: str,
        final_urls: List[str],
        headlines: List[str],
        descriptions: List[str],
        status: str = "PAUSED",
    ) -> Dict[str, Any]:
        """
        Create an asset group for a Performance Max campaign.

        Args:
            campaign_resource_name: Parent campaign resource name
            name: Asset group name
            final_urls: Landing page URLs
            headlines: List of headlines (up to 5)
            descriptions: List of descriptions (up to 5)
            status: Initial status

        Returns:
            Asset group data
        """
        await self._ensure_initialized()

        def _create_asset_group():
            asset_group_service = self._client.get_service("AssetGroupService")
            asset_service = self._client.get_service("AssetService")

            operations = []

            # Create asset group
            ag_operation = self._client.get_type("AssetGroupOperation")
            asset_group = ag_operation.create
            asset_group.name = name
            asset_group.campaign = campaign_resource_name
            asset_group.status = self._client.enums.AssetGroupStatusEnum[status]

            for url in final_urls:
                asset_group.final_urls.append(url)

            operations.append(ag_operation)

            response = asset_group_service.mutate_asset_groups(
                customer_id=self.customer_id, operations=operations
            )

            return {
                "resource_name": response.results[0].resource_name,
                "name": name,
            }

        return await self._run_sync(_create_asset_group)

    async def update_campaign_status(
        self, campaign_resource_name: str, status: str
    ) -> Dict[str, Any]:
        """Update campaign status (ENABLED, PAUSED, REMOVED)."""
        await self._ensure_initialized()

        def _update():
            campaign_service = self._client.get_service("CampaignService")

            operation = self._client.get_type("CampaignOperation")
            campaign = operation.update

            campaign.resource_name = campaign_resource_name
            campaign.status = self._client.enums.CampaignStatusEnum[status]

            # Set the update mask
            self._client.copy_from(
                operation.update_mask,
                self._client.get_type("FieldMask")(paths=["status"]),
            )

            response = campaign_service.mutate_campaigns(
                customer_id=self.customer_id, operations=[operation]
            )

            return {"resource_name": campaign_resource_name, "status": status}

        return await self._run_sync(_update)

    async def get_campaigns(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all campaigns for this customer."""
        await self._ensure_initialized()

        def _get_campaigns():
            ga_service = self._client.get_service("GoogleAdsService")

            query = f"""
                SELECT
                    campaign.id,
                    campaign.name,
                    campaign.status,
                    campaign.advertising_channel_type,
                    campaign_budget.amount_micros,
                    metrics.cost_micros,
                    metrics.impressions,
                    metrics.clicks,
                    metrics.conversions
                FROM campaign
                WHERE campaign.status != 'REMOVED'
                ORDER BY campaign.id
                LIMIT {limit}
            """

            response = ga_service.search(customer_id=self.customer_id, query=query)

            campaigns = []
            for row in response:
                campaigns.append({
                    "id": str(row.campaign.id),
                    "name": row.campaign.name,
                    "status": row.campaign.status.name,
                    "type": row.campaign.advertising_channel_type.name,
                    "daily_budget_micros": row.campaign_budget.amount_micros,
                    "total_cost_micros": row.metrics.cost_micros,
                    "impressions": row.metrics.impressions,
                    "clicks": row.metrics.clicks,
                    "conversions": row.metrics.conversions,
                })

            return campaigns

        return await self._run_sync(_get_campaigns)

    # =========================================================================
    # Metrics & Reporting
    # =========================================================================

    async def get_campaign_metrics(
        self,
        campaign_id: str,
        start_date: str,
        end_date: str,
    ) -> List[MetricsSnapshot]:
        """
        Get daily campaign metrics for a date range.

        Args:
            campaign_id: Campaign ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of daily metrics snapshots
        """
        await self._ensure_initialized()

        def _get_metrics():
            ga_service = self._client.get_service("GoogleAdsService")

            query = f"""
                SELECT
                    segments.date,
                    metrics.impressions,
                    metrics.clicks,
                    metrics.conversions,
                    metrics.cost_micros,
                    metrics.conversions_value
                FROM campaign
                WHERE campaign.id = {campaign_id}
                    AND segments.date >= '{start_date}'
                    AND segments.date <= '{end_date}'
                ORDER BY segments.date
            """

            response = ga_service.search(customer_id=self.customer_id, query=query)

            results = []
            for row in response:
                impressions = row.metrics.impressions
                clicks = row.metrics.clicks
                conversions = int(row.metrics.conversions)
                spend_cents = row.metrics.cost_micros // 10000  # Convert micros to cents
                revenue_cents = int(row.metrics.conversions_value * 100)

                ctr = (clicks / impressions * 100) if impressions > 0 else None
                cpc_cents = (spend_cents // clicks) if clicks > 0 else None
                cpa_cents = (spend_cents // conversions) if conversions > 0 else None
                roas = (revenue_cents / spend_cents) if spend_cents > 0 else None

                results.append(
                    MetricsSnapshot(
                        date=datetime.strptime(row.segments.date, "%Y-%m-%d").date(),
                        impressions=impressions,
                        clicks=clicks,
                        conversions=conversions,
                        spend_cents=spend_cents,
                        revenue_cents=revenue_cents,
                        ctr=ctr,
                        cpc_cents=cpc_cents,
                        cpa_cents=cpa_cents,
                        roas=roas,
                    )
                )

            return results

        return await self._run_sync(_get_metrics)

    async def get_account_metrics(
        self,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """Get account-level metrics for a date range."""
        await self._ensure_initialized()

        def _get_metrics():
            ga_service = self._client.get_service("GoogleAdsService")

            query = f"""
                SELECT
                    metrics.impressions,
                    metrics.clicks,
                    metrics.conversions,
                    metrics.cost_micros,
                    metrics.conversions_value
                FROM customer
                WHERE segments.date >= '{start_date}'
                    AND segments.date <= '{end_date}'
            """

            response = ga_service.search(customer_id=self.customer_id, query=query)

            total = {
                "impressions": 0,
                "clicks": 0,
                "conversions": 0,
                "cost_micros": 0,
                "revenue": 0,
            }

            for row in response:
                total["impressions"] += row.metrics.impressions
                total["clicks"] += row.metrics.clicks
                total["conversions"] += int(row.metrics.conversions)
                total["cost_micros"] += row.metrics.cost_micros
                total["revenue"] += row.metrics.conversions_value

            return total

        return await self._run_sync(_get_metrics)

    # =========================================================================
    # YouTube Video (for Performance Max)
    # =========================================================================

    async def create_youtube_video_asset(
        self,
        youtube_video_id: str,
    ) -> str:
        """
        Create a YouTube video asset for use in Performance Max.

        Note: Video must already be uploaded to YouTube (unlisted is fine).

        Args:
            youtube_video_id: YouTube video ID (e.g., "dQw4w9WgXcQ")

        Returns:
            Asset resource name
        """
        await self._ensure_initialized()

        def _create_asset():
            asset_service = self._client.get_service("AssetService")

            operation = self._client.get_type("AssetOperation")
            asset = operation.create

            asset.type_ = self._client.enums.AssetTypeEnum.YOUTUBE_VIDEO
            asset.youtube_video_asset.youtube_video_id = youtube_video_id

            response = asset_service.mutate_assets(
                customer_id=self.customer_id, operations=[operation]
            )

            return response.results[0].resource_name

        return await self._run_sync(_create_asset)


# =============================================================================
# Factory Function
# =============================================================================


def create_google_client(refresh_token: str, customer_id: str) -> GoogleAdsClient:
    """Create a Google Ads client instance."""
    if not is_google_configured():
        raise RuntimeError(
            "Google Ads not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, "
            "and GOOGLE_DEVELOPER_TOKEN environment variables."
        )
    return GoogleAdsClient(refresh_token, customer_id)
