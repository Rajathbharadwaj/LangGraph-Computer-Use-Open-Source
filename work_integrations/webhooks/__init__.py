"""
Webhook handlers for Work Integrations.

Each handler processes incoming webhooks from platforms:
- GitHub: push, pull_request, release, issues
- Slack: message events, reactions
- Linear: issue updates, comments, projects
"""

from .github_webhook import process_github_webhook
from .slack_webhook import SlackWebhookHandler, get_slack_webhook_handler
from .linear_webhook import LinearWebhookHandler, get_linear_webhook_handler

__all__ = [
    # GitHub
    "process_github_webhook",
    # Slack
    "SlackWebhookHandler",
    "get_slack_webhook_handler",
    # Linear
    "LinearWebhookHandler",
    "get_linear_webhook_handler",
]
