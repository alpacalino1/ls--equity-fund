# Position Attribution Template

This is a template for the position_attribution.py implementation that will handle position tracking and analysis.

## Planned Implementation

```python
"""
Meridian Capital Partners · reporting/position_attribution.py
─────────────────────────────────────────────────────────────────
Position attribution: mark-to-market, FIFO round-trips, performance analysis.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json

logger = logging.getLogger("meridian.reporting.position_attribution")

class PositionAttribution:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize position attribution engine."""
        if config is None:
            config = {}
            
        self.config = config
        self.output_dir = Path("output/reporting")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Position attribution engine initialized")
        
    def analyze_positions(self, trades: List[Dict[str, Any]], 
                         market_data: pd.DataFrame,
                         current_positions: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Analyze portfolio positions with comprehensive metrics.
        
        Includes mark-to-market, FIFO round-trips, best/worst performers,
        and predictive power analysis.
        """
        logger.info(f"Analyzing {len(trades)} trades and positions")
        
        # 1. Mark-to-market current positions
        mtm_results = self._mark_to_market(current_positions, market_data)
        
        # 2. Calculate round-trip performance (FIFO)
        round_trip_results = self._calculate_round_trips(trades, market_data)
        
        # 3. Identify best/worst performers
        performance_results = self._analyze_performance(trades, market_data)
        
        # 4. Calculate predictive power (entry score vs realized return)
        predictive_results = self._calculate_predictive_power(trades, market_data)
        
        # Combine all results
        analysis_results = {
            'mark_to_market': mtm_results,
            'round_trips': round_trip_results,
            'performance': performance_results,
            'predictive_power': predictive_results,
            'timestamp': datetime.now().isoformat()
        }
        
        # Save results
        self._save_analysis(analysis_results)
        
        return analysis_results
        
    def _mark_to_market(self, positions: pd.DataFrame, 
                       market_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate mark-to-market values for current positions.
        """
        if positions is None or positions.empty:
            return {'total_value': 0, 'positions': []}
            
        mtm_positions = []
        total_value = 0
        
        for _, position in positions.iterrows():
            ticker = position['ticker']
            quantity = abs(position['quantity']) if 'quantity' in position else 0
            side = position.get('side', 'long')
            
            # Get current market price
            ticker_data = market_data[market_data['ticker'] == ticker]
            if ticker_data.empty:
                current_price = 0
                logger.warning(f"No market data for {ticker} MTM")
            else:
                current_price = ticker_data['close'].iloc[0]
                
            # Calculate position value
            position_value = quantity * current_price
            total_value += position_value
            
            mtm_positions.append({
                'ticker': ticker,
                'quantity': quantity,
                'side': side,
                'current_price': current_price,
                'position_value': position_value,
                'weight': position.get('weight', 0)
            })
            
        # Sort by position value
        mtm_positions.sort(key=lambda x: x['position_value'], reverse=True)
        
        return {
            'total_value': total_value,
            'positions': mtm_positions,
            'as_of_date': datetime.now().strftime('%Y-%m-%d')
        }
        
    def _calculate_round_trips(self, trades: List[Dict[str, Any]], 
                              market_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate round-trip performance using FIFO methodology.
        """
        # This would implement full FIFO accounting for:
        # - Matching buys and sells
        - Calculating P&L per round-trip
        - Tracking holding periods
        - Calculating returns per trade
        
        # Simplified implementation for template
       _fifo_trades = []
        for trade in trades:
            ticker = trade['ticker']
            side = trade['side']
            quantity = trade['quantity']
            
            # Get entry price from trade data or market data
            entry_price = trade.get('price', 0) or self._get_price_for_date(
                ticker, trade.get('date'), market_data
            )
            
            # For exits, calculate performance
            if side in ['sell', 'cover']:
                # Would match with corresponding entry trades
                exit_price = entry_price  # Simplified
                pl = (exit_price - entry_price) * quantity
                return_pct = (exit_price / entry_price - 1) if entry_price > 0 else 0
                
                _fifo_trades.append({
                    'ticker': ticker,
                    'entry_date': trade.get('entry_date', 'N/A'),
                    'exit_date': trade.get('date', 'N/A'),
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'quantity': quantity,
                    'pnl': pl,
                    'return_pct': return_pct,
                    'holding_period': trade.get('holding_days', 0)
                })
                
        # Calculate summary statistics
        if _fifo_trades:
            returns = [t['return_pct'] for t in _fifo_trades if t['return_pct'] is not None]
            if returns:
                avg_return = np.mean(returns)
                win_rate = len([r for r in returns if r > 0]) / len(returns)
            else:
                avg_return = 0
                win_rate = 0
        else:
            avg_return = 0
            win_rate = 0
            
        return {
            'round_trips': _fifo_trades,
            'total_round_trips': len(_fifo_trades),
            'average_return': avg_return,
            'win_rate': win_rate,
            'total_pnl': sum(t['pnl'] for t in _fifo_trades)
        }
        
    def _analyze_performance(self, trades: List[Dict[str, Any]], 
                           market_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Identify best and worst performing positions by side.
        """
        # Separate long and short trades
        long_trades = [t for t in trades if t['side'] in ['buy', 'long']]
        short_trades = [t for t in trades if t['side'] in ['sell', 'short']]
        
        # Calculate performance for each
        def _calc_side_performance(side_trades, side_name):
            performances = []
            for trade in side_trades:
                ticker = trade['ticker']
                entry_price = trade.get('price', 0) or self._get_price_for_date(
                    ticker, trade.get('date'), market_data
                )
                
                # Get current price or exit price
                current_data = market_data[market_data['ticker'] == ticker]
                if not current_data.empty:
                    current_price = current_data['close'].iloc[0]
                    return_pct = (current_price / entry_price - 1) if entry_price > 0 else 0
                else:
                    return_pct = 0
                    
                performances.append({
                    'ticker': ticker,
                    'entry_price': entry_price,
                    'current_price': current_price,
                    'return_pct': return_pct,
                    'quantity': trade['quantity']
                })
                
            # Sort by return
            performances.sort(key=lambda x: x['return_pct'], reverse=True)
            
            return {
                'best': performances[:5],  # Top 5
                'worst': performances[-5:] if len(performances) >= 5 else performances[::-1][:5],
                'average_return': np.mean([p['return_pct'] for p in performances]) if performances else 0
            }
            
        return {
            'long_performance': _calc_side_performance(long_trades, 'long'),
            'short_performance': _calc_side_performance(short_trades, 'short')
        }
        
    def _calculate_predictive_power(self, trades: List[Dict[str, Any]], 
                                   market_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate Spearman correlation between entry-time score and realized return.
        """
        # This would require:
        # 1. Entry scores from factor system (from Layer 2)
        # 2. Realized returns from trade execution (from Layer 6)
        # 3. Correlation analysis between the two
        
        # Simplified implementation for template
        correlations = {}
        
        # Example: correlation for different factor scores vs returns
        factor_types = ['momentum', 'value', 'quality', 'composite']
        
        for factor_type in factor_types:
            # Would extract factor scores and realized returns
            scores = []  # Factor scores at entry
            returns = []  # Realized returns
            
            # Calculate Spearman correlation
            if scores and returns and len(scores) == len(returns):
                from scipy.stats import spearmanr
                try:
                    corr, p_value = spearmanr(scores, returns)
                    correlations[factor_type] = {
                        'correlation': corr,
                        'p_value': p_value,
                        'sample_size': len(scores)
                    }
                except Exception as e:
                    correlations[factor_type] = {
                        'correlation': 0,
                        'p_value': 1,
                        'sample_size': 0,
                        'error': str(e)
                    }
            else:
                correlations[factor_type] = {
                    'correlation': 0,
                    'p_value': 1,
                    'sample_size': 0
                }
                
        return {
            'predictive_correlations': correlations,
            'overall_predictive_power': np.mean([v['correlation'] for v in correlations.values() if 'correlation' in v])
        }
        
    def _get_price_for_date(self, ticker: str, date: str, 
                           market_data: pd.DataFrame) -> float:
        """
        Get price for specific ticker and date from market data.
        """
        if not date or ticker not in market_data['ticker'].values:
            return 0
            
        ticker_data = market_data[market_data['ticker'] == ticker]
        if ticker_data.empty:
            return 0
            
        # Find closest date
        date_matches = ticker_data[ticker_data['date'] == date]
        if not date_matches.empty:
            return date_matches['close'].iloc[0]
            
        # Return latest available price
        return ticker_data['close'].iloc[-1] if not ticker_data.empty else 0
        
    def _save_analysis(self, analysis_results: Dict[str, Any]):
        """Save position analysis results to file."""
        try:
            output_file = self.output_dir / "position_analysis.json"
            with open(output_file, 'w') as f:
                json.dump(analysis_results, f, indent=2, default=str)
            logger.info(f"Position analysis saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save position analysis: {e}")
            
    def generate_position_report(self, analysis_results: Dict[str, Any]) -> str:
        """
        Generate human-readable position analysis report.
        """
        report_lines = [
            "MERIDIAN CAPITAL PARTNERS - POSITION ANALYSIS REPORT",
            "=" * 60,
            f"Generated: {analysis_results.get('timestamp', 'N/A')}",
            ""
        ]
        
        # Mark-to-Market Summary
        mtm = analysis_results.get('mark_to_market', {})
        report_lines.extend([
            "MARK-TO-MARKET SUMMARY",
            "-" * 30,
            f"Total Portfolio Value: ${mtm.get('total_value', 0):,.2f}",
            f"As of Date: {mtm.get('as_of_date', 'N/A')}",
            ""
        ])
        
        # Top 5 Positions
        positions = mtm.get('positions', [])[:5]
        if positions:
            report_lines.append("TOP 5 POSITIONS BY VALUE:")
            report_lines.append("Ticker    Quantity    Price    Value        Weight")
            report_lines.append("-" * 55)
            for pos in positions:
                report_lines.append(
                    f"{pos['ticker']:<8} {pos['quantity']:>8.0f} "
                    f"${pos['current_price']:>7.2f} ${pos['position_value']:>10.2f} "
                    f"{pos['weight']:>7.2%}"
                )
            report_lines.append("")
            
        # Round Trip Performance
        round_trips = analysis_results.get('round_trips', {})
        report_lines.extend([
            "ROUND-TRIP PERFORMANCE",
            "-" * 30,
            f"Total Round Trips: {round_trips.get('total_round_trips', 0)}",
            f"Average Return: {round_trips.get('average_return', 0):.2%}",
            f"Win Rate: {round_trips.get('win_rate', 0):.2%}",
            f"Total P&L: ${round_trips.get('total_pnl', 0):,.2f}",
            ""
        ])
        
        # Performance by Side
        perf = analysis_results.get('performance', {})
        long_perf = perf.get('long_performance', {})
        short_perf = perf.get('short_performance', {})
        
        report_lines.extend([
            "PERFORMANCE BY SIDE",
            "-" * 30,
            f"Long Avg Return: {long_perf.get('average_return', 0):.2%}",
            f"Short Avg Return: {short_perf.get('average_return', 0):.2%}",
            ""
        ])
        
        # Predictive Power
        pred_power = analysis_results.get('predictive_power', {})
        correlations = pred_power.get('predictive_correlations', {})
        
        report_lines.extend([
            "PREDICTIVE POWER ANALYSIS",
            "-" * 30,
            "Factor        Correlation  Sample Size",
            "-" * 40
        ])
        
        for factor, stats in correlations.items():
            corr = stats.get('correlation', 0)
            sample_size = stats.get('sample_size', 0)
            report_lines.append(f"{factor:<12} {corr:>11.3f}  {sample_size:>11}")
            
        overall_pred = pred_power.get('overall_predictive_power', 0)
        report_lines.extend([
            f"Overall Predictive Power: {overall_pred:.3f}",
            ""
        ])
        
        return "\n".join(report_lines)

# Convenience function
def analyze_portfolio_positions(trades: List[Dict[str, Any]], 
                               market_data: pd.DataFrame,
                               current_positions: pd.DataFrame = None,
                               config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Analyze portfolio positions with comprehensive metrics."""
    analyzer = PositionAttribution(config or {})
    return analyzer.analyze_positions(trades, market_data, current_positions)
```

## Key Features to Implement

1. **Mark-to-Market Valuation**: Current portfolio position values
2. **FIFO Round-Trip Accounting**: Complete buy/sell matching with P&L calculation
3. **Performance Ranking**: Best/worst performers by side (long/short)  
4. **Predictive Power Analysis**: Spearman correlation entry scores vs realized returns
5. **Comprehensive Reporting**: Detailed position-level analysis

## Integration Points

- Uses trade data from Layer 6 execution
- Integrates market data for current pricing
- Works with portfolio data from Layer 4
- Feeds dashboard and tear sheet generators
- Supports factor score correlation analysis