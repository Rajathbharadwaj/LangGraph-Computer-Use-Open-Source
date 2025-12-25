"""
Meta Conversions API (CAPI) Client

Sends server-side conversion events to Meta for attribution.
Links customer actions (visits, purchases) back to ad campaigns.

Docs: https://developers.facebook.com/docs/marketing-api/conversions-api
"""

import logging
import hashlib
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx

from ..config import get_crm_settings, CAPI_EVENTS

logger = logging.getLogger(__name__)


class MetaCAPIClient:
    """
    Client for Meta Conversions API.

    Sends server-side events for attribution tracking.
    """

    def __init__(
        self,
        pixel_id: str,
        access_token: str,
        test_event_code: Optional[str] = None,
    ):
        """
        Initialize CAPI client.

        Args:
            pixel_id: Meta Pixel ID
            access_token: Access token with CAPI permissions
            test_event_code: Test event code (for development)
        """
        self.pixel_id = pixel_id
        self.access_token = access_token
        self.test_event_code = test_event_code

        settings = get_crm_settings()
        self.api_version = settings.meta_api_version
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # =========================================================================
    # Hashing Helpers (Required for user data matching)
    # =========================================================================

    @staticmethod
    def hash_value(value: str) -> str:
        """Hash a value using SHA256 (required by CAPI)."""
        if not value:
            return ""
        # Normalize: lowercase, strip whitespace
        normalized = value.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """Normalize phone number for CAPI (digits only, no country code formatting)."""
        if not phone:
            return ""
        # Remove all non-digit characters
        digits = "".join(c for c in phone if c.isdigit())
        return digits

    # =========================================================================
    # Event Sending
    # =========================================================================

    async def send_event(
        self,
        event_name: str,
        event_time: Optional[datetime] = None,
        # User data (at least one required for matching)
        phone: Optional[str] = None,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None,
        country: str = "US",
        # Attribution
        click_id: Optional[str] = None,  # ctwa_clid from Click-to-WhatsApp
        # Event data
        value: Optional[float] = None,
        currency: str = "USD",
        # Additional
        content_name: Optional[str] = None,
        content_category: Optional[str] = None,
        event_source_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a conversion event to Meta CAPI.

        Args:
            event_name: Event type (Lead, Purchase, Visit, etc.)
            event_time: When the event occurred
            phone: Customer phone number
            email: Customer email
            first_name: Customer first name
            last_name: Customer last name
            city: Customer city
            state: Customer state
            zip_code: Customer zip code
            country: Customer country (default US)
            click_id: CTWA click ID for attribution
            value: Event value (e.g., purchase amount)
            currency: Currency code
            content_name: Product/content name
            content_category: Product/content category
            event_source_url: URL where event occurred

        Returns:
            API response
        """
        client = await self._get_client()

        # Build user_data with hashed PII
        user_data = {}

        if phone:
            user_data["ph"] = [self.hash_value(self.normalize_phone(phone))]

        if email:
            user_data["em"] = [self.hash_value(email)]

        if first_name:
            user_data["fn"] = [self.hash_value(first_name)]

        if last_name:
            user_data["ln"] = [self.hash_value(last_name)]

        if city:
            user_data["ct"] = [self.hash_value(city)]

        if state:
            user_data["st"] = [self.hash_value(state)]

        if zip_code:
            user_data["zp"] = [self.hash_value(zip_code)]

        if country:
            user_data["country"] = [self.hash_value(country)]

        # Add click_id for attribution (not hashed)
        if click_id:
            user_data["ctwa_clid"] = click_id

        # Build event data
        event_data: Dict[str, Any] = {
            "event_name": event_name,
            "event_time": int((event_time or datetime.utcnow()).timestamp()),
            "action_source": "website",  # Or "physical_store" for visits
            "user_data": user_data,
        }

        # Add custom data if present
        custom_data = {}
        if value is not None:
            custom_data["value"] = value
            custom_data["currency"] = currency

        if content_name:
            custom_data["content_name"] = content_name

        if content_category:
            custom_data["content_category"] = content_category

        if custom_data:
            event_data["custom_data"] = custom_data

        if event_source_url:
            event_data["event_source_url"] = event_source_url

        # Build request payload
        payload = {
            "data": [event_data],
            "access_token": self.access_token,
        }

        # Add test event code if in development
        if self.test_event_code:
            payload["test_event_code"] = self.test_event_code

        # Send to CAPI
        url = f"{self.base_url}/{self.pixel_id}/events"

        try:
            response = await client.post(url, json=payload)
            result = response.json()

            if response.status_code == 200:
                events_received = result.get("events_received", 0)
                logger.info(
                    f"CAPI event sent: {event_name}, "
                    f"events_received: {events_received}"
                )
            else:
                logger.error(f"CAPI error: {result}")

            return result

        except Exception as e:
            logger.error(f"CAPI request failed: {e}")
            return {"error": str(e)}

    # =========================================================================
    # Convenience Methods for Common Events
    # =========================================================================

    async def send_lead_event(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        click_id: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a Lead event (customer inquiry/first contact).

        Called when a new customer messages via Click-to-WhatsApp.
        """
        return await self.send_event(
            event_name="Lead",
            phone=phone,
            email=email,
            click_id=click_id,
            first_name=first_name,
            last_name=last_name,
        )

    async def send_visit_event(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        click_id: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        event_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Send a custom Visit event (physical store visit via check-in).

        Note: This is a custom event. Standard events like Purchase
        will have better optimization in Meta's systems.
        """
        return await self.send_event(
            event_name="Visit",
            event_time=event_time,
            phone=phone,
            email=email,
            click_id=click_id,
            first_name=first_name,
            last_name=last_name,
        )

    async def send_purchase_event(
        self,
        value: float,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        click_id: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        currency: str = "USD",
        event_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Send a Purchase event (customer made a purchase).

        This is a standard Meta event with full optimization support.
        """
        return await self.send_event(
            event_name="Purchase",
            event_time=event_time,
            phone=phone,
            email=email,
            click_id=click_id,
            first_name=first_name,
            last_name=last_name,
            value=value,
            currency=currency,
        )

    # =========================================================================
    # Batch Events
    # =========================================================================

    async def send_batch_events(
        self, events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Send multiple events in a single request.

        Args:
            events: List of event dictionaries (same format as send_event)

        Returns:
            API response with events_received count
        """
        client = await self._get_client()

        # Process each event
        processed_events = []
        for event in events:
            # Hash user data
            user_data = {}
            if event.get("phone"):
                user_data["ph"] = [self.hash_value(self.normalize_phone(event["phone"]))]
            if event.get("email"):
                user_data["em"] = [self.hash_value(event["email"])]
            if event.get("first_name"):
                user_data["fn"] = [self.hash_value(event["first_name"])]
            if event.get("last_name"):
                user_data["ln"] = [self.hash_value(event["last_name"])]
            if event.get("click_id"):
                user_data["ctwa_clid"] = event["click_id"]

            event_data = {
                "event_name": event.get("event_name", "Lead"),
                "event_time": int(event.get("event_time", datetime.utcnow()).timestamp())
                if isinstance(event.get("event_time"), datetime)
                else int(event.get("event_time", time.time())),
                "action_source": "website",
                "user_data": user_data,
            }

            if event.get("value"):
                event_data["custom_data"] = {
                    "value": event["value"],
                    "currency": event.get("currency", "USD"),
                }

            processed_events.append(event_data)

        # Build request
        payload = {
            "data": processed_events,
            "access_token": self.access_token,
        }

        if self.test_event_code:
            payload["test_event_code"] = self.test_event_code

        url = f"{self.base_url}/{self.pixel_id}/events"

        try:
            response = await client.post(url, json=payload)
            result = response.json()

            logger.info(
                f"CAPI batch sent: {len(events)} events, "
                f"received: {result.get('events_received', 0)}"
            )

            return result

        except Exception as e:
            logger.error(f"CAPI batch request failed: {e}")
            return {"error": str(e)}


# =============================================================================
# Factory Functions
# =============================================================================


def create_capi_client(
    pixel_id: Optional[str] = None,
    access_token: Optional[str] = None,
    test_event_code: Optional[str] = None,
) -> MetaCAPIClient:
    """
    Create a CAPI client.

    Uses settings from environment if not provided.
    """
    settings = get_crm_settings()

    return MetaCAPIClient(
        pixel_id=pixel_id or settings.meta_pixel_id,
        access_token=access_token or settings.meta_capi_access_token,
        test_event_code=test_event_code or settings.meta_capi_test_code,
    )


async def create_capi_client_for_user(user_id: str) -> Optional[MetaCAPIClient]:
    """
    Create a CAPI client for a specific user.

    Uses the user's pixel and access token if configured.
    """
    # For now, use the app-level CAPI settings
    # In the future, each user could have their own pixel
    settings = get_crm_settings()

    if not settings.meta_pixel_id or not settings.meta_capi_access_token:
        logger.warning("CAPI not configured - events will not be sent")
        return None

    return MetaCAPIClient(
        pixel_id=settings.meta_pixel_id,
        access_token=settings.meta_capi_access_token,
        test_event_code=settings.meta_capi_test_code,
    )
