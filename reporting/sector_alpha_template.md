# Sector-Relative Performance Template

This is a template for the sector_alpha.py implementation that will handle sector-relative performance analysis.

## Planned Implementation

```python
"""
Meridian Capital Partners · reporting/sector_alpha.py
─────────────────────────────────────────────────────────────────
Sector-relative performance: per-sector alpha vs sector ETFs.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json

logger = logging.getLogger("meridian.reporting.sector_alpha")

class SectorAlphaAnalysis:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize sector alpha analysis engine."""
        if config is None:
            config = {}
            
        self.config = config
        self.lookback_days = config.get("lookback_days", 90)
        self.sector_etfs = config.get("sector_etfs", {
            'Information Technology': 'XLK',
            'Financials': 'XLF',
            'Health Care': 'XLV',
            'Energy': 'XLE',
            'Industrials': 'XLI',
            'Communication Services': 'XLC',
            'Consumer Discretionary': 'XLY',
            'Consumer Staples': 'XLP',
            'Materials': 'XLB',
            'Real Estate': 'XLRE',
            'Utilities': 'XLU'
        })
        self.output_dir = Path("output/reporting")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Sector alpha analysis engine initialized")
        
    def analyze_sector_alpha(self, portfolio_positions: pd.DataFrame,
                            market_data: pd.DataFrame,
                            sector_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze sector-relative performance to calculate stock-selection alpha.
        
        For each sector:
        - Calculate 90-day performance of portfolio holdings
        - Compare vs corresponding sector ETF performance
        - Calculate stock-selection alpha (portfolio - sector ETF)
        - Track winner/loser sector counts
        """
        logger.info("Analyzing sector-relative performance")
        
        if portfolio_positions.empty or sector_data.empty:
            logger.warning("Empty portfolio or sector data for alpha analysis")
            return self._create_empty_analysis()
            
        # 1. Calculate per-sector performance
        sector_performance = self._calculate_sector_performance(
            portfolio_positions, market_data, sector_data
        )
        
        # 2. Calculate sector ETF performance
        etf_performance = self._calculate_etf_performance(market_data)
        
        # 3. Calculate sector alpha (stock-selection alpha)
        sector_alpha = self._calculate_sector_alpha(sector_performance, etf_performance)
        
        # 4. Count winner/loser sectors
        sector_counts = self._count_sector_performance(sector_alpha)
        
        # 5. Calculate total alpha across sectors
        total_alpha = self._calculate_total_alpha(sector_alpha)
        
        # Combine all results
        analysis_results = {
            'sector_performance': sector_performance,
            'etf_performance': etf_performance,
            'sector_alpha': sector_alpha,
            'sector_counts': sector_counts,
            'total_alpha': total_alpha,
            'analysis_period': f"{self.lookback_days} days",
            'analysis_date': datetime.now().isoformat()
        }
        
        # Save results
        self._save_analysis(analysis_results)
        
        return analysis_results
        
    def _calculate_sector_performance(self, portfolio_positions: pd.DataFrame,
                                     market_data: pd.DataFrame,
                                     sector_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate portfolio performance by sector.
        """
        # Merge portfolio positions with sector data
        portfolio_with_sector = portfolio_positions.merge(
            sector_data[['ticker', 'sector']], 
            on='ticker', 
            how='left'
        )
        
        # Group by sector and calculate weighted returns
        sector_returns = {}
        
        for sector in portfolio_with_sector['sector'].unique():
            sector_positions = portfolio_with_sector[
                portfolio_with_sector['sector'] == sector
            ]
            
            if sector_positions.empty:
                sector_returns[sector] = {
                    'return': 0,
                    'weight': 0,
                    'tickers': []
                }
                continue
                
            # Calculate sector-weighted return
            total_weight = sector_positions['weight'].abs().sum()
            if total_weight == 0:
                sector_return = 0
            else:
                # Get returns for each ticker in sector
                sector_tickers = sector_positions['ticker'].tolist()
                ticker_returns = self._get_ticker_returns(sector_tickers, market_data)
                
                # Calculate weighted average return
                weighted_returns = []
                for _, position in sector_positions.iterrows():
                    ticker = position['ticker']
                    weight = abs(position['weight']) / total_weight if total_weight > 0 else 0
                    ticker_return = ticker_returns.get(ticker, 0)
                    weighted_returns.append(weight * ticker_return)
                    
                sector_return = sum(weighted_returns)
                
            sector_returns[sector] = {
                'return': sector_return,
                'weight': total_weight,
                'tickers': sector_tickers,
                'position_count': len(sector_positions)
            }
            
        return sector_returns
        
    def _calculate_etf_performance(self, market_data: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate sector ETF performance over lookback period.
        """
        etf_returns = {}
        
        # Get date range for lookback period
        latest_date = pd.to_datetime(market_data['date'].max()) if not market_data.empty else datetime.now()
        start_date = latest_date - timedelta(days=self.lookback_days)
        
        for sector, etf_ticker in self.sector_etfs.items():
            # Get ETF price data
            etf_data = market_data[market_data['ticker'] == etf_ticker]
            
            if etf_data.empty:
                etf_returns[sector] = 0
                logger.warning(f"No data for sector ETF {etf_ticker}")
                continue
                
            # Filter to lookback period
            period_data = etf_data[
                pd.to_datetime(etf_data['date']) >= start_date
            ].sort_values('date')
            
            if len(period_data) < 2:
                etf_returns[sector] = 0
                continue
                
            # Calculate total return
            start_price = period_data['close'].iloc[0]
            end_price = period_data['close'].iloc[-1]
            total_return = (end_price / start_price - 1) if start_price > 0 else 0
            
            etf_returns[sector] = total_return
            
        return etf_returns
        
    def _calculate_sector_alpha(self, sector_performance: Dict[str, Any],
                               etf_performance: Dict[str, float]) -> Dict[str, Any]:
        """
        Calculate stock-selection alpha per sector.
        Alpha = Portfolio Sector Return - Sector ETF Return
        """
        sector_alpha = {}
        
        for sector, perf_data in sector_performance.items():
            portfolio_return = perf_data['return']
            etf_return = etf_performance.get(sector, 0)
            alpha = portfolio_return - etf_return
            
            sector_alpha[sector] = {
                'portfolio_return': portfolio_return,
                'etf_return': etf_return,
                'alpha': alpha,
                'sector_weight': perf_data['weight'],
                'position_count': perf_data['position_count'],
                'performance_vs_benchmark': 'Outperform' if alpha > 0 else 'Underperform'
            }
            
        return sector_alpha
        
    def _count_sector_performance(self, sector_alpha: Dict[str, Any]) -> Dict[str, int]:
        """
        Count winner and loser sectors.
        """
        winners = 0
        losers = 0
        neutral = 0
        
        for sector, alpha_data in sector_alpha.items():
            alpha = alpha_data['alpha']
            if alpha > 0.001:  # 10 bps threshold
                winners += 1
            elif alpha < -0.001:  # -10 bps threshold
                losers += 1
            else:
                neutral += 1
                
        return {
            'winners': winners,
            'losers': losers,
            'neutral': neutral,
            'total_sectors': len(sector_alpha)
        }
        
    def _calculate_total_alpha(self, sector_alpha: Dict[str, Any]) -> float:
        """
        Calculate total alpha across all sectors (weighted sum).
        """
        total_alpha = 0
        total_weight = sum(alpha_data['sector_weight'] for alpha_data in sector_alpha.values())
        
        if total_weight == 0:
            return 0
            
        for sector, alpha_data in sector_alpha.items():
            weight = alpha_data['sector_weight'] / total_weight if total_weight > 0 else 0
            alpha = alpha_data['alpha']
            total_alpha += weight * alpha
            
        return total_alpha
        
    def _get_ticker_returns(self, tickers: List[str], 
                           market_data: pd.DataFrame) -> Dict[str, float]:
        """
        Get total returns for list of tickers over lookback period.
        """
        returns = {}
        
        # Get date range for lookback period
        latest_date = pd.to_datetime(market_data['date'].max()) if not market_data.empty else datetime.now()
        start_date = latest_date - timedelta(days=self.lookback_days)
        
        for ticker in tickers:
            ticker_data = market_data[market_data['ticker'] == ticker]
            
            if ticker_data.empty:
                returns[ticker] = 0
                continue
                
            # Filter to lookback period
            period_data = ticker_data[
                pd.to_datetime(ticker_data['date']) >= start_date
            ].sort_values('date')
            
            if len(period_data) < 2:
                returns[ticker] = 0
                continue
                
            # Calculate total return
            start_price = period_data['close'].iloc[0]
            end_price = period_data['close'].iloc[-1]
            total_return = (end_price / start_price - 1) if start_price > 0 else 0
            
            returns[ticker] = total_return
            
        return returns
        
    def _create_empty_analysis(self) -> Dict[str, Any]:
        """Create empty analysis structure."""
        return {
            'sector_performance': {},
            'etf_performance': {},
            'sector_alpha': {},
            'sector_counts': {'winners': 0, 'losers': 0, 'neutral': 0, 'total_sectors': 0},
            'total_alpha': 0,
            'analysis_period': f"{self.lookback_days} days",
            'analysis_date': datetime.now().isoformat()
        }
        
    def _save_analysis(self, analysis_results: Dict[str, Any]):
        """Save sector alpha analysis results to file."""
        try:
            output_file = self.output_dir / "sector_alpha.json"
            with open(output_file, 'w') as f:
                json.dump(analysis_results, f, indent=2, default=str)
            logger.info(f"Sector alpha analysis saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save sector alpha analysis: {e}")
            
    def generate_sector_alpha_report(self, analysis_results: Dict[str, Any]) -> str:
        """
        Generate human-readable sector alpha analysis report.
        """
        report_lines = [
            "MERIDIAN CAPITAL PARTNERS - SECTOR ALPHA ANALYSIS REPORT",
            "=" * 65,
            f"Generated: {analysis_results.get('analysis_date', 'N/A')}",
            f"Analysis Period: {analysis_results.get('analysis_period', 'N/A')}",
            ""
        ]
        
        # Sector Alpha Analysis
        sector_alpha = analysis_results.get('sector_alpha', {})
        if sector_alpha:
            report_lines.extend([
                "SECTOR ALPHA ANALYSIS",
                "-" * 35,
                "Sector                  Portfolio   ETF Return   Alpha     Positions",
                "-" * 65
            ])
            
            # Sort by alpha descending
            sorted_sectors = sorted(
                sector_alpha.items(), 
                key=lambda x: x[1]['alpha'], 
                reverse=True
            )
            
            for sector, data in sorted_sectors:
                portfolio_return = data['portfolio_return']
                etf_return = data['etf_return']
                alpha = data['alpha']
                positions = data['position_count']
                perf_indicator = data['performance_vs_benchmark']
                
                report_lines.append(
                    f"{sector:<22} {portfolio_return:>9.2%}  {etf_return:>9.2%}  "
                    f"{alpha:>8.2%}  {positions:>9} ({perf_indicator})"
                )
                
            report_lines.append("")
            
        # Summary Statistics
        sector_counts = analysis_results.get('sector_counts', {})
        total_alpha = analysis_results.get('total_alpha', 0)
        
        report_lines.extend([
            "SUMMARY STATISTICS",
            "-" * 25,
            f"Total Alpha: {total_alpha:.2%}",
            f"Winning Sectors: {sector_counts.get('winners', 0)}",
            f"Losing Sectors: {sector_counts.get('losers', 0)}",
            f"Neutral Sectors: {sector_counts.get('neutral', 0)}",
            f"Total Sectors: {sector_counts.get('total_sectors', 0)}",
            ""
        ])
        
        # Top Contributors
        if sector_alpha:
            top_positive = sorted(
                [(s, d['alpha']) for s, d in sector_alpha.items() if d['alpha'] > 0],
                key=lambda x: x[1],
                reverse=True
            )[:3]
            
            top_negative = sorted(
                [(s, d['alpha']) for s, d in sector_alpha.items() if d['alpha'] < 0],
                key=lambda x: x[1]
            )[:3]
            
            if top_positive:
                report_lines.extend([
                    "TOP POSITIVE CONTRIBUTORS",
                    "-" * 30
                ])
                for sector, alpha in top_positive:
                    report_lines.append(f"{sector:<20} {alpha:>8.2%}")
                report_lines.append("")
                
            if top_negative:
                report_lines.extend([
                    "LARGEST NEGATIVE CONTRIBUTORS",
                    "-" * 35
                ])
                for sector, alpha in top_negative:
                    report_lines.append(f"{sector:<20} {alpha:>8.2%}")
                report_lines.append("")
                
        return "\n".join(report_lines)

# Convenience function
def analyze_sector_alpha(portfolio_positions: pd.DataFrame,
                         market_data: pd.DataFrame,
                         sector_data: pd.DataFrame,
                        config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Analyze sector-relative performance and calculate alpha."""
    analyzer = SectorAlphaAnalysis(config or {})
    return analyzer.analyze_sector_alpha(portfolio_positions, market_data, sector_data)
```

## Key Features to Implement

1. **Per-Sector Performance**: Calculate portfolio returns by sector
2. **Sector ETF Benchmarking**: Compare vs corresponding sector ETFs
3. **Stock Selection Alpha**: Measure alpha from security selection within sectors
4. **Winner/Loser Tracking**: Count outperforming vs underperforming sectors
5. **Total Alpha Calculation**: Aggregate performance across all sectors
6. **Comprehensive Reporting**: Detailed sector-level analysis

## Integration Points

- Uses portfolio positions from Layer 4
- Consumes market data for return calculations
- Works with sector data for grouping
- Integrates with sector ETF data
- Feeds dashboard and tear sheet generators
- Supports attribution analysis