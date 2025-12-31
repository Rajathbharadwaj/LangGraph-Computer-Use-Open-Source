"""
Work Integrations Module - Build in Public Automation

This module captures work activity from developer platforms (GitHub, Slack, Notion,
Linear, Figma) and generates AI-powered draft X posts.

Components:
- OAuth manager for platform authentication
- Platform clients for API access
- Webhook handlers for real-time activity capture
- Activity aggregator for daily digest processing
- Draft generator using Deep Agent with style transfer
"""

from .routes import router

__all__ = ["router"]
