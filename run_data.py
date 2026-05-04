#!/usr/bin/env python3
"""
Meridian Capital Partners · run_data.py
─────────────────────────────────────────────────────────────────
Layer 1 orchestrator — run this to ingest ALL 5 data sources.
Usage: python run_data.py [--source universe|market|fundamentals|sec|insider|institutional|all]
"""

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from data.db import MeridianDB
from data import universe, market_data, fundamentals, sec_edgar, insider, institutional

# ── Setup ───────────────────────────────────────────────────────────────

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("meridian.main")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def run_all_sources(tickers: list[str], config: dict, db: MeridianDB):
    """Run all 5 data sources sequentially."""
    t0 = time.time()

    # Source 2a: Market Data (prices)
    logger.info("═══ Source 2a: Market Data (daily OHLCV) ═══")
    market_data.fetch_daily_prices(tickers, config, db)
    logger.info("Market data: %.1f min", (time.time() - t0) / 60)

    # Source 2b: Fundamentals + derived ratios
    logger.info("═══ Source 2b: Fundamentals + Derived Ratios ═══")
    fundamentals.update_fundamentals(tickers, config, db)
    logger.info("Fundamentals: %.1f min", (time.time() - t0) / 60)

    # Source 3: SEC EDGAR
    t_sec = time.time()
    logger.info("═══ Source 3: SEC EDGAR Filings ═══")
    sec_edgar.update_sec_filings(tickers, config, db)
    logger.info("SEC filings: %.1f min", (time.time() - t_sec) / 60)

    # Source 4: Insider Transactions
    t_ins = time.time()
    logger.info("═══ Source 4: Insider Transactions ═══")
    insider.update_insider(tickers, config, db)
    logger.info("Insider: %.1f min", (time.time() - t_ins) / 60)

    # Source 5: Institutional Holdings
    t_inst = time.time()
    logger.info("═══ Source 5: Institutional Holdings ═══")
    institutional.update_institutional(tickers, config, db)
    logger.info("Institutional: %.1f min", (time.time() - t_inst) / 60)

    logger.info("═════════════════════════════════════════════════")
    logger.info("Layer 1 COMPLETE — total time: %.1f min", (time.time() - t0) / 60)
    logger.info("Database: %s", db.db_path)


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Layer 1 Data Ingestion")
    parser.add_argument("--source", default="all",
                        choices=["universe", "market", "fundamentals", "sec", "insider", "institutional", "all"],
                        help="Which data source to refresh (default: all)")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    db = MeridianDB(config.get("db_path", "cache/meridian.db"))

    # Source 1: Universe (always runs first if needed)
    logger.info("═══ Source 1: Universe (S&P 500 + benchmarks) ═══")
    tickers = universe.update_universe(db, config)
    logger.info("Total tickers in universe: %d", len(tickers))

    if args.source == "universe":
        logger.info("Universe only — done.")
        return

    # Run specific source or all
    sources_map = {
        "market": lambda: market_data.fetch_daily_prices(tickers, config, db),
        "fundamentals": lambda: fundamentals.update_fundamentals(tickers, config, db),
        "sec": lambda: sec_edgar.update_sec_filings(tickers, config, db),
        "insider": lambda: insider.update_insider(tickers, config, db),
        "institutional": lambda: institutional.update_institutional(tickers, config, db),
    }

    if args.source == "all":
        run_all_sources(tickers, config, db)
    else:
        sources_map[args.source]()
        logger.info("Source '%s' complete.", args.source)


if __name__ == "__main__":
    main()
