#!/usr/bin/env python3
"""
Meridian Capital Partners · run_risk.py
─────────────────────────────────────────────────────────────────
Layer 5 orchestrator — run this to perform risk management checks.
Usage: python run_risk.py [--check portfolio|circuit-breakers|pre-trade] [--ticker TICKER]
"""

import argparse
import logging
import sys
import time
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List

import yaml
from dotenv import load_dotenv

from data.db import MeridianDB
from risk import factor_risk_model, pre_trade, circuit_breakers

# ── Setup ───────────────────────────────────────────────────────────────

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("meridian.risk.main")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def get_factor_data() -> pd.DataFrame:
    """Load factor scores from output directory."""
    scores_path = Path("output/factor_scores/combined_scores.csv")
    if not scores_path.exists():
        logger.error(f"Factor scores not found at {scores_path}")
        return pd.DataFrame()
        
    try:
        scores_df = pd.DataFrame(pd.read_csv(scores_path))
        logger.info(f"Loaded factor scores for {len(scores_df)} stocks")
        return scores_df
    except Exception as e:
        logger.error(f"Failed to load factor scores: {e}")
        return pd.DataFrame()


def get_price_data(db: MeridianDB, lookback_days: int = 120) -> pd.DataFrame:
    """Get historical price data for risk model."""
    query = f"""
    SELECT ticker, date, close, volume
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


def get_portfolio_data() -> pd.DataFrame:
    """Load current portfolio data."""
    # Try MVO portfolio first, then conviction
    portfolio_files = [
        "output/portfolio/portfolio_mvo_positions.csv",
        "output/portfolio/portfolio_conviction_positions.csv"
    ]
    
    for portfolio_file in portfolio_files:
        portfolio_path = Path(portfolio_file)
        if portfolio_path.exists():
            try:
                portfolio_df = pd.read_csv(portfolio_path)
                logger.info(f"Loaded portfolio from {portfolio_file}")
                return portfolio_df
            except Exception as e:
                logger.error(f"Failed to load portfolio from {portfolio_file}: {e}")
                
    logger.warning("No portfolio data found")
    return pd.DataFrame()


def get_market_data(db: MeridianDB) -> pd.DataFrame:
    """Get market data for risk checks."""
    query = """
    SELECT ticker, close as price, volume
    FROM daily_prices 
    WHERE date = (SELECT MAX(date) FROM daily_prices)
    """
    
    try:
        market_df = pd.read_sql_query(query, db._connect())
        logger.info(f"Loaded market data for {len(market_df)} stocks")
        return market_df
    except Exception as e:
        logger.error(f"Failed to load market data: {e}")
        return pd.DataFrame()


def run_factor_risk_analysis(config: dict, db: MeridianDB) -> Dict[str, Any]:
    """Run factor risk model analysis."""
    logger.info("Running factor risk model analysis")
    
    # Load input data
    factor_data = get_factor_data()
    price_data = get_price_data(db)
    
    if factor_data.empty or price_data.empty:
        logger.error("Missing input data for factor risk model")
        return {}
        
    # Build factor risk model
    risk_config = config.get("risk", {}).get("factor_model", {})
    model = factor_risk_model.FactorRiskModel(risk_config)
    result = model.build_factor_model(factor_data, price_data)
    
    # Save results
    if result.get('status') == 'success':
        output_dir = Path("output/risk")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save factor returns
        if not result['factor_returns'].empty:
            result['factor_returns'].to_csv(output_dir / "factor_returns.csv")
            
        # Save factor covariance matrix
        if result['factor_covariance'].size > 0:
            pd.DataFrame(result['factor_covariance']).to_csv(output_dir / "factor_covariance.csv", index=False)
            
        logger.info("Factor risk model saved to output/risk/")
        
    return result


def run_circuit_breakers(portfolio_value: float = None, daily_pnl: float = 0, 
                        weekly_pnl: float = 0, config: dict = None) -> List[Dict[str, Any]]:
    """Run circuit breaker checks."""
    logger.info("Running circuit breaker checks")
    
    if portfolio_value is None:
        portfolio_value = config.get("risk", {}).get("aum", 100_000_000)
        
    # Get circuit breaker instance
    cb_config = config.get("risk", {}).get("circuit_breakers", {})
    cb = circuit_breakers.get_circuit_breaker(cb_config)
    
    # Load performance history
    cb.load_performance_history()
    
    # Get portfolio data
    portfolio_df = get_portfolio_data()
    positions = []
    if not portfolio_df.empty:
        positions = portfolio_df.to_dict('records')
        
    # Check all circuit breakers
    actions = circuit_breakers.check_all_circuit_breakers(
        portfolio_value=portfolio_value,
        daily_pnl=daily_pnl,
        weekly_pnl=weekly_pnl,
        drawdown_peak=portfolio_value * 1.1,  # Example peak value
        positions=positions,
        config=cb_config
    )
    
    # Save performance history
    cb.save_performance_history()
    
    # Report results
    if actions:
        logger.warning(f"Circuit breakers triggered {len(actions)} actions:")
        for action_set in actions:
            for action in action_set.get('actions', []):
                logger.warning(f"  - {action['type']}: {action['reason']}")
    else:
        logger.info("No circuit breaker actions triggered")
        
    return actions


def run_pre_trade_check(trade_request: Dict[str, Any], config: dict, db: MeridianDB) -> Dict[str, Any]:
    """Run pre-trade risk check."""
    logger.info(f"Running pre-trade check for {trade_request}")
    
    # Load portfolio and market data
    portfolio_df = get_portfolio_data()
    market_data = get_market_data(db)
    
    # Load factor model if available
    factor_model = {}  # In practice, you'd load the saved factor model
    
    # Run pre-trade check
    checker_config = config.get("risk", {}).get("pre_trade", {})
    result = pre_trade.check_pre_trade(
        trade_request, portfolio_df, market_data, factor_model, checker_config
    )
    
    # Report results
    if result['approved']:
        logger.info(f"Trade approved: {trade_request['ticker']}")
    else:
        logger.warning(f"Trade rejected: {trade_request['ticker']}")
        for reason in result['veto_reasons']:
            logger.warning(f"  - {reason}")
            
    return result


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Layer 5 Risk Management")
    parser.add_argument("--check", default="portfolio",
                        choices=["portfolio", "circuit-breakers", "pre-trade"],
                        help="Type of risk check to run")
    parser.add_argument("--ticker", help="Specific ticker for pre-trade check")
    parser.add_argument("--action", help="Action for pre-trade check (buy/sell/short/close)")
    parser.add_argument("--quantity", type=int, default=100, help="Quantity for pre-trade check")
    parser.add_argument("--portfolio-value", type=float, help="Portfolio value for circuit breakers")
    parser.add_argument("--daily-pnl", type=float, default=0, help="Daily P&L for circuit breakers")
    parser.add_argument("--weekly-pnl", type=float, default=0, help="Weekly P&L for circuit breakers")
    parser.add_argument("--set-halt", action="store_true", help="Set trading halt")
    parser.add_argument("--clear-halt", action="store_true", help="Clear trading halt")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    db = MeridianDB(config.get("db_path", "cache/meridian.db"))
    
    t0 = time.time()
    
    if args.set_halt:
        # Set trading halt
        checker = pre_trade.PreTradeChecker(config.get("risk", {}).get("pre_trade", {}))
        checker.set_halt("Manual halt requested")
        logger.info("Trading halt set")
        return
        
    if args.clear_halt:
        # Clear trading halt
        checker = pre_trade.PreTradeChecker(config.get("risk", {}).get("pre_trade", {}))
        checker.clear_halt()
        logger.info("Trading halt cleared")
        return
    
    if args.check == "portfolio":
        # Run factor risk model
        result = run_factor_risk_analysis(config, db)
        if result.get('status') == 'success':
            logger.info("═════════════════════════════════════════════════")
            logger.info("Factor Risk Model COMPLETE")
            logger.info(f"Factors: {len(result.get('factor_returns', pd.DataFrame()).columns) if not result.get('factor_returns', pd.DataFrame()).empty else 0}")
            logger.info(f"Time taken: {(time.time() - t0):.1f} seconds")
            
    elif args.check == "circuit-breakers":
        # Run circuit breaker checks
        portfolio_value = args.portfolio_value or config.get("risk", {}).get("aum", 100_000_000)
        actions = run_circuit_breakers(
            portfolio_value=portfolio_value,
            daily_pnl=args.daily_pnl,
            weekly_pnl=args.weekly_pnl,
            config=config
        )
        
        logger.info("═════════════════════════════════════════════════")
        logger.info("Circuit Breaker Check COMPLETE")
        logger.info(f"Actions triggered: {len(actions)}")
        logger.info(f"Time taken: {(time.time() - t0):.1f} seconds")
        
    elif args.check == "pre-trade":
        # Run pre-trade check
        if not args.ticker:
            logger.error("Ticker required for pre-trade check")
            sys.exit(1)
            
        trade_request = {
            'ticker': args.ticker,
            'action': args.action or 'buy',
            'quantity': args.quantity
        }
        
        result = run_pre_trade_check(trade_request, config, db)
        
        logger.info("═════════════════════════════════════════════════")
        logger.info("Pre-Trade Check COMPLETE")
        logger.info(f"Approved: {result['approved']}")
        logger.info(f"Time taken: {(time.time() - t0):.1f} seconds")
        
        if result['veto_reasons']:
            print("\nVeto Reasons:")
            for reason in result['veto_reasons']:
                print(f"  - {reason}")


if __name__ == "__main__":
    main()
