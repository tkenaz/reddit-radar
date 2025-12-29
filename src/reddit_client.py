"""Reddit API client wrapper using PRAW."""
import praw
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from .config import get_settings


class RedditClient:
    """Wrapper around PRAW for Reddit API interactions."""

    def __init__(self):
        """Initialize Reddit client with credentials from config."""
        settings = get_settings()
        config = settings.reddit
        rate_config = settings.rate_limit

        self.reddit = praw.Reddit(
            client_id=config.client_id,
            client_secret=config.client_secret,
            username=config.username,
            password=config.password,
            user_agent=config.user_agent
        )

        self.rate_config = rate_config

        # Track last action times for rate limiting
        self.last_post_time: Dict[str, datetime] = {}
        self.last_comment_time = None

    def _can_post_to_subreddit(self, subreddit: str) -> tuple[bool, Optional[str]]:
        """Check if enough time has passed to post to this subreddit."""
        if subreddit in self.last_post_time:
            time_since_last = datetime.now() - self.last_post_time[subreddit]
            min_wait = timedelta(seconds=self.rate_config.min_seconds_between_posts)

            if time_since_last < min_wait:
                wait_remaining = (min_wait - time_since_last).total_seconds()
                return False, f"Must wait {wait_remaining:.0f} more seconds before posting to r/{subreddit}"

        return True, None

    def _can_comment(self) -> tuple[bool, Optional[str]]:
        """Check if enough time has passed to comment."""
        if self.last_comment_time:
            time_since_last = datetime.now() - self.last_comment_time
            min_wait = timedelta(seconds=self.rate_config.min_seconds_between_comments)

            if time_since_last < min_wait:
                wait_remaining = (min_wait - time_since_last).total_seconds()
                return False, f"Must wait {wait_remaining:.0f} more seconds before commenting"

        return True, None

    def create_post(
        self,
        subreddit: str,
        title: str,
        text: Optional[str] = None,
        url: Optional[str] = None,
        flair_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a post in a subreddit.

        Args:
            subreddit: Name of subreddit (without r/)
            title: Post title
            text: Post text (for text posts)
            url: URL (for link posts)
            flair_id: Optional flair ID

        Returns:
            Dict with post_id, url, timestamp
        """
        can_post, error_msg = self._can_post_to_subreddit(subreddit)
        if not can_post:
            raise ValueError(error_msg)

        sub = self.reddit.subreddit(subreddit)

        if text is not None:
            submission = sub.submit(title=title, selftext=text)
        elif url is not None:
            submission = sub.submit(title=title, url=url)
        else:
            raise ValueError("Must provide either 'text' or 'url'")

        if flair_id:
            submission.flair.select(flair_id)

        self.last_post_time[subreddit] = datetime.now()

        return {
            "post_id": submission.id,
            "url": f"https://reddit.com{submission.permalink}",
            "timestamp": datetime.fromtimestamp(submission.created_utc).isoformat(),
            "subreddit": subreddit
        }

    def create_comment(self, post_id: str, text: str) -> Dict[str, Any]:
        """Comment on a post."""
        can_comment, error_msg = self._can_comment()
        if not can_comment:
            raise ValueError(error_msg)

        submission = self.reddit.submission(id=post_id)
        comment = submission.reply(text)

        self.last_comment_time = datetime.now()

        return {
            "comment_id": comment.id,
            "permalink": f"https://reddit.com{comment.permalink}",
            "timestamp": datetime.fromtimestamp(comment.created_utc).isoformat()
        }

    def reply_to_comment(self, comment_id: str, text: str) -> Dict[str, Any]:
        """Reply to a comment."""
        can_comment, error_msg = self._can_comment()
        if not can_comment:
            raise ValueError(error_msg)

        comment = self.reddit.comment(id=comment_id)
        reply = comment.reply(text)

        self.last_comment_time = datetime.now()

        return {
            "reply_id": reply.id,
            "permalink": f"https://reddit.com{reply.permalink}",
            "timestamp": datetime.fromtimestamp(reply.created_utc).isoformat()
        }

    def get_post(self, post_id: str) -> Dict[str, Any]:
        """Get details about a post."""
        submission = self.reddit.submission(id=post_id)

        submission.comments.replace_more(limit=0)
        top_comments = []
        for comment in submission.comments[:5]:
            top_comments.append({
                "id": comment.id,
                "author": str(comment.author),
                "body": comment.body,
                "score": comment.score,
                "created_utc": datetime.fromtimestamp(comment.created_utc).isoformat()
            })

        return {
            "id": submission.id,
            "title": submission.title,
            "author": str(submission.author),
            "subreddit": str(submission.subreddit),
            "score": submission.score,
            "upvote_ratio": submission.upvote_ratio,
            "num_comments": submission.num_comments,
            "created_utc": datetime.fromtimestamp(submission.created_utc).isoformat(),
            "url": f"https://reddit.com{submission.permalink}",
            "selftext": submission.selftext if submission.is_self else None,
            "link_url": submission.url if not submission.is_self else None,
            "top_comments": top_comments
        }

    def get_my_karma(self) -> Dict[str, int]:
        """Get current user's karma."""
        user = self.reddit.user.me()
        return {
            "link_karma": user.link_karma,
            "comment_karma": user.comment_karma,
            "total_karma": user.link_karma + user.comment_karma
        }

    def get_inbox(self, unread_only: bool = True) -> List[Dict[str, Any]]:
        """Get inbox messages."""
        messages = []
        inbox = self.reddit.inbox.unread() if unread_only else self.reddit.inbox.all(limit=25)

        for item in inbox:
            message_data = {
                "id": item.id,
                "type": "comment" if hasattr(item, "submission") else "message",
                "subject": getattr(item, "subject", None),
                "body": item.body,
                "author": str(item.author) if item.author else "[deleted]",
                "created_utc": datetime.fromtimestamp(item.created_utc).isoformat(),
                "permalink": f"https://reddit.com{item.context}" if hasattr(item, "context") else None
            }
            messages.append(message_data)

        return messages

    def search_posts(
        self,
        query: str,
        subreddit: Optional[str] = None,
        time_filter: str = "week",
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search for posts by query.

        Args:
            query: Search query string
            subreddit: Specific subreddit to search (None = all)
            time_filter: Time filter (hour, day, week, month, year, all)
            limit: Maximum number of results (default 20, max 100)

        Returns:
            List of post dicts with details
        """
        limit = min(limit, 100)

        if subreddit:
            search_results = self.reddit.subreddit(subreddit).search(
                query,
                time_filter=time_filter,
                limit=limit
            )
        else:
            search_results = self.reddit.subreddit("all").search(
                query,
                time_filter=time_filter,
                limit=limit
            )

        posts = []
        for submission in search_results:
            post_data = {
                "id": submission.id,
                "title": submission.title,
                "author": str(submission.author),
                "subreddit": str(submission.subreddit),
                "score": submission.score,
                "upvote_ratio": submission.upvote_ratio,
                "num_comments": submission.num_comments,
                "created_utc": datetime.fromtimestamp(submission.created_utc).isoformat(),
                "url": f"https://reddit.com{submission.permalink}",
                "selftext": submission.selftext[:500] if submission.is_self else None,
                "link_url": submission.url if not submission.is_self else None
            }
            posts.append(post_data)

        return posts
