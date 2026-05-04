"""
Meridian Capital Partners · factors/growth.py
─────────────────────────────────────────────────────────────────
Factor 4/8 — Growth (3 sub-factors)
All scores are 0-100 percentile ranks within GICS sectors.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import BaseFactorScorer

logger = logging.getLogger("meridian.factors.growth")


class GrowthScorer(BaseFactorScorer):
    def __init__(self):
        super().__init__("Growth")

    def calculate_sub_factors(self, universe: pd.DataFrame, db: Any) -> pd.DataFrame:
        """
        Calculate growth sub-factors:
        1. Revenue growth YoY
        2. Earnings growth YoY
        3. Margin expansion (improving net margin)
        """
        logger.info("Calculating growth sub-factors...")
        
        # Get derived ratios data for growth metrics
        ratios_query = """
        SELECT ticker, period, revenue_growth_yoy, earnings_growth_yoy, 
               net_margin, gross_margin, operating_margin
        FROM derived_ratios
        ORDER BY ticker, period
        """
        ratios_data = pd.read_sql_query(ratios_query, db._connect())
        
        if ratios_data.empty:
            logger.warning("No derived ratios data found for growth calculation")
            return pd.DataFrame(columns=['ticker', 'sector', 'revenue_growth_yoy', 
                                       'earnings_growth_yoy', 'margin_expansion'])
        
        # Get universe for sector mapping
        universe_query = "SELECT ticker, gics_sector FROM universe"
        universe_data = pd.read_sql_query(universe_query, db._connect())
        
        results = []
        
        for ticker in ratios_data['ticker'].unique():
            ticker_ratios = ratios_data[ratios_data['ticker'] == ticker].sort_values('period')
            if ticker_ratios.empty:
                continue
                
            # Get sector
            sector_row = universe_data[universe_data['ticker'] == ticker]
            if sector_row.empty:
                continue
            sector = sector_row.iloc[0]['gics_sector']
            
            # Get latest ratios
            latest_ratios = ticker_ratios.iloc[-1]
            
            # 1. Revenue growth YoY (already calculated in L1)
            revenue_growth_yoy = latest_ratios['revenue_growth_yoy']
            
            # 2. Earnings growth YoY (already calculated in L1)
            earnings_growth_yoy = latest_ratios['earnings_growth_yoy']
            
            # 3. Margin expansion (net margin improvement)
            margin_expansion = None
            if len(ticker_ratios) >= 2:
                latest_net_margin = latest_ratios['net_margin']
                prev_net_margin = ticker_ratios.iloc[-2]['net_margin']
                if pd.notna(latest_net_margin) and pd.notna(prev_net_margin):
                    margin_expansion = latest_net_margin - prev_net_margin
            
            results.append({
                'ticker': ticker,
                'sector': sector,
                'revenue_growth_yoy': revenue_growth_yoy,
                'earnings_growth_yoy': earnings_growth_yoy,
                'margin_expansion': margin_expansion
            })
        
        result_df = pd.DataFrame(results)
        logger.info(f"Growth sub-factors calculated for {len(result_df)} tickers")
        return result_df

    def score_sub_factors(self, sub_factors_df: pd.DataFrame) -> pd.DataFrame:
        """Convert growth sub-factors to percentile scores (0-100) within each sector."""
        if sub_factors_df.empty:
            return pd.DataFrame()
            
        scores_df = sub_factors_df[['ticker', 'sector']].copy()
        
        # Score each sub-factor (higher is better for all growth metrics)
        scores_df['score_revenue_growth_yoy'] = self.calculate_percentile_scores(sub_factors_df, 'revenue_growth_yoy', ascending=True)
        scores_df['score_earnings_growth_yoy'] = self.calculate_percentile_scores(sub_factors_df, 'earnings_growth_yoy', ascending=True)
        scores_df['score_margin_expansion'] = self.calculate_percentile_scores(sub_factors_df, 'margin_expansion', ascending=True)
        
        # Composite score (equal weights)
        weights = {
            'score_revenue_growth_yoy': 0.3333,
            'score_earnings_growth_yoy': 0.3333,
            'score_margin_expansion': 0.3333
        }
        
        scores_df['composite_score'] = self.composite_score(scores_df, weights)
        
        return scores_df


# Convenience function to score growth
def score_growth(universe: pd.DataFrame, db: Any) -> pd.DataFrame:
    """Score all stocks on growth factor."""
    scorer = GrowthScorer()
    sub_factors = scorer.calculate_sub_factors(universe, db)
    scores = scorer.score_sub_factors(sub_factors)
    return scores
