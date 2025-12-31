"""
Webhook handlers for Work Integrations.

Each handler processes incoming webhooks from platforms:
- GitHub: push, pull_request, release, issues
- Slack: message events
- Linear: issue updates
"""

from .github_webhook import process_github_webhook

__all__ = ["process_github_webhook"]
