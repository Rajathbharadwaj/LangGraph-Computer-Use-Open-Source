"""
Business preferences memory for Ads Agent.

Uses PostgresStore with namespace (user_id, "ads_preferences")
Stores business context for ad targeting and content generation defaults.
"""

from dataclasses import dataclass, asdict, field
from typing import Optional, List


@dataclass
class BusinessPreferences:
    """User's business context for ad targeting defaults."""

    user_id: str
    business_name: str
    business_type: str  # restaurant, ecommerce, service, saas, retail, etc.
    location_city: str
    location_state: str
    location_country: str = "US"
    service_radius_miles: int = 10
    default_daily_budget_cents: int = 2000  # $20 default
    target_audience: str = "local customers"
    brand_voice: str = "friendly"  # friendly, professional, casual, fun, luxury
    website_url: Optional[str] = None
    phone_number: Optional[str] = None
    primary_products: List[str] = field(default_factory=list)  # Main offerings
    unique_selling_points: List[str] = field(default_factory=list)  # USPs/differentiators

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BusinessPreferences":
        """Create BusinessPreferences from dictionary."""
        return cls(**data)


class AdsUserMemory:
    """
    Manages ads-specific user preferences using LangGraph Store.

    Namespace: (user_id, "ads_preferences")
    """

    def __init__(self, store, user_id: str):
        """
        Initialize ads memory manager.

        Args:
            store: LangGraph Store (PostgresStore or InMemoryStore)
            user_id: Clerk user ID
        """
        self.store = store
        self.user_id = user_id
        self.namespace = (user_id, "ads_preferences")

    def get_preferences(self) -> Optional[BusinessPreferences]:
        """Get saved business preferences."""
        try:
            item = self.store.get(self.namespace, "current")
            if item and item.value:
                return BusinessPreferences.from_dict(item.value)
            return None
        except Exception as e:
            print(f"Error loading ads preferences: {e}")
            return None

    def save_preferences(self, preferences: BusinessPreferences):
        """Save/update business preferences."""
        try:
            self.store.put(self.namespace, "current", preferences.to_dict())
            print(f"Saved ads preferences for user {self.user_id}")
        except Exception as e:
            print(f"Error saving ads preferences: {e}")
            raise

    def update_preference(self, key: str, value):
        """Update a single preference field."""
        prefs = self.get_preferences()
        if prefs:
            if hasattr(prefs, key):
                setattr(prefs, key, value)
                self.save_preferences(prefs)
            else:
                raise ValueError(f"Unknown preference key: {key}")
        else:
            raise ValueError("No preferences found to update")

    def get_targeting_defaults(self) -> dict:
        """Get default targeting based on business preferences."""
        prefs = self.get_preferences()
        if not prefs:
            return {
                "countries": ["US"],
                "age_min": 18,
                "age_max": 65,
            }

        return {
            "countries": [prefs.location_country],
            "cities": [
                {
                    "key": f"{prefs.location_city}, {prefs.location_state}",
                    "radius": prefs.service_radius_miles,
                    "distance_unit": "mile",
                }
            ],
            "age_min": 18,
            "age_max": 65,
        }

    def get_budget_cents(self) -> int:
        """Get default daily budget in cents."""
        prefs = self.get_preferences()
        if prefs:
            return prefs.default_daily_budget_cents
        return 2000  # $20 default


# =============================================================================
# Campaign Draft Memory (for approval workflow)
# =============================================================================


@dataclass
class CampaignDraft:
    """
    A draft campaign awaiting user approval.

    Stored in user's memory namespace until approved or rejected.
    """

    draft_id: str
    platform: str  # "meta" or "google"
    name: str
    headline: str
    description: str
    destination_url: str
    daily_budget_cents: int
    targeting: dict
    call_to_action: str = "LEARN_MORE"
    status: str = "pending"  # pending, approved, rejected
    feedback: Optional[str] = None  # User feedback if rejected

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CampaignDraft":
        return cls(**data)


class CampaignDraftManager:
    """
    Manages campaign drafts awaiting approval.

    Namespace: (user_id, "ads_drafts")
    """

    def __init__(self, store, user_id: str):
        self.store = store
        self.user_id = user_id
        self.namespace = (user_id, "ads_drafts")

    def save_draft(self, draft: CampaignDraft):
        """Save a campaign draft."""
        self.store.put(self.namespace, draft.draft_id, draft.to_dict())
        print(f"Saved draft {draft.draft_id} for user {self.user_id}")

    def get_draft(self, draft_id: str) -> Optional[CampaignDraft]:
        """Get a specific draft by ID."""
        item = self.store.get(self.namespace, draft_id)
        if item and item.value:
            return CampaignDraft.from_dict(item.value)
        return None

    def get_pending_drafts(self) -> List[CampaignDraft]:
        """Get all pending drafts."""
        try:
            items = list(self.store.search(self.namespace, limit=100))
            drafts = []
            for item in items:
                draft = CampaignDraft.from_dict(item.value)
                if draft.status == "pending":
                    drafts.append(draft)
            return drafts
        except Exception as e:
            print(f"Error getting pending drafts: {e}")
            return []

    def approve_draft(self, draft_id: str) -> Optional[CampaignDraft]:
        """Mark a draft as approved."""
        draft = self.get_draft(draft_id)
        if draft:
            draft.status = "approved"
            self.save_draft(draft)
            return draft
        return None

    def reject_draft(self, draft_id: str, feedback: str) -> Optional[CampaignDraft]:
        """Mark a draft as rejected with feedback."""
        draft = self.get_draft(draft_id)
        if draft:
            draft.status = "rejected"
            draft.feedback = feedback
            self.save_draft(draft)
            return draft
        return None

    def delete_draft(self, draft_id: str):
        """Delete a draft."""
        try:
            self.store.delete(self.namespace, draft_id)
            print(f"Deleted draft {draft_id}")
        except Exception as e:
            print(f"Error deleting draft: {e}")
