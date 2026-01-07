"""Activities for notification operations."""

import logging
from datetime import datetime

import httpx
from temporalio import activity

from ..config import get_settings
from ..models.types import NotificationSeverity

logger = logging.getLogger(__name__)


@activity.defn
async def send_slack_notification(message: str, severity: NotificationSeverity) -> bool:
    """Send a notification to Slack.

    Args:
        message: The message to send
        severity: The severity level of the notification

    Returns:
        True if successful, False if no webhook configured

    Raises:
        Exception: If the Slack API request fails
    """
    settings = get_settings()
    
    activity.logger.info(f"Activity: send_slack_notification with severity {severity}")
    
    # If no Slack webhook is configured, skip silently
    if not settings.slack_webhook_url:
        activity.logger.info("No Slack webhook configured, skipping notification")
        return False
    
    # In dry run mode, just log
    if settings.dry_run_mode:
        activity.logger.info(f"[DRY RUN] Would send Slack notification: {message}")
        return True
    
    # Map severity to Slack colors
    color_map = {
        NotificationSeverity.INFO: "#36a64f",      # Green
        NotificationSeverity.WARNING: "#ff9900",   # Orange
        NotificationSeverity.ERROR: "#ff0000",     # Red
        NotificationSeverity.CRITICAL: "#990000",  # Dark Red
    }
    
    # Map severity to emoji
    emoji_map = {
        NotificationSeverity.INFO: ":information_source:",
        NotificationSeverity.WARNING: ":warning:",
        NotificationSeverity.ERROR: ":x:",
        NotificationSeverity.CRITICAL: ":rotating_light:",
    }
    
    # Build Slack message payload
    payload = {
        "attachments": [
            {
                "color": color_map.get(severity, "#808080"),
                "title": f"{emoji_map.get(severity, ':bell:')} Temporal Capacity Management",
                "text": message,
                "footer": "Temporal Cloud Capacity Automation",
                "ts": int(datetime.now().timestamp()),
            }
        ]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.slack_webhook_url,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
        
        activity.logger.info("Successfully sent Slack notification")
        return True
        
    except Exception as e:
        activity.logger.error(f"Failed to send Slack notification: {e}")
        raise
