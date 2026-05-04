"""
Meridian Capital Partners · factors/institutional.py
─────────────────────────────────────────────────────────────────
Factor 8/8 — Institutional (3 sub-factors)
Uses institutional holdings data from L1.
All scores are 0-100 percentile ranks within GICS sectors.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import BaseFactorScorer

logger = logging.getLogger("meridian.factors.institutional")


class InstitutionalScorer(BaseFactorScorer):
    def __init__(self):
        super().__init__("Institutional")

    def calculate_sub_factors(self, universe: pd.DataFrame, db: Any) -> pd.DataFrame:
        """
        Calculate institutional sub-factors:
        1. Net flow (recent buying vs selling by institutions)
        2. Concentration (how many quality funds hold the stock)
        3. Fund quality (which funds are buying - weighting by fund reputation)
        """
        logger.info("Calculating institutional sub-factors...")
        
        # Get institutional holdings data from L1 database
        inst_query = """
        SELECT ticker, fund_name, filing_date, quarter_end, shares, value, change_shares
        FROM institutional_holdings
        ORDER BY ticker, quarter_end
        """
        inst_data = pd.read_sql_query(inst_query, db._connect())
        
        if inst_data.empty:
            logger.warning("No institutional holdings data found for calculation")
            return pd.DataFrame(columns=['ticker', 'sector', 'net_flow', 'concentration', 'fund_quality'])
        
        # Get universe for sector mapping
        universe_query = "SELECT ticker, gics_sector FROM universe"
        universe_data = pd.read_sql_query(universe_query, db._connect())
        
        # Define high-quality funds (based on AUM and track record)
        quality_funds = {
            'Citadel Advisors': 1.0,
            'Bridgewater Associates': 1.0,
            'Renaissance Technologies': 1.0,
            'Two Sigma Investments': 0.9,
            'DE Shaw & Co': 0.9,
            'Point72 Asset Management': 0.8,
            'Millennium Management': 0.8,
            'Baupost Group': 0.7,
            'Appaloosa Management': 0.7,
            'Tiger Global Management': 0.7
        }
        
        results = []
        
        # Look at recent institutional activity (last 2 quarters)
        if 'quarter_end' in inst_data.columns:
            inst_data['quarter_end'] = pd.to_datetime(inst_data['quarter_end'])
            # Get the latest quarter in the data
            latest_quarter = inst_data['quarter_end'].max()
            # Get the previous quarter
            prev_quarter = latest_quarter - pd.DateOffset(months=3)
            # Filter for recent data
            recent_inst = inst_data[inst_data['quarter_end'] >= prev_quarter]
        else:
            recent_inst = inst_data  # Use all data if no date filtering possible
            
        for ticker in recent_inst['ticker'].unique():
            if pd.isna(ticker):
                continue
                
            ticker_inst = recent_inst[recent_inst['ticker'] == ticker]
            if ticker_inst.empty:
                # Still include ticker with zeros
                sector_row = universe_data[universe_data['ticker'] == ticker]
                if not sector_row.empty:
                    sector = sector_row.iloc[0]['gics_sector']
                    results.append({
                        'ticker': ticker,
                        'sector': sector,
                        'net_flow': 0,
                        'concentration': 0,
                        'fund_quality': 0
                    })
                continue
                
            # Get sector
            sector_row = universe_data[universe_data['ticker'] == ticker]
            if sector_row.empty:
                continue
            sector = sector_row.iloc[0]['gics_sector']
            
            # 1. Net flow (sum of change_shares - positive = buying, negative = selling)
            net_flow = ticker_inst['change_shares'].sum()
            
            # 2. Concentration (number of distinct quality funds holding)
            quality_holders = ticker_inst[ticker_inst['fund_name'].isin(quality_funds.keys())]
            concentration = quality_holders['fund_name'].nunique()
            
            # 3. Fund quality (weighted sum based on fund quality scores)
            fund_quality = 0
            for _, row in quality_holders.iterrows():
                fund_name = row['fund_name']
                if fund_name in quality_funds:
                    fund_quality += quality_funds[fund_name]
            
            results.append({
                'ticker': ticker,
                'sector': sector,
                'net_flow': net_flow,
                'concentration': concentration,
                'fund_quality': fund_quality
            })
        
        result_df = pd.DataFrame(results)
        logger.info(f"Institutional sub-factors calculated for {len(result_df)} tickers")
        return result_df

    def score_sub_factors(self, sub_factors_df: pd.DataFrame) -> pd.DataFrame:
        """Convert institutional sub-factors to percentile scores (0-100) within each sector."""
        if sub_factors_df.empty:
            return pd.DataFrame()
            
        scores_df = sub_factors_df[['ticker', 'sector']].copy()
        
        # Score each sub-factor (higher is better for all institutional metrics)
        scores_df['score_net_flow'] = self.calculate_percentile_scores(sub_factors_df, 'net_flow', ascending=True)
        scores_df['score_concentration'] = self.calculate_percentile_scores(sub_factors_df, 'concentration', ascending=True)
        scores_df['score_fund_quality'] = self.calculate_percentile_scores(sub_factors_df, 'fund_quality', ascending=True)
        
        # Composite score (equal weights)
        weights = {
            'score_net_flow': 0.3333,
            'score_concentration': 0.3333,
            'score_fund_quality': 0.3333
        }
        
        scores_df['composite_score'] = self.composite_score(scores_df, weights)
        
        return scores_df


# Convenience function to score institutional holdings
def score_institutional(universe: pd.DataFrame, db: Any) -> pd.DataFrame:
    """Score all stocks on institutional factor."""
    scorer = InstitutionalScorer()
    sub_factors = scorer.calculate_sub_factors(universe, db)
    scores = scorer.score_sub_factors(sub_factors)
    return scores
