"""
Draft Store - SQLite storage for pending response drafts.

Stores drafts with metadata for approval workflow:
- draft_id: unique identifier for Telegram callbacks
- post_url: Reddit post URL
- post_title: Post title for context
- subreddit: Target subreddit
- draft_content: Generated response text
- intent: Classification intent
- status: pending/approved/rejected/posted
- created_at: Timestamp
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum


class DraftStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"
    EDITED = "edited"


@dataclass
class Draft:
    id: str
    post_id: str
    post_url: str
    post_title: str
    subreddit: str
    content: str
    intent: str
    confidence: float
    status: DraftStatus
    created_at: datetime
    posted_at: Optional[datetime] = None
    reddit_comment_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "post_id": self.post_id,
            "post_url": self.post_url,
            "post_title": self.post_title,
            "subreddit": self.subreddit,
            "content": self.content,
            "intent": self.intent,
            "confidence": self.confidence,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "reddit_comment_id": self.reddit_comment_id,
        }


class DraftStore:
    """SQLite-based storage for draft responses."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to data/drafts.db in project root
            project_root = Path(__file__).parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "drafts.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS drafts (
                    id TEXT PRIMARY KEY,
                    post_id TEXT NOT NULL,
                    post_url TEXT NOT NULL,
                    post_title TEXT NOT NULL,
                    subreddit TEXT NOT NULL,
                    content TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    posted_at TEXT,
                    reddit_comment_id TEXT,
                    UNIQUE(post_id)
                )
            """)

            # Index for quick status lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_drafts_status
                ON drafts(status)
            """)

            conn.commit()

    def save_draft(
        self,
        post_id: str,
        post_url: str,
        post_title: str,
        subreddit: str,
        content: str,
        intent: str,
        confidence: float,
    ) -> Draft:
        """Save a new draft or update existing one for the same post."""
        draft_id = str(uuid.uuid4())[:8]  # Short ID for callback_data
        now = datetime.utcnow()

        with sqlite3.connect(self.db_path) as conn:
            # Check if draft for this post already exists
            cursor = conn.execute(
                "SELECT id FROM drafts WHERE post_id = ?",
                (post_id,)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing draft
                conn.execute("""
                    UPDATE drafts
                    SET content = ?, intent = ?, confidence = ?,
                        status = 'pending', created_at = ?
                    WHERE post_id = ?
                """, (content, intent, confidence, now.isoformat(), post_id))
                draft_id = existing[0]
            else:
                # Insert new draft
                conn.execute("""
                    INSERT INTO drafts
                    (id, post_id, post_url, post_title, subreddit, content,
                     intent, confidence, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """, (draft_id, post_id, post_url, post_title, subreddit,
                      content, intent, confidence, now.isoformat()))

            conn.commit()

        return Draft(
            id=draft_id,
            post_id=post_id,
            post_url=post_url,
            post_title=post_title,
            subreddit=subreddit,
            content=content,
            intent=intent,
            confidence=confidence,
            status=DraftStatus.PENDING,
            created_at=now,
        )

    def get_draft(self, draft_id: str) -> Optional[Draft]:
        """Get a draft by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM drafts WHERE id = ?",
                (draft_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_draft(row)

    def get_pending_drafts(self) -> List[Draft]:
        """Get all pending drafts."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM drafts WHERE status = 'pending' ORDER BY created_at DESC"
            )
            return [self._row_to_draft(row) for row in cursor.fetchall()]

    def update_status(
        self,
        draft_id: str,
        status: DraftStatus,
        reddit_comment_id: Optional[str] = None
    ) -> bool:
        """Update draft status."""
        with sqlite3.connect(self.db_path) as conn:
            posted_at = datetime.utcnow().isoformat() if status == DraftStatus.POSTED else None

            cursor = conn.execute("""
                UPDATE drafts
                SET status = ?, posted_at = ?, reddit_comment_id = ?
                WHERE id = ?
            """, (status.value, posted_at, reddit_comment_id, draft_id))

            conn.commit()
            return cursor.rowcount > 0

    def update_content(self, draft_id: str, new_content: str) -> bool:
        """Update draft content (for edits)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE drafts
                SET content = ?, status = 'edited'
                WHERE id = ?
            """, (new_content, draft_id))

            conn.commit()
            return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, int]:
        """Get draft statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT status, COUNT(*) as count
                FROM drafts
                GROUP BY status
            """)

            stats = {row[0]: row[1] for row in cursor.fetchall()}
            stats["total"] = sum(stats.values())
            return stats

    def cleanup_old_drafts(self, days: int = 30) -> int:
        """Remove drafts older than specified days."""
        with sqlite3.connect(self.db_path) as conn:
            cutoff = datetime.utcnow().isoformat()
            cursor = conn.execute("""
                DELETE FROM drafts
                WHERE created_at < datetime(?, '-' || ? || ' days')
                AND status IN ('rejected', 'posted')
            """, (cutoff, days))

            conn.commit()
            return cursor.rowcount

    def _row_to_draft(self, row: sqlite3.Row) -> Draft:
        """Convert database row to Draft object."""
        return Draft(
            id=row["id"],
            post_id=row["post_id"],
            post_url=row["post_url"],
            post_title=row["post_title"],
            subreddit=row["subreddit"],
            content=row["content"],
            intent=row["intent"],
            confidence=row["confidence"],
            status=DraftStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            posted_at=datetime.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
            reddit_comment_id=row["reddit_comment_id"],
        )


# Convenience function
def get_draft_store() -> DraftStore:
    """Get the default draft store instance."""
    return DraftStore()
