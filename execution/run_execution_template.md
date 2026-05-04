# Execution Runner Template

This is a template for the run_execution.py implementation that will serve as the main entry point.

## Planned Implementation

```python
#!/usr/bin/env python3
"""
Meridian Capital Partners · run_execution.py
─────────────────────────────────────────────────────────────────
Main entry point for execution layer - paper trading with Alpaca.
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
from execution.broker import AlpacaBroker
from execution.executor import OrderExecutor
from execution.costs import SlippageTracker
from execution.short_check import ShortAvailabilityChecker
from execution.order_manager import OrderManager

# ── Setup ───────────────────────────────────────────────────────────────

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("meridian.execution.main")

def load_config(path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)

def get_portfolio_trades() -> List[Dict[str, Any]]:
    """Load portfolio trades from Layer 4 output."""
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
                
                # Convert to trade list format
                trades = []
                for _, row in portfolio_df.iterrows():
                    # Skip near-zero positions
                    if abs(row['weight']) < 0.001:
                        continue
                        
                    # Convert weight to quantity (simplified for template)
                    quantity = int(abs(row['weight']) * 1000)  # 1000 share base
                    
                    trade = {
                        'ticker': row['ticker'],
                        'side': 'buy' if row['weight'] > 0 else 'short',
                        'quantity': quantity,
                        'reason': f"Portfolio weight: {row['weight']:.2%}"
                    }
                    trades.append(trade)
                    
                return trades
                
            except Exception as e:
                logger.error(f"Failed to load portfolio from {portfolio_file}: {e}")
                
    logger.warning("No portfolio data found")
    return []

def get_market_data(db: MeridianDB) -> pd.DataFrame:
    """Get current market data for limit price calculation."""
    query = """
    SELECT ticker, close, volume
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

def get_current_portfolio(db: MeridianDB) -> pd.DataFrame:
    """Get current portfolio positions from Alpaca."""
    # This would sync with Alpaca positions in real implementation
    query = """
    SELECT ticker, weight
    FROM portfolio_positions
    WHERE date = (SELECT MAX(date) FROM portfolio_positions)
    """
    
    try:
        portfolio_df = pd.read_sql_query(query, db._connect())
        logger.info(f"Loaded current portfolio positions for {len(portfolio_df)} stocks")
        return portfolio_df
    except Exception as e:
        logger.error(f"Failed to load current portfolio: {e}")
        return pd.DataFrame()

def confirm_live_trading() -> bool:
    """Confirm user wants to proceed with live trading."""
    print("⚠️  WARNING: Live trading mode selected!")
    print("This will place REAL ORDERS with YOUR MONEY.")
    print("")
    print("To proceed, type exactly: YES I UNDERSTAND THE RISKS")
    print("(or 'quit' to cancel)")
    print("")
    
    user_input = input("Confirmation: ").strip()
    
    if user_input == "YES I UNDERSTAND THE RISKS":
        logger.info("Live trading confirmed by user")
        return True
    elif user_input.lower() == "quit":
        logger.info("User cancelled live trading")
        return False
    else:
        logger.warning(f"Invalid confirmation: '{user_input}'")
        print("❌ Invalid confirmation. Aborting live trading.")
        return False

def run_dry_execution(trades: List[Dict[str, Any]], market_data: pd.DataFrame,
                     current_portfolio: pd.DataFrame, config: dict) -> Dict[str, Any]:
    """Run dry execution - log what would happen without placing orders."""
    logger.info("🏃 Running DRY EXECUTION mode")
    logger.info(f"Would process {len(trades)} trades")
    
    results = {
        'trades_processed': 0,
        'trades_approved': 0,
        'trades_rejected': 0,
        'estimated_cost': 0.0,
        'details': []
    }
    
    # Initialize components (without actually connecting to Alpaca in dry run)
    short_checker = ShortAvailabilityChecker(config.get("execution", {}).get("short_check", {}))
    
    for i, trade in enumerate(trades):
        ticker = trade['ticker']
        side = trade['side']
        quantity = trade['quantity']
        
        logger.info(f"[{i+1}/{len(trades)}] DRY RUN: {side} {quantity} {ticker}")
        
        # Short availability check (simulated)
        if side == 'short':
            shortable = short_checker.is_shortable(ticker)
            if not shortable:
                logger.info(f"  ❌ Would reject: Short not available for {ticker}")
                results['trades_rejected'] += 1
                results['details'].append({
                    'ticker': ticker,
                    'status': 'rejected',
                    'reason': 'short_not_available'
                })
                continue
                
        # Get limit price (simulated)
        ticker_data = market_data[market_data['ticker'] == ticker]
        if ticker_data.empty:
            logger.info(f"  ❌ Would reject: No market data for {ticker}")
            results['trades_rejected'] += 1
            results['details'].append({
                'ticker': ticker,
                'status': 'rejected',
                'reason': 'no_market_data'
            })
            continue
            
        current_price = ticker_data['close'].iloc[0]
        logger.info(f"  💰 Would place: {side} {quantity} {ticker} @ ~${current_price:.2f}")
        
        results['trades_approved'] += 1
        results['details'].append({
            'ticker': ticker,
            'side': side,
            'quantity': quantity,
            'estimated_price': current_price,
            'status': 'would_place'
        })
        
    results['trades_processed'] = len(trades)
    
    logger.info("🏁 DRY EXECUTION COMPLETE")
    logger.info(f"   Trades processed: {results['trades_processed']}")
    logger.info(f"   Trades approved:  {results['trades_approved']}")
    logger.info(f"   Trades rejected:  {results['trades_rejected']}")
    
    return results

def run_live_execution(trades: List[Dict[str, Any]], market_data: pd.DataFrame,
                      current_portfolio: pd.DataFrame, config: dict) -> Dict[str, Any]:
    """Run live execution - place actual orders with Alpaca."""
    logger.info("🚀 Running LIVE EXECUTION mode")
    logger.info(f"Will process {len(trades)} trades with Alpaca")
    
    # Initialize execution components
    executor = OrderExecutor(config.get("execution", {}))
    
    # Execute trades
    execution_results = executor.execute_trades(trades, market_data, current_portfolio)
    
    # Process results
    successful_executions = [r for r in execution_results if r.get('status') == 'filled']
    failed_executions = [r for r in execution_results if r.get('status') != 'filled']
    
    logger.info("🏁 LIVE EXECUTION COMPLETE")
    logger.info(f"   Total trades:     {len(execution_results)}")
    logger.info(f"   Successful:       {len(successful_executions)}")
    logger.info(f"   Failed:           {len(failed_executions)}")
    
    # Generate execution summary
    summary = {
        'total_trades': len(execution_results),
        'successful_executions': len(successful_executions),
        'failed_executions': len(failed_executions),
        'total_filled_quantity': sum(
            r.get('total_filled_qty', 0) for r in successful_executions
        ),
        'average_slippage_bps': sum(
            r.get('average_slippage_bps', 0) for r in successful_executions
        ) / len(successful_executions) if successful_executions else 0,
        'details': execution_results
    }
    
    return summary

def generate_execution_report(results: Dict[str, Any], mode: str) -> str:
    """Generate human-readable execution report."""
    report_lines = [
        "=" * 60,
        f"MERIDIAN CAPITAL PARTNERS - EXECUTION REPORT ({mode.upper()})",
        "=" * 60,
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        ""
    ]
    
    if mode == "dry":
        report_lines.extend([
            f"Trades Processed: {results['trades_processed']}",
            f"Trades Approved:  {results['trades_approved']}",
            f"Trades Rejected:  {results['trades_rejected']}",
            ""
        ])
        
        if results['details']:
            report_lines.append("TRADE DETAILS:")
            report_lines.append("-" * 40)
            for detail in results['details'][:10]:  # Show first 10
                if detail.get('status') == 'would_place':
                    report_lines.append(
                        f"  ✓ {detail['side']} {detail['quantity']} {detail['ticker']} "
                        f"@ ~${detail.get('estimated_price', 0):.2f}"
                    )
                else:
                    report_lines.append(
                        f"  ✗ {detail['ticker']}: {detail.get('reason', 'Unknown')}"
                    )
                    
    else:  # live mode
        report_lines.extend([
            f"Total Trades:     {results['total_trades']}",
            f"Successful:       {results['successful_executions']}",
            f"Failed:           {results['failed_executions']}",
            f"Total Filled Qty: {results['total_filled_quantity']:,}",
            f"Avg Slippage:     {results['average_slippage_bps']:.2f} bps",
            ""
        ])
        
        if results['details']:
            report_lines.append("EXECUTION DETAILS (First 10):")
            report_lines.append("-" * 40)
            for detail in results['details'][:10]:
                trade = detail.get('trade', {})
                report_lines.append(
                    f"  {trade.get('side', '?')} {trade.get('quantity', 0)} {trade.get('ticker', '???')} "
                    f"→ Status: {detail.get('status', 'Unknown')}"
                )
    
    report_lines.extend([
        "",
        "Report saved to: output/execution/execution_report.txt",
        "=" * 60
    ])
    
    return "\n".join(report_lines)

def save_execution_report(report_text: str, mode: str):
    """Save execution report to file."""
    output_dir = Path("output/execution")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = output_dir / f"execution_report_{mode}_{timestamp}.txt"
    
    try:
        with open(filename, 'w') as f:
            f.write(report_text)
        logger.info(f"Execution report saved to {filename}")
    except Exception as e:
        logger.error(f"Failed to save execution report: {e}")

def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Layer 6 Execution")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Dry run mode - log what would happen without placing orders")
    parser.add_argument("--execute", action="store_true",
                       help="Live execution mode - place actual orders with Alpaca")
    parser.add_argument("--portfolio-file", 
                       help="Custom portfolio CSV file (default: auto-detect)")
    parser.add_argument("--config", default="config.yaml", 
                       help="Path to config file")
    args = parser.parse_args()
    
    # Validate arguments
    if not args.dry_run and not args.execute:
        logger.error("Must specify either --dry-run or --execute")
        sys.exit(1)
        
    if args.dry_run and args.execute:
        logger.error("Cannot specify both --dry-run and --execute")
        sys.exit(1)
    
    # Load configuration
    config = load_config(args.config)
    db = MeridianDB(config.get("db_path", "cache/meridian.db"))
    
    # Check live trading safety
    if args.execute:
        execution_config = config.get("execution", {})
        if execution_config.get("mode", "paper") == "live":
            if not confirm_live_trading():
                logger.info("Live trading cancelled by user")
                sys.exit(0)
        else:
            logger.info("Using paper trading mode (default)")
    
    # Load portfolio trades
    logger.info("Loading portfolio trades...")
    trades = get_portfolio_trades()
    
    if not trades:
        logger.error("No trades to execute. Generate portfolio first with run_portfolio.py")
        sys.exit(1)
        
    logger.info(f"Loaded {len(trades)} trades from portfolio")
    
    # Load market data
    logger.info("Loading market data...")
    market_data = get_market_data(db)
    
    if market_data.empty:
        logger.error("No market data available for execution")
        sys.exit(1)
    
    # Load current portfolio
    logger.info("Loading current portfolio...")
    current_portfolio = get_current_portfolio(db)
    
    # Execute based on mode
    start_time = time.time()
    
    if args.dry_run:
        results = run_dry_execution(trades, market_data, current_portfolio, config)
        mode = "dry"
    else:
        results = run_live_execution(trades, market_data, current_portfolio, config)
        mode = "live"
    
    execution_time = time.time() - start_time
    
    # Generate and save report
    report_text = generate_execution_report(results, mode)
    print(report_text)
    save_execution_report(report_text, mode)
    
    logger.info(f"Execution completed in {execution_time:.1f} seconds")
    
    if mode == "live":
        # Generate cost report
        from execution.costs import get_cost_report
        cost_report = get_cost_report(30, config.get("execution", {}).get("costs", {}))
        
        logger.info("30-Day Execution Cost Summary:")
        logger.info(f"  Average Slippage: {cost_report['metrics']['avg_slippage_bps']:.2f} bps")
        logger.info(f"  Total Cost: ${cost_report['metrics']['total_dollar_cost']:,.2f}")
        logger.info(f"  Executions: {cost_report['metrics']['execution_count']}")

if __name__ == "__main__":
    main()
```

## Key Features to Implement

1. **Dual Mode Operation** - `--dry-run` for testing, `--execute` for live trading
2. **Safety Confirmations** - Explicit user confirmation required for live trading
3. **Portfolio Integration** - Load trades from Layer 4 portfolio optimization
4. **Market Data Utilization** - Use current prices for limit order calculation
5. **Comprehensive Logging** - Detailed execution logs for audit and analysis
6. **Error Handling** - Graceful degradation when components fail
7. **Reporting** - Human-readable execution reports with cost analysis
8. **Configuration Driven** - All settings managed through config.yaml

## Command Line Interface

```bash
# Dry run mode (recommended for testing)
python run_execution.py --dry-run

# Live execution (with safety confirmation)
python run_execution.py --execute

# Custom portfolio file
python run_execution.py --dry-run --portfolio-file my_portfolio.csv

# Help
python run_execution.py --help
```

## Integration Points

- Loads portfolio trades from Layer 4 output
- Uses all execution components (broker, executor, costs, short check, order manager)
- Integrates with database for market data and portfolio state
- Works with configuration system for all settings
- Generates comprehensive execution reports for analysis