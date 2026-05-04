"""
Meridian Capital Partners · factors/short_interest.py
─────────────────────────────────────────────────────────────────
Factor 6/8 — Short Interest (2 sub-factors)
Note: Short interest data was not included in Layer 1 data pipeline.
This factor assumes we have access to short interest data.
All scores are 0-100 percentile ranks within GICS sectors.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import BaseFactorScorer

logger = logging.getLogger("meridian.factors.short_interest")


class ShortInterestScorer(BaseFactorScorer):
    def __init__(self):
        super().__init__("ShortInterest")

    def calculate_sub_factors(self, universe: pd.DataFrame, db: Any) -> pd.DataFrame:
        """
        Calculate short interest sub-factors:
        1. Days to cover (higher = more bearish signal)
        2. % of float shorted (higher = more bearish signal)
        
        Note: This requires short interest data which was not ingested in L1.
        Implementation assumes we have access to:
        - Short interest (number of shares)
        - Float (shares outstanding - restricted shares)
        - Average daily volume
        """
        logger.info("Calculating short interest sub-factors (requires short interest data)...")
        
        # In a real implementation, we would query short interest data here
        # For now, we'll return empty data since this wasn't ingested in L1
        
        logger.warning("Short interest data not available in L1 data. Returning empty DataFrame.")
        return pd.DataFrame(columns=['ticker', 'sector', 'days_to_cover', 'pct_float_shorted'])
        
        # Placeholder for actual implementation if short interest data was available:
        """
        # Get short interest data from database
        short_query = '''
        SELECT ticker, date, short_interest_shares, float_shares, avg_daily_volume
        FROM short_interest
        ORDER BY ticker, date
        '''
        short_data = pd.read_sql_query(short_query, db._connect())
        
        if short_data.empty:
            logger.warning("No short interest data found for calculation")
            return pd.DataFrame(columns=['ticker', 'sector', 'days_to_cover', 'pct_float_shorted'])
        
        # Get universe for sector mapping
        universe_query = "SELECT ticker, gics_sector FROM universe"
        universe_data = pd.read_sql_query(universe_query, db._connect())
        
        results = []
        
        for ticker in short_data['ticker'].unique():
            ticker_short = short_data[short_data['ticker'] == ticker].sort_values('date')
            if ticker_short.empty:
                continue
                
            # Get sector
            sector_row = universe_data[universe_data['ticker'] == ticker]
            if sector_row.empty:
                continue
            sector = sector_row.iloc[0]['gics_sector']
            
            # Get latest short interest data
            latest_short = ticker_short.iloc[-1]
            
            # 1. Days to cover = Short Interest / Average Daily Volume
            days_to_cover = None
            if pd.notna(latest_short['short_interest_shares']) and pd.notna(latest_short['avg_daily_volume']) and latest_short['avg_daily_volume'] > 0:
                days_to_cover = latest_short['short_interest_shares'] / latest_short['avg_daily_volume']
                
            # 2. % of float shorted = Short Interest / Float
            pct_float_shorted = None
            if pd.notna(latest_short['short_interest_shares']) and pd.notna(latest_short['float_shares']) and latest_short['float_shares'] > 0:
                pct_float_shorted = latest_short['short_interest_shares'] / latest_short['float_shares']
            
            results.append({
                'ticker': ticker,
                'sector': sector,
                'days_to_cover': days_to_cover,
                'pct_float_shorted': pct_float_shorted
            })
        
        result_df = pd.DataFrame(results)
        logger.info(f"Short interest sub-factors calculated for {len(result_df)} tickers")
        return result_df
        """

    def score_sub_factors(self, sub_factors_df: pd.DataFrame) -> pd.DataFrame:
        """Convert short interest sub-factors to percentile scores (0-100) within each sector.
        
        Note: For short interest, HIGHER values indicate MORE BEARISH sentiment,
        so we want LOWER scores for higher short interest (inverted scoring).
        """
        if sub_factors_df.empty:
            return pd.DataFrame()
            
        scores_df = sub_factors_df[['ticker', 'sector']].copy()
        
        # Score each sub-factor (LOWER scores for higher short interest - inverted)
        scores_df['score_days_to_cover'] = self.calculate_percentile_scores(sub_factors_df, 'days_to_cover', ascending=False)
        scores_df['score_pct_float_shorted'] = self.calculate_percentile_scores(sub_factors_df, 'pct_float_shorted', ascending=False)
        
        # Composite score (equal weights)
        weights = {
            'score_days_to_cover': 0.5,
            'score_pct_float_shorted': 0.5
        }
        
        scores_df['composite_score'] = self.composite_score(scores_df, weights)
        
        return scores_df


# Convenience function to score short interest
def score_short_interest(universe: pd.DataFrame, db: Any) -> pd.DataFrame:
    """Score all stocks on short interest factor."""
    scorer = ShortInterestScorer()
    sub_factors = scorer.calculate_sub_factors(universe, db)
    scores = scorer.score_sub_factors(sub_factors)
    return scores
