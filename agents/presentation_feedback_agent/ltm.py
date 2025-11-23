"""
Long-term memory for Presentation Feedback Agent.
Caches analysis results to avoid re-analyzing identical transcripts.
"""

import aiosqlite
import json
import hashlib
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class LongTermMemory:
    """SQLite-based cache for presentation analysis results."""

    def __init__(self, db_path: str = "./agents/presentation_feedback_agent/ltm_cache.db"):
        """
        Initialize LTM with database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        logger.info(f"Initialized LTM with database: {db_path}")

    async def initialize(self):
        """Create the database table if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS analysis_cache (
                    transcript_hash TEXT PRIMARY KEY,
                    presentation_id TEXT,
                    analysis_result TEXT,
                    created_at TEXT,
                    access_count INTEGER DEFAULT 1,
                    last_accessed TEXT
                )
            """)
            await db.commit()
        logger.info("LTM database initialized")

    def _hash_transcript(self, transcript: str) -> str:
        """Generate a hash of the transcript for cache lookup."""
        return hashlib.sha256(transcript.encode('utf-8')).hexdigest()

    async def lookup(self, transcript: str) -> Optional[dict]:
        """
        Look up cached analysis for a transcript.

        Args:
            transcript: Presentation transcript text

        Returns:
            Cached analysis result as dict, or None if not found
        """
        transcript_hash = self._hash_transcript(transcript)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT analysis_result, access_count FROM analysis_cache WHERE transcript_hash = ?",
                (transcript_hash,)
            ) as cursor:
                row = await cursor.fetchone()

                if row:
                    analysis_result, access_count = row

                    # Update access count and last accessed time
                    await db.execute(
                        """UPDATE analysis_cache
                           SET access_count = ?, last_accessed = ?
                           WHERE transcript_hash = ?""",
                        (access_count + 1, datetime.now(timezone.utc).isoformat(), transcript_hash)
                    )
                    await db.commit()

                    logger.info(f"Cache hit for transcript hash: {transcript_hash[:16]}... (access count: {access_count + 1})")
                    return json.loads(analysis_result)

        logger.info(f"Cache miss for transcript hash: {transcript_hash[:16]}...")
        return None

    async def save(self, transcript: str, presentation_id: str, analysis_result: dict):
        """
        Save analysis result to cache.

        Args:
            transcript: Presentation transcript text
            presentation_id: ID of the presentation
            analysis_result: Analysis result to cache
        """
        transcript_hash = self._hash_transcript(transcript)
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO analysis_cache
                   (transcript_hash, presentation_id, analysis_result, created_at, access_count, last_accessed)
                   VALUES (?, ?, ?, ?, 1, ?)""",
                (transcript_hash, presentation_id, json.dumps(analysis_result), now, now)
            )
            await db.commit()

        logger.info(f"Saved analysis to cache for presentation: {presentation_id}")

    async def get_stats(self) -> dict:
        """Get cache statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*), SUM(access_count) FROM analysis_cache") as cursor:
                row = await cursor.fetchone()
                total_entries, total_accesses = row if row else (0, 0)

        return {
            "total_cached_analyses": total_entries or 0,
            "total_cache_hits": (total_accesses or 0) - (total_entries or 0)
        }

    async def clear_cache(self):
        """Clear all cached entries (use with caution)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM analysis_cache")
            await db.commit()
        logger.warning("Cache cleared")
