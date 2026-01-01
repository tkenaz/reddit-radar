"""
Telegram Approval Bot - Handles draft approval workflow.

Polls Telegram for button callbacks and processes:
- ✅ Post: Posts the draft to Reddit
- ✏️ Edit: Waits for edited version, then posts
- ❌ Skip: Marks draft as rejected

Run as a separate process:
    python -m src.approval_bot
"""

import time
import logging
import requests
from typing import Optional, Dict, Any
from datetime import datetime

from .config import get_settings
from .draft_store import DraftStore, DraftStatus, get_draft_store
from .reddit_client import RedditClient
from .notifier import TelegramNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ApprovalBot:
    """Telegram bot for approving and posting draft responses."""

    def __init__(self):
        settings = get_settings()

        if not settings.telegram:
            raise ValueError("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")

        self.telegram = TelegramNotifier(settings.telegram)
        self.api_url = self.telegram.api_url
        self.chat_id = settings.telegram.chat_id

        self.draft_store = get_draft_store()
        self.reddit = None  # Lazy load to avoid auth issues at startup

        self.last_update_id = 0
        self.pending_edits: Dict[str, str] = {}  # chat_id -> draft_id awaiting edit

    def _get_reddit(self) -> RedditClient:
        """Lazy load Reddit client."""
        if self.reddit is None:
            self.reddit = RedditClient()
            logger.info("Reddit client initialized")
        return self.reddit

    def get_updates(self, timeout: int = 30) -> list:
        """Long poll for Telegram updates."""
        try:
            response = requests.get(
                f"{self.api_url}/getUpdates",
                params={
                    "offset": self.last_update_id + 1,
                    "timeout": timeout,
                    "allowed_updates": ["callback_query", "message"]
                },
                timeout=timeout + 5
            )
            response.raise_for_status()
            data = response.json()

            if data.get("ok"):
                return data.get("result", [])
            return []

        except requests.exceptions.Timeout:
            return []
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
            time.sleep(5)
            return []

    def handle_callback(self, callback_query: Dict[str, Any]):
        """Handle button press callback."""
        callback_id = callback_query["id"]
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        message_id = message.get("message_id")
        from_user = callback_query.get("from", {}).get("username", "unknown")

        logger.info(f"Callback from @{from_user}: {data}")

        # Parse callback data
        if ":" not in data:
            self.telegram.answer_callback(callback_id, "Invalid action")
            return

        action, draft_id = data.split(":", 1)

        # Get draft from store
        draft = self.draft_store.get_draft(draft_id)
        if not draft:
            self.telegram.answer_callback(callback_id, "Draft not found or expired")
            return

        if action == "post":
            self._handle_post(callback_id, message_id, draft)
        elif action == "edit":
            self._handle_edit_request(callback_id, message_id, draft)
        elif action == "skip":
            self._handle_skip(callback_id, message_id, draft)
        else:
            self.telegram.answer_callback(callback_id, f"Unknown action: {action}")

    def _handle_post(self, callback_id: str, message_id: int, draft):
        """Post the draft to Reddit."""
        try:
            # Answer callback immediately
            self.telegram.answer_callback(callback_id, "Posting to Reddit...")

            # Post to Reddit
            reddit = self._get_reddit()
            result = reddit.create_comment(draft.post_id, draft.content)

            # Update draft status
            self.draft_store.update_status(
                draft.id,
                DraftStatus.POSTED,
                reddit_comment_id=result["comment_id"]
            )

            # Update Telegram message
            success_text = (
                f"✅ *Posted successfully!*\n\n"
                f"r/{draft.subreddit}: {draft.post_title[:50]}...\n\n"
                f"[View Comment]({result['permalink']})"
            )
            self.telegram.update_message(message_id, success_text)

            logger.info(f"Posted draft {draft.id} to Reddit: {result['permalink']}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to post draft {draft.id}: {error_msg}")

            # Check for rate limiting
            if "wait" in error_msg.lower() or "rate" in error_msg.lower():
                self.telegram.send_confirmation(
                    f"⚠️ Rate limited: {error_msg}\n\nTry again in a few minutes."
                )
            else:
                self.telegram.send_confirmation(f"❌ Failed to post: {error_msg}")

    def _handle_edit_request(self, callback_id: str, message_id: int, draft):
        """Request an edited version from the user."""
        self.telegram.answer_callback(callback_id, "Send your edited version")

        # Store pending edit
        self.pending_edits[str(self.chat_id)] = draft.id

        # Send instruction
        self.telegram.send_confirmation(
            f"✏️ *Edit mode for:* {draft.post_title[:50]}...\n\n"
            f"Current draft:\n```\n{draft.content}\n```\n\n"
            f"Reply with your edited version, or /cancel to abort."
        )

        logger.info(f"Edit requested for draft {draft.id}")

    def _handle_skip(self, callback_id: str, message_id: int, draft):
        """Skip/reject the draft."""
        self.telegram.answer_callback(callback_id, "Skipped")

        # Update status
        self.draft_store.update_status(draft.id, DraftStatus.REJECTED)

        # Update message
        skip_text = (
            f"❌ *Skipped*\n\n"
            f"r/{draft.subreddit}: {draft.post_title[:50]}..."
        )
        self.telegram.update_message(message_id, skip_text)

        logger.info(f"Skipped draft {draft.id}")

    def handle_message(self, message: Dict[str, Any]):
        """Handle text messages (for edits)."""
        chat_id = str(message.get("chat", {}).get("id"))
        text = message.get("text", "")

        # Check if this is an edit response
        if chat_id in self.pending_edits:
            draft_id = self.pending_edits[chat_id]

            if text.strip().lower() == "/cancel":
                del self.pending_edits[chat_id]
                self.telegram.send_confirmation("Edit cancelled.")
                return

            # Get draft and update content
            draft = self.draft_store.get_draft(draft_id)
            if draft:
                # Update content
                self.draft_store.update_content(draft_id, text)

                # Post to Reddit
                try:
                    reddit = self._get_reddit()
                    result = reddit.create_comment(draft.post_id, text)

                    self.draft_store.update_status(
                        draft_id,
                        DraftStatus.POSTED,
                        reddit_comment_id=result["comment_id"]
                    )

                    self.telegram.send_confirmation(
                        f"✅ *Edited version posted!*\n\n"
                        f"[View Comment]({result['permalink']})"
                    )

                    logger.info(f"Posted edited draft {draft_id}: {result['permalink']}")

                except Exception as e:
                    logger.error(f"Failed to post edited draft: {e}")
                    self.telegram.send_confirmation(f"❌ Failed to post: {e}")

            del self.pending_edits[chat_id]

    def run(self):
        """Main bot loop."""
        logger.info("=" * 60)
        logger.info("Reddit Radar Approval Bot Starting")
        logger.info("=" * 60)

        # Check pending drafts
        pending = self.draft_store.get_pending_drafts()
        logger.info(f"Pending drafts: {len(pending)}")

        logger.info("Listening for button presses...")
        logger.info("Press Ctrl+C to stop")
        logger.info("-" * 60)

        try:
            while True:
                updates = self.get_updates(timeout=30)

                for update in updates:
                    self.last_update_id = update["update_id"]

                    if "callback_query" in update:
                        self.handle_callback(update["callback_query"])
                    elif "message" in update:
                        self.handle_message(update["message"])

        except KeyboardInterrupt:
            logger.info("\nShutting down...")
        except Exception as e:
            logger.error(f"Bot error: {e}")
            raise


def main():
    """Entry point for approval bot."""
    bot = ApprovalBot()
    bot.run()


if __name__ == "__main__":
    main()
