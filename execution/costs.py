"""
Meridian Capital Partners · execution/costs.py
Slippage tracking and execution cost analysis.
"""
import logging, json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("meridian.execution.costs")

class SlippageTracker:
    def __init__(self, config=None):
        if config is None: config = {}
        self.cache_days = config.get("cache_days", 30)
        self.output_dir = Path("output/execution")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.history = self._load()

    def _load(self):
        hf = self.output_dir / "execution_history.json"
        if hf.exists():
            try:
                with open(hf) as f: return json.load(f)
            except: return []
        return []

    def _save(self):
        cutoff = (datetime.now() - timedelta(days=self.cache_days)).isoformat()
        filtered = [r for r in self.history if r.get("timestamp", "") > cutoff]
        try:
            with open(self.output_dir / "execution_history.json", "w") as f:
                json.dump(filtered, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save execution history: {e}")

    def record(self, record):
        record["timestamp"] = datetime.now().isoformat()
        self.history.append(record)
        self._save()
        slip = record.get("slippage_bps", 0)
        if abs(slip) > 10: logger.warning(f"Significant slippage: {slip:.1f} bps for {record.get('ticker', '?')}")

    def calculate_slippage(self, fill_price, signal_price):
        return ((fill_price - signal_price) / signal_price) * 10000 if signal_price else 0

    def get_rolling_metrics(self, days=30):
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        recent = [r for r in self.history if r.get("timestamp", "") > cutoff]
        if not recent: return {"avg_slippage_bps": 0, "median_slippage_bps": 0, "p95_slippage_bps": 0, "total_cost": 0, "count": 0}
        slips = [r.get("slippage_bps", 0) for r in recent]
        arr = np.array(slips)
        cost = sum(abs(r.get("slippage_bps", 0) / 10000) * r.get("filled_qty", 0) * r.get("signal_price", 0) for r in recent)
        return {"avg_slippage_bps": float(np.mean(arr)), "median_slippage_bps": float(np.median(arr)), "p95_slippage_bps": float(np.percentile(arr, 95)), "total_cost": cost, "count": len(recent)}

    def get_worst_fills(self, count=5):
        return sorted(self.history, key=lambda x: abs(x.get("slippage_bps", 0)), reverse=True)[:count]

_tracker = None
def get_tracker(config=None):
    global _tracker
    if _tracker is None: _tracker = SlippageTracker(config)
    return _tracker
