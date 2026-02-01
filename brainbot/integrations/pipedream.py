"""Pipedream integration for BrainBot.

Pipedream is a webhook-based integration platform that connects 1000+ services.
BrainBot uses it as a bridge to external services like email, calendar, etc.

Architecture:
- Outbound: BrainBot calls Pipedream webhooks to trigger workflows
- Inbound: Pipedream calls BrainBot's webhook endpoint with events

Docs: https://pipedream.com/docs
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class PipedreamConfig(BaseModel):
    """Pipedream integration configuration."""

    enabled: bool = False

    # Outbound webhooks (BrainBot → Pipedream)
    webhook_daily_digest: str = ""  # Triggers daily digest email
    webhook_notification: str = ""  # Triggers instant notification
    webhook_log_event: str = ""  # Logs events to external service

    # Inbound webhook secret (for verifying Pipedream → BrainBot calls)
    inbound_secret: str = ""

    # Optional: API key for Pipedream REST API
    api_key: str = ""

    @property
    def is_configured(self) -> bool:
        """Check if at least one webhook is configured."""
        return bool(
            self.webhook_daily_digest or
            self.webhook_notification or
            self.webhook_log_event
        )


class PipedreamClient:
    """
    Client for interacting with Pipedream webhooks.

    Usage:
        config = PipedreamConfig(webhook_daily_digest="https://...")
        client = PipedreamClient(config)

        # Trigger a workflow
        result = client.trigger("daily_digest", {
            "subject": "BrainBot Daily Digest",
            "body": "Here's what happened today..."
        })
    """

    WEBHOOK_TIMEOUT = 30  # seconds

    def __init__(self, config: PipedreamConfig):
        """
        Initialize Pipedream client.

        Args:
            config: Pipedream configuration
        """
        self.config = config
        self._webhook_map = {
            "daily_digest": config.webhook_daily_digest,
            "notification": config.webhook_notification,
            "log_event": config.webhook_log_event,
        }

    def trigger(
        self,
        workflow: str,
        data: dict[str, Any],
        timeout: int = None,
    ) -> dict:
        """
        Trigger a Pipedream workflow via webhook.

        Args:
            workflow: Workflow name (daily_digest, notification, log_event)
            data: Payload to send to the webhook
            timeout: Request timeout in seconds

        Returns:
            Dict with success status and response/error
        """
        webhook_url = self._webhook_map.get(workflow)

        if not webhook_url:
            return {
                "success": False,
                "error": f"No webhook configured for workflow: {workflow}",
            }

        return self._call_webhook(webhook_url, data, timeout or self.WEBHOOK_TIMEOUT)

    def trigger_custom(
        self,
        webhook_url: str,
        data: dict[str, Any],
        timeout: int = None,
    ) -> dict:
        """
        Trigger a custom webhook URL.

        Args:
            webhook_url: Full Pipedream webhook URL
            data: Payload to send
            timeout: Request timeout in seconds

        Returns:
            Dict with success status and response/error
        """
        return self._call_webhook(webhook_url, data, timeout or self.WEBHOOK_TIMEOUT)

    def _call_webhook(
        self,
        url: str,
        data: dict[str, Any],
        timeout: int,
    ) -> dict:
        """Make HTTP POST request to webhook."""
        try:
            # Add metadata to payload
            payload = {
                "timestamp": datetime.now().isoformat(),
                "source": "brainbot",
                **data,
            }

            json_data = json.dumps(payload).encode("utf-8")

            request = Request(
                url,
                data=json_data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "BrainBot/1.0",
                },
                method="POST",
            )

            with urlopen(request, timeout=timeout) as response:
                response_body = response.read().decode("utf-8")

                # Try to parse as JSON
                try:
                    response_data = json.loads(response_body)
                except json.JSONDecodeError:
                    response_data = {"raw": response_body}

                logger.info(f"Webhook triggered successfully: {url[:50]}...")
                return {
                    "success": True,
                    "status_code": response.status,
                    "response": response_data,
                }

        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            logger.error(f"Webhook HTTP error: {e.code} - {error_body}")
            return {
                "success": False,
                "error": f"HTTP {e.code}: {e.reason}",
                "details": error_body,
            }

        except URLError as e:
            logger.error(f"Webhook connection error: {e.reason}")
            return {
                "success": False,
                "error": f"Connection error: {e.reason}",
            }

        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def test_connection(self) -> dict:
        """
        Test webhook connections.

        Returns:
            Dict with test results for each configured webhook
        """
        results = {}

        for name, url in self._webhook_map.items():
            if url:
                result = self.trigger(name, {"test": True, "ping": "pong"})
                results[name] = {
                    "configured": True,
                    "reachable": result["success"],
                    "error": result.get("error"),
                }
            else:
                results[name] = {"configured": False}

        return results


class PipedreamConfigManager:
    """Manages Pipedream configuration persistence."""

    CONFIG_FILE = "pipedream.json"

    def __init__(self, config_dir: Path):
        """
        Initialize config manager.

        Args:
            config_dir: Directory for configuration files
        """
        self.config_dir = config_dir
        self.config_file = config_dir / self.CONFIG_FILE

    def load(self) -> PipedreamConfig:
        """Load configuration from file."""
        if not self.config_file.exists():
            return PipedreamConfig()

        try:
            data = json.loads(self.config_file.read_text())
            return PipedreamConfig(**data)
        except Exception as e:
            logger.warning(f"Failed to load Pipedream config: {e}")
            return PipedreamConfig()

    def save(self, config: PipedreamConfig) -> bool:
        """Save configuration to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(
                json.dumps(config.model_dump(), indent=2)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save Pipedream config: {e}")
            return False

    def update(self, **kwargs) -> PipedreamConfig:
        """Update specific configuration fields."""
        config = self.load()
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        self.save(config)
        return config
