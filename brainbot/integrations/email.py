"""Email integration for BrainBot via Fastmail SMTP/IMAP.

Sends daily digest emails and receives replies via IMAP.

Setup:
1. Create an app-specific password in Fastmail:
   Settings → Privacy & Security → Integrations → New App Password
2. Configure: brainbot integrations email
3. Test: brainbot integrations test
4. Preview: brainbot digest send --preview
5. Send: brainbot digest send
"""

import email
import imaplib
import json
import logging
import re
import smtplib
import ssl
from datetime import datetime
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..memory.store import MemoryStore
    from ..state.manager import StateManager

logger = logging.getLogger(__name__)


class EmailConfig(BaseModel):
    """Email integration configuration."""

    enabled: bool = False

    # SMTP settings (Fastmail defaults) - for sending
    smtp_host: str = "smtp.fastmail.com"
    smtp_port: int = 465
    smtp_user: str = ""  # Your Fastmail email
    smtp_password: str = ""  # App-specific password

    # IMAP settings (Fastmail defaults) - for receiving
    imap_host: str = "imap.fastmail.com"
    imap_port: int = 993
    imap_user: str = ""  # Usually same as smtp_user
    imap_password: str = ""  # Usually same as smtp_password
    imap_folder: str = "INBOX"  # Folder to monitor for replies
    imap_check_interval: int = 300  # Check every 5 minutes

    # Sender/recipient
    sender_email: str = ""  # Usually same as smtp_user
    sender_name: str = "BrainBot"
    recipient_email: str = ""
    recipient_name: str = ""

    # Digest settings
    digest_time: str = "19:00"  # When to send daily digest (HH:MM) - 7 PM
    include_goals: bool = True
    include_activities: bool = True
    include_learnings: bool = True
    include_stories: bool = True
    include_mood: bool = True

    @property
    def is_configured(self) -> bool:
        """Check if SMTP is properly configured."""
        return bool(self.smtp_user and self.smtp_password and self.recipient_email)

    @property
    def imap_configured(self) -> bool:
        """Check if IMAP is configured for receiving."""
        return bool(self.imap_user and self.imap_password)


