"""
Meridian Capital Partners · portfolio/transaction_costs.py
─────────────────────────────────────────────────────────────────
Transaction cost model for portfolio optimization.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List
import warnings

logger = logging.getLogger("meridian.portfolio.transaction_costs")


class TransactionCostModel:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize transaction cost model with configuration."""
        if config is None:
            config = {}
            
        # Cost components in basis points
        self.commission_bps = config.get("commission_bps", 0.0)  # Alpaca is $0
        self.spread_cost_bps = config.get("spread_cost_bps", 0.0)  # Will calculate from data
        self.impact_coef = config.get("market_impact_coefficient", 0.10)
        
        logger.info("Transaction cost model initialized")

    def calculate_costs(self, ticker: str, trade_size: float, adv: float, 
                       avg_spread: float, daily_vol_bps: float) -> Dict[str, float]:
        """
        Calculate transaction costs for a single trade.
        
        Args:
            ticker: Stock ticker
            trade_size: Number of shares to trade
            adv: Average daily volume
            avg_spread: Average bid-ask spread in dollars
            daily_vol_bps: Daily volatility in basis points
            
        Returns:
            Dict with cost components in basis points
        """
        if adv <= 0 or daily_vol_bps <= 0:
            logger.warning(f"Invalid ADV or vol for {ticker}, using zero costs")
            return {
                "commission_bps": 0.0,
                "spread_cost_bps": 0.0,
                "market_impact_bps": 0.0,
                "total_bps": 0.0
            }
            
        # 1. Commission cost (Alpaca = $0)
        commission_cost = self.commission_bps
        
        # 2. Spread cost (50% of average bid-ask spread)
        # Convert spread from $ to bps: (spread / price) * 10000
        # We're given spread in $, so we need price to convert to bps
        # For cost modeling, we'll use a fixed assumption or derive from spread
        spread_cost = (avg_spread / 2) * 10000 / 100  # Simplified - 50% of spread in bps equivalent
        
        # 3. Market impact cost
        # coef * sqrt(trade_size/ADV) * daily_vol_bps
        impact_cost = self.impact_coef * np.sqrt(abs(trade_size) / adv) * daily_vol_bps
        
        total_cost = commission_cost + spread_cost + impact_cost
        
        return {
            "commission_bps": commission_cost,
            "spread_cost_bps": spread_cost,
            "market_impact_bps": impact_cost,
            "total_bps": total_cost
        }

    def calculate_costs_vector(self, positions: pd.DataFrame, market_data: pd.DataFrame) -> pd.Series:
        """
        Calculate transaction costs for a vector of positions.
        
        Args:
            positions: DataFrame with columns [ticker, current_shares, target_shares]
            market_data: DataFrame with price/volume/spread data
            
        Returns:
            Series of total costs in basis points indexed by ticker
        """
        costs = {}
        
        for _, row in positions.iterrows():
            ticker = row['ticker']
            trade_size = row['target_shares'] - row['current_shares']
            
            if trade_size == 0:
                costs[ticker] = 0.0
                continue
                
            # Get market data for this ticker
            market_row = market_data[market_data['ticker'] == ticker]
            if market_row.empty:
                logger.warning(f"No market data for {ticker}, using zero costs")
                costs[ticker] = 0.0
                continue
                
            market_info = market_row.iloc[0]
            adv = market_info.get('adv', 0)
            avg_spread = market_info.get('avg_spread', 0)
            daily_vol_bps = market_info.get('daily_vol_bps', 0)
            current_price = market_info.get('price', 0)
            
            if adv <= 0 or daily_vol_bps <= 0 or current_price <= 0:
                costs[ticker] = 0.0
                continue
                
            cost_details = self.calculate_costs(
                ticker, trade_size, adv, avg_spread, daily_vol_bps
            )
            costs[ticker] = cost_details['total_bps']
            
        return pd.Series(costs)

    def apply_costs_to_returns(self, expected_returns: pd.Series, 
                              positions: pd.DataFrame, market_data: pd.DataFrame) -> pd.Series:
        """
        Apply transaction costs to expected returns.
        
        Args:
            expected_returns: Series of expected returns indexed by ticker
            positions: DataFrame with position data
            market_data: DataFrame with market data
            
        Returns:
            Series of net expected returns after costs
        """
        costs_bps = self.calculate_costs_vector(positions, market_data)
        
        # Convert basis points to decimal returns
        costs_decimal = costs_bps / 10000
        
        # Subtract costs from expected returns
        net_returns = expected_returns.subtract(costs_decimal, fill_value=0)
        
        return net_returns

    def get_market_data_for_costs(self, db_connection, tickers: List[str]) -> pd.DataFrame:
        """
        Fetch market data needed for cost calculations.
        
        Returns:
            DataFrame with ticker, price, adv, avg_spread, daily_vol_bps
        """
        try:
            # Get latest prices
            price_query = f"""
            SELECT ticker, close as price
            FROM daily_prices 
            WHERE date = (SELECT MAX(date) FROM daily_prices)
            AND ticker IN ({','.join(['?' for _ in tickers])})
            """
            prices = pd.read_sql_query(price_query, db_connection, params=tickers)
            
            # Get ADV (20-day average)
            adv_query = f"""
            SELECT ticker, AVG(volume) as adv
            FROM daily_prices 
            WHERE date >= DATE('now', '-20 days')
            AND ticker IN ({','.join(['?' for _ in tickers])})
            GROUP BY ticker
            """
            adv = pd.read_sql_query(adv_query, db_connection, params=tickers)
            
            # Get price volatility (standard deviation of daily returns over 20 days)
            vol_query = f"""
            WITH daily_returns AS (
                SELECT ticker, date, 
                       LOG(close / LAG(close) OVER (PARTITION BY ticker ORDER BY date)) as ret
                FROM daily_prices 
                WHERE date >= DATE('now', '-20 days')
                AND ticker IN ({','.join(['?' for _ in tickers])})
            )
            SELECT ticker, 
                   STDDEV(ret) * 10000 as daily_vol_bps  -- Convert to basis points
            FROM daily_returns 
            WHERE ret IS NOT NULL
            GROUP BY ticker
            """
            volatility = pd.read_sql_query(vol_query, db_connection, params=tickers)
            
            # For spread estimation, we'll use a simplified approach
            # In practice, you'd get this from market data feeds
            spreads = prices.copy()
            spreads['avg_spread'] = spreads['price'] * 0.001  # Assume 10bps bid-ask spread
            
            # Merge all data
            result = prices.merge(adv, on='ticker', how='left') \
                          .merge(volatility, on='ticker', how='left') \
                          .merge(spreads[['ticker', 'avg_spread']], on='ticker', how='left')
                          
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch market data for costs: {e}")
            return pd.DataFrame()


# Convenience function
def get_transaction_costs(ticker: str, trade_size: float, adv: float, 
                         avg_spread: float, daily_vol_bps: float,
                         config: Dict[str, Any] = None) -> Dict[str, float]:
    """Calculate transaction costs for a single trade."""
    model = TransactionCostModel(config or {})
    return model.calculate_costs(ticker, trade_size, adv, avg_spread, daily_vol_bps)
