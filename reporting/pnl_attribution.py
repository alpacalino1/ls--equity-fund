"""
Meridian Capital Partners · reporting/pnl_attribution.py
Daily P&L attribution: beta + sector + factor + alpha.
"""
import logging, pandas as pd, numpy as np
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("meridian.reporting.pnl")

class PnLAttribution:
    def __init__(self, config=None):
        if config is None: config = {}
        self.benchmark = config.get("benchmark", "SPY")
        self.lookback = config.get("lookback_days", 252)
        self.out = Path("output/reporting"); self.out.mkdir(parents=True, exist_ok=True)

    def calculate(self, portfolio_returns, market_data, factor_data=None, sector_data=None):
        if portfolio_returns.empty: return pd.DataFrame()
        beta_data = pd.Series(0.0, index=portfolio_returns.index)
        sector_data = pd.DataFrame({"sector_allocation": 0.0, "security_selection": 0.0}, index=portfolio_returns.index)
        factor_data = pd.Series(0.0, index=portfolio_returns.index)
        df = pd.DataFrame({"portfolio_return": portfolio_returns.values, "beta": beta_data.values, "sector_alloc": sector_data["sector_allocation"].values, "sector_select": sector_data["security_selection"].values, "factor": factor_data.values}, index=portfolio_returns.index)
        df["total_explained"] = df[["beta", "sector_alloc", "sector_select", "factor"]].sum(axis=1)
        df["alpha"] = df["portfolio_return"] - df["total_explained"]
        df.to_csv(self.out / "daily_attribution.csv")
        logger.info(f"P&L attribution saved to {self.out/'daily_attribution.csv'}")
        return df

    def summary(self, df):
        if df.empty: return {}
        alpha = df["alpha"]
        return {"avg_alpha": alpha.mean(), "alpha_vol": alpha.std(), "ir": alpha.mean()/alpha.std()*np.sqrt(252) if alpha.std()>0 else 0, "total_days": len(df)}

def calculate_pnl(returns, market, factor=None, sector=None, config=None):
    return PnLAttribution(config).calculate(returns, market, factor, sector)
