#!/usr/bin/env python3
"""
Meridian Capital Partners · run_portfolio.py
─────────────────────────────────────────────────────────────────
Layer 4 orchestrator — run this to build portfolios with MVO or conviction-tilt.
Usage: python run_portfolio.py --optimize-method mvo|conviction [--ticker TICKER]
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
from portfolio import optimizer, mvo_optimizer

# ── Setup ───────────────────────────────────────────────────────────────

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("meridian.portfolio.main")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def get_factor_scores() -> pd.DataFrame:
    """Load factor scores from output directory."""
    scores_path = Path("output/factor_scores/combined_scores.csv")
    if not scores_path.exists():
        logger.error(f"Factor scores not found at {scores_path}")
        return pd.DataFrame()
        
    try:
        scores_df = pd.read_csv(scores_path)
        logger.info(f"Loaded factor scores for {len(scores_df)} stocks")
        return scores_df
    except Exception as e:
        logger.error(f"Failed to load factor scores: {e}")
        return pd.DataFrame()


def get_universe_data(db: MeridianDB) -> pd.DataFrame:
    """Get universe data with sector and beta information."""
    query = """
    SELECT u.ticker, u.gics_sector as sector, 
           COALESCE(dr.beta, 1.0) as beta
    FROM universe u
    LEFT JOIN derived_ratios dr ON u.ticker = dr.ticker AND dr.period = (
        SELECT MAX(period) FROM derived_ratios dr2 WHERE dr2.ticker = u.ticker
    )
    WHERE u.gics_sector != 'Benchmark'
    """
    
    try:
        universe_df = pd.read_sql_query(query, db._connect())
        logger.info(f"Loaded universe data for {len(universe_df)} stocks")
        return universe_df
    except Exception as e:
        logger.error(f"Failed to load universe data: {e}")
        return pd.DataFrame()


def get_price_data(db: MeridianDB, lookback_days: int = 120) -> pd.DataFrame:
    """Get historical price data for covariance matrix calculation."""
    query = f"""
    SELECT ticker, date, close
    FROM daily_prices
    WHERE date >= DATE('now', '-{lookback_days} days')
    ORDER BY ticker, date
    """
    
    try:
        price_df = pd.read_sql_query(query, db._connect())
        logger.info(f"Loaded price data for {len(price_df)} records")
        return price_df
    except Exception as e:
        logger.error(f"Failed to load price data: {e}")
        return pd.DataFrame()


def get_market_data(db: MeridianDB) -> pd.DataFrame:
    """Get market data for transaction cost calculations."""
    query = """
    WITH latest_prices AS (
        SELECT ticker, close as price, volume
        FROM daily_prices dp1
        WHERE date = (SELECT MAX(date) FROM daily_prices dp2 WHERE dp2.ticker = dp1.ticker)
    ),
    avg_daily_volume AS (
        SELECT ticker, AVG(volume) as adv
        FROM daily_prices
        WHERE date >= DATE('now', '-20 days')
        GROUP BY ticker
    )
    SELECT lp.ticker, lp.price, adv.volume as volume, 
           lp.price * 0.001 as avg_spread  -- Estimating 10bps spread
    FROM latest_prices lp
    JOIN avg_daily_volume adv ON lp.ticker = adv.ticker
    """
    
    try:
        market_df = pd.read_sql_query(query, db._connect())
        logger.info(f"Loaded market data for {len(market_df)} stocks")
        return market_df
    except Exception as e:
        logger.error(f"Failed to load market data: {e}")
        return pd.DataFrame()


def run_conviction_optimization(scores: pd.DataFrame, universe: pd.DataFrame,
                               current_positions: pd.DataFrame = None,
                               market_data: pd.DataFrame = None,
                               config: dict = None) -> Dict[str, Any]:
    """Run conviction-tilt portfolio optimization."""
    logger.info("Running conviction-tilt portfolio optimization")
    
    opt = optimizer.ConvictionOptimizer(config.get("portfolio", {}).get("conviction", {}))
    result = opt.optimize_portfolio(scores, universe, current_positions, market_data)
    
    return result


def run_mvo_optimization(scores: pd.DataFrame, universe: pd.DataFrame,
                        price_data: pd.DataFrame,
                        current_positions: pd.DataFrame = None,
                        market_data: pd.DataFrame = None,
                        config: dict = None) -> Dict[str, Any]:
    """Run MVO portfolio optimization."""
    logger.info("Running MVO portfolio optimization")
    
    opt = mvo_optimizer.MVPOptimizer(config.get("portfolio", {}).get("mvo", {}))
    result = opt.optimize_portfolio(scores, universe, price_data, 
                                   current_positions, market_data)
    
    return result


def save_portfolio_result(result: Dict[str, Any], method: str):
    """Save portfolio result to output directory."""
    output_dir = Path("output/portfolio")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save portfolio positions
    positions_df = pd.DataFrame(result.get('positions', []))
    positions_file = output_dir / f"portfolio_{method}_positions.csv"
    positions_df.to_csv(positions_file, index=False)
    
    # Save portfolio stats
    stats_file = output_dir / f"portfolio_{method}_stats.json"
    try:
        import json
        with open(stats_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Failed to save portfolio stats: {e}")
    
    logger.info(f"Portfolio saved to {positions_file}")


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Layer 4 Portfolio Construction")
    parser.add_argument("--optimize-method", default="conviction",
                        choices=["mvo", "conviction"],
                        help="Optimization method (default: conviction)")
    parser.add_argument("--ticker", help="Specific ticker to analyze (build微型portfolio)")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    db = MeridianDB(config.get("db_path", "cache/meridian.db"))
    
    # Load input data
    logger.info("Loading input data...")
    scores_df = get_factor_scores()
    if scores_df.empty:
        logger.error("No factor scores available. Run Layer 2 first.")
        sys.exit(1)
        
    universe_df = get_universe_data(db)
    if universe_df.empty:
        logger.error("No universe data available.")
        sys.exit(1)
        
    market_data = get_market_data(db)
    price_data = get_price_data(db)
    
    # Filter to specific ticker if requested
    if args.ticker:
        scores_df = scores_df[scores_df['ticker'] == args.ticker]
        universe_df = universe_df[universe_df['ticker'] == args.ticker]
        if not market_data.empty:
            market_data = market_data[market_data['ticker'] == args.ticker]
        if not price_data.empty:
            price_data = price_data[price_data['ticker'] == args.ticker]
    
    # Run optimization
    t0 = time.time()
    
    if args.optimize_method == "mvo":
        if price_data.empty:
            logger.warning("No price data available for MVO, falling back to conviction")
            args.optimize_method = "conviction"
        else:
            result = run_mvo_optimization(scores_df, universe_df, price_data, 
                                        market_data=market_data, config=config)
    else:
        result = run_conviction_optimization(scores_df, universe_df, 
                                           market_data=market_data, config=config)
    
    # Report results
    stats = result.get('portfolio_stats', {})
    logger.info("═════════════════════════════════════════════════")
    logger.info(f"Portfolio Construction COMPLETE — Method: {args.optimize_method}")
    logger.info(f"Time taken: {(time.time() - t0):.1f} seconds")
    logger.info(f"Positions: {stats.get('total_positions', 0)}")
    logger.info(f"Long Gross: {stats.get('long_gross', 0):.2%}")
    logger.info(f"Short Gross: {stats.get('short_gross', 0):.2%}")
    logger.info(f"Net Exposure: {stats.get('net_exposure', 0):.2%}")
    
    if 'expected_return' in stats:
        logger.info(f"Expected Return: {stats.get('expected_return', 0):.2%}")
        logger.info(f"Volatility: {stats.get('volatility', 0):.2%}")
        logger.info(f"Sharpe Ratio: {stats.get('sharpe_ratio', 0):.2f}")
    
    # Save result
    save_portfolio_result(result, args.optimize_method)
    
    # Print top 5 positions
    positions = result.get('positions', [])
    if positions:
        positions_df = pd.DataFrame(positions)
        top_long = positions_df[positions_df['weight'] > 0].nlargest(5, 'weight')
        top_short = positions_df[positions_df['weight'] < 0].nsmallest(5, 'weight')
        
        print("\nTop 5 Long Positions:")
        if not top_long.empty:
            for _, row in top_long.iterrows():
                print(f"  {row['ticker']:>6} {row['weight']:>8.2%} ({row['sector']})")
        else:
            print("  None")
            
        print("\nTop 5 Short Positions:")
        if not top_short.empty:
            for _, row in top_short.iterrows():
                print(f"  {row['ticker']:>6} {row['weight']:>8.2%} ({row['sector']})")
        else:
            print("  None")


if __name__ == "__main__":
    main()
