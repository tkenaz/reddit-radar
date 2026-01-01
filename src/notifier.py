"""
Unified notification system for Reddit Radar.
Supports Telegram, Slack, Email, and Console output.
"""
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import json
import logging

from .config import get_settings, TelegramConfig, SlackConfig, EmailConfig

logger = logging.getLogger(__name__)


class Priority(Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Notification:
    """Notification data container."""
    title: str
    message: str
    priority: Priority = Priority.NORMAL
    url: Optional[str] = None


class BaseNotifier(ABC):
    """Abstract base class for notifiers."""

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """Send a notification. Returns True if successful."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if this notifier is properly configured."""
        pass


class TelegramNotifier(BaseNotifier):
    """Telegram notification sender with inline keyboard support."""

    def __init__(self, config: TelegramConfig):
        self.config = config
        self.api_url = f"https://api.telegram.org/bot{config.bot_token}"

    def is_configured(self) -> bool:
        return bool(self.config and self.config.bot_token and self.config.chat_id)

    def send(self, notification: Notification) -> bool:
        if not self.is_configured():
            return False

        try:
            # Format message with markdown
            message = f"**{notification.title}**\n\n{notification.message}"
            if notification.url:
                message += f"\n\n[View on Reddit]({notification.url})"

            # Add priority emoji
            priority_emoji = {
                Priority.LOW: "",
                Priority.NORMAL: "",
                Priority.HIGH: "🔥 ",
                Priority.URGENT: "🚨 "
            }
            message = priority_emoji.get(notification.priority, "") + message

            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.config.chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False
                },
                timeout=10
            )
            response.raise_for_status()
            return True

        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
            return False

    def send_draft_for_approval(
        self,
        draft_id: str,
        post_title: str,
        post_url: str,
        subreddit: str,
        intent: str,
        confidence: float,
        draft_content: str,
        score: int = 0,
        comments: int = 0,
    ) -> Optional[int]:
        """
        Send a draft response for approval with inline keyboard.

        Returns message_id if successful, None otherwise.
        """
        if not self.is_configured():
            return None

        try:
            # Normalize intent to string
            intent_str = intent.value if hasattr(intent, 'value') else str(intent)

            # Format message
            intent_emoji = {
                "hot_lead": "🔥",
                "partnership": "🤝",
                "content_idea": "💡",
            }
            emoji = intent_emoji.get(intent_str, "📝")

            message = (
                f"{emoji} *{intent_str.upper()}* ({confidence:.0%})\n\n"
                f"*{self._escape_markdown(post_title[:100])}*\n"
                f"r/{subreddit} | ↑{score} | 💬{comments}\n\n"
                f"---\n\n"
                f"*Draft Response:*\n"
                f"```\n{draft_content}\n```\n\n"
                f"[View Post]({post_url})"
            )

            # Inline keyboard with approval buttons
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Post", "callback_data": f"post:{draft_id}"},
                        {"text": "✏️ Edit", "callback_data": f"edit:{draft_id}"},
                        {"text": "❌ Skip", "callback_data": f"skip:{draft_id}"},
                    ]
                ]
            }

            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.config.chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "reply_markup": keyboard,
                    "disable_web_page_preview": True,
                },
                timeout=10
            )
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                return result["result"]["message_id"]
            return None

        except Exception as e:
            logger.error(f"Telegram draft notification failed: {e}")
            return None

    def update_message(
        self,
        message_id: int,
        new_text: str,
        remove_keyboard: bool = True
    ) -> bool:
        """Update an existing message (e.g., after approval)."""
        if not self.is_configured():
            return False

        try:
            payload = {
                "chat_id": self.config.chat_id,
                "message_id": message_id,
                "text": new_text,
                "parse_mode": "Markdown",
            }

            if remove_keyboard:
                payload["reply_markup"] = {"inline_keyboard": []}

            response = requests.post(
                f"{self.api_url}/editMessageText",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return True

        except Exception as e:
            logger.error(f"Telegram message update failed: {e}")
            return False

    def answer_callback(self, callback_query_id: str, text: str = "") -> bool:
        """Answer a callback query (removes loading state from button)."""
        try:
            response = requests.post(
                f"{self.api_url}/answerCallbackQuery",
                json={
                    "callback_query_id": callback_query_id,
                    "text": text,
                },
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Telegram callback answer failed: {e}")
            return False

    def send_confirmation(self, text: str) -> bool:
        """Send a simple confirmation message."""
        if not self.is_configured():
            return False

        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": self.config.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Telegram confirmation failed: {e}")
            return False

    def _escape_markdown(self, text: str) -> str:
        """Escape special markdown characters."""
        for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            text = text.replace(char, f'\\{char}')
        return text


class SlackNotifier(BaseNotifier):
    """Slack webhook notification sender."""

    def __init__(self, config: SlackConfig):
        self.config = config

    def is_configured(self) -> bool:
        return bool(self.config and self.config.webhook_url)

    def send(self, notification: Notification) -> bool:
        if not self.is_configured():
            return False

        try:
            # Format as Slack blocks
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": notification.title}
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": notification.message}
                }
            ]

            if notification.url:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"<{notification.url}|View on Reddit>"}
                })

            response = requests.post(
                self.config.webhook_url,
                json={"blocks": blocks},
                timeout=10
            )
            response.raise_for_status()
            return True

        except Exception as e:
            print(f"Slack notification failed: {e}")
            return False


