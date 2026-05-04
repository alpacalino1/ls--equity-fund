# P&L Attribution Template

This is a template for the pnl_attribution.py implementation that will handle daily P&L decomposition.

## Planned Implementation

```python
"""
Meridian Capital Partners · reporting/pnl_attribution.py
─────────────────────────────────────────────────────────────────
Daily P&L attribution: beta + sector + factor + alpha decomposition.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("meridian.reporting.pnl_attribution")

class PnLAttribution:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize P&L attribution engine."""
        if config is None:
            config = {}
            
        self.config = config
        self.benchmark_ticker = config.get("benchmark", "SPY")
        self.lookback_days = config.get("lookback_days", 252)
        self.output_dir = Path("output/reporting")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("P&L attribution engine initialized")
        
    def calculate_daily_attribution(self, portfolio_returns: pd.Series, 
                                   market_data: pd.DataFrame,
                                   factor_data: pd.DataFrame = None,
                                   sector_data: pd.DataFrame = None) -> pd.DataFrame:
        """
        Calculate daily P&L attribution decomposition.
        
        Attribution components:
        1. Beta: net_beta * SPY_return
        2. Sector: Brinson-style sector allocation/picking
        3. Factor: regression on factor return spreads
        4. Alpha: residual after subtracting all components
        """
        if portfolio_returns.empty:
            logger.warning("Empty portfolio returns for attribution")
            return pd.DataFrame()
            
        # Get date range
        start_date = portfolio_returns.index.min()
        end_date = portfolio_returns.index.max()
        
        logger.info(f"Calculating attribution for {len(portfolio_returns)} days: {start_date} to {end_date}")
        
        # 1. Beta Attribution
        beta_attribution = self._calculate_beta_attribution(
            portfolio_returns, market_data
        )
        
        # 2. Sector Attribution (Brinson-style)
        sector_attribution = self._calculate_sector_attribution(
            portfolio_returns, market_data, sector_data
        )
        
        # 3. Factor Attribution
        factor_attribution = self._calculate_factor_attribution(
            portfolio_returns, factor_data, market_data
        )
        
        # 4. Combine all components
        attribution_df = self._combine_attribution_components(
            portfolio_returns, beta_attribution, sector_attribution, 
            factor_attribution, market_data
        )
        
        # Save to file
        self._save_attribution(attribution_df)
        
        return attribution_df
        
    def _calculate_beta_attribution(self, portfolio_returns: pd.Series, 
                                  market_data: pd.DataFrame) -> pd.Series:
        """
        Calculate beta attribution component.
        Beta attribution = portfolio_beta * market_return
        """
        # Get benchmark returns (SPY)
        benchmark_data = market_data[market_data['ticker'] == self.benchmark_ticker]
        if benchmark_data.empty:
            logger.warning(f"No benchmark data found for {self.benchmark_ticker}")
            return pd.Series(0.0, index=portfolio_returns.index)
            
        # Align dates
        benchmark_returns = benchmark_data.set_index('date')['return'].reindex(
            portfolio_returns.index, method='ffill'
        ).fillna(0)
        
        # Calculate portfolio beta (simplified - would use regression in practice)
        portfolio_beta = 1.0  # Simplified - would calculate from historical data
        
        # Beta attribution = beta * market return
        beta_attribution = portfolio_beta * benchmark_returns
        
        logger.debug(f"Beta attribution calculated: avg={beta_attribution.mean():.4f}")
        return beta_attribution
        
    def _calculate_sector_attribution(self, portfolio_returns: pd.Series,
                                    market_data: pd.DataFrame,
                                    sector_data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Brinson-style sector attribution.
        
        Components:
        1. Sector allocation: (portfolio_weight - benchmark_weight) * benchmark_return
        2. Security selection: portfolio_weight * (security_return - benchmark_return)
        """
        if sector_data is None or sector_data.empty:
            logger.warning("No sector data for attribution")
            return pd.DataFrame(index=portfolio_returns.index)
            
        # This would involve:
        # 1. Calculate portfolio sector weights over time
        # 2. Calculate benchmark sector returns
        # 3. Calculate allocation and selection effects
        
        # Simplified implementation for template
        attribution_data = pd.DataFrame({
            'date': portfolio_returns.index,
            'sector_allocation': 0.0,  # Would calculate actual values
            'security_selection': 0.0,  # Would calculate actual values
        }).set_index('date')
        
        logger.debug("Sector attribution calculated using Brinson methodology")
        return attribution_data
        
    def _calculate_factor_attribution(self, portfolio_returns: pd.Series,
                                    factor_data: pd.DataFrame,
                                    market_data: pd.DataFrame) -> pd.Series:
        """
        Calculate factor attribution using regression on factor returns.
        """
        if factor_data is None or factor_data.empty:
            logger.warning("No factor data for attribution")
            return pd.Series(0.0, index=portfolio_returns.index)
            
        # This would involve:
        # 1. Get factor returns over time
        # 2. Run regression of portfolio returns on factor returns
        # 3. Calculate factor contribution to returns
        
        # Simplified implementation for template
        factor_attribution = pd.Series(0.0, index=portfolio_returns.index)
        
        logger.debug("Factor attribution calculated via regression")
        return factor_attribution
        
    def _combine_attribution_components(self, portfolio_returns: pd.Series,
                                      beta_attribution: pd.Series,
                                      sector_attribution: pd.DataFrame,
                                      factor_attribution: pd.Series,
                                      market_data: pd.DataFrame) -> pd.DataFrame:
        """
        Combine all attribution components and calculate alpha residual.
        """
        # Create combined attribution dataframe
        attribution_df = pd.DataFrame({
            'date': portfolio_returns.index,
            'portfolio_return': portfolio_returns.values,
            'beta_attribution': beta_attribution.values,
            'sector_allocation': sector_attribution.get('sector_allocation', pd.Series(0.0, index=portfolio_returns.index)).values,
            'security_selection': sector_attribution.get('security_selection', pd.Series(0.0, index=portfolio_returns.index)).values,
            'factor_attribution': factor_attribution.values,
        }).set_index('date')
        
        # Calculate total explained return
        attribution_df['total_explained'] = (
            attribution_df['beta_attribution'] +
            attribution_df['sector_allocation'] +
            attribution_df['security_selection'] +
            attribution_df['factor_attribution']
        )
        
        # Calculate alpha residual (unexplained return)
        attribution_df['alpha_residual'] = (
            attribution_df['portfolio_return'] - attribution_df['total_explained']
        )
        
        # Add cumulative components
        attribution_df['cumulative_portfolio'] = (1 + attribution_df['portfolio_return']).cumprod() - 1
        attribution_df['cumulative_alpha'] = (1 + attribution_df['alpha_residual']).cumprod() - 1
        
        return attribution_df
        
    def _save_attribution(self, attribution_df: pd.DataFrame):
        """Save attribution results to CSV file."""
        if attribution_df.empty:
            return
            
        output_file = self.output_dir / "daily_attribution.csv"
        try:
            attribution_df.to_csv(output_file)
            logger.info(f"P&L attribution saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save attribution: {e}")
            
    def get_attribution_summary(self, attribution_df: pd.DataFrame) -> Dict[str, float]:
        """Get summary statistics for attribution analysis."""
        if attribution_df.empty:
            return {}
            
        return {
            'total_days': len(attribution_df),
            'avg_portfolio_return': attribution_df['portfolio_return'].mean(),
            'avg_beta_attribution': attribution_df['beta_attribution'].mean(),
            'avg_sector_allocation': attribution_df['sector_allocation'].mean(),
            'avg_security_selection': attribution_df['security_selection'].mean(),
            'avg_factor_attribution': attribution_df['factor_attribution'].mean(),
            'avg_alpha_residual': attribution_df['alpha_residual'].mean(),
            'alpha_volatility': attribution_df['alpha_residual'].std(),
            'information_ratio': (attribution_df['alpha_residual'].mean() / 
                                attribution_df['alpha_residual'].std()) * np.sqrt(252) if attribution_df['alpha_residual'].std() > 0 else 0,
            'r_squared': self._calculate_r_squared(attribution_df)
        }
        
    def _calculate_r_squared(self, attribution_df: pd.DataFrame) -> float:
        """Calculate R-squared of attribution model."""
        if len(attribution_df) < 2:
            return 0.0
            
        portfolio_returns = attribution_df['portfolio_return']
        explained_returns = attribution_df['total_explained']
        
        # Calculate R-squared manually
        ss_res = ((portfolio_returns - explained_returns) ** 2).sum()
        ss_tot = ((portfolio_returns - portfolio_returns.mean()) ** 2).sum()
        
        if ss_tot == 0:
            return 1.0
            
        return 1 - (ss_res / ss_tot)

# Convenience function
def calculate_pnl_attribution(portfolio_returns: pd.Series, 
                             market_data: pd.DataFrame,
                             factor_data: pd.DataFrame = None,
                             sector_data: pd.DataFrame = None,
                             config: Dict[str, Any] = None) -> pd.DataFrame:
    """Calculate daily P&L attribution decomposition."""
    attributor = PnLAttribution(config or {})
    return attributor.calculate_daily_attribution(
        portfolio_returns, market_data, factor_data, sector_data
    )
```

## Key Features to Implement

1. **Four-Way Attribution Decomposition**:
   - Beta component (market exposure)
   - Sector component (Brinson methodology)
   - Factor component (regression-based)
   - Alpha residual (unexplained returns)

2. **Industry-Standard Methodologies**:
   - Brinson sector attribution
   - Factor regression analysis
   - Risk-adjusted performance metrics

3. **Comprehensive Output**:
   - Daily attribution components
   - Cumulative performance tracking
   - Summary statistics and ratios

4. **Persistence**:
   - CSV export for analysis
   - Historical tracking capabilities

## Integration Points

- Consumes portfolio returns from Layer 4
- Uses market data from Data Layer
- Integrates factor data from Layer 2
- Works with sector data for Brinson attribution
- Feeds dashboard and tear sheet generators