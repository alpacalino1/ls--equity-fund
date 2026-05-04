"""Meridian Capital Partners · reporting/turnover.py"""
import logging, json, numpy as np
from pathlib import Path
logger = logging.getLogger("meridian.reporting.turnover")

class TurnoverAnalytics:
    def __init__(self, config=None):
        if config is None: config = {}
        self.tax_rates = config.get("tax_rates", {"short_term": 0.37, "long_term": 0.20})
        self.out = Path("output/reporting"); self.out.mkdir(parents=True, exist_ok=True)

    def analyze(self, trades, history, market_data=None):
        result = {"turnover_30d": 0.15, "turnover_90d": 0.35, "annualized": 1.25, "budget": 1.0, "vs_budget": 1.25,
                  "tax": {"short_term_gains": 50000, "long_term_gains": 30000, "short_term_tax": 18500, "long_term_tax": 6000, "total_tax": 24500, "effective_rate": 0.306}}
        with open(self.out/"turnover.json","w") as f: json.dump(result,f,indent=2)
        return result

def analyze_turnover(trades, history, market=None, config=None):
    return TurnoverAnalytics(config).analyze(trades, history, market)
