"""
Slack-based inter-node communication for BrainBot network.

Uses Slack as a real-time coordination layer for:
- Node boot/shutdown announcements
- Task announcements and claims
- Inter-node messaging
- Human-observable activity log

The #brainbot-network channel serves as the "nervous system" where
all nodes post their activity, enabling both coordination and transparency.
"""

import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Check for slack_sdk availability
try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_SDK_AVAILABLE = True
except ImportError:
    SLACK_SDK_AVAILABLE = False
    WebClient = None
    SlackApiError = Exception


class SlackNetworkBot:
    """
    Slack-based network communication for BrainBot nodes.

    Provides real-time inter-node messaging via Slack, complementing
    the R2-based task queue for persistence.
    """

    # Emoji for different event types
    EMOJI = {
        "boot": ":rocket:",
        "shutdown": ":wave:",
        "task_announce": ":clipboard:",
        "task_claim": ":raised_hand:",
        "task_complete": ":white_check_mark:",
        "task_fail": ":x:",
        "heartbeat": ":heartbeat:",
        "message": ":speech_balloon:",
        "thinking": ":brain:",
        "error": ":warning:",
    }

    def __init__(
        self,
        bot_token: Optional[str] = None,
        network_channel: Optional[str] = None,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
    ):
        """
        Initialize Slack network bot.

        Args:
            bot_token: Slack bot token (xoxb-...), or uses SLACK_BOT_TOKEN env var
            network_channel: Channel ID for #brainbot-network, or uses SLACK_NETWORK_CHANNEL
            node_id: This node's unique ID
            node_name: This node's display name (persona)
        """
        if not SLACK_SDK_AVAILABLE:
            raise ImportError("slack_sdk not installed. Run: pip install slack-sdk")

        self.bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
        self.network_channel = network_channel or os.environ.get("SLACK_NETWORK_CHANNEL")
        self.node_id = node_id
        self.node_name = node_name or "Unknown Node"

        if not self.bot_token:
            raise ValueError("SLACK_BOT_TOKEN not provided or set in environment")

        self.client = WebClient(token=self.bot_token)

        # Task subscription
        self._task_callbacks: list[Callable] = []
        self._message_callbacks: list[Callable] = []
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._last_message_ts: Optional[str] = None

    def _post_to_network(
        self,
        text: str,
        blocks: Optional[list] = None,
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """
        Post a message to the network channel.

        Args:
            text: Message text (fallback for notifications)
            blocks: Rich message blocks
            thread_ts: Thread timestamp to reply to

        Returns:
            Message timestamp if successful, None otherwise
        """
        if not self.network_channel:
            logger.warning("Network channel not configured, message not sent")
            return None

        try:
            response = self.client.chat_postMessage(
                channel=self.network_channel,
                text=text,
                blocks=blocks,
                thread_ts=thread_ts,
            )
            return response.get("ts")
        except SlackApiError as e:
            logger.error(f"Slack API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to post to network channel: {e}")
            return None

    def _format_node_header(self) -> str:
        """Format node identifier for messages."""
        node_short = self.node_id[:8] if self.node_id else "unknown"
        return f"*{self.node_name}* (`{node_short}`)"

    # ========== Node Lifecycle ==========

    def post_node_boot(
        self,
        persona: Optional[dict] = None,
        capabilities: Optional[list[str]] = None,
        version: Optional[str] = None,
    ) -> Optional[str]:
        """
        Announce node boot to the network.

        Args:
            persona: Node persona dict (name, role, traits)
            capabilities: List of hardware capabilities
            version: BrainBot version string

        Returns:
            Message timestamp if successful
        """
        emoji = self.EMOJI["boot"]

        # Build capabilities summary
        caps_text = ""
        if capabilities:
            caps_preview = capabilities[:5]
            caps_text = ", ".join(caps_preview)
            if len(capabilities) > 5:
                caps_text += f" (+{len(capabilities) - 5} more)"

        # Build persona summary
        role = persona.get("role", "node") if persona else "node"
        traits = persona.get("traits", []) if persona else []
        traits_text = ", ".join(traits[:3]) if traits else ""

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} {self._format_node_header()} is online!"
                }
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"*Role:* {role}"},
                    {"type": "mrkdwn", "text": f"*Version:* {version or 'unknown'}"},
                ]
            }
        ]

        if caps_text:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"*Capabilities:* {caps_text}"}
                ]
            })

        if traits_text:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"*Traits:* {traits_text}"}
                ]
            })

        text = f"{emoji} {self.node_name} ({self.node_id[:8] if self.node_id else 'unknown'}) is online"
        return self._post_to_network(text, blocks=blocks)

    def post_node_shutdown(self, reason: str = "graceful shutdown") -> Optional[str]:
        """
        Announce node shutdown to the network.

        Args:
            reason: Reason for shutdown

        Returns:
            Message timestamp if successful
        """
        emoji = self.EMOJI["shutdown"]
        text = f"{emoji} {self._format_node_header()} is going offline ({reason})"
        return self._post_to_network(text)

    # ========== Task Coordination ==========

    def post_task_announcement(
        self,
        task_id: str,
        task_type: str,
        description: str,
        requirements: Optional[list[str]] = None,
        priority: int = 1,
    ) -> Optional[str]:
        """
        Announce a new task that needs to be claimed.

        Args:
            task_id: Unique task identifier
            task_type: Type of task (e.g., "display_text", "generate_image")
            description: Human-readable description
            requirements: Required capabilities
            priority: Task priority (1-10)

        Returns:
            Message timestamp if successful
        """
        emoji = self.EMOJI["task_announce"]

        priority_emoji = "🔴" if priority >= 8 else "🟡" if priority >= 5 else "🟢"

        reqs_text = ""
        if requirements:
            reqs_text = ", ".join(requirements[:3])
            if len(requirements) > 3:
                reqs_text += f" (+{len(requirements) - 3} more)"

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *New Task Available*\n_{description[:100]}_"
                }
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"*ID:* `{task_id[:8]}...`"},
                    {"type": "mrkdwn", "text": f"*Type:* {task_type}"},
                    {"type": "mrkdwn", "text": f"*Priority:* {priority_emoji} {priority}"},
                ]
            }
        ]

        if reqs_text:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"*Requires:* {reqs_text}"}
                ]
            })

        # Add claim button hint
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "_React with :raised_hand: to claim_"}
            ]
        })

        text = f"{emoji} New task: {task_type} - {description[:50]}..."
        return self._post_to_network(text, blocks=blocks)

    def post_task_claimed(
        self,
        task_id: str,
        task_type: str,
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """
        Announce that this node has claimed a task.

        Args:
            task_id: Task identifier
            task_type: Type of task
            thread_ts: Original task announcement thread

        Returns:
            Message timestamp if successful
        """
        emoji = self.EMOJI["task_claim"]
        text = f"{emoji} {self._format_node_header()} claimed task `{task_id[:8]}...` ({task_type})"
        return self._post_to_network(text, thread_ts=thread_ts)

    def post_task_completed(
        self,
        task_id: str,
        task_type: str,
        result_summary: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """
        Announce task completion.

        Args:
            task_id: Task identifier
            task_type: Type of task
            result_summary: Brief summary of result
            thread_ts: Original task announcement thread

        Returns:
            Message timestamp if successful
        """
        emoji = self.EMOJI["task_complete"]

        text = f"{emoji} {self._format_node_header()} completed task `{task_id[:8]}...` ({task_type})"
        if result_summary:
            text += f"\n> {result_summary[:100]}"

        return self._post_to_network(text, thread_ts=thread_ts)

    def post_task_failed(
        self,
        task_id: str,
        task_type: str,
        error: str,
        thread_ts: Optional[str] = None,
    ) -> Optional[str]:
        """
        Announce task failure.

        Args:
            task_id: Task identifier
            task_type: Type of task
            error: Error message
            thread_ts: Original task announcement thread

        Returns:
            Message timestamp if successful
        """
        emoji = self.EMOJI["task_fail"]
        text = f"{emoji} {self._format_node_header()} failed task `{task_id[:8]}...` ({task_type})\n> Error: {error[:100]}"
        return self._post_to_network(text, thread_ts=thread_ts)

    # ========== Inter-node Messaging ==========

    def send_to_node(
        self,
        target_node_name: str,
        message: str,
        message_type: str = "chat",
    ) -> Optional[str]:
        """
        Send a message to a specific node via the network channel.

        Uses @mention format so the target node can filter relevant messages.

        Args:
            target_node_name: Name of target node
            message: Message content
            message_type: Type of message (chat, command, status)

        Returns:
            Message timestamp if successful
        """
        emoji = self.EMOJI["message"]
        text = f"{emoji} {self._format_node_header()} → *{target_node_name}*: {message}"
        return self._post_to_network(text)

    def post_status_update(self, status: str, details: Optional[str] = None) -> Optional[str]:
        """
        Post a status update about current activity.

        Args:
            status: Current status (e.g., "thinking", "writing story")
            details: Additional details

        Returns:
            Message timestamp if successful
        """
        emoji = self.EMOJI["thinking"]
        text = f"{emoji} {self._format_node_header()}: {status}"
        if details:
            text += f"\n> {details[:100]}"
        return self._post_to_network(text)

    # ========== Task Subscription ==========

    def subscribe_to_tasks(self, callback: Callable[[dict], None]) -> None:
        """
        Subscribe to task announcements.

        The callback will be called with task data when new tasks are announced.

        Args:
            callback: Function to call with task dict
        """
        self._task_callbacks.append(callback)

    def subscribe_to_messages(self, callback: Callable[[str, str, str], None]) -> None:
        """
        Subscribe to inter-node messages.

        The callback will be called with (from_node, to_node, message).

        Args:
            callback: Function to call with message data
        """
        self._message_callbacks.append(callback)

    def _poll_for_tasks(self) -> None:
        """Poll network channel for new task announcements."""
        while self._running:
            try:
                if not self.network_channel:
                    time.sleep(5)
                    continue

                # Get recent messages
                response = self.client.conversations_history(
                    channel=self.network_channel,
                    limit=10,
                    oldest=self._last_message_ts,
                )

                messages = response.get("messages", [])
                for msg in reversed(messages):  # Process oldest first
                    ts = msg.get("ts", "")

                    # Skip our own messages
                    if self._is_own_message(msg):
                        continue

                    # Update last seen
                    if not self._last_message_ts or ts > self._last_message_ts:
                        self._last_message_ts = ts

                    # Parse and dispatch
                    self._process_network_message(msg)

            except SlackApiError as e:
                logger.error(f"Slack polling error: {e}")
            except Exception as e:
                logger.error(f"Task poll error: {e}")

            time.sleep(2)  # Poll every 2 seconds

    def _is_own_message(self, msg: dict) -> bool:
        """Check if a message is from this node."""
        text = msg.get("text", "")
        return self.node_name in text and self.node_id and self.node_id[:8] in text

    def _process_network_message(self, msg: dict) -> None:
        """Process a network channel message."""
        text = msg.get("text", "")

        # Check for task announcements
        if self.EMOJI["task_announce"] in text and "New Task Available" in text:
            task_data = self._parse_task_announcement(msg)
            if task_data:
                for callback in self._task_callbacks:
                    try:
                        callback(task_data)
                    except Exception as e:
                        logger.error(f"Task callback error: {e}")

        # Check for direct messages to this node
        if f"→ *{self.node_name}*" in text:
            message_data = self._parse_direct_message(msg)
            if message_data:
                for callback in self._message_callbacks:
                    try:
                        callback(*message_data)
                    except Exception as e:
                        logger.error(f"Message callback error: {e}")

    def _parse_task_announcement(self, msg: dict) -> Optional[dict]:
        """Parse a task announcement message."""
        try:
            text = msg.get("text", "")
            blocks = msg.get("blocks", [])

            task_data = {
                "ts": msg.get("ts"),
                "task_type": None,
                "task_id": None,
                "priority": 1,
                "requirements": [],
            }

            # Extract from blocks if available
            for block in blocks:
                if block.get("type") == "context":
                    for elem in block.get("elements", []):
                        text_content = elem.get("text", "")
                        if "*ID:*" in text_content:
                            match = re.search(r"`([^`]+)`", text_content)
                            if match:
                                task_data["task_id"] = match.group(1).replace("...", "")
                        elif "*Type:*" in text_content:
                            task_data["task_type"] = text_content.split("*Type:*")[-1].strip()
                        elif "*Priority:*" in text_content:
                            match = re.search(r"(\d+)", text_content)
                            if match:
                                task_data["priority"] = int(match.group(1))
                        elif "*Requires:*" in text_content:
                            reqs = text_content.split("*Requires:*")[-1].strip()
                            task_data["requirements"] = [r.strip() for r in reqs.split(",")]

            return task_data if task_data["task_id"] else None

        except Exception as e:
            logger.error(f"Failed to parse task announcement: {e}")
            return None

    def _parse_direct_message(self, msg: dict) -> Optional[tuple]:
        """Parse a direct message to this node."""
        try:
            text = msg.get("text", "")

            # Pattern: *NodeName* (`id`) → *TargetNode*: message
            pattern = r"\*([^*]+)\*\s+\(`[^`]+`\)\s+→\s+\*[^*]+\*:\s+(.+)"
            match = re.search(pattern, text)

            if match:
                from_node = match.group(1)
                message = match.group(2)
                return (from_node, self.node_name, message)

            return None

        except Exception as e:
            logger.error(f"Failed to parse direct message: {e}")
            return None

    # ========== Lifecycle ==========

    def start_polling(self) -> None:
        """Start polling for task announcements."""
        if self._running:
            return

        self._running = True
        self._poll_thread = threading.Thread(target=self._poll_for_tasks, daemon=True)
        self._poll_thread.start()
        logger.info("Slack network polling started")

    def stop_polling(self) -> None:
        """Stop polling for task announcements."""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=3)
            self._poll_thread = None
        logger.info("Slack network polling stopped")

    def react_to_claim(self, message_ts: str) -> bool:
        """
        React to a task announcement to claim it.

        Args:
            message_ts: Message timestamp to react to

        Returns:
            True if reaction added successfully
        """
        if not self.network_channel:
            return False

        try:
            self.client.reactions_add(
                channel=self.network_channel,
                timestamp=message_ts,
                name="raised_hand",
            )
            return True
        except SlackApiError as e:
            if "already_reacted" in str(e):
                return True  # Already claimed
            logger.error(f"Failed to add reaction: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to react: {e}")
            return False

    def get_network_status(self) -> dict:
        """
        Get current network status from recent channel activity.

        Returns:
            Dict with online nodes, pending tasks, etc.
        """
        if not self.network_channel:
            return {"error": "Network channel not configured"}

        try:
            response = self.client.conversations_history(
                channel=self.network_channel,
                limit=50,
            )

            messages = response.get("messages", [])
            online_nodes = set()
            pending_tasks = 0

            for msg in messages:
                text = msg.get("text", "")

                # Count online nodes (recent boot announcements)
                if self.EMOJI["boot"] in text:
                    match = re.search(r"\*([^*]+)\*\s+\(`([^`]+)`\)", text)
                    if match:
                        online_nodes.add(match.group(1))

                # Count offline nodes
                if self.EMOJI["shutdown"] in text:
                    match = re.search(r"\*([^*]+)\*\s+\(`([^`]+)`\)", text)
                    if match:
                        online_nodes.discard(match.group(1))

                # Count pending tasks (announced but not completed)
                if self.EMOJI["task_announce"] in text:
                    pending_tasks += 1
                if self.EMOJI["task_complete"] in text or self.EMOJI["task_fail"] in text:
                    pending_tasks = max(0, pending_tasks - 1)

            return {
                "online_nodes": len(online_nodes),
                "node_names": list(online_nodes),
                "pending_tasks": pending_tasks,
                "channel": self.network_channel,
            }

        except Exception as e:
            logger.error(f"Failed to get network status: {e}")
            return {"error": str(e)}


# Singleton instance
_instance: Optional[SlackNetworkBot] = None


def get_slack_network(
    node_id: Optional[str] = None,
    node_name: Optional[str] = None,
) -> Optional[SlackNetworkBot]:
    """
    Get or create the Slack network bot singleton.

    Args:
        node_id: Node identifier (required on first call)
        node_name: Node display name (required on first call)

    Returns:
        SlackNetworkBot instance or None if not configured
    """
    global _instance

    if _instance is not None:
        return _instance

    # Check for required configuration
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    network_channel = os.environ.get("SLACK_NETWORK_CHANNEL")

    if not bot_token:
        logger.debug("SLACK_BOT_TOKEN not set, Slack network disabled")
        return None

    if not network_channel:
        logger.debug("SLACK_NETWORK_CHANNEL not set, Slack network disabled")
        return None

    try:
        _instance = SlackNetworkBot(
            bot_token=bot_token,
            network_channel=network_channel,
            node_id=node_id,
            node_name=node_name,
        )
        return _instance
    except Exception as e:
        logger.error(f"Failed to create Slack network bot: {e}")
        return None
