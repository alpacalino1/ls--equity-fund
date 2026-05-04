"""
Meridian Capital Partners · factors/insider.py
─────────────────────────────────────────────────────────────────
Factor 7/8 — Insider (3 sub-factors)
Uses insider transaction data from L1.
All scores are 0-100 percentile ranks within GICS sectors.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import BaseFactorScorer

logger = logging.getLogger("meridian.factors.insider")


class InsiderScorer(BaseFactorScorer):
    def __init__(self):
        super().__init__("Insider")

    def calculate_sub_factors(self, universe: pd.DataFrame, db: Any) -> pd.DataFrame:
        """
        Calculate insider sub-factors:
        1. Cluster buys (multiple insiders buying recently)
        2. CEO/CFO buys (insider titles)
        3. Buy/sell ratio (net buying activity)
        """
        logger.info("Calculating insider sub-factors...")
        
        # Get insider transaction data from L1 database
        insider_query = """
        SELECT ticker, filing_date, insider_name, title, transaction_type, shares, price, value
        FROM insider_transactions
        ORDER BY ticker, filing_date
        """
        insider_data = pd.read_sql_query(insider_query, db._connect())
        
        if insider_data.empty:
            logger.warning("No insider transaction data found for calculation")
            return pd.DataFrame(columns=['ticker', 'sector', 'cluster_buys', 'executive_buys', 'buy_sell_ratio'])
        
        # Get universe for sector mapping
        universe_query = "SELECT ticker, gics_sector FROM universe"
        universe_data = pd.read_sql_query(universe_query, db._connect())
        
        results = []
        
        # Define executive titles
        exec_titles = ['CEO', 'CFO', 'Chief Executive Officer', 'Chief Financial Officer', 
                      'President', 'Chairman', 'COO', 'Chief Operating Officer']
        
        # Look at recent insider activity (last 90 days)
        cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=90)
        if 'filing_date' in insider_data.columns:
            insider_data['filing_date'] = pd.to_datetime(insider_data['filing_date'])
            recent_insider = insider_data[insider_data['filing_date'] >= cutoff_date]
        else:
            recent_insider = insider_data  # Use all data if no date filtering possible
            
        for ticker in recent_insider['ticker'].unique():
            if pd.isna(ticker):
                continue
                
            ticker_insider = recent_insider[recent_insider['ticker'] == ticker]
            if ticker_insider.empty:
                # Still include ticker with zeros
                sector_row = universe_data[universe_data['ticker'] == ticker]
                if not sector_row.empty:
                    sector = sector_row.iloc[0]['gics_sector']
                    results.append({
                        'ticker': ticker,
                        'sector': sector,
                        'cluster_buys': 0,
                        'executive_buys': 0,
                        'buy_sell_ratio': 0
                    })
                continue
                
            # Get sector
            sector_row = universe_data[universe_data['ticker'] == ticker]
            if sector_row.empty:
                continue
            sector = sector_row.iloc[0]['gics_sector']
            
            # 1. Cluster buys (number of distinct insiders buying in recent period)
            buy_transactions = ticker_insider[
                (ticker_insider['transaction_type'].str.contains('Buy', case=False, na=False)) &
                (ticker_insider['shares'] > 0)
            ]
            cluster_buys = buy_transactions['insider_name'].nunique() if not buy_transactions.empty else 0
            
            # 2. Executive buys (CEOs/CFOs buying)
            exec_buys = 0
            if not buy_transactions.empty:
                for _, row in buy_transactions.iterrows():
                    title = str(row['title']) if pd.notna(row['title']) else ''
                    if any(exec_title.lower() in title.lower() for exec_title in exec_titles):
                        exec_buys += 1
                        
            # 3. Buy/sell ratio (total shares bought / total shares sold)
            total_bought = buy_transactions['shares'].sum() if not buy_transactions.empty else 0
            
            sell_transactions = ticker_insider[
                (ticker_insider['transaction_type'].str.contains('Sale', case=False, na=False)) &
                (ticker_insider['shares'] > 0)
            ]
            total_sold = sell_transactions['shares'].sum() if not sell_transactions.empty else 0
            
            buy_sell_ratio = 0
            if total_sold > 0:
                buy_sell_ratio = total_bought / total_sold
            elif total_bought > 0:
                # If only buying, give a high ratio
                buy_sell_ratio = total_bought / 1  # Use 1 as denominator to get actual bought shares
            
            results.append({
                'ticker': ticker,
                'sector': sector,
                'cluster_buys': cluster_buys,
                'executive_buys': exec_buys,
                'buy_sell_ratio': buy_sell_ratio
            })
        
        result_df = pd.DataFrame(results)
        logger.info(f"Insider sub-factors calculated for {len(result_df)} tickers")
        return result_df

    def score_sub_factors(self, sub_factors_df: pd.DataFrame) -> pd.DataFrame:
        """Convert insider sub-factors to percentile scores (0-100) within each sector."""
        if sub_factors_df.empty:
            return pd.DataFrame()
            
        scores_df = sub_factors_df[['ticker', 'sector']].copy()
        
        # Score each sub-factor (higher is better for all insider metrics)
        scores_df['score_cluster_buys'] = self.calculate_percentile_scores(sub_factors_df, 'cluster_buys', ascending=True)
        scores_df['score_executive_buys'] = self.calculate_percentile_scores(sub_factors_df, 'executive_buys', ascending=True)
        scores_df['score_buy_sell_ratio'] = self.calculate_percentile_scores(sub_factors_df, 'buy_sell_ratio', ascending=True)
        
        # Composite score (equal weights)
        weights = {
            'score_cluster_buys': 0.3333,
            'score_executive_buys': 0.3333,
            'score_buy_sell_ratio': 0.3333
        }
        
        scores_df['composite_score'] = self.composite_score(scores_df, weights)
        
        return scores_df


# Convenience function to score insider activity
def score_insider(universe: pd.DataFrame, db: Any) -> pd.DataFrame:
    """Score all stocks on insider factor."""
    scorer = InsiderScorer()
    sub_factors = scorer.calculate_sub_factors(universe, db)
    scores = scorer.score_sub_factors(sub_factors)
    return scores
