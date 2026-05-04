"""
Meridian Capital Partners · factors/quality.py
─────────────────────────────────────────────────────────────────
Factor 3/8 — Quality (8 sub-factors)
All scores are 0-100 percentile ranks within GICS sectors.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import BaseFactorScorer

logger = logging.getLogger("meridian.factors.quality")


class QualityScorer(BaseFactorScorer):
    def __init__(self):
        super().__init__("Quality")

    def calculate_sub_factors(self, universe: pd.DataFrame, db: Any) -> pd.DataFrame:
        """
        Calculate quality sub-factors:
        1. ROE stability (std dev of 12Q ROEs, invert)
        2. Gross margin level
        3. Gross margin trend (latest minus 4Q ago)
        4. Debt/equity (invert)
        5. CFO/NI (higher = real cash earnings)
        6. Accruals ratio ((NI-CFO)/TA, invert)
        7. Piotroski F-Score (1-9): 9 binary signals
        8. Altman Z-Score
        """
        logger.info("Calculating quality sub-factors...")
        
        # Get derived ratios data
        ratios_query = """
        SELECT ticker, period, roe, gross_margin, operating_margin, net_margin,
               debt_to_equity, cfo_to_ni, accruals_ratio, retained_earnings,
               working_capital, total_liabilities, ebit, shares_outstanding,
               dividends_paid, buybacks, asset_turnover
        FROM derived_ratios
        """
        ratios_data = pd.read_sql_query(ratios_query, db._connect())
        
        # Get fundamentals data for additional calculations
        fundamentals_query = """
        SELECT ticker, period, statement_type, field, value
        FROM fundamentals
        WHERE statement_type IN ('income', 'balance', 'cashflow')
        """
        fundamentals_data = pd.read_sql_query(fundamentals_query, db._connect())
        
        if ratios_data.empty:
            logger.warning("No derived ratios data found for quality calculation")
            return pd.DataFrame(columns=['ticker', 'sector', 'roe_stability', 'gross_margin_level', 
                                       'gross_margin_trend', 'debt_equity_inverse', 'cfo_to_ni',
                                       'accruals_inverse', 'piotroski_score', 'altman_z_score'])
        
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
            
            # 1. ROE stability (std dev of 12Q ROEs, invert)
            roe_history = ticker_ratios['roe'].dropna()
            roe_stability = None
            if len(roe_history) >= 4:  # Need at least 4 quarters
                roe_std = roe_history.std()
                roe_stability = 1 / roe_std if roe_std > 0 else None  # Invert so lower std = higher score
            
            # 2. Gross margin level (latest)
            gross_margin_level = latest_ratios['gross_margin']
            
            # 3. Gross margin trend (latest minus 4Q ago)
            gross_margin_trend = None
            if len(ticker_ratios) >= 4:
                latest_gm = latest_ratios['gross_margin']
                old_gm = ticker_ratios.iloc[-4]['gross_margin']
                if pd.notna(latest_gm) and pd.notna(old_gm):
                    gross_margin_trend = latest_gm - old_gm
            
            # 4. Debt/equity (invert)
            debt_equity_inverse = None
            if pd.notna(latest_ratios['debt_to_equity']) and latest_ratios['debt_to_equity'] > 0:
                debt_equity_inverse = 1 / latest_ratios['debt_to_equity']
                
            # 5. CFO/NI
            cfo_to_ni = latest_ratios['cfo_to_ni']
            
            # 6. Accruals ratio (invert)
            accruals_inverse = None
            if pd.notna(latest_ratios['accruals_ratio']):
                accruals_inverse = 1 / abs(latest_ratios['accruals_ratio']) if latest_ratios['accruals_ratio'] != 0 else None
            
            # 7. Piotroski F-Score (1-9)
            piotroski_score = self._calculate_piotroski_score(ticker, fundamentals_data, ticker_ratios)
            
            # 8. Altman Z-Score
            altman_z_score = self._calculate_altman_z_score(ticker, fundamentals_data, latest_ratios)
            
            results.append({
                'ticker': ticker,
                'sector': sector,
                'roe_stability': roe_stability,
                'gross_margin_level': gross_margin_level,
                'gross_margin_trend': gross_margin_trend,
                'debt_equity_inverse': debt_equity_inverse,
                'cfo_to_ni': cfo_to_ni,
                'accruals_inverse': accruals_inverse,
                'piotroski_score': piotroski_score,
                'altman_z_score': altman_z_score
            })
        
        result_df = pd.DataFrame(results)
        logger.info(f"Quality sub-factors calculated for {len(result_df)} tickers")
        return result_df

    def score_sub_factors(self, sub_factors_df: pd.DataFrame) -> pd.DataFrame:
        """Convert quality sub-factors to percentile scores (0-100) within each sector."""
        if sub_factors_df.empty:
            return pd.DataFrame()
            
        scores_df = sub_factors_df[['ticker', 'sector']].copy()
        
        # Score each sub-factor
        # Higher is better for most quality metrics
        scores_df['score_roe_stability'] = self.calculate_percentile_scores(sub_factors_df, 'roe_stability', ascending=True)
        scores_df['score_gross_margin_level'] = self.calculate_percentile_scores(sub_factors_df, 'gross_margin_level', ascending=True)
        scores_df['score_gross_margin_trend'] = self.calculate_percentile_scores(sub_factors_df, 'gross_margin_trend', ascending=True)
        scores_df['score_debt_equity_inverse'] = self.calculate_percentile_scores(sub_factors_df, 'debt_equity_inverse', ascending=True)
        scores_df['score_cfo_to_ni'] = self.calculate_percentile_scores(sub_factors_df, 'cfo_to_ni', ascending=True)
        scores_df['score_accruals_inverse'] = self.calculate_percentile_scores(sub_factors_df, 'accruals_inverse', ascending=True)
        scores_df['score_piotroski_score'] = self.calculate_percentile_scores(sub_factors_df, 'piotroski_score', ascending=True)
        scores_df['score_altman_z_score'] = self.calculate_percentile_scores(sub_factors_df, 'altman_z_score', ascending=True)
        
        # Composite score (equal weights)
        weights = {
            'score_roe_stability': 0.125,
            'score_gross_margin_level': 0.125,
            'score_gross_margin_trend': 0.125,
            'score_debt_equity_inverse': 0.125,
            'score_cfo_to_ni': 0.125,
            'score_accruals_inverse': 0.125,
            'score_piotroski_score': 0.125,
            'score_altman_z_score': 0.125
        }
        
        scores_df['composite_score'] = self.composite_score(scores_df, weights)
        
        return scores_df

    def _calculate_piotroski_score(self, ticker: str, fundamentals_data: pd.DataFrame, ratios_data: pd.DataFrame) -> float:
        """Calculate Piotroski F-Score (0-9 points based on 9 binary criteria)."""
        score = 0
        
        # Get latest data
        inc_data = fundamentals_data[(fundamentals_data['ticker'] == ticker) & 
                                   (fundamentals_data['statement_type'] == 'income')]
        bs_data = fundamentals_data[(fundamentals_data['ticker'] == ticker) & 
                                  (fundamentals_data['statement_type'] == 'balance')]
        cf_data = fundamentals_data[(fundamentals_data['ticker'] == ticker) & 
                                 (fundamentals_data['statement_type'] == 'cashflow')]
        
        if inc_data.empty or bs_data.empty or cf_data.empty:
            return 0
            
        latest_inc = inc_data.iloc[-1] if not inc_data.empty else None
        latest_bs = bs_data.iloc[-1] if not bs_data.empty else None
        latest_cf = cf_data.iloc[-1] if not cf_data.empty else None
        
        # Need to pivot to get field:value format
        inc_fields = {}
        bs_fields = {}
        cf_fields = {}
        
        for _, row in inc_data.iterrows():
            inc_fields[row['field']] = row['value']
            
        for _, row in bs_data.iterrows():
            bs_fields[row['field']] = row['value']
            
        for _, row in cf_data.iterrows():
            cf_fields[row['field']] = row['value']
        
        # 1. Positive Return on Assets (ROA)
        if 'Net Income' in inc_fields and 'Total Assets' in bs_fields:
            roa = inc_fields['Net Income'] / bs_fields['Total Assets'] if bs_fields['Total Assets'] != 0 else 0
            if roa > 0:
                score += 1
                
        # 2. Positive Operating Cash Flow
        if 'Operating Cash Flow' in cf_fields and cf_fields['Operating Cash Flow'] > 0:
            score += 1
            
        # 3. Higher ROA this year vs last year
        if len(inc_data) >= 2 and len(bs_data) >= 2:
            prev_inc_idx = max(0, len(inc_data) - 2)
            prev_bs_idx = max(0, len(bs_data) - 2)
            
            prev_inc = inc_data.iloc[prev_inc_idx]
            prev_bs = bs_data.iloc[prev_bs_idx]
            
            prev_inc_fields = {}
            prev_bs_fields = {}
            
            for _, row in inc_data.iloc[[prev_inc_idx]].iterrows():
                prev_inc_fields[row['field']] = row['value']
                
            for _, row in bs_data.iloc[[prev_bs_idx]].iterrows():
                prev_bs_fields[row['field']] = row['value']
                
            if ('Net Income' in inc_fields and 'Total Assets' in bs_fields and 
                'Net Income' in prev_inc_fields and 'Total Assets' in prev_bs_fields):
                curr_roa = inc_fields['Net Income'] / bs_fields['Total Assets'] if bs_fields['Total Assets'] != 0 else 0
                prev_roa = prev_inc_fields['Net Income'] / prev_bs_fields['Total Assets'] if prev_bs_fields['Total Assets'] != 0 else 0
                if curr_roa > prev_roa:
                    score += 1
                    
        # 4. Cash Flow from Operations > Net Income
        if ('Operating Cash Flow' in cf_fields and 'Net Income' in inc_fields and 
            cf_fields['Operating Cash Flow'] > inc_fields['Net Income']):
            score += 1
            
        # 5. Decrease in leverage (long-term)
        if len(bs_data) >= 2:
            prev_bs_idx = max(0, len(bs_data) - 2)
            prev_bs = bs_data.iloc[prev_bs_idx]
            prev_bs_fields = {}
            
            for _, row in bs_data.iloc[[prev_bs_idx]].iterrows():
                prev_bs_fields[row['field']] = row['value']
                
            if ('Long Term Debt And Capital Lease Obligation' in bs_fields and 
                'Total Assets' in bs_fields and 
                'Long Term Debt And Capital Lease Obligation' in prev_bs_fields and 
                'Total Assets' in prev_bs_fields):
                curr_leverage = bs_fields['Long Term Debt And Capital Lease Obligation'] / bs_fields['Total Assets'] if bs_fields['Total Assets'] != 0 else 0
                prev_leverage = prev_bs_fields['Long Term Debt And Capital Lease Obligation'] / prev_bs_fields['Total Assets'] if prev_bs_fields['Total Assets'] != 0 else 0
                if curr_leverage < prev_leverage:
                    score += 1
                    
        # 6. Increase in current ratio
        if ('Current Assets' in bs_fields and 'Current Liabilities' in bs_fields and 
            'Current Assets' in prev_bs_fields and 'Current Liabilities' in prev_bs_fields):
            curr_cr = bs_fields['Current Assets'] / bs_fields['Current Liabilities'] if bs_fields['Current Liabilities'] != 0 else 0
            prev_cr = prev_bs_fields['Current Assets'] / prev_bs_fields['Current Liabilities'] if prev_bs_fields['Current Liabilities'] != 0 else 0
            if curr_cr > prev_cr:
                score += 1
                
        # 7. No increase in shares (no dilution)
        if ('Ordinary Shares Number' in bs_fields and 'Ordinary Shares Number' in prev_bs_fields):
            if bs_fields['Ordinary Shares Number'] <= prev_bs_fields['Ordinary Shares Number']:
                score += 1
                
        # 8. Increase in gross margin
        if 'Gross Profit' in inc_fields and 'Total Revenue' in inc_fields and \
           'Gross Profit' in prev_inc_fields and 'Total Revenue' in prev_inc_fields:
            curr_gm = inc_fields['Gross Profit'] / inc_fields['Total Revenue'] if inc_fields['Total Revenue'] != 0 else 0
            prev_gm = prev_inc_fields['Gross Profit'] / prev_inc_fields['Total Revenue'] if prev_inc_fields['Total Revenue'] != 0 else 0
            if curr_gm > prev_gm:
                score += 1
                
        # 9. Increase in asset turnover
        if ('Total Revenue' in inc_fields and 'Total Assets' in bs_fields and 
            'Total Revenue' in prev_inc_fields and 'Total Assets' in prev_bs_fields):
            curr_at = inc_fields['Total Revenue'] / bs_fields['Total Assets'] if bs_fields['Total Assets'] != 0 else 0
            prev_at = prev_inc_fields['Total Revenue'] / prev_bs_fields['Total Assets'] if prev_bs_fields['Total Assets'] != 0 else 0
            if curr_at > prev_at:
                score += 1
                
        return score

    def _calculate_altman_z_score(self, ticker: str, fundamentals_data: pd.DataFrame, latest_ratios: pd.Series) -> float:
        """Calculate Altman Z-Score."""
        # Z = 1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 0.6*(MktCap/TL) + 1.0*(Sales/TA)
        # Where: WC = Working Capital, TA = Total Assets, RE = Retained Earnings
        # TL = Total Liabilities, Sales = Revenue, MktCap = Market Capitalization
        
        z_score = 0.0
        
        # Get market cap from latest ratios
        shares_outstanding = latest_ratios['shares_outstanding']
        market_cap = None
        if shares_outstanding and pd.notna(shares_outstanding):
            # We would need current price to calculate market cap
            # For now we'll use a simplified calculation with available data
            pass
            
        # Get fundamental data for this ticker
        inc_data = fundamentals_data[(fundamentals_data['ticker'] == ticker) & 
                                   (fundamentals_data['statement_type'] == 'income')]
        bs_data = fundamentals_data[(fundamentals_data['ticker'] == ticker) & 
                                  (fundamentals_data['statement_type'] == 'balance')]
        
        if inc_data.empty or bs_data.empty:
            return 0
            
        # Create field maps
        inc_fields = {}
        bs_fields = {}
        
        for _, row in inc_data.iterrows():
            inc_fields[row['field']] = row['value']
            
        for _, row in bs_data.iterrows():
            bs_fields[row['field']] = row['value']
            
        # Calculate components
        wc_ta = None
        re_ta = None
        ebit_ta = None
        mktcap_tl = None
        sales_ta = None
        
        # 1. Working Capital / Total Assets
        if 'Working Capital' in bs_fields and 'Total Assets' in bs_fields and bs_fields['Total Assets'] != 0:
            wc_ta = bs_fields['Working Capital'] / bs_fields['Total Assets']
            
        # 2. Retained Earnings / Total Assets
        if 'Retained Earnings' in bs_fields and 'Total Assets' in bs_fields and bs_fields['Total Assets'] != 0:
            re_ta = bs_fields['Retained Earnings'] / bs_fields['Total Assets']
            
        # 3. EBIT / Total Assets
        if 'EBIT' in inc_fields and 'Total Assets' in bs_fields and bs_fields['Total Assets'] != 0:
            ebit_ta = inc_fields['EBIT'] / bs_fields['Total Assets']
            
        # 4. Market Cap / Total Liabilities (simplified - using book value)
        if 'Total Liabilities Net Minority Interest' in bs_fields and bs_fields['Total Liabilities Net Minority Interest'] != 0:
            # We don't have market cap, so we'll skip this component
            mktcap_tl = 0
            
        # 5. Sales / Total Assets
        if 'Total Revenue' in inc_fields and 'Total Assets' in bs_fields and bs_fields['Total Assets'] != 0:
            sales_ta = inc_fields['Total Revenue'] / bs_fields['Total Assets']
            
        # Calculate Z-Score
        z_score = 0
        if wc_ta is not None:
            z_score += 1.2 * wc_ta
        if re_ta is not None:
            z_score += 1.4 * re_ta
        if ebit_ta is not None:
            z_score += 3.3 * ebit_ta
        if mktcap_tl is not None:
            z_score += 0.6 * mktcap_tl
        if sales_ta is not None:
            z_score += 1.0 * sales_ta
            
        return z_score


# Convenience function to score quality
def score_quality(universe: pd.DataFrame, db: Any) -> pd.DataFrame:
    """Score all stocks on quality factor."""
    scorer = QualityScorer()
    sub_factors = scorer.calculate_sub_factors(universe, db)
    scores = scorer.score_sub_factors(sub_factors)
    return scores
