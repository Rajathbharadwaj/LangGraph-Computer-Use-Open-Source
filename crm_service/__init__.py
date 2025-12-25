"""
CRM Service - Customer Relationship Management & Unified Inbox

This package provides:
- Unified messaging across WhatsApp, Instagram DM, and Messenger
- Customer tracking and lifecycle management
- Smart tagging and visit tracking (QR Code check-in)
- Meta Conversions API (CAPI) for attribution
- Automated follow-ups (review requests, reactivation)

Architecture:
- clients/: Meta messaging and CAPI clients
- services/: Business logic (customer, conversation, attribution)
- webhooks/: Meta webhook handler for incoming messages
- routes.py: FastAPI endpoints
- config.py: Settings and scopes
"""

from .config import get_crm_settings, CRMSettings

__all__ = ["get_crm_settings", "CRMSettings"]
