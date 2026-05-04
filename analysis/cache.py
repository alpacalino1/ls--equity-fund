"""
Meridian Capital Partners · analysis/cache.py
─────────────────────────────────────────────────────────────────
SQLite-based cache for AI analysis results with TTL eviction.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger("meridian.analysis.cache")


class AnalysisCache:
    def __init__(self, db_path: str = "cache/analysis_cache.db", ttl_days: int = 30):
        """Initialize analysis cache with SQLite backend."""
        self.db_path = db_path
        self.ttl_days = ttl_days
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._cleanup_expired()

    def _connect(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        return conn

    def _init_schema(self):
        """Initialize cache table schema."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analyzer TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,  -- e.g., filing accession number, transcript date
                    result TEXT NOT NULL,       -- JSON serialized result
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(analyzer, ticker, artifact_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_analyzer_ticker ON analysis_results(analyzer, ticker)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON analysis_results(created_at)")
        logger.info(f"Analysis cache initialized at {self.db_path}")

    def get(self, analyzer: str, ticker: str, artifact_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached analysis result.
        Returns None if not found or expired.
        """
        with self._connect() as conn:
            row = conn.execute("""
                SELECT result, created_at FROM analysis_results 
                WHERE analyzer = ? AND ticker = ? AND artifact_id = ?
            """, (analyzer, ticker, artifact_id)).fetchone()
            
            if not row:
                return None
                
            # Check if expired
            created_at = datetime.fromisoformat(row['created_at'])
            if datetime.now() - created_at > timedelta(days=self.ttl_days):
                # Expired - delete and return None
                self.delete(analyzer, ticker, artifact_id)
                return None
                
            try:
                return json.loads(row['result'])
            except json.JSONDecodeError:
                logger.warning(f"Failed to deserialize cached result for {analyzer}:{ticker}:{artifact_id}")
                return None

    def put(self, analyzer: str, ticker: str, artifact_id: str, result: Dict[str, Any]) -> bool:
        """
        Store analysis result in cache.
        Returns True if stored successfully.
        """
        try:
            result_json = json.dumps(result)
            with self._connect() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO analysis_results 
                    (analyzer, ticker, artifact_id, result) 
                    VALUES (?, ?, ?, ?)
                """, (analyzer, ticker, artifact_id, result_json))
                return True
        except Exception as e:
            logger.error(f"Failed to cache result for {analyzer}:{ticker}:{artifact_id}: {e}")
            return False

    def delete(self, analyzer: str, ticker: str, artifact_id: str) -> bool:
        """Delete specific cache entry."""
        try:
            with self._connect() as conn:
                conn.execute("""
                    DELETE FROM analysis_results 
                    WHERE analyzer = ? AND ticker = ? AND artifact_id = ?
                """, (analyzer, ticker, artifact_id))
                return True
        except Exception as e:
            logger.error(f"Failed to delete cache entry for {analyzer}:{ticker}:{artifact_id}: {e}")
            return False

    def _cleanup_expired(self):
        """Remove expired entries from cache."""
        cutoff_date = datetime.now() - timedelta(days=self.ttl_days)
        try:
            with self._connect() as conn:
                deleted_count = conn.execute("""
                    DELETE FROM analysis_results 
                    WHERE created_at < ?
                """, (cutoff_date.isoformat(),)).rowcount
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} expired cache entries")
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")

    def clear(self):
        """Clear entire cache."""
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM analysis_results")
            logger.info("Analysis cache cleared")
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            with self._connect() as conn:
                total = conn.execute("SELECT COUNT(*) FROM analysis_results").fetchone()[0]
                recent = conn.execute("""
                    SELECT COUNT(*) FROM analysis_results 
                    WHERE created_at > ?
                """, ((datetime.now() - timedelta(days=7)).isoformat(),)).fetchone()[0]
                
                return {
                    "total_entries": total,
                    "recent_entries": recent,
                    "ttl_days": self.ttl_days
                }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e)}
