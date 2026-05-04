# Tear Sheet Generator Template

This is a template for the tear_sheet.py implementation that will generate institutional-format performance reports.

## Planned Implementation

```python
"""
Meridian Capital Partners · reporting/tear_sheet.py
─────────────────────────────────────────────────────────────────
Institutional tear sheet generator: performance metrics, charts, analysis.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json

logger = logging.getLogger("meridian.reporting.tear_sheet")

class TearSheetGenerator:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize tear sheet generator."""
        if config is None:
            config = {}
            
        self.config = config
        self.output_dir = Path("output/reporting/tear_sheets")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Tear sheet generator initialized")
        
    def generate_tear_sheet(self, portfolio_data: Dict[str, Any],
                           market_data: pd.DataFrame,
                           benchmark_data: pd.DataFrame = None) -> str:
        """
        Generate comprehensive institutional-format tear sheet.
        
        Includes:
        - Performance metrics vs SPY
        - Monthly returns grid
        - Equity curve visualization data
        - Drawdown analysis
        - Rolling 12-month Sharpe ratio
        - Factor and sector exposures
        - Turnover statistics
        """
        logger.info("Generating institutional tear sheet")
        
        # 1. Calculate performance metrics vs benchmark
        performance_metrics = self._calculate_performance_metrics(
            portfolio_data, benchmark_data
        )
        
        # 2. Generate monthly returns grid
        monthly_grid = self._generate_monthly_returns_grid(portfolio_data)
        
        # 3. Calculate equity curve data
        equity_curve = self._calculate_equity_curve(portfolio_data)
        
        # 4. Analyze drawdowns
        drawdown_analysis = self._analyze_drawdowns(portfolio_data)
        
        # 5. Calculate rolling Sharpe ratios
        rolling_sharpe = self._calculate_rolling_sharpe(portfolio_data)
        
        # 6. Analyze factor and sector exposures
        exposures = self._analyze_exposures(portfolio_data)
        
        # 7. Include turnover statistics
        turnover_stats = self._get_turnover_statistics()
        
        # Combine all components
        tear_sheet_data = {
            'performance_metrics': performance_metrics,
            'monthly_returns_grid': monthly_grid,
            'equity_curve': equity_curve,
            'drawdown_analysis': drawdown_analysis,
            'rolling_sharpe': rolling_sharpe,
            'exposures': exposures,
            'turnover_stats': turnover_stats,
            'generated_date': datetime.now().isoformat(),
            'period': self._get_analysis_period(portfolio_data)
        }
        
        # Generate formatted report
        report_content = self._format_tear_sheet(tear_sheet_data)
        
        # Save report
        filename = self._save_tear_sheet(report_content)
        
        return filename
        
    def _calculate_performance_metrics(self, portfolio_data: Dict[str, Any],
                                     benchmark_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate key performance metrics vs benchmark.
        """
        # Extract portfolio returns
        portfolio_returns = portfolio_data.get('returns', pd.Series())
        
        if portfolio_returns.empty:
            return {}
            
        # Calculate metrics
        total_return = (1 + portfolio_returns).prod() - 1
        annualized_return = (1 + total_return) ** (252 / len(portfolio_returns)) - 1
        volatility = portfolio_returns.std() * np.sqrt(252)
        sharpe_ratio = annualized_return / volatility if volatility > 0 else 0
        max_drawdown = self._calculate_max_drawdown(portfolio_returns)
        calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown < 0 else 0
        skewness = portfolio_returns.skew()
        kurtosis = portfolio_returns.kurtosis()
        
        # Benchmark comparison (if available)
        benchmark_metrics = {}
        if benchmark_data is not None and not benchmark_data.empty:
            benchmark_returns = benchmark_data['return'] if 'return' in benchmark_data.columns else pd.Series()
            if not benchmark_returns.empty:
                bench_total_return = (1 + benchmark_returns).prod() - 1
                bench_annualized = (1 + bench_total_return) ** (252 / len(benchmark_returns)) - 1
                bench_volatility = benchmark_returns.std() * np.sqrt(252)
                bench_sharpe = bench_annualized / bench_volatility if bench_volatility > 0 else 0
                
                benchmark_metrics = {
                    'total_return': bench_total_return,
                    'annualized_return': bench_annualized,
                    'volatility': bench_volatility,
                    'sharpe_ratio': bench_sharpe
                }
                
                # Relative metrics
                alpha = annualized_return - bench_annualized
                tracking_error = (portfolio_returns - benchmark_returns).std() * np.sqrt(252)
                information_ratio = alpha / tracking_error if tracking_error > 0 else 0
                
                benchmark_metrics.update({
                    'alpha': alpha,
                    'tracking_error': tracking_error,
                    'information_ratio': information_ratio
                })
        
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'calmar_ratio': calmar_ratio,
            'skewness': skewness,
            'kurtosis': kurtosis,
            'benchmark': benchmark_metrics,
            'total_days': len(portfolio_returns)
        }
        
    def _generate_monthly_returns_grid(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate monthly returns grid for institutional presentation.
        """
        portfolio_returns = portfolio_data.get('returns', pd.Series())
        
        if portfolio_returns.empty:
            return {}
            
        # Convert to DataFrame with dates
        returns_df = pd.DataFrame({
            'date': portfolio_returns.index,
            'return': portfolio_returns.values
        })
        returns_df['date'] = pd.to_datetime(returns_df['date'])
        
        # Group by year-month
        returns_df['year'] = returns_df['date'].dt.year
        returns_df['month'] = returns_df['date'].dt.month
        
        monthly_returns = returns_df.groupby(['year', 'month'])['return'].apply(
            lambda x: (1 + x).prod() - 1
        ).reset_index()
        
        # Pivot to create grid
        monthly_grid = monthly_returns.pivot(index='year', columns='month', values='return')
        
        # Add summary statistics
        yearly_returns = monthly_returns.groupby('year')['return'].apply(
            lambda x: (1 + x).prod() - 1
        )
        
        return {
            'monthly_grid': monthly_grid.to_dict() if not monthly_grid.empty else {},
            'yearly_returns': yearly_returns.to_dict(),
            'best_month': monthly_returns['return'].max(),
            'worst_month': monthly_returns['return'].min(),
            'avg_monthly_return': monthly_returns['return'].mean()
        }
        
    def _calculate_equity_curve(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate equity curve data for visualization.
        """
        portfolio_returns = portfolio_data.get('returns', pd.Series())
        
        if portfolio_returns.empty:
            return {}
            
        # Calculate cumulative returns
        cumulative_returns = (1 + portfolio_returns).cumprod()
        
        # Calculate running metrics
        running_volatility = portfolio_returns.rolling(window=21).std() * np.sqrt(252)  # 21-day rolling annualized vol
        running_sharpe = (portfolio_returns.rolling(window=21).mean() * 252) / running_volatility
        
        return {
            'dates': portfolio_returns.index.tolist(),
            'cumulative_returns': cumulative_returns.tolist(),
            'running_volatility': running_volatility.tolist(),
            'running_sharpe': running_sharpe.tolist(),
            'current_value': cumulative_returns.iloc[-1] if not cumulative_returns.empty else 1
        }
        
    def _analyze_drawdowns(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze drawdown characteristics.
        """
        portfolio_returns = portfolio_data.get('returns', pd.Series())
        
        if portfolio_returns.empty:
            return {}
            
        # Calculate cumulative wealth
        cumulative_wealth = (1 + portfolio_returns).cumprod()
        
        # Calculate running maximum
        running_max = cumulative_wealth.expanding().max()
        
        # Calculate drawdowns
        drawdowns = (cumulative_wealth - running_max) / running_max
        
        max_drawdown = drawdowns.min()
        max_drawdown_date = drawdowns.idxmin()
        
        # Calculate drawdown duration
        in_drawdown = drawdowns < 0
        drawdown_periods = []
        
        if not in_drawdown.empty:
            # Find drawdown periods
            start_idx = None
            for i, is_dd in enumerate(in_drawdown):
                if is_dd and start_idx is None:
                    start_idx = i
                elif not is_dd and start_idx is not None:
                    drawdown_periods.append((start_idx, i-1))
                    start_idx = None
                    
            # Handle ongoing drawdown
            if start_idx is not None:
                drawdown_periods.append((start_idx, len(in_drawdown)-1))
                
        avg_drawdown = drawdowns[drawdowns < 0].mean() if len(drawdowns[drawdowns < 0]) > 0 else 0
        drawdown_duration = len([dd for dd in drawdowns if dd < 0])
        
        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_date': str(max_drawdown_date) if pd.notnull(max_drawdown_date) else '',
            'avg_drawdown': avg_drawdown,
            'drawdown_duration_days': drawdown_duration,
            'recovery_time': 0,  # Would calculate actual recovery time
            'drawdown_periods': len(drawdown_periods)
        }
        
    def _calculate_rolling_sharpe(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate rolling 12-month Sharpe ratios.
        """
        portfolio_returns = portfolio_data.get('returns', pd.Series())
        
        if portfolio_returns.empty:
            return {}
            
        # Calculate 252-day (12-month) rolling Sharpe
        rolling_window = min(252, len(portfolio_returns))
        
        rolling_mean = portfolio_returns.rolling(window=rolling_window).mean() * 252
        rolling_vol = portfolio_returns.rolling(window=rolling_window).std() * np.sqrt(252)
        rolling_sharpe = rolling_mean / rolling_vol
        
        return {
            'current_12m_sharpe': rolling_sharpe.iloc[-1] if not rolling_sharpe.empty else 0,
            'avg_12m_sharpe': rolling_sharpe.mean(),
            'max_12m_sharpe': rolling_sharpe.max(),
            'min_12m_sharpe': rolling_sharpe.min(),
            'sharpe_volatility': rolling_sharpe.std()
        }
        
    def _analyze_exposures(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze factor and sector exposures.
        """
        # This would integrate with factor data from Layer 2 and sector data
        # For template, return basic structure
        
        return {
            'factor_exposures': {
                'momentum': 0.15,
                'value': 0.12,
                'quality': 0.18,
                'growth': 0.10,
                'size': -0.05,
                'volatility': 0.02
            },
            'sector_exposures': {
                'Technology': 0.25,
                'Financials': 0.15,
                'Healthcare': 0.12,
                'Consumer_Discretionary': 0.10,
                'Industrials': 0.08,
                'Energy': 0.07,
                'Utilities': 0.06,
                'Materials': 0.05,
                'Real_Estate': 0.04,
                'Consumer_Staples': 0.04,
                'Communications': 0.04
            },
            'net_beta': 0.95,
            'gross_exposure': 1.85,
            'net_exposure': 0.12
        }
        
    def _get_turnover_statistics(self) -> Dict[str, Any]:
        """
        Get turnover statistics from turnover analysis.
        """
        # This would integrate with turnover.py results
        # For template, return basic structure
        
        return {
            'current_30d_turnover': 0.15,
            'current_90d_turnover': 0.35,
            'annualized_turnover': 1.25,
            'turnover_budget': 1.00,
            'vs_budget': 1.25,
            'status': 'Above Budget'
        }
        
    def _calculate_max_drawdown(self, returns: pd.Series) -> float:
        """Calculate maximum drawdown from returns series."""
        if returns.empty:
            return 0
            
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdowns = (cumulative - running_max) / running_max
        return drawdowns.min()
        
    def _get_analysis_period(self, portfolio_data: Dict[str, Any]) -> str:
        """Get analysis period string."""
        portfolio_returns = portfolio_data.get('returns', pd.Series())
        
        if portfolio_returns.empty:
            return "N/A"
            
        start_date = portfolio_returns.index.min()
        end_date = portfolio_returns.index.max()
        
        return f"{start_date} to {end_date}"
        
    def _format_tear_sheet(self, tear_sheet_data: Dict[str, Any]) -> str:
        """
        Format tear sheet data into institutional presentation.
        """
        lines = []
        
        # Header
        lines.extend([
            "MERIDIAN CAPITAL PARTNERS",
            "PORTFOLIO PERFORMANCE TEAR SHEET",
            "=" * 70,
            f"Generated: {tear_sheet_data.get('generated_date', 'N/A')[:10]}",
            f"Analysis Period: {tear_sheet_data.get('period', 'N/A')}",
            "",
            "PERFORMANCE METRICS",
            "-" * 30
        ])
        
        # Performance Metrics
        metrics = tear_sheet_data.get('performance_metrics', {})
        if metrics:
            lines.extend([
                f"Total Return:         {metrics.get('total_return', 0):.2%}",
                f"Annualized Return:    {metrics.get('annualized_return', 0):.2%}",
                f"Volatility:           {metrics.get('volatility', 0):.2%}",
                f"Sharpe Ratio:         {metrics.get('sharpe_ratio', 0):.2f}",
                f"Max Drawdown:         {metrics.get('max_drawdown', 0):.2%}",
                f"Calmar Ratio:         {metrics.get('calmar_ratio', 0):.2f}",
                f"Skewness:             {metrics.get('skewness', 0):.2f}",
                f"Kurtosis:             {metrics.get('kurtosis', 0):.2f}",
                ""
            ])
            
            # Benchmark comparison
            bench_metrics = metrics.get('benchmark', {})
            if bench_metrics:
                lines.extend([
                    "VS BENCHMARK (SPY)",
                    "-" * 20,
                    f"Alpha:                {bench_metrics.get('alpha', 0):.2%}",
                    f"Tracking Error:       {bench_metrics.get('tracking_error', 0):.2%}",
                    f"Information Ratio:    {bench_metrics.get('information_ratio', 0):.2f}",
                    ""
                ])
                
        # Monthly Returns Grid
        monthly_data = tear_sheet_data.get('monthly_returns_grid', {})
        if monthly_data:
            lines.extend([
                "MONTHLY RETURNS GRID (%)",
                "-" * 30
            ])
            
            # Would format monthly grid nicely
            lines.extend([
                "Year   Jan  Feb  Mar  Apr  May  Jun  Jul  Aug  Sep  Oct  Nov  Dec",
                "-" * 65
                # Format actual monthly data here
            ])
            
            lines.extend([
                f"Best Month:  {monthly_data.get('best_month', 0):.2%}",
                f"Worst Month: {monthly_data.get('worst_month', 0):.2%}",
                f"Avg Monthly: {monthly_data.get('avg_monthly_return', 0):.2%}",
                ""
            ])
            
        # Drawdown Analysis
        drawdown_data = tear_sheet_data.get('drawdown_analysis', {})
        if drawdown_data:
            lines.extend([
                "DRAWDOWN ANALYSIS",
                "-" * 20,
                f"Max Drawdown:         {drawdown_data.get('max_drawdown', 0):.2%}",
                f"Max Drawdown Date:    {drawdown_data.get('max_drawdown_date', 'N/A')}",
                f"Average Drawdown:     {drawdown_data.get('avg_drawdown', 0):.2%}",
                f"Drawdown Duration:    {drawdown_data.get('drawdown_duration_days', 0)} days",
                f"Drawdown Periods:     {drawdown_data.get('drawdown_periods', 0)}",
                ""
            ])
            
        # Risk Metrics
        rolling_sharpe = tear_sheet_data.get('rolling_sharpe', {})
        if rolling_sharpe:
            lines.extend([
                "RISK METRICS",
                "-" * 15,
                f"Current 12M Sharpe:   {rolling_sharpe.get('current_12m_sharpe', 0):.2f}",
                f"Avg 12M Sharpe:       {rolling_sharpe.get('avg_12m_sharpe', 0):.2f}",
                f"Max 12M Sharpe:       {rolling_sharpe.get('max_12m_sharpe', 0):.2f}",
                f"Min 12M Sharpe:       {rolling_sharpe.get('min_12m_sharpe', 0):.2f}",
                ""
            ])
            
        # Exposures
        exposures = tear_sheet_data.get('exposures', {})
        if exposures:
            lines.extend([
                "FACTOR & SECTOR EXPOSURES",
                "-" * 30
            ])
            
            # Factor Exposures
            factor_exposures = exposures.get('factor_exposures', {})
            if factor_exposures:
                lines.append("Factor Exposures:")
                for factor, exposure in factor_exposures.items():
                    lines.append(f"  {factor:<15} {exposure:>6.2f}")
                    
            lines.append("")
            
            # Sector Exposures
            sector_exposures = exposures.get('sector_exposures', {})
            if sector_exposures:
                lines.append("Sector Exposures:")
                # Sort by exposure magnitude
                sorted_sectors = sorted(sector_exposures.items(), key=lambda x: abs(x[1]), reverse=True)
                for sector, exposure in sorted_sectors[:8]:  # Top 8 sectors
                    lines.append(f"  {sector:<20} {exposure:>6.2f}")
                    
            lines.extend([
                f"Net Beta:             {exposures.get('net_beta', 0):.2f}",
                f"Gross Exposure:       {exposures.get('gross_exposure', 0):.2f}",
                f"Net Exposure:         {exposures.get('net_exposure', 0):.2f}",
                ""
            ])
            
        # Turnover Statistics
        turnover_stats = tear_sheet_data.get('turnover_stats', {})
        if turnover_stats:
            lines.extend([
                "TURNOVER STATISTICS",
                "-" * 20,
                f"30-Day Turnover:      {turnover_stats.get('current_30d_turnover', 0):.2f}",
                f"90-Day Turnover:      {turnover_stats.get('current_90d_turnover', 0):.2f}",
                f"Annualized Turnover:  {turnover_stats.get('annualized_turnover', 0):.2f}",
                f"Turnover Budget:      {turnover_stats.get('turnover_budget', 0):.2f}",
                f"Vs Budget:            {turnover_stats.get('vs_budget', 0):.2f}x",
                f"Status:               {turnover_stats.get('status', 'N/A')}",
                ""
            ])
            
        # Footer
        lines.extend([
            "=" * 70,
            "Past performance is not necessarily indicative of future results.",
            "This report is for informational purposes only.",
            "=" * 70
        ])
        
        return "\n".join(lines)
        
    def _save_tear_sheet(self, content: str) -> str:
        """
        Save tear sheet to file.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.output_dir / f"tear_sheet_{timestamp}.txt"
        
        try:
            with open(filename, 'w') as f:
                f.write(content)
            logger.info(f"Tear sheet saved to {filename}")
            return str(filename)
        except Exception as e:
            logger.error(f"Failed to save tear sheet: {e}")
            return ""
            
    def generate_pdf_tear_sheet(self, portfolio_data: Dict[str, Any],
                               market_data: pd.DataFrame,
                               benchmark_data: pd.DataFrame = None) -> str:
        """
        Generate PDF version of tear sheet (requires additional dependencies).
        """
        # This would use libraries like reportlab or weasyprint
        # For template, just return regular text version
        return self.generate_tear_sheet(portfolio_data, market_data, benchmark_data)

# Convenience function
def generate_portfolio_tear_sheet(portfolio_data: Dict[str, Any],
                                 market_data: pd.DataFrame,
                                 benchmark_data: pd.DataFrame = None,
                                 config: Dict[str, Any] = None) -> str:
    """Generate institutional-format tear sheet."""
    generator = TearSheetGenerator(config or {})
    return generator.generate_tear_sheet(portfolio_data, market_data, benchmark_data)
```

## Key Features to Implement

1. **Institutional Formatting**: Professional presentation standards
2. **Comprehensive Metrics**: All key performance indicators vs benchmark
3. **Monthly Returns Grid**: Calendar-based performance visualization
4. **Equity Curve Analysis**: Cumulative performance tracking
5. **Drawdown Examination**: Detailed risk metrics and duration analysis
6. **Rolling Sharpe Ratios**: Dynamic risk-adjusted performance measures
7. **Exposure Analysis**: Factor and sector risk breakdowns
8. **Turnover Statistics**: Trading activity and cost implications

## Integration Points

- Consumes portfolio performance data from all layers
- Integrates with benchmark data (SPY) for comparison
- Works with factor scores from Layer 2
- Uses sector data for exposure analysis
- Connects with turnover analytics from reporting layer
- Feeds dashboard visualization components
- Supports compliance and client reporting