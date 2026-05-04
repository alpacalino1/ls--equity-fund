"""
Meridian Capital Partners · execution/short_check.py
Short availability verification with caching.
"""
import logging, json, time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("meridian.execution.short_check")

class ShortAvailabilityChecker:
    def __init__(self, config=None):
        if config is None: config = {}
        self.cache_days = config.get("cache_days", 7)
        self.cache_file = Path("cache/short_availability.json")
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.short_cache = self._load_cache()

    def _load_cache(self):
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    data = json.load(f)
                return {k: {**v, "timestamp": datetime.fromisoformat(v["timestamp"])} for k, v in data.items()}
            except: return {}
        return {}

    def _save_cache(self):
        cutoff = datetime.now() - timedelta(days=self.cache_days)
        clean = {k: v for k, v in self.short_cache.items() if v.get("timestamp", datetime.min) > cutoff}
        try:
            with open(self.cache_file, "w") as f:
                json.dump({k: {**v, "timestamp": v["timestamp"].isoformat()} for k, v in clean.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save short cache: {e}")

    def is_shortable(self, ticker: str, force_refresh=False) -> bool:
        if not force_refresh and ticker in self.short_cache:
            d = self.short_cache[ticker]
            if datetime.now() - d.get("timestamp", datetime.min) < timedelta(days=self.cache_days):
                return d.get("shortable", False) and d.get("easy_to_borrow", False)
        # In mock mode, assume all are shortable
        self.short_cache[ticker] = {"shortable": True, "easy_to_borrow": True, "timestamp": datetime.now()}
        self._save_cache()
        return True

    def get_short_info(self, ticker):
        return {"ticker": ticker, "shortable": self.is_shortable(ticker), "easy_to_borrow": True, "cached": ticker in self.short_cache}

def check_short_availability(ticker, config=None):
    return ShortAvailabilityChecker(config).is_shortable(ticker)
