"""
Meridian Capital Partners · factors/revision.py
─────────────────────────────────────────────────────────────────
Factor 5/8 — Revision (2 sub-factors)
Note: Analyst estimates were not included in Layer 1 data pipeline.
This factor assumes we have access to analyst estimates data.
All scores are 0-100 percentile ranks within GICS sectors.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import BaseFactorScorer

logger = logging.getLogger("meridian.factors.revision")


class RevisionScorer(BaseFactorScorer):
    def __init__(self):
        super().__init__("Revision")

    def calculate_sub_factors(self, universe: pd.DataFrame, db: Any) -> pd.DataFrame:
        """
        Calculate revision sub-factors:
        1. Earnings estimate revisions up (positive revisions)
        2. Number of upward revisions vs downward (analyst count)
        
        Note: This requires analyst estimate data which was not ingested in L1.
        Implementation assumes we have access to:
        - Current EPS estimates
        - Previous EPS estimates
        - Number of analysts making upward/downward revisions
        """
        logger.info("Calculating revision sub-factors (requires analyst estimates data)...")
        
        # In a real implementation, we would query analyst estimate data here
        # For now, we'll return empty data since this wasn't ingested in L1
        
        logger.warning("Analyst estimates not available in L1 data. Returning empty DataFrame.")
        return pd.DataFrame(columns=['ticker', 'sector', 'eps_revision_up', 'analyst_revision_direction'])
        
        # Placeholder for actual implementation if analyst data was available:
        """
        # Get analyst estimate data from database
        analyst_query = '''
        SELECT ticker, period, eps_estimate_current, eps_estimate_previous,
               analysts_upward_revisions, analysts_downward_revisions
        FROM analyst_estimates
        ORDER BY ticker, period
        '''
        analyst_data = pd.read_sql_query(analyst_query, db._connect())
        
        if analyst_data.empty:
            logger.warning("No analyst estimate data found for revision calculation")
            return pd.DataFrame(columns=['ticker', 'sector', 'eps_revision_up', 'analyst_revision_direction'])
        
        # Get universe for sector mapping
        universe_query = "SELECT ticker, gics_sector FROM universe"
        universe_data = pd.read_sql_query(universe_query, db._connect())
        
        results = []
        
        for ticker in analyst_data['ticker'].unique():
            ticker_analyst = analyst_data[analyst_data['ticker'] == ticker].sort_values('period')
            if ticker_analyst.empty:
                continue
                
            # Get sector
            sector_row = universe_data[universe_data['ticker'] == ticker]
            if sector_row.empty:
                continue
            sector = sector_row.iloc[0]['gics_sector']
            
            # Get latest estimates
            latest_estimates = ticker_analyst.iloc[-1]
            
            # 1. EPS estimate revision up (current - previous)
            eps_revision_up = None
            if pd.notna(latest_estimates['eps_estimate_current']) and pd.notna(latest_estimates['eps_estimate_previous']):
                eps_revision_up = latest_estimates['eps_estimate_current'] - latest_estimates['eps_estimate_previous']
                
            # 2. Analyst revision direction (upward vs downward)
            analyst_revision_direction = None
            if pd.notna(latest_estimates['analysts_upward_revisions']) and pd.notna(latest_estimates['analysts_downward_revisions']):
                analyst_revision_direction = latest_estimates['analysts_upward_revisions'] - latest_estimates['analysts_downward_revisions']
            
            results.append({
                'ticker': ticker,
                'sector': sector,
                'eps_revision_up': eps_revision_up,
                'analyst_revision_direction': analyst_revision_direction
            })
        
        result_df = pd.DataFrame(results)
        logger.info(f"Revision sub-factors calculated for {len(result_df)} tickers")
        return result_df
        """

    def score_sub_factors(self, sub_factors_df: pd.DataFrame) -> pd.DataFrame:
        """Convert revision sub-factors to percentile scores (0-100) within each sector."""
        if sub_factors_df.empty:
            return pd.DataFrame()
            
        scores_df = sub_factors_df[['ticker', 'sector']].copy()
        
        # Score each sub-factor (higher is better for positive revisions)
        scores_df['score_eps_revision_up'] = self.calculate_percentile_scores(sub_factors_df, 'eps_revision_up', ascending=True)
        scores_df['score_analyst_revision_direction'] = self.calculate_percentile_scores(sub_factors_df, 'analyst_revision_direction', ascending=True)
        
        # Composite score (equal weights)
        weights = {
            'score_eps_revision_up': 0.5,
            'score_analyst_revision_direction': 0.5
        }
        
        scores_df['composite_score'] = self.composite_score(scores_df, weights)
        
        return scores_df


# Convenience function to score revision
def score_revision(universe: pd.DataFrame, db: Any) -> pd.DataFrame:
    """Score all stocks on revision factor."""
    scorer = RevisionScorer()
    sub_factors = scorer.calculate_sub_factors(universe, db)
    scores = scorer.score_sub_factors(sub_factors)
    return scores
