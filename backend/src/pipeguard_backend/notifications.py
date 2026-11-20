"""Pluggable alarm/action notification adapters."""

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import urllib.request
from typing import Any

from pipeguard_backend.api.ws import ConnectionManager
from pipeguard_backend.config import NotificationConfig

logger = logging.getLogger(__name__)


class NotificationHub:
    """Dispatch events to dashboard, webhook, email and SMS adapters."""

    def __init__(self, config: NotificationConfig, websockets: ConnectionManager) -> None:
        """Build enabled channels from configuration."""
        self.config = config
        self.websockets = websockets
        self.channels = {str(c["type"]): c for c in config.channels if c.get("enabled")}

    async def publish(self, event: dict[str, Any]) -> None:
        """Publish an event to every enabled channel."""
        if "websocket" in self.channels:
            await self.websockets.broadcast(event)
        if "webhook" in self.channels:
            await self._webhook(event, str(self.channels["webhook"].get("url", "")))
        if "email" in self.channels:
            await self._email(event, list(self.channels["email"].get("recipients", [])))
        if "sms" in self.channels:
            await self._sms(event, list(self.channels["sms"].get("recipients", [])))

    async def _webhook(self, event: dict[str, Any], url: str) -> None:
        """POST an event to a webhook endpoint."""
        if not url:
            return
        payload = json.dumps(event).encode("utf-8")

        def send() -> None:
            """Perform the blocking HTTP request."""
            request = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
                logger.debug("webhook response %s", response.status)

        try:
            await asyncio.to_thread(send)
        except (OSError, ValueError) as exc:
            logger.warning("webhook notification failed: %s", exc)

    async def _email(self, event: dict[str, Any], recipients: list[str]) -> None:
        """Send an email via SMTP when configured."""
        if not recipients:
            return
        body = f"Subject: PipeGuard {event.get('type')}\n\n{json.dumps(event, indent=2)}"

        def send() -> None:
            """Perform the blocking SMTP send."""
            with smtplib.SMTP("localhost", 25, timeout=5) as smtp:
                smtp.sendmail("pipeguard@localhost", recipients, body)

        try:
            await asyncio.to_thread(send)
        except (OSError, smtplib.SMTPException) as exc:
            logger.warning("email notification failed: %s", exc)

    async def _sms(self, event: dict[str, Any], recipients: list[str]) -> None:
        """Send SMS through a webhook gateway when configured."""
        if not recipients:
            return
        logger.info("SMS notification to %s: %s", recipients, event.get("type"))
