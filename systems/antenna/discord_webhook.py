"""
The Antenna — Discord Integration (AN.5)
Sends digests and alerts to Discord via webhook.
Team 2950 — The Devastators
"""

import logging
import time
import requests
from typing import Optional

from config import DISCORD_WEBHOOK_URL
from digest import split_for_discord

logger = logging.getLogger("antenna.discord")


def send_message(content: str, webhook_url: Optional[str] = None) -> bool:
    """Send a single message to Discord via webhook."""
    url = webhook_url or DISCORD_WEBHOOK_URL
    if not url:
        logger.warning(
            "No Discord webhook URL configured. "
            "Set ANTENNA_DISCORD_WEBHOOK environment variable."
        )
        return False

    try:
        resp = requests.post(url, json={
            "content": content,
            "username": "The Antenna",
        }, timeout=10)
        resp.raise_for_status()
        logger.info("Discord message sent successfully.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Discord message: {e}")
        return False


def send_digest(digest_text: str, webhook_url: Optional[str] = None) -> bool:
    """
    Send a full digest to Discord, splitting into multiple messages
    if needed (Discord 2000 char limit).
    """
    chunks = split_for_discord(digest_text)
    success = True

    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(1)  # Don't spam Discord
        if not send_message(chunk, webhook_url):
            success = False

    if success:
        logger.info(f"Digest sent in {len(chunks)} message(s).")
    return success


def send_critical_alert(alert_text: str, webhook_url: Optional[str] = None) -> bool:
    """Send a critical alert immediately."""
    return send_message(alert_text, webhook_url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if DISCORD_WEBHOOK_URL:
        print("Discord webhook configured. Sending test message...")
        send_message("The Antenna test message. If you see this, the webhook works!")
    else:
        print("No DISCORD_WEBHOOK_URL set.")
        print("Set it with: export ANTENNA_DISCORD_WEBHOOK='https://discord.com/api/webhooks/...'")
        print("\nTo test, run:")
        print("  ANTENNA_DISCORD_WEBHOOK='your_url' python3 discord_webhook.py")
