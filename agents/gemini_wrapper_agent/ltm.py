import os
import logging
import hashlib
import aiosqlite
from typing import Optional

_logger = logging.getLogger(__name__)
DB_PATH = "ltm_gemini.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ltm (
                query_hash TEXT PRIMARY KEY,
                input_text TEXT NOT NULL,
                output_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
    _logger.info(f"Initialized LTM database at {DB_PATH}")

async def lookup(input_text: str) -> Optional[str]:
    query_hash = hashlib.sha256(input_text.encode()).hexdigest()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT output_text FROM ltm WHERE query_hash = ?", (query_hash,))
        row = await cursor.fetchone()
        if row:
            _logger.info(f"LTM cache hit for hash {query_hash}")
            return row[0]
    return None

async def save(input_text: str, output_text: str):
    query_hash = hashlib.sha256(input_text.encode()).hexdigest()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO ltm (query_hash, input_text, output_text) VALUES (?, ?, ?)",
            (query_hash, input_text, output_text)
        )
        await db.commit()
    _logger.info(f"Saved to LTM for hash {query_hash}")
