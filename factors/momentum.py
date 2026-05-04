"""
Meridian Capital Partners · factors/momentum.py
─────────────────────────────────────────────────────────────────
Factor 1/8 — Momentum (6 sub-factors)
All scores are 0-100 percentile ranks within GICS sectors.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import BaseFactorScorer

logger = logging.getLogger("meridian.factors.momentum")


class MomentumScorer(BaseFactorScorer):
    def __init__(self):
        super().__init__("Momentum")

    def calculate_sub_factors(self, universe: pd.DataFrame, db: Any) -> pd.DataFrame:
        """
        Calculate momentum sub-factors:
        1. 12-1 month return (skip recent 1mo)
        2. 6-month return
        3. 3-month return
        4. Acceleration (recent 3m minus older 3m)
        5. 52-week-high proximity
        6. Relative strength vs sector ETF
        """
        logger.info("Calculating momentum sub-factors...")
        
        # Get price data for all tickers
        query = """
        SELECT ticker, date, close 
        FROM daily_prices 
        ORDER BY ticker, date
        """
        price_data = pd.read_sql_query(query, db._connect())
        
        if price_data.empty:
            logger.warning("No price data found for momentum calculation")
            return pd.DataFrame(columns=['ticker', 'sector', 'mom_12_1', 'mom_6', 'mom_3', 
                                       'acceleration', 'high52_proximity', 'relative_strength'])
        
        # Convert date to datetime
        price_data['date'] = pd.to_datetime(price_data['date'])
        latest_date = price_data['date'].max()
        
        # Calculate returns for each ticker
        results = []
        
        for ticker in universe['ticker'].unique():
            ticker_data = price_data[price_data['ticker'] == ticker].copy()
            if ticker_data.empty:
                continue
                
            ticker_data = ticker_data.sort_values('date')
            
            # Get sector for this ticker
            sector_row = universe[universe['ticker'] == ticker]
            if sector_row.empty:
                continue
            sector = sector_row.iloc[0]['gics_sector']
            
            # Calculate various return periods
            current_price = ticker_data['close'].iloc[-1] if not ticker_data.empty else None
            if current_price is None:
                continue
                
            # 12-month return (11 months ago)
            date_11m_ago = latest_date - pd.DateOffset(months=11)
            price_11m_ago = ticker_data[ticker_data['date'] <= date_11m_ago]['close'].iloc[-1] if not ticker_data[ticker_data['date'] <= date_11m_ago].empty else None
            
            # 1-month return (1 month ago)
            date_1m_ago = latest_date - pd.DateOffset(months=1)
            price_1m_ago = ticker_data[ticker_data['date'] <= date_1m_ago]['close'].iloc[-1] if not ticker_data[ticker_data['date'] <= date_1m_ago].empty else None
            
            # 6-month return
            date_6m_ago = latest_date - pd.DateOffset(months=6)
            price_6m_ago = ticker_data[ticker_data['date'] <= date_6m_ago]['close'].iloc[-1] if not ticker_data[ticker_data['date'] <= date_6m_ago].empty else None
            
            # 3-month return
            date_3m_ago = latest_date - pd.DateOffset(months=3)
            price_3m_ago = ticker_data[ticker_data['date'] <= date_3m_ago]['close'].iloc[-1] if not ticker_data[ticker_data['date'] <= date_3m_ago].empty else None
            
            # 9-month return (for acceleration calc)
            date_9m_ago = latest_date - pd.DateOffset(months=9)
            price_9m_ago = ticker_data[ticker_data['date'] <= date_9m_ago]['close'].iloc[-1] if not ticker_data[ticker_data['date'] <= date_9m_ago].empty else None
            
            # 52-week high
            year_ago_date = latest_date - pd.DateOffset(years=1)
            recent_year_data = ticker_data[ticker_data['date'] >= year_ago_date]
            high_52w = recent_year_data['close'].max() if not recent_year_data.empty else None
            
            # Get sector ETF for relative strength
            sector_etf = self._get_sector_etf(sector)
            sector_return = 0.0
            if sector_etf:
                sector_data = price_data[price_data['ticker'] == sector_etf]
                if not sector_data.empty:
                    sector_data = sector_data.sort_values('date')
                    sector_current = sector_data['close'].iloc[-1] if not sector_data.empty else None
                    sector_6m_ago = sector_data[sector_data['date'] <= date_6m_ago]['close'].iloc[-1] if not sector_data[sector_data['date'] <= date_6m_ago].empty else None
                    if sector_current and sector_6m_ago and sector_6m_ago > 0:
                        sector_return = (sector_current / sector_6m_ago) - 1
            
            # Calculate sub-factors
            mom_12_1 = None
            if price_11m_ago and price_1m_ago and price_1m_ago > 0:
                mom_12_1 = (price_11m_ago / price_1m_ago) - 1
                
            mom_6 = None
            if price_6m_ago and current_price and price_6m_ago > 0:
                mom_6 = (current_price / price_6m_ago) - 1
                
            mom_3 = None
            if price_3m_ago and current_price and price_3m_ago > 0:
                mom_3 = (current_price / price_3m_ago) - 1
                
            acceleration = None
            if mom_3 is not None and price_9m_ago and price_6m_ago and price_6m_ago > 0:
                mom_3_old = (price_6m_ago / price_9m_ago) - 1
                acceleration = mom_3 - mom_3_old
                
            high52_proximity = None
            if high_52w and current_price and high_52w > 0:
                high52_proximity = current_price / high_52w
                
            relative_strength = None
            if mom_6 is not None:
                relative_strength = mom_6 - sector_return
            
            results.append({
                'ticker': ticker,
                'sector': sector,
                'mom_12_1': mom_12_1,
                'mom_6': mom_6,
                'mom_3': mom_3,
                'acceleration': acceleration,
                'high52_proximity': high52_proximity,
                'relative_strength': relative_strength
            })
        
        result_df = pd.DataFrame(results)
        logger.info(f"Momentum sub-factors calculated for {len(result_df)} tickers")
        return result_df

    def score_sub_factors(self, sub_factors_df: pd.DataFrame) -> pd.DataFrame:
        """Convert momentum sub-factors to percentile scores (0-100) within each sector."""
        if sub_factors_df.empty:
            return pd.DataFrame()
            
        scores_df = sub_factors_df[['ticker', 'sector']].copy()
        
        # Score each sub-factor (higher is better for all momentum metrics)
        scores_df['score_12_1'] = self.calculate_percentile_scores(sub_factors_df, 'mom_12_1', ascending=True)
        scores_df['score_6'] = self.calculate_percentile_scores(sub_factors_df, 'mom_6', ascending=True)
        scores_df['score_3'] = self.calculate_percentile_scores(sub_factors_df, 'mom_3', ascending=True)
        scores_df['score_acceleration'] = self.calculate_percentile_scores(sub_factors_df, 'acceleration', ascending=True)
        scores_df['score_high52_proximity'] = self.calculate_percentile_scores(sub_factors_df, 'high52_proximity', ascending=True)
        scores_df['score_relative_strength'] = self.calculate_percentile_scores(sub_factors_df, 'relative_strength', ascending=True)
        
        # Composite score (equal weights)
        weights = {
            'score_12_1': 0.1667,
            'score_6': 0.1667,
            'score_3': 0.1667,
            'score_acceleration': 0.1667,
            'score_high52_proximity': 0.1667,
            'score_relative_strength': 0.1667
        }
        
        scores_df['composite_score'] = self.composite_score(scores_df, weights)
        
        return scores_df

    def _get_sector_etf(self, sector: str) -> str:
        """Map GICS sector to corresponding ETF."""
        sector_etf_map = {
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
        }
        return sector_etf_map.get(sector, '')


# Convenience function to score momentum
def score_momentum(universe: pd.DataFrame, db: Any) -> pd.DataFrame:
    """Score all stocks on momentum factor."""
    scorer = MomentumScorer()
    sub_factors = scorer.calculate_sub_factors(universe, db)
    scores = scorer.score_sub_factors(sub_factors)
    return scores
