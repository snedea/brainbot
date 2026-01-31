"""BrainBot memory store using SQLite."""

import json
import logging
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from contextlib import contextmanager
from threading import Lock

logger = logging.getLogger(__name__)


class MemoryStore:
    """
    SQLite-based persistent memory for BrainBot.

    Stores:
    - Journal entries (daily reflections)
    - Goals (daily/weekly/project)
    - Project ideas backlog
    - Bedtime stories
    - Human requests
    """

    def __init__(self, db_path: Path):
        """
        Initialize memory store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._lock = Lock()
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._get_connection() as conn:
            # Journal entries
            conn.execute("""
                CREATE TABLE IF NOT EXISTS journal_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    entry_type TEXT NOT NULL DEFAULT 'daily',
                    title TEXT,
                    content TEXT NOT NULL,
                    mood TEXT,
                    energy REAL,
                    created_at TEXT NOT NULL,
                    UNIQUE(date, entry_type)
                )
            """)

            # Goals
            conn.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_type TEXT NOT NULL DEFAULT 'daily',
                    description TEXT NOT NULL,
                    priority INTEGER DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    due_date TEXT,
                    completed_at TEXT,
                    notes TEXT
                )
            """)

            # Project ideas backlog
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_ideas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    complexity TEXT DEFAULT 'medium',
                    priority INTEGER DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'idea',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    notes TEXT,
                    tags TEXT
                )
            """)

            # Bedtime stories
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bedtime_stories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    theme TEXT,
                    mood TEXT,
                    created_at TEXT NOT NULL,
                    displayed_on_lcd INTEGER DEFAULT 0,
                    rating INTEGER
                )
            """)

            # Human requests
            conn.execute("""
                CREATE TABLE IF NOT EXISTS human_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    context TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority TEXT DEFAULT 'normal',
                    created_at TEXT NOT NULL,
                    responded_at TEXT,
                    response TEXT
                )
            """)

            # Learnings (things BrainBot has learned)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS learnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    tags TEXT
                )
            """)

            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Get a database connection with thread safety."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    # =========== Journal Methods ===========

    def add_journal_entry(
        self,
        content: str,
        entry_type: str = "daily",
        title: Optional[str] = None,
        mood: Optional[str] = None,
        energy: Optional[float] = None,
        entry_date: Optional[date] = None,
    ) -> int:
        """
        Add a journal entry.

        Args:
            content: Journal entry content
            entry_type: Type of entry (daily, morning, evening)
            title: Optional title
            mood: Current mood
            energy: Current energy level
            entry_date: Date for entry (defaults to today)

        Returns:
            ID of created entry
        """
        entry_date = entry_date or date.today()
        now = datetime.now().isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO journal_entries
                (date, entry_type, title, content, mood, energy, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(entry_date), entry_type, title, content, mood, energy, now),
            )
            conn.commit()
            return cursor.lastrowid

    def get_journal_entry(
        self, entry_date: date, entry_type: str = "daily"
    ) -> Optional[dict]:
        """Get a journal entry for a specific date."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM journal_entries WHERE date = ? AND entry_type = ?",
                (str(entry_date), entry_type),
            ).fetchone()

            return dict(row) if row else None

    def get_recent_journal_entries(self, limit: int = 7) -> list[dict]:
        """Get recent journal entries."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM journal_entries ORDER BY date DESC LIMIT ?",
                (limit,),
            ).fetchall()

            return [dict(row) for row in rows]

    # =========== Goal Methods ===========

    def add_goal(
        self,
        description: str,
        goal_type: str = "daily",
        priority: int = 1,
        due_date: Optional[date] = None,
    ) -> int:
        """Add a goal."""
        now = datetime.now().isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO goals (goal_type, description, priority, due_date, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (goal_type, description, priority, str(due_date) if due_date else None, now),
            )
            conn.commit()
            return cursor.lastrowid

    def update_goal(
        self,
        goal_id: int,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Update a goal."""
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
            if status == "completed":
                updates.append("completed_at = ?")
                params.append(datetime.now().isoformat())

        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)

        if notes is not None:
            updates.append("notes = ?")
            params.append(notes)

        if not updates:
            return False

        params.append(goal_id)

        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE goals SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            return True

    def get_pending_goals(self, goal_type: Optional[str] = None) -> list[dict]:
        """Get pending goals."""
        with self._get_connection() as conn:
            if goal_type:
                rows = conn.execute(
                    "SELECT * FROM goals WHERE status = 'pending' AND goal_type = ? ORDER BY priority DESC",
                    (goal_type,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM goals WHERE status = 'pending' ORDER BY priority DESC"
                ).fetchall()

            return [dict(row) for row in rows]

    def get_todays_goals(self) -> list[dict]:
        """Get today's daily goals."""
        today = str(date.today())
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM goals
                WHERE goal_type = 'daily'
                AND date(created_at) = ?
                ORDER BY priority DESC
                """,
                (today,),
            ).fetchall()

            return [dict(row) for row in rows]

    # =========== Project Ideas Methods ===========

    def add_project_idea(
        self,
        title: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        complexity: str = "medium",
        priority: int = 1,
        tags: Optional[list[str]] = None,
    ) -> int:
        """Add a project idea to the backlog."""
        now = datetime.now().isoformat()
        tags_str = json.dumps(tags) if tags else None

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO project_ideas
                (title, description, category, complexity, priority, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (title, description, category, complexity, priority, tags_str, now),
            )
            conn.commit()
            return cursor.lastrowid

    def get_next_project_idea(self) -> Optional[dict]:
        """Get the next project idea to work on."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM project_ideas
                WHERE status = 'idea'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """
            ).fetchone()

            if row:
                result = dict(row)
                if result.get("tags"):
                    result["tags"] = json.loads(result["tags"])
                return result
            return None

    def start_project(self, project_id: int) -> bool:
        """Mark a project as started."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE project_ideas SET status = 'in_progress', started_at = ? WHERE id = ?",
                (now, project_id),
            )
            conn.commit()
            return True

    def complete_project(self, project_id: int, notes: Optional[str] = None) -> bool:
        """Mark a project as complete."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE project_ideas SET status = 'completed', completed_at = ?, notes = ? WHERE id = ?",
                (now, notes, project_id),
            )
            conn.commit()
            return True

    def get_project_ideas(self, status: Optional[str] = None, limit: int = 10) -> list[dict]:
        """Get project ideas."""
        with self._get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM project_ideas WHERE status = ? ORDER BY priority DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM project_ideas ORDER BY priority DESC LIMIT ?",
                    (limit,),
                ).fetchall()

            results = []
            for row in rows:
                r = dict(row)
                if r.get("tags"):
                    r["tags"] = json.loads(r["tags"])
                results.append(r)
            return results

    # =========== Bedtime Stories Methods ===========

    def add_bedtime_story(
        self,
        title: str,
        content: str,
        theme: Optional[str] = None,
        mood: Optional[str] = None,
        story_date: Optional[date] = None,
    ) -> int:
        """Add a bedtime story."""
        story_date = story_date or date.today()
        now = datetime.now().isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO bedtime_stories
                (date, title, content, theme, mood, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(story_date), title, content, theme, mood, now),
            )
            conn.commit()
            return cursor.lastrowid

    def get_todays_story(self) -> Optional[dict]:
        """Get today's bedtime story."""
        today = str(date.today())
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM bedtime_stories WHERE date = ? ORDER BY created_at DESC LIMIT 1",
                (today,),
            ).fetchone()

            return dict(row) if row else None

    def get_recent_stories(self, limit: int = 7) -> list[dict]:
        """Get recent bedtime stories."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM bedtime_stories ORDER BY date DESC LIMIT ?",
                (limit,),
            ).fetchall()

            return [dict(row) for row in rows]

    def mark_story_displayed(self, story_id: int) -> bool:
        """Mark a story as displayed on LCD."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE bedtime_stories SET displayed_on_lcd = 1 WHERE id = ?",
                (story_id,),
            )
            conn.commit()
            return True

    # =========== Human Requests Methods ===========

    def add_human_request(
        self,
        request_type: str,
        description: str,
        context: Optional[str] = None,
        priority: str = "normal",
    ) -> int:
        """Add a request for human assistance."""
        now = datetime.now().isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO human_requests
                (request_type, description, context, priority, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (request_type, description, context, priority, now),
            )
            conn.commit()
            logger.info(f"Human request created: {request_type} - {description}")
            return cursor.lastrowid

    def respond_to_request(self, request_id: int, response: str) -> bool:
        """Mark a human request as responded."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE human_requests SET status = 'responded', responded_at = ?, response = ? WHERE id = ?",
                (now, response, request_id),
            )
            conn.commit()
            return True

    def get_pending_requests(self) -> list[dict]:
        """Get pending human requests."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM human_requests WHERE status = 'pending' ORDER BY created_at ASC"
            ).fetchall()

            return [dict(row) for row in rows]

    # =========== Learnings Methods ===========

    def add_learning(
        self,
        category: str,
        title: str,
        content: str,
        source: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> int:
        """Record something BrainBot has learned."""
        now = datetime.now().isoformat()
        tags_str = json.dumps(tags) if tags else None

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO learnings (category, title, content, source, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (category, title, content, source, tags_str, now),
            )
            conn.commit()
            return cursor.lastrowid

    def get_learnings(self, category: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Get learnings."""
        with self._get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM learnings WHERE category = ? ORDER BY created_at DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM learnings ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

            results = []
            for row in rows:
                r = dict(row)
                if r.get("tags"):
                    r["tags"] = json.loads(r["tags"])
                results.append(r)
            return results