class EmailNotifier(BaseNotifier):
    """Email notification sender via SMTP."""

    def __init__(self, config: EmailConfig):
        self.config = config

    def is_configured(self) -> bool:
        return bool(
            self.config and
            self.config.smtp_host and
            self.config.smtp_user and
            self.config.to_address
        )

    def send(self, notification: Notification) -> bool:
        if not self.is_configured():
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self.config.from_address
            msg["To"] = self.config.to_address
            msg["Subject"] = f"[Reddit Radar] {notification.title}"

            body = notification.message
            if notification.url:
                body += f"\n\nLink: {notification.url}"

            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.send_message(msg)

            return True

        except Exception as e:
            print(f"Email notification failed: {e}")
            return False


class ConsoleNotifier(BaseNotifier):
    """Console output for testing/debugging."""

    def is_configured(self) -> bool:
        return True

    def send(self, notification: Notification) -> bool:
        priority_prefix = {
            Priority.LOW: "[LOW]",
            Priority.NORMAL: "[NORMAL]",
            Priority.HIGH: "[HIGH] 🔥",
            Priority.URGENT: "[URGENT] 🚨"
        }

        print("\n" + "=" * 60)
        print(f"{priority_prefix.get(notification.priority, '')} {notification.title}")
        print("-" * 60)
        print(notification.message)
        if notification.url:
            print(f"\nURL: {notification.url}")
        print("=" * 60 + "\n")

        return True


class MultiNotifier:
    """Sends notifications to all configured channels."""

    def __init__(self, notifiers: List[BaseNotifier] = None):
        self.notifiers = notifiers or []

    def add_notifier(self, notifier: BaseNotifier):
        """Add a notifier to the chain."""
        if notifier.is_configured():
            self.notifiers.append(notifier)

    def send(self, notification: Notification) -> dict:
        """Send to all notifiers. Returns dict of results."""
        results = {}
        for notifier in self.notifiers:
            name = notifier.__class__.__name__
            results[name] = notifier.send(notification)
        return results

    def send_simple(self, title: str, message: str, priority: Priority = Priority.NORMAL, url: str = None) -> dict:
        """Convenience method to send a simple notification."""
        return self.send(Notification(title=title, message=message, priority=priority, url=url))


def get_notifier(include_console: bool = False) -> MultiNotifier:
    """
    Get a configured MultiNotifier based on available settings.

    Args:
        include_console: If True, also print to console (useful for debugging)

    Returns:
        MultiNotifier configured with all available notification channels
    """
    settings = get_settings()
    notifier = MultiNotifier()

    if settings.telegram:
        notifier.add_notifier(TelegramNotifier(settings.telegram))

    if settings.slack:
        notifier.add_notifier(SlackNotifier(settings.slack))

    if settings.email:
        notifier.add_notifier(EmailNotifier(settings.email))

    if include_console or not notifier.notifiers:
        # Always add console if no other notifiers configured
        notifier.add_notifier(ConsoleNotifier())

    return notifier
