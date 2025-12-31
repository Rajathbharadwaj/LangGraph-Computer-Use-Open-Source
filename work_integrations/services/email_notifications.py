"""
Email Notification Service for Work Integrations.

Sends email notifications for:
- New drafts ready for review
- Draft expiration reminders
- Weekly activity summaries

Uses SendGrid or falls back to SMTP.
"""

import logging
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


class EmailNotificationService:
    """
    Email notification service for work integrations.

    Supports SendGrid API or can be extended for other providers.
    """

    def __init__(self):
        self.sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL", "noreply@paralleluniverse.ai")
        self.from_name = os.getenv("FROM_NAME", "Parallel Universe")
        self.frontend_url = os.getenv("FRONTEND_URL", "https://app.paralleluniverse.ai")
        self.enabled = bool(self.sendgrid_api_key)

        if not self.enabled:
            logger.warning("Email notifications disabled - SENDGRID_API_KEY not set")

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """
        Send an email via SendGrid.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email body
            text_content: Plain text fallback (optional)

        Returns:
            True if sent successfully
        """
        if not self.enabled:
            logger.debug(f"Email skipped (disabled): {subject} to {to_email}")
            return False

        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": self.from_email, "name": self.from_name},
            "subject": subject,
            "content": [
                {"type": "text/html", "value": html_content},
            ],
        }

        if text_content:
            payload["content"].insert(0, {"type": "text/plain", "value": text_content})

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {self.sendgrid_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code in [200, 202]:
                    logger.info(f"Email sent: {subject} to {to_email}")
                    return True
                else:
                    logger.error(
                        f"Email failed ({response.status_code}): {response.text}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Email error: {e}")
            return False

    async def send_new_drafts_notification(
        self,
        to_email: str,
        user_name: str,
        drafts: List[Dict[str, Any]],
    ) -> bool:
        """
        Notify user of new drafts ready for review.

        Args:
            to_email: User's email
            user_name: User's name for greeting
            drafts: List of draft info dicts

        Returns:
            True if sent successfully
        """
        subject = f"📝 {len(drafts)} new draft(s) ready for review"

        # Build draft previews
        draft_html = ""
        for draft in drafts[:3]:  # Show max 3 previews
            theme = draft.get("theme", "Daily Update")
            content_preview = draft.get("content", "")[:100] + "..."
            draft_html += f"""
            <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin-bottom: 12px;">
                <p style="margin: 0 0 8px 0; font-weight: 600; color: #4f46e5;">{theme}</p>
                <p style="margin: 0; color: #4b5563; font-size: 14px;">{content_preview}</p>
            </div>
            """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 32px;">
                <h1 style="color: #18181b; margin: 0;">Parallel Universe</h1>
                <p style="color: #71717a; margin-top: 4px;">Build in Public Automation</p>
            </div>

            <p style="color: #27272a; font-size: 16px;">Hi {user_name},</p>

            <p style="color: #3f3f46; font-size: 16px;">
                Your daily work activity has been processed and we've generated
                <strong>{len(drafts)} new draft(s)</strong> for you to review.
            </p>

            <h3 style="color: #27272a; margin-top: 24px;">Draft Previews</h3>
            {draft_html}

            <div style="text-align: center; margin-top: 32px;">
                <a href="{self.frontend_url}/integrations?tab=drafts"
                   style="display: inline-block; background: #4f46e5; color: white; padding: 12px 32px; border-radius: 8px; text-decoration: none; font-weight: 600;">
                    Review Drafts
                </a>
            </div>

            <p style="color: #71717a; font-size: 14px; margin-top: 32px; text-align: center;">
                Drafts expire in 7 days if not reviewed.
            </p>

            <hr style="border: none; border-top: 1px solid #e4e4e7; margin: 32px 0;">

            <p style="color: #a1a1aa; font-size: 12px; text-align: center;">
                You're receiving this because you have work integrations enabled on Parallel Universe.
                <br>
                <a href="{self.frontend_url}/settings" style="color: #a1a1aa;">Manage email preferences</a>
            </p>
        </body>
        </html>
        """

        text_content = f"""
Hi {user_name},

Your daily work activity has been processed and we've generated {len(drafts)} new draft(s) for you to review.

Review your drafts at: {self.frontend_url}/integrations?tab=drafts

Drafts expire in 7 days if not reviewed.

- Parallel Universe
        """

        return await self.send_email(to_email, subject, html_content, text_content)

    async def send_draft_expiring_reminder(
        self,
        to_email: str,
        user_name: str,
        expiring_count: int,
        days_remaining: int = 1,
    ) -> bool:
        """
        Remind user about expiring drafts.

        Args:
            to_email: User's email
            user_name: User's name
            expiring_count: Number of drafts expiring
            days_remaining: Days until expiration

        Returns:
            True if sent successfully
        """
        subject = f"⏰ {expiring_count} draft(s) expiring in {days_remaining} day(s)"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 32px;">
                <h1 style="color: #18181b; margin: 0;">Parallel Universe</h1>
            </div>

            <p style="color: #27272a;">Hi {user_name},</p>

            <p style="color: #3f3f46;">
                You have <strong>{expiring_count} draft(s)</strong> that will expire in
                <strong>{days_remaining} day(s)</strong>. Review them now to keep your
                "build in public" momentum going!
            </p>

            <div style="text-align: center; margin-top: 32px;">
                <a href="{self.frontend_url}/integrations?tab=drafts"
                   style="display: inline-block; background: #4f46e5; color: white; padding: 12px 32px; border-radius: 8px; text-decoration: none; font-weight: 600;">
                    Review Drafts
                </a>
            </div>

            <hr style="border: none; border-top: 1px solid #e4e4e7; margin: 32px 0;">

            <p style="color: #a1a1aa; font-size: 12px; text-align: center;">
                <a href="{self.frontend_url}/settings" style="color: #a1a1aa;">Manage email preferences</a>
            </p>
        </body>
        </html>
        """

        return await self.send_email(to_email, subject, html_content)

    async def send_weekly_summary(
        self,
        to_email: str,
        user_name: str,
        stats: Dict[str, Any],
    ) -> bool:
        """
        Send weekly activity summary.

        Args:
            to_email: User's email
            user_name: User's name
            stats: Weekly stats dict

        Returns:
            True if sent successfully
        """
        subject = "📊 Your weekly work activity summary"

        activities = stats.get("activities_captured", 0)
        drafts_generated = stats.get("drafts_generated", 0)
        drafts_approved = stats.get("drafts_approved", 0)
        posts_made = stats.get("posts_made", 0)
        platforms = stats.get("platforms", [])

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 32px;">
                <h1 style="color: #18181b; margin: 0;">Your Week in Review</h1>
                <p style="color: #71717a;">Build in Public Summary</p>
            </div>

            <p style="color: #27272a;">Hi {user_name},</p>

            <p style="color: #3f3f46;">Here's what you accomplished this week:</p>

            <div style="background: #f8f9fa; padding: 24px; border-radius: 12px; margin: 24px 0;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 16px;">
                    <div style="text-align: center; flex: 1;">
                        <div style="font-size: 32px; font-weight: bold; color: #4f46e5;">{activities}</div>
                        <div style="color: #71717a; font-size: 14px;">Activities Captured</div>
                    </div>
                    <div style="text-align: center; flex: 1;">
                        <div style="font-size: 32px; font-weight: bold; color: #059669;">{drafts_approved}</div>
                        <div style="color: #71717a; font-size: 14px;">Drafts Approved</div>
                    </div>
                    <div style="text-align: center; flex: 1;">
                        <div style="font-size: 32px; font-weight: bold; color: #0ea5e9;">{posts_made}</div>
                        <div style="color: #71717a; font-size: 14px;">Posts Made</div>
                    </div>
                </div>

                <p style="color: #71717a; font-size: 14px; margin: 0; text-align: center;">
                    Connected platforms: {', '.join(platforms) if platforms else 'None'}
                </p>
            </div>

            <div style="text-align: center; margin-top: 32px;">
                <a href="{self.frontend_url}/integrations"
                   style="display: inline-block; background: #4f46e5; color: white; padding: 12px 32px; border-radius: 8px; text-decoration: none; font-weight: 600;">
                    View Dashboard
                </a>
            </div>

            <hr style="border: none; border-top: 1px solid #e4e4e7; margin: 32px 0;">

            <p style="color: #a1a1aa; font-size: 12px; text-align: center;">
                <a href="{self.frontend_url}/settings" style="color: #a1a1aa;">Manage email preferences</a>
            </p>
        </body>
        </html>
        """

        return await self.send_email(to_email, subject, html_content)


# Singleton instance
_service: Optional[EmailNotificationService] = None


def get_email_notification_service() -> EmailNotificationService:
    """Get or create the email notification service."""
    global _service
    if _service is None:
        _service = EmailNotificationService()
    return _service
