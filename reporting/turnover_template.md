# Turnover Analytics Template

This is a template for the turnover.py implementation that will handle portfolio turnover analysis and tax estimation.

## Planned Implementation

```python
"""
Meridian Capital Partners · reporting/turnover.py
─────────────────────────────────────────────────────────────────
Turnover analytics: trailing turnover rates, tax estimation via FIFO.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json

logger = logging.getLogger("meridian.reporting.turnover")

class TurnoverAnalytics:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize turnover analytics engine."""
        if config is None:
            config = {}
            
        self.config = config
        self.turnover_periods = config.get("turnover_periods", [30, 90])
        self.tax_rates = config.get("tax_rates", {
            'short_term': 0.37,  # 37% for holdings < 1 year
            'long_term': 0.20    # 20% for holdings >= 1 year
        })
        self.output_dir = Path("output/reporting")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Turnover analytics engine initialized")
        
    def analyze_turnover(self, trades: List[Dict[str, Any]], 
                        portfolio_history: List[Dict[str, Any]],
                        market_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze portfolio turnover and estimate tax implications.
        
        Calculates:
        - Trailing 30/90-day turnover rates
        - Annualized turnover vs budget
        - Tax estimation via FIFO accounting
        - Short-term vs long-term gain breakdown
        """
        logger.info(f"Analyzing turnover for {len(trades)} trades")
        
        # 1. Calculate trailing turnover rates
        turnover_rates = self._calculate_turnover_rates(trades, portfolio_history)
        
        # 2. Calculate tax implications (FIFO)
        tax_analysis = self._calculate_tax_implications(trades, market_data)
        
        # 3. Compare vs turnover budget
        budget_comparison = self._compare_vs_budget(turnover_rates)
        
        # Combine all results
        analysis_results = {
            'turnover_rates': turnover_rates,
            'tax_analysis': tax_analysis,
            'budget_comparison': budget_comparison,
            'total_trades': len(trades),
            'analysis_date': datetime.now().isoformat()
        }
        
        # Save results
        self._save_analysis(analysis_results)
        
        return analysis_results
        
    def _calculate_turnover_rates(self, trades: List[Dict[str, Any]], 
                                 portfolio_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate trailing turnover rates for specified periods.
        Turnover = (Total trades value / Average AUM) * (Period adjustment)
        """
        if not trades:
            return {period: {'rate': 0, 'annualized': 0} for period in self.turnover_periods}
            
        # Convert trades to DataFrame
        trades_df = pd.DataFrame(trades)
        
        # Get date range for analysis
        latest_date = datetime.now()
        turnover_data = {}
        
        for period in self.turnover_periods:
            # Calculate period start date
            period_start = latest_date - timedelta(days=period)
            
            # Filter trades in period
            period_trades = [
                trade for trade in trades 
                if pd.to_datetime(trade.get('date', latest_date)) >= period_start
            ]
            
            if not period_trades:
                turnover_data[period] = {
                    'rate': 0,
                    'annualized': 0,
                    'trade_count': 0,
                    'total_value': 0
                }
                continue
                
            # Calculate total trade value
            total_value = sum(
                abs(trade.get('quantity', 0) * trade.get('price', 0) 
                    if trade.get('price') else 0)
                for trade in period_trades
            )
            
            # Estimate average AUM (would come from portfolio history)
            avg_aum = self._estimate_average_aum(portfolio_history, period_start, latest_date)
            
            # Calculate turnover rate
            if avg_aum > 0:
                turnover_rate = total_value / avg_aum
                annualized_rate = turnover_rate * (365 / period)
            else:
                turnover_rate = 0
                annualized_rate = 0
                
            turnover_data[period] = {
                'rate': turnover_rate,
                'annualized': annualized_rate,
                'trade_count': len(period_trades),
                'total_value': total_value,
                'avg_aum': avg_aum
            }
            
        return turnover_data
        
    def _calculate_tax_implications(self, trades: List[Dict[str, Any]], 
                                   market_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate tax implications using FIFO accounting.
        
        Tax rates:
        - Short-term gains (< 1 year): 37%
        - Long-term gains (>= 1 year): 20%
        """
        if not trades:
            return {
                'short_term_gains': 0,
                'long_term_gains': 0,
                'short_term_tax': 0,
                'long_term_tax': 0,
                'total_tax_impact': 0,
                'effective_tax_rate': 0
            }
            
        # This would implement full FIFO accounting:
        # 1. Track all positions with purchase dates/prices
        # 2. Match sells with earliest purchases (FIFO)
        # 3. Calculate holding periods for each sale
        # 4. Apply appropriate tax rates
        # 5. Sum tax implications
        
        # Simplified implementation for template
        short_term_gains = 0
        long_term_gains = 0
        
        # Example calculation (would be replaced with real FIFO logic)
        for trade in trades:
            if trade['side'] in ['sell', 'cover']:  # Closing positions
                # Would calculate actual gains based on FIFO matching
                # For now, assume mixed short/long term gains
                gain_amount = abs(trade.get('quantity', 0) * (trade.get('price', 0) - trade.get('entry_price', 0)))
                short_term_gains += gain_amount * 0.6  # Assumed split
                long_term_gains += gain_amount * 0.4
                
        # Calculate tax amounts
        short_term_tax = short_term_gains * self.tax_rates['short_term']
        long_term_tax = long_term_gains * self.tax_rates['long_term']
        total_tax = short_term_tax + long_term_tax
        
        # Calculate effective tax rate
        total_gains = short_term_gains + long_term_gains
        effective_tax_rate = total_tax / total_gains if total_gains > 0 else 0
        
        return {
            'short_term_gains': short_term_gains,
            'long_term_gains': long_term_gains,
            'short_term_tax': short_term_tax,
            'long_term_tax': long_term_tax,
            'total_tax_impact': total_tax,
            'effective_tax_rate': effective_tax_rate,
            'total_realized_gains': total_gains
        }
        
    def _compare_vs_budget(self, turnover_rates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare turnover rates vs configured budget.
        """
        budget = self.config.get("turnover_budget", 1.0)  # Default 100% annual turnover
        comparison = {}
        
        for period, data in turnover_rates.items():
            actual_annualized = data.get('annualized', 0)
            vs_budget = actual_annualized / budget if budget > 0 else 0
            
            comparison[period] = {
                'actual': actual_annualized,
                'budget': budget,
                'vs_budget': vs_budget,
                'status': 'Under Budget' if vs_budget < 1 else 'Over Budget' if vs_budget > 1 else 'On Budget'
            }
            
        return comparison
        
    def _estimate_average_aum(self, portfolio_history: List[Dict[str, Any]], 
                              start_date: datetime, end_date: datetime) -> float:
        """
        Estimate average assets under management for turnover calculation.
        """
        # Filter history to period
        period_history = [
            record for record in portfolio_history
            if start_date <= pd.to_datetime(record.get('date', datetime.now())) <= end_date
        ]
        
        if not period_history:
            return 1_000_000  # Default $1M AUM assumption
            
        # Calculate average of portfolio values
        values = [record.get('portfolio_value', 1_000_000) for record in period_history]
        return np.mean(values) if values else 1_000_000
        
    def _save_analysis(self, analysis_results: Dict[str, Any]):
        """Save turnover analysis results to file."""
        try:
            output_file = self.output_dir / "turnover_analysis.json"
            with open(output_file, 'w') as f:
                json.dump(analysis_results, f, indent=2, default=str)
            logger.info(f"Turnover analysis saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save turnover analysis: {e}")
            
    def generate_turnover_report(self, analysis_results: Dict[str, Any]) -> str:
        """
        Generate human-readable turnover analysis report.
        """
        report_lines = [
            "MERIDIAN CAPITAL PARTNERS - TURNOVER ANALYSIS REPORT",
            "=" * 60,
            f"Generated: {analysis_results.get('analysis_date', 'N/A')}",
            f"Total Trades Analyzed: {analysis_results.get('total_trades', 0)}",
            ""
        ]
        
        # Turnover Rates
        turnover_rates = analysis_results.get('turnover_rates', {})
        if turnover_rates:
            report_lines.extend([
                "TURNOVER RATES",
                "-" * 30,
                "Period   Turnover   Annualized   Trades   Value",
                "-" * 55
            ])
            
            for period, data in turnover_rates.items():
                rate = data.get('rate', 0)
                annualized = data.get('annualized', 0)
                trades = data.get('trade_count', 0)
                value = data.get('total_value', 0)
                
                report_lines.append(
                    f"{period:>6}d {rate:>9.2%}  {annualized:>10.2%}  "
                    f"{trades:>6}  ${value:>10,.0f}"
                )
            report_lines.append("")
            
        # Budget Comparison
        budget_comparison = analysis_results.get('budget_comparison', {})
        if budget_comparison:
            report_lines.extend([
                "BUDGET COMPARISON",
                "-" * 30,
                "Period   Actual    Budget    vs Budget   Status",
                "-" * 50
            ])
            
            for period, data in budget_comparison.items():
                actual = data.get('actual', 0)
                budget = data.get('budget', 0)
                vs_budget = data.get('vs_budget', 0)
                status = data.get('status', '')
                
                report_lines.append(
                    f"{period:>6}d {actual:>7.2%}  {budget:>7.2%}  "
                    f"{vs_budget:>10.2f}x   {status}"
                )
            report_lines.append("")
            
        # Tax Analysis
        tax_analysis = analysis_results.get('tax_analysis', {})
        if tax_analysis:
            short_term_gains = tax_analysis.get('short_term_gains', 0)
            long_term_gains = tax_analysis.get('long_term_gains', 0)
            short_term_tax = tax_analysis.get('short_term_tax', 0)
            long_term_tax = tax_analysis.get('long_term_tax', 0)
            total_tax = tax_analysis.get('total_tax_impact', 0)
            effective_rate = tax_analysis.get('effective_tax_rate', 0)
            total_gains = tax_analysis.get('total_realized_gains', 0)
            
            report_lines.extend([
                "TAX ANALYSIS (FIFO)",
                "-" * 30,
                f"Short-term Gains: ${short_term_gains:,.0f} (@ {self.tax_rates['short_term']:.0%})",
                f"Long-term Gains:  ${long_term_gains:,.0f} (@ {self.tax_rates['long_term']:.0%})",
                f"Short-term Tax:   ${short_term_tax:,.0f}",
                f"Long-term Tax:    ${long_term_tax:,.0f}",
                f"Total Tax Impact: ${total_tax:,.0f}",
                f"Effective Tax Rate: {effective_rate:.1%}",
                f"Total Realized Gains: ${total_gains:,.0f}",
                ""
            ])
            
        return "\n".join(report_lines)

# Convenience function
def analyze_turnover(trades: List[Dict[str, Any]], 
                     portfolio_history: List[Dict[str, Any]],
                     market_data: pd.DataFrame,
                     config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Analyze portfolio turnover and tax implications."""
    analyzer = TurnoverAnalytics(config or {})
    return analyzer.analyze_turnover(trades, portfolio_history, market_data)
```

## Key Features to Implement

1. **Trailing Turnover Calculation**: 30/90-day turnover rates with annualization
2. **Budget Comparison**: Actual vs configured turnover targets
3. **FIFO Tax Accounting**: Detailed tax estimation with short/long-term distinction
4. **Comprehensive Reporting**: Multi-period analysis with status indicators
5. **Configurable Parameters**: Custom periods, tax rates, and budgets

## Integration Points

- Uses trade execution data from Layer 6
- Consumes portfolio history from database
- Works with market data for accurate pricing
- Feeds dashboard and tear sheet generators
- Supports compliance and tax reporting
- Integrates with P&L attribution analysis