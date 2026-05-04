"""
Meridian Capital Partners · factors/__init__.py
─────────────────────────────────────────────────────────────────
Layer 2 — Scoring Engine.
Exports all factor modules for easy importing.
"""

from . import momentum, value, quality, growth, revision, short_interest, insider, institutional

__all__ = ["momentum", "value", "quality", "growth", "revision", "short_interest", "insider", "institutional"]
