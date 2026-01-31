"""Slack integration for BrainBot using Bolt SDK with Socket Mode."""

import logging
import os
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Check for slack_bolt availability
try:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    App = None
    SocketModeHandler = None


class SlackBot:
    """
    Slack bot integration for BrainBot.

    Uses Socket Mode so no public URL is needed - perfect for
    home setups like Raspberry Pi.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        app_token: Optional[str] = None,
        on_message: Optional[Callable[[str], str]] = None,
    ):
        """
        Initialize Slack bot.

        Args:
            bot_token: Slack bot token (xoxb-...), or uses SLACK_BOT_TOKEN env var
            app_token: Slack app token (xapp-...), or uses SLACK_APP_TOKEN env var
            on_message: Callback to handle messages, receives text, returns response
        """
        if not SLACK_AVAILABLE:
            raise ImportError(
                "slack_bolt not installed. Run: pip install slack-bolt"
            )

        self.bot_token = bot_token or os.environ.get("SLACK_BOT_TOKEN")
        self.app_token = app_token or os.environ.get("SLACK_APP_TOKEN")

        if not self.bot_token:
            raise ValueError("SLACK_BOT_TOKEN not provided or set in environment")
        if not self.app_token:
            raise ValueError("SLACK_APP_TOKEN not provided or set in environment")

        self.on_message = on_message
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._handler: Optional[SocketModeHandler] = None

        # Initialize Slack app
        self.app = App(token=self.bot_token)
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Setup Slack event handlers."""

        @self.app.event("app_mention")
        def handle_mention(event, say):
            """Handle @BrainBot mentions in channels."""
            self._handle_message(event, say)

        @self.app.event("message")
        def handle_dm(event, say):
            """Handle direct messages."""
            # Only respond to DMs (no channel_type means it's a DM)
            # Also ignore bot messages to prevent loops
            if event.get("channel_type") == "im" and not event.get("bot_id"):
                self._handle_message(event, say)

    def _handle_message(self, event: dict, say: Callable) -> None:
        """Process incoming message and respond."""
        text = event.get("text", "").strip()
        user = event.get("user", "unknown")

        # Remove bot mention if present (e.g., "<@U123ABC> hello" -> "hello")
        import re
        text = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()

        if not text:
            return

        logger.debug(f"Slack message from {user}: {text[:50]}...")

        # Get response from BrainBot
        if self.on_message:
            try:
                response = self.on_message(text)
                if response:
                    say(response)
            except Exception as e:
                logger.error(f"Error handling Slack message: {e}")
                say(f"Sorry, I encountered an error: {str(e)[:100]}")
        else:
            say("BrainBot is running but chat is not connected.")

    def start(self, blocking: bool = False) -> None:
        """
        Start the Slack bot.

        Args:
            blocking: If True, blocks the current thread. If False, runs in background.
        """
        if self._running:
            logger.warning("Slack bot already running")
            return

        self._handler = SocketModeHandler(self.app, self.app_token)
        self._running = True

        logger.info("Starting Slack bot (Socket Mode)...")

        if blocking:
            self._handler.start()
        else:
            self._thread = threading.Thread(target=self._handler.start, daemon=True)
            self._thread.start()
            logger.info("Slack bot started in background")

    def stop(self) -> None:
        """Stop the Slack bot."""
        if self._handler and self._running:
            self._running = False
            try:
                self._handler.close()
                logger.info("Slack bot stopped")
            except Exception as e:
                logger.error(f"Error stopping Slack bot: {e}")


def run_slack_bot():
    """Run Slack bot standalone (for testing)."""
    import sys
    sys.path.insert(0, str(__file__).rsplit("/", 3)[0])

    from ..config.settings import Settings
    from ..agent.delegator import ClaudeDelegator

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    settings = Settings.load()
    delegator = ClaudeDelegator(settings)

    def handle_chat(message: str) -> str:
        """Handle chat message via Claude."""
        result = delegator.delegate_for_chat(message)
        return result.output if result.success else f"Error: {result.error}"

    bot = SlackBot(on_message=handle_chat)

    print("Starting BrainBot Slack integration...")
    print("Send a DM or @mention me in a channel!")
    print("Press Ctrl+C to stop")

    try:
        bot.start(blocking=True)
    except KeyboardInterrupt:
        print("\nStopping...")
        bot.stop()


if __name__ == "__main__":
    run_slack_bot()
