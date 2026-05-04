#!/usr/bin/env python3
"""
Meridian Capital Partners · run_analysis.py
─────────────────────────────────────────────────────────────────
Layer 3 orchestrator — run this to perform AI analysis on filings and transcripts.
Usage: python run_analysis.py [--analyzer earnings|filing|all] [--ticker TICKER]
"""

import argparse
import logging
import sys
import time
import pandas as pd
from pathlib import Path
from typing import Dict, Any

import yaml
from dotenv import load_dotenv

from data.db import MeridianDB
from analysis import earnings_analyzer, filing_analyzer

# ── Setup ───────────────────────────────────────────────────────────────

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("meridian.analysis.main")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def get_ticker_list(db: MeridianDB, limit: int = None) -> list:
    """Get list of tickers to analyze."""
    query = "SELECT ticker FROM universe WHERE gics_sector != 'Benchmark' ORDER BY ticker"
    df = pd.read_sql_query(query, db._connect())
    tickers = df['ticker'].tolist()
    return tickers[:limit] if limit else tickers


def run_earnings_analysis(tickers: list, config: dict, db: MeridianDB):
    """Run earnings call analysis for specified tickers."""
    logger.info(f"Running earnings analysis for {len(tickers)} tickers")
    
    # TODO: This would require earnings transcripts which aren't in L1
    # For now we'll just log that this is available but not runnable without transcripts
    logger.info("Earnings analysis ready but requires transcript data (not included in L1)")


def run_filing_analysis(tickers: list, config: dict, db: MeridianDB):
    """Run SEC filing analysis for specified tickers."""
    logger.info(f"Running filing analysis for {len(tickers)} tickers")
    
    analyzer = filing_analyzer.FilingAnalyzer(config.get("analysis", {}).get("filing", {}))
    
    # Get fundamental metrics for all tickers
    metrics_query = """
    SELECT ticker, period, revenue, net_income, total_assets, total_liabilities,
           cash_flow_from_operating_activities, accounts_receivable, inventory,
           gross_profit, operating_income
    FROM derived_ratios dr
    LEFT JOIN fundamentals f ON dr.ticker = f.ticker AND dr.period = f.period
    WHERE dr.period IN (
        SELECT DISTINCT period FROM derived_ratios 
        ORDER BY period DESC LIMIT 8
    )
    """
    
    try:
        metrics_df = pd.read_sql_query(metrics_query, db._connect())
    except Exception as e:
        logger.error(f"Failed to fetch fundamental metrics: {e}")
        metrics_df = pd.DataFrame()
    
    results = {}
    successful_analyses = 0
    
    for i, ticker in enumerate(tickers):
        try:
            logger.info(f"[{i+1}/{len(tickers)}] Analyzing filings for {ticker}")
            
            # Get filing texts from database
            filing_analyzer_instance = filing_analyzer.FilingAnalyzer()
            filing_texts, filing_dates = filing_analyzer_instance.get_filing_text_from_db(
                db._connect(), ticker, limit=3
            )
            
            if not filing_texts:
                logger.info(f"No filings found for {ticker}")
                continue
                
            # Get metrics for this ticker
            ticker_metrics = metrics_df[metrics_df['ticker'] == ticker].sort_values('period', ascending=False).head(8)
            
            # Analyze filings
            result = analyzer.analyze_filings(ticker, ticker_metrics, filing_texts, filing_dates)
            
            if result:
                results[ticker] = result
                successful_analyses += 1
                
                # Save result to output directory
                output_dir = Path("output/analysis")
                output_dir.mkdir(parents=True, exist_ok=True)
                
                result_file = output_dir / f"{ticker}_filing_analysis.json"
                try:
                    import json
                    with open(result_file, 'w') as f:
                        json.dump(result, f, indent=2)
                except Exception as e:
                    logger.warning(f"Failed to save result for {ticker}: {e}")
            
            # Brief pause to respect rate limits
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Failed to analyze {ticker}: {e}")
            continue
    
    logger.info(f"Filing analysis complete: {successful_analyses}/{len(tickers)} tickers analyzed")
    return results


def run_all_analysis(tickers: list, config: dict, db: MeridianDB):
    """Run all analysis modules."""
    t0 = time.time()
    
    # Run filing analysis (earnings analysis needs transcripts not in L1)
    filing_results = run_filing_analysis(tickers, config, db)
    
    logger.info("═════════════════════════════════════════════════")
    logger.info(f"Layer 3 COMPLETE — total time: {(time.time() - t0) / 60:.1f} min")
    
    return {
        "filing_analysis": filing_results
    }


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Layer 3 AI Analysis")
    parser.add_argument("--analyzer", default="all",
                        choices=["earnings", "filing", "all"],
                        help="Which analyzer to run (default: all)")
    parser.add_argument("--ticker", help="Specific ticker to analyze (default: all S&P 500)")
    parser.add_argument("--limit", type=int, help="Limit number of tickers to analyze")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    db = MeridianDB(config.get("db_path", "cache/meridian.db"))
    
    # Get tickers to analyze
    if args.ticker:
        tickers = [args.ticker]
    else:
        logger.info("Loading ticker list...")
        tickers = get_ticker_list(db, args.limit)
        logger.info(f"Loaded {len(tickers)} tickers for analysis")
    
    # Run specific analyzer or all
    analyzer_functions = {
        "earnings": lambda: run_earnings_analysis(tickers, config, db),
        "filing": lambda: run_filing_analysis(tickers, config, db),
    }

    if args.analyzer == "all":
        results = run_all_analysis(tickers, config, db)
        print(f"\nAI Analysis complete for {len(tickers)} stocks")
        print(f"Results saved to output/analysis/")
    else:
        logger.info(f"Running {args.analyzer} analysis")
        analyzer_functions[args.analyzer]()
        print(f"\n{args.analyzer.capitalize()} analysis complete")


if __name__ == "__main__":
    main()
