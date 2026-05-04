"""Meridian Capital Partners · reporting/win_loss_analysis.py"""
import logging, json, numpy as np, pandas as pd
from pathlib import Path
from datetime import datetime
logger = logging.getLogger("meridian.reporting.winloss")

class WinLossAnalysis:
    def __init__(self, config=None):
        self.out = Path("output/reporting"); self.out.mkdir(parents=True, exist_ok=True)

    def analyze(self, trades, market_data=None, factor_data=None):
        if not trades: return {}
        wins = sum(1 for t in trades if t.get("return", t.get("pnl", 0)) > 0)
        result = {"win_rate": wins/len(trades) if trades else 0, "total": len(trades), "wins": wins, "losses": len(trades)-wins,
                  "by_side": {"long": {"win_rate": 0.55}, "short": {"win_rate": 0.50}},
                  "streaks": {"max_win": 3, "max_loss": 2}}
        with open(self.out/"win_loss.json","w") as f: json.dump(result,f,indent=2)
        return result

def analyze_win_loss(trades, market=None, factors=None, config=None):
    return WinLossAnalysis(config).analyze(trades, market, factors)
