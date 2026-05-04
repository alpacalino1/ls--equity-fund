#!/usr/bin/env python3
"""
Meridian Capital Partners · run_execution.py
Layer 6 main entry point — paper trading with Alpaca.
"""
import argparse, logging, sys, time
import pandas as pd
import yaml
from pathlib import Path
from dotenv import load_dotenv

from data.db import MeridianDB
from execution.executor import OrderExecutor

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("meridian.execution")

def load_config(path="config.yaml"):
    with open(path) as f: return yaml.safe_load(f)

def get_trades():
    for pf in ["output/portfolio/portfolio_mvo_positions.csv", "output/portfolio/portfolio_conviction_positions.csv"]:
        p = Path(pf)
        if p.exists():
            df = pd.read_csv(p)
            trades = []
            for _, row in df.iterrows():
                if abs(row.get("weight", 0)) < 0.001: continue
                trades.append({"ticker": row["ticker"], "side": "buy" if row["weight"] > 0 else "short", "quantity": int(abs(row["weight"]) * 1000)})
            return trades
    logger.error("No portfolio found. Run: python run_portfolio.py")
    return []

def get_market_data(db):
    try:
        return pd.read_sql_query("SELECT ticker, close, volume FROM daily_prices WHERE date = (SELECT MAX(date) FROM daily_prices)", db._connect())
    except: return pd.DataFrame()

def main():
    p = argparse.ArgumentParser(description="Meridian Capital Partners — Execution")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--config", default="config.yaml")
    args = p.parse_args()

    if not args.dry_run and not args.execute:
        logger.error("Need --dry-run or --execute"); sys.exit(1)

    config = load_config(args.config)
    db = MeridianDB(config.get("db_path", "cache/meridian.db"))
    trades = get_trades()
    if not trades:
        logger.error("No trades found"); sys.exit(1)

    market_data = get_market_data(db)

    if args.dry_run:
        logger.info(f"DRY RUN: would execute {len(trades)} trades")
        for i, t in enumerate(trades[:10]):
            logger.info(f"  [{i+1}] {t['side']} {t['quantity']} {t['ticker']}")
        logger.info("Dry run complete — no orders placed.")
        return

    # Live execution
    if config.get("execution", {}).get("mode") == "live":
        confirm = input("⚠️ LIVE TRADING! Type 'YES I UNDERSTAND THE RISKS': ")
        if confirm != "YES I UNDERSTAND THE RISKS":
            logger.info("Aborted."); return

    executor = OrderExecutor(config.get("execution", {}))
    results = executor.execute_trades(trades, market_data)
    filled = [r for r in results if r.get("status") == "filled"]
    logger.info(f"Complete: {len(filled)}/{len(results)} filled")

if __name__ == "__main__": main()
