"""
Meridian Capital Partners · data/__init__.py
─────────────────────────────────────────────────────────────────
Layer 1 — Data Infrastructure.
Orchestrates all 5 data sources into a unified SQLite warehouse.
"""

from . import db, universe, market_data, fundamentals, sec_edgar, insider, institutional

__all__ = ["db", "universe", "market_data", "fundamentals", "sec_edgar", "insider", "institutional"]
