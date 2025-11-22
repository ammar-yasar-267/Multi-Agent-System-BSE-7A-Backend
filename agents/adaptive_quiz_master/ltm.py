import os
import logging
import hashlib
import aiosqlite
import json
from typing import Optional, Dict, List, Any
from datetime import datetime, UTC

_logger = logging.getLogger("aqma")
DB_PATH = "adaptive_quiz_master_ltm.db"

async def init_db():
    """Initialize all LTM tables including generated questions cache."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Table for user performance (updated with bloom_level)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_performance (
                user_id TEXT,
                topic TEXT,
                score FLOAT,
                difficulty TEXT,
                bloom_level TEXT,  -- NEW: Store Bloom's taxonomy level
                timestamp TEXT,
                PRIMARY KEY (user_id, topic, timestamp)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_topic ON user_performance(user_id, topic)")

        # Table for quiz history
        await db.execute("""
            CREATE TABLE IF NOT EXISTS quiz_history (
                quiz_id TEXT PRIMARY KEY,
                user_id TEXT,
                session_id TEXT,
                topic TEXT,
                questions TEXT,
                performance_score FLOAT,
                difficulty TEXT,
                timestamp TEXT
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_quiz_user ON quiz_history(user_id)")

        # Cache for dynamically generated questions
        await db.execute("""
            CREATE TABLE IF NOT EXISTS generated_questions (
                id TEXT PRIMARY KEY,
                topic TEXT,
                type TEXT,
                question_text TEXT,
                options TEXT,
                correct_option_index INTEGER,
                difficulty TEXT,
                bloom_taxonomy_level TEXT,
                generated_at TEXT
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_topic ON generated_questions(topic)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_difficulty ON generated_questions(difficulty)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bloom ON generated_questions(bloom_taxonomy_level)")

        await db.commit()
    _logger.info(f"Initialized LTM database at {DB_PATH}")

async def save_performance(user_id: str, topic: str, score: float, difficulty: str, bloom_level: str = "remember"):
    """Save user performance for a specific topic."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO user_performance (user_id, topic, score, difficulty, bloom_level, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, topic, score, difficulty, bloom_level, datetime.now(UTC).isoformat())
        )
        await db.commit()
    _logger.info(f"Saved performance: user={user_id}, topic={topic}, score={score}, difficulty={difficulty}, bloom_level={bloom_level}")

async def save_quiz(
    quiz_id: str,
    user_id: str,
    session_id: str,
    topic: str,
    questions: List[Dict],
    performance_score: float,
    difficulty: str
):
    """Save or update quiz details in history."""
    questions_json = json.dumps(questions, ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if quiz_id already exists
        cursor = await db.execute("SELECT quiz_id FROM quiz_history WHERE quiz_id = ?", (quiz_id,))
        existing = await cursor.fetchone()
        
        if existing:
            # Update existing record
            await db.execute(
                """UPDATE quiz_history 
                   SET user_id = ?, session_id = ?, topic = ?, questions = ?, 
                       performance_score = ?, difficulty = ?, timestamp = ?
                   WHERE quiz_id = ?""",
                (user_id, session_id, topic, questions_json, performance_score, difficulty, 
                 datetime.now(UTC).isoformat(), quiz_id)
            )
            _logger.info(f"Updated quiz {quiz_id} for user {user_id}")
        else:
            # Insert new record
            await db.execute(
                """INSERT INTO quiz_history 
                   (quiz_id, user_id, session_id, topic, questions, performance_score, difficulty, timestamp) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (quiz_id, user_id, session_id, topic, questions_json, performance_score, difficulty, 
                 datetime.now(UTC).isoformat())
            )
            _logger.info(f"Saved quiz {quiz_id} for user {user_id}")
        
        await db.commit()

async def get_user_performance(user_id: str, topic: str) -> Optional[Dict]:
    """Retrieve the latest performance for a user on a topic."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT score, difficulty, bloom_level, timestamp FROM user_performance WHERE user_id = ? AND topic = ? ORDER BY timestamp DESC LIMIT 1",
            (user_id, topic)
        )
        row = await cursor.fetchone()
        if row:
            return {"score": row[0], "difficulty": row[1], "bloom_level": row[2], "timestamp": row[3]}
        return None

async def lookup_quiz_history(quiz_id: str) -> Optional[Dict]:
    """Retrieve a quiz by its ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT user_id, session_id, topic, questions, performance_score, difficulty, timestamp 
               FROM quiz_history WHERE quiz_id = ?""",
            (quiz_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                "user_id": row[0],
                "session_id": row[1],
                "topic": row[2],
                "questions": json.loads(row[3]),
                "performance_score": row[4],
                "difficulty": row[5],
                "timestamp": row[6]
            }
        return None

async def get_generated_questions(
    topic: str,
    types: List[str],
    bloom: str,
    difficulty: str
) -> List[Dict]:
    """Retrieve cached generated questions matching criteria."""
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ','.join('?' for _ in types)
        query = f"""
            SELECT * FROM generated_questions
            WHERE topic = ? 
              AND type IN ({placeholders})
              AND bloom_taxonomy_level = ?
              AND difficulty = ?
            ORDER BY generated_at DESC
        """
        params = [topic] + types + [bloom, difficulty]
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            if not rows:
                return []
            columns = [desc[0] for desc in cursor.description]
            questions = []
            for row in rows:
                q = dict(zip(columns, row))
                q["options"] = json.loads(q["options"]) if q["options"] else []
                questions.append(q)
            return questions

async def cache_generated_questions(topic: str, questions: List[Dict]):
    """Cache dynamically generated questions for future use."""
    if not questions:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        for q in questions:
            await db.execute("""
                INSERT OR IGNORE INTO generated_questions 
                (id, topic, type, question_text, options, correct_option_index, difficulty, bloom_taxonomy_level, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                q["id"],
                topic,
                q["type"],
                q["question_text"],
                json.dumps(q["options"], ensure_ascii=False),
                q.get("correct_option_index"),
                q["difficulty"],
                q["bloom_taxonomy_level"],
                datetime.now(UTC).isoformat()
            ))
        await db.commit()
    _logger.info(f"Cached {len(questions)} generated questions for topic: {topic}")