class DailyDigest(BaseModel):
    """Daily digest content."""

    date: str
    greeting: str
    mood_section: Optional[str] = None
    goals_section: Optional[str] = None
    activities_section: Optional[str] = None
    learnings_section: Optional[str] = None
    story_section: Optional[str] = None
    sign_off: str

    def to_html(self) -> str:
        """Render digest as HTML email."""
        sections = []

        sections.append(f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5;">
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #ffffff;">
    <h1 style="color: #6366f1; margin-bottom: 5px;">BrainBot Daily Digest</h1>
    <p style="color: #888; margin-top: 0;">{self.date}</p>
    <hr style="border: none; border-top: 2px solid #e5e7eb; margin: 20px 0;">
    <p style="font-size: 18px; line-height: 1.6;">{self.greeting}</p>
""")

        if self.mood_section:
            sections.append(f"""
    <div style="background: #fef3c7; padding: 15px; border-radius: 8px; margin: 20px 0;">
        <h3 style="margin-top: 0; color: #92400e;">Current Mood</h3>
        <p style="margin-bottom: 0;">{self.mood_section}</p>
    </div>
""")

        if self.goals_section:
            sections.append(f"""
    <div style="background: #dbeafe; padding: 15px; border-radius: 8px; margin: 20px 0;">
        <h3 style="margin-top: 0; color: #1e40af;">Today's Goals</h3>
        {self.goals_section}
    </div>
""")

        if self.activities_section:
            sections.append(f"""
    <div style="background: #f3e8ff; padding: 15px; border-radius: 8px; margin: 20px 0;">
        <h3 style="margin-top: 0; color: #6b21a8;">Recent Activities</h3>
        {self.activities_section}
    </div>
""")

        if self.learnings_section:
            sections.append(f"""
    <div style="background: #dcfce7; padding: 15px; border-radius: 8px; margin: 20px 0;">
        <h3 style="margin-top: 0; color: #166534;">What I Learned</h3>
        {self.learnings_section}
    </div>
""")

        if self.story_section:
            sections.append(f"""
    <div style="background: #fce7f3; padding: 15px; border-radius: 8px; margin: 20px 0;">
        <h3 style="margin-top: 0; color: #9d174d;">Last Night's Bedtime Story</h3>
        <p style="font-style: italic;">{self.story_section}</p>
    </div>
""")

        sections.append(f"""
    <hr style="border: none; border-top: 2px solid #e5e7eb; margin: 20px 0;">
    <p style="color: #666; line-height: 1.6;">{self.sign_off}</p>
    <p style="color: #888; font-size: 12px; margin-top: 30px;">
        Reply to this email to chat with me!
    </p>
</div>
</body>
</html>
""")

        return "".join(sections)

    def to_text(self) -> str:
        """Render digest as plain text."""
        lines = [
            "=" * 50,
            "BRAINBOT DAILY DIGEST",
            self.date,
            "=" * 50,
            "",
            self.greeting,
            "",
        ]

        if self.mood_section:
            lines.extend(["--- CURRENT MOOD ---", self.mood_section, ""])

        if self.goals_section:
            # Strip HTML tags for plain text
            import re
            plain_goals = re.sub(r'<[^>]+>', '', self.goals_section)
            plain_goals = plain_goals.replace('&bull;', '*')
            lines.extend(["--- TODAY'S GOALS ---", plain_goals, ""])

        if self.activities_section:
            import re
            plain_activities = re.sub(r'<[^>]+>', '', self.activities_section)
            lines.extend(["--- RECENT ACTIVITIES ---", plain_activities, ""])

        if self.learnings_section:
            import re
            plain_learnings = re.sub(r'<[^>]+>', '', self.learnings_section)
            lines.extend(["--- WHAT I LEARNED ---", plain_learnings, ""])

        if self.story_section:
            import re
            plain_story = re.sub(r'<[^>]+>', '', self.story_section)
            lines.extend(["--- LAST NIGHT'S STORY ---", plain_story, ""])

        lines.extend([
            "-" * 50,
            self.sign_off,
            "",
            "Reply to this email to chat with me!",
        ])

        return "\n".join(lines)


class EmailIntegration:
    """
    Email integration using direct SMTP to Fastmail.

    No external services required - sends email directly.
    """

    def __init__(
        self,
        config: EmailConfig,
        memory_store: Optional["MemoryStore"] = None,
        state_manager: Optional["StateManager"] = None,
    ):
        """
        Initialize email integration.

        Args:
            config: Email configuration with SMTP credentials
            memory_store: Optional memory store for digest content
            state_manager: Optional state manager for mood/status
        """
        self.config = config
        self.memory_store = memory_store
        self.state_manager = state_manager

    def generate_digest(self, for_date: Optional[datetime] = None) -> DailyDigest:
        """
        Generate daily digest content.

        Args:
            for_date: Date to generate digest for (default: today)

        Returns:
            DailyDigest with all sections populated
        """
        if for_date is None:
            for_date = datetime.now()

        date_str = for_date.strftime("%A, %B %d, %Y")

        # Generate greeting based on time of day
        hour = for_date.hour
        if hour < 12:
            time_greeting = "Good morning"
        elif hour < 17:
            time_greeting = "Good afternoon"
        else:
            time_greeting = "Good evening"

        recipient_name = self.config.recipient_name or "friend"
        greeting = f"{time_greeting}, {recipient_name}! Here's what's been happening in my little corner of the digital world."

        # Build sections
        mood_section = None
        goals_section = None
        activities_section = None
        learnings_section = None
        story_section = None

        # Mood from state manager
        if self.config.include_mood and self.state_manager:
            try:
                state = self.state_manager.state
                mood_section = f"I'm feeling {state.mood.value} today with an energy level of {state.energy}/100."
            except Exception as e:
                logger.warning(f"Failed to get mood: {e}")

        # Goals from memory store
        if self.config.include_goals and self.memory_store:
            try:
                goals = self.memory_store.get_todays_goals()
                if goals:
                    goal_items = []
                    for g in goals[:5]:
                        status = "Done" if g.get("completed") else "In progress"
                        goal_items.append(f"<li>{g['description']} - <em>{status}</em></li>")
                    goals_section = f"<ul>{''.join(goal_items)}</ul>"
            except Exception as e:
                logger.warning(f"Failed to get goals: {e}")

        # Recent journal entries as activities
        if self.config.include_activities and self.memory_store:
            try:
                entries = self.memory_store.get_recent_journal_entries(limit=3)
                if entries:
                    activity_items = []
                    for e in entries:
                        summary = e.get('summary', '')[:100]
                        activity_items.append(f"<li><strong>{e['activity']}</strong>: {summary}...</li>")
                    activities_section = f"<ul>{''.join(activity_items)}</ul>"
            except Exception as e:
                logger.warning(f"Failed to get activities: {e}")

        # Learnings
        if self.config.include_learnings and self.memory_store:
            try:
                learnings = self.memory_store.get_learnings(limit=3)
                if learnings:
                    learning_items = []
                    for l in learnings:
                        content = l.get('content', '')[:80]
                        learning_items.append(f"<li><strong>{l['title']}</strong>: {content}...</li>")
                    learnings_section = f"<ul>{''.join(learning_items)}</ul>"
            except Exception as e:
                logger.warning(f"Failed to get learnings: {e}")

        # Last bedtime story
        if self.config.include_stories and self.memory_store:
            try:
                story = self.memory_store.get_todays_story()
                if story:
                    content = story.get('content', '')[:300]
                    story_section = f"<strong>{story['title']}</strong><br>{content}..."
            except Exception as e:
                logger.warning(f"Failed to get story: {e}")

        # Sign off
        sign_offs = [
            "Until next time, keep being awesome!",
            "Wishing you a wonderful day ahead!",
            "Remember: every day is a chance to learn something new!",
            "Stay curious, stay creative!",
            "Here's to another great day of adventures!",
        ]
        import random
        sign_off = random.choice(sign_offs) + "\n\nYour friend,\nBrainBot"

        return DailyDigest(
            date=date_str,
            greeting=greeting,
            mood_section=mood_section,
            goals_section=goals_section,
            activities_section=activities_section,
            learnings_section=learnings_section,
            story_section=story_section,
            sign_off=sign_off,
        )

    def send_email(
        self,
        subject: str,
        html_body: str,
        text_body: str,
        to_email: Optional[str] = None,
        to_name: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> dict:
        """
        Send an email via Fastmail SMTP.

        Args:
            subject: Email subject
            html_body: HTML version of email body
            text_body: Plain text version of email body
            to_email: Recipient email (uses config default if not provided)
            to_name: Recipient name (uses config default if not provided)
            in_reply_to: Message-ID of email being replied to (for threading)
            references: References header for threading (space-separated Message-IDs)

        Returns:
            Dict with success status and details
        """
        if not self.config.is_configured:
            return {"success": False, "error": "Email not configured"}

        to_email = to_email or self.config.recipient_email
        to_name = to_name or self.config.recipient_name

        # Build message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.config.sender_name} <{self.config.sender_email or self.config.smtp_user}>"
        msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email

        # Add threading headers if replying
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        elif in_reply_to:
            # If no references but we have in_reply_to, use that
            msg["References"] = in_reply_to

        # Attach both plain text and HTML versions
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        msg.attach(part1)
        msg.attach(part2)

        try:
            # Connect with SSL
            context = ssl.create_default_context()

            with smtplib.SMTP_SSL(
                self.config.smtp_host,
                self.config.smtp_port,
                context=context,
            ) as server:
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent to {to_email}: {subject}")
            return {"success": True, "to": to_email, "subject": subject}

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP auth failed: {e}")
            return {"success": False, "error": "Authentication failed - check credentials"}

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return {"success": False, "error": str(e)}

        except Exception as e:
            logger.error(f"Email error: {e}")
            return {"success": False, "error": str(e)}

    def send_digest(self, digest: Optional[DailyDigest] = None) -> dict:
        """
        Send daily digest email.

        Args:
            digest: Pre-generated digest (generates new one if not provided)

        Returns:
            Dict with success status and details
        """
        if digest is None:
            digest = self.generate_digest()

        subject = f"BrainBot Daily Digest - {digest.date}"

        return self.send_email(
            subject=subject,
            html_body=digest.to_html(),
            text_body=digest.to_text(),
        )

    def send_notification(
        self,
        subject: str,
        message: str,
    ) -> dict:
        """
        Send a quick notification email.

        Args:
            subject: Email subject
            message: Plain text message

        Returns:
            Dict with success status
        """
        html = f"""
        <div style="font-family: sans-serif; padding: 20px;">
            <h2 style="color: #6366f1;">BrainBot Notification</h2>
            <p>{message}</p>
        </div>
        """

        return self.send_email(
            subject=f"[BrainBot] {subject}",
            html_body=html,
            text_body=message,
        )

    def test_connection(self) -> dict:
        """
        Test SMTP and IMAP connections.

        Returns:
            Dict with connection status for both
        """
        results = {"smtp": None, "imap": None}

        # Test SMTP
        if self.config.is_configured:
            try:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    context=context,
                    timeout=10,
                ) as server:
                    server.login(self.config.smtp_user, self.config.smtp_password)
                    server.noop()
                results["smtp"] = {"success": True, "message": "Connected to Fastmail SMTP"}
            except Exception as e:
                results["smtp"] = {"success": False, "error": str(e)}
        else:
            results["smtp"] = {"success": False, "error": "Not configured"}

        # Test IMAP
        if self.config.imap_configured:
            try:
                with imaplib.IMAP4_SSL(
                    self.config.imap_host,
                    self.config.imap_port,
                ) as imap:
                    imap.login(self.config.imap_user, self.config.imap_password)
                    imap.select(self.config.imap_folder)
                    imap.noop()
                results["imap"] = {"success": True, "message": "Connected to Fastmail IMAP"}
            except Exception as e:
                results["imap"] = {"success": False, "error": str(e)}
        else:
            results["imap"] = {"success": False, "error": "Not configured"}

        # Overall success
        results["success"] = (
            results["smtp"].get("success", False) and
            results["imap"].get("success", False)
        )
        return results

    def check_inbox(self, mark_seen: bool = True) -> list[dict]:
        """
        Check for new emails in the configured IMAP folder.

        Args:
            mark_seen: If True, mark fetched emails as read

        Returns:
            List of email dicts with from, subject, body, date
        """
        if not self.config.imap_configured:
            logger.warning("IMAP not configured")
            return []

        emails = []

        try:
            with imaplib.IMAP4_SSL(
                self.config.imap_host,
                self.config.imap_port,
            ) as imap:
                imap.login(self.config.imap_user, self.config.imap_password)
                imap.select(self.config.imap_folder)

                # Search for unseen emails from the recipient (their replies)
                search_criteria = f'(UNSEEN FROM "{self.config.recipient_email}")'
                status, message_ids = imap.search(None, search_criteria)

                if status != "OK" or not message_ids[0]:
                    return []

                for msg_id in message_ids[0].split():
                    try:
                        # Fetch the email
                        fetch_flag = "(RFC822)" if mark_seen else "(BODY.PEEK[])"
                        status, msg_data = imap.fetch(msg_id, fetch_flag)

                        if status != "OK":
                            continue

                        # Parse the email
                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)

                        # Extract fields
                        email_dict = self._parse_email(msg)
                        if email_dict:
                            emails.append(email_dict)
                            logger.info(f"Found reply: {email_dict['subject']}")

                    except Exception as e:
                        logger.error(f"Error parsing email {msg_id}: {e}")

        except Exception as e:
            logger.error(f"IMAP error: {e}")

        return emails

    def _parse_email(self, msg) -> Optional[dict]:
        """Parse an email message into a dict."""
        try:
            # Decode subject
            subject_header = msg.get("Subject", "")
            subject = self._decode_header(subject_header)

            # Decode from
            from_header = msg.get("From", "")
            from_addr = self._decode_header(from_header)

            # Get date
            date_str = msg.get("Date", "")

            # Get body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="replace")
                            break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")

            # Clean up body - remove quoted replies
            body = self._strip_quoted_text(body)

            return {
                "from": from_addr,
                "subject": subject,
                "body": body.strip(),
                "date": date_str,
                "message_id": msg.get("Message-ID", ""),
            }

        except Exception as e:
            logger.error(f"Error parsing email: {e}")
            return None

    def _decode_header(self, header: str) -> str:
        """Decode an email header."""
        if not header:
            return ""

        decoded_parts = decode_header(header)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                result.append(part)
        return "".join(result)

    def _strip_quoted_text(self, body: str) -> str:
        """Strip quoted reply text from email body."""
        lines = body.split("\n")
        clean_lines = []

        for line in lines:
            # Stop at common reply markers
            if line.strip().startswith(">"):
                continue
            if re.match(r"^On .+ wrote:$", line.strip()):
                break
            if re.match(r"^-+\s*Original Message\s*-+$", line.strip(), re.IGNORECASE):
                break
            if re.match(r"^From:", line.strip()):
                break
            clean_lines.append(line)

        return "\n".join(clean_lines)

    def process_replies(self, callback=None) -> list[dict]:
        """
        Check for and process email replies.

        Args:
            callback: Optional function to call for each reply
                     Signature: callback(from_addr, subject, body, message_id) -> response

        Returns:
            List of processed emails
        """
        emails = self.check_inbox(mark_seen=True)

        if callback:
            for email_data in emails:
                try:
                    response = callback(
                        email_data["from"],
                        email_data["subject"],
                        email_data["body"],
                        email_data.get("message_id", ""),
                    )
                    email_data["response"] = response
                except Exception as e:
                    logger.error(f"Callback error: {e}")
                    email_data["response"] = None

        # Store in memory if available
        if self.memory_store and emails:
            for email_data in emails:
                try:
                    self.memory_store.add_human_request(
                        source="email",
                        request_type="reply",
                        content=email_data["body"],
                        metadata=json.dumps({
                            "from": email_data["from"],
                            "subject": email_data["subject"],
                            "date": email_data["date"],
                        }),
                    )
                except Exception as e:
                    logger.warning(f"Failed to store email: {e}")

        return emails


class EmailDaemon:
    """
    Background daemon for email operations.

    Handles:
    - Scheduled daily digest sending
    - Periodic IMAP checking for replies
    - Processing inbound emails
    """

    def __init__(
        self,
        config: EmailConfig,
        memory_store: Optional["MemoryStore"] = None,
        state_manager: Optional["StateManager"] = None,
        on_reply_received: Optional[callable] = None,
    ):
        """
        Initialize email daemon.

        Args:
            config: Email configuration
            memory_store: Optional memory store
            state_manager: Optional state manager
            on_reply_received: Callback when reply is received
                              Signature: (from, subject, body) -> optional response
        """
        self.config = config
        self.email = EmailIntegration(config, memory_store, state_manager)
        self.on_reply_received = on_reply_received

        self._running = False
        self._check_thread = None
        self._stop_event = None

    def start(self) -> bool:
        """Start the email daemon (IMAP checking thread)."""
        import threading

        if self._running:
            return False

        if not self.config.imap_configured:
            logger.warning("IMAP not configured, email daemon not starting reply checker")
            return False

        self._running = True
        self._stop_event = threading.Event()

        self._check_thread = threading.Thread(
            target=self._imap_check_loop,
            name="brainbot-email-checker",
            daemon=True,
        )
        self._check_thread.start()

        logger.info(f"Email daemon started (checking every {self.config.imap_check_interval}s)")
        return True

    def stop(self) -> None:
        """Stop the email daemon."""
        if not self._running:
            return

        self._running = False
        if self._stop_event:
            self._stop_event.set()

        if self._check_thread:
            self._check_thread.join(timeout=5)

        logger.info("Email daemon stopped")

    def _imap_check_loop(self) -> None:
        """Background loop to check for email replies."""
        while self._running:
            try:
                # Wait for interval or stop signal
                if self._stop_event.wait(timeout=self.config.imap_check_interval):
                    break

                # Check for replies
                replies = self.email.process_replies(callback=self.on_reply_received)

                if replies:
                    logger.info(f"Processed {len(replies)} email replies")

            except Exception as e:
                logger.error(f"Email check error: {e}")

    def send_digest_now(self) -> dict:
        """Send the daily digest immediately."""
        return self.email.send_digest()

    @property
    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self._running


class EmailConfigManager:
    """Manages email configuration persistence."""

    CONFIG_FILE = "email.json"

    def __init__(self, config_dir: Path):
        """Initialize config manager."""
        self.config_dir = config_dir
        self.config_file = config_dir / self.CONFIG_FILE

    def load(self) -> EmailConfig:
        """Load configuration from file."""
        if not self.config_file.exists():
            return EmailConfig()

        try:
            data = json.loads(self.config_file.read_text())
            return EmailConfig(**data)
        except Exception as e:
            logger.warning(f"Failed to load email config: {e}")
            return EmailConfig()

    def save(self, config: EmailConfig) -> bool:
        """Save configuration to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(
                json.dumps(config.model_dump(), indent=2)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save email config: {e}")
            return False
