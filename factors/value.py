"""
Meridian Capital Partners · factors/value.py
─────────────────────────────────────────────────────────────────
Factor 2/8 — Value (6 sub-factors)
All scores are 0-100 percentile ranks within GICS sectors.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import BaseFactorScorer

logger = logging.getLogger("meridian.factors.value")


class ValueScorer(BaseFactorScorer):
    def __init__(self):
        super().__init__("Value")

    def calculate_sub_factors(self, universe: pd.DataFrame, db: Any) -> pd.DataFrame:
        """
        Calculate value sub-factors:
        1. Forward earnings yield (1/forward P/E)
        2. Book-to-price
        3. FCF yield
        4. EV/EBITDA (invert for scoring)
        5. Shareholder yield (TTM buybacks + dividends / mkt cap)
        6. Sales-to-EV (revenue / EV)
        """
        logger.info("Calculating value sub-factors...")
        
        # Get latest fundamental data and price data
        query = """
        SELECT ticker, period, field, value 
        FROM fundamentals 
        WHERE period IN (
            SELECT MAX(period) 
            FROM fundamentals f2 
            WHERE f2.ticker = fundamentals.ticker 
            AND f2.statement_type = 'income'
        )
        AND statement_type = 'income'
        """
        fundamentals_data = pd.read_sql_query(query, db._connect())
        
        # Get latest balance sheet data
        bs_query = """
        SELECT ticker, period, field, value 
        FROM fundamentals 
        WHERE period IN (
            SELECT MAX(period) 
            FROM fundamentals f2 
            WHERE f2.ticker = fundamentals.ticker 
            AND f2.statement_type = 'balance'
        )
        AND statement_type = 'balance'
        """
        balance_data = pd.read_sql_query(bs_query, db._connect())
        
        # Get derived ratios
        ratios_query = """
        SELECT ticker, period, 
               fcf_yield, shares_outstanding, dividends_paid, buybacks
        FROM derived_ratios 
        WHERE period IN (
            SELECT MAX(period) 
            FROM derived_ratios dr2 
            WHERE dr2.ticker = derived_ratios.ticker
        )
        """
        ratios_data = pd.read_sql_query(ratios_query, db._connect())
        
        # Get latest market cap data (needed for some calculations)
        price_query = """
        SELECT dp.ticker, dp.close, u.gics_sector,
               dr.shares_outstanding
        FROM daily_prices dp
        JOIN universe u ON dp.ticker = u.ticker
        LEFT JOIN derived_ratios dr ON dp.ticker = dr.ticker AND dr.period IN (
            SELECT MAX(period) FROM derived_ratios dr2 WHERE dr2.ticker = dr.ticker
        )
        WHERE dp.date = (SELECT MAX(date) FROM daily_prices)
        """
        price_data = pd.read_sql_query(price_query, db._connect())
        
        if fundamentals_data.empty or price_data.empty:
            logger.warning("Missing data for value calculation")
            return pd.DataFrame(columns=['ticker', 'sector', 'earnings_yield', 'book_to_price', 
                                       'fcf_yield', 'ev_ebitda', 'shareholder_yield', 'sales_to_ev'])
        
        results = []
        
        for _, row in price_data.iterrows():
            ticker = row['ticker']
            sector = row['gics_sector']
            current_price = row['close']
            shares_outstanding = row['shares_outstanding']
            
            if not current_price or current_price <= 0:
                continue
                
            market_cap = current_price * shares_outstanding if shares_outstanding else None
            
            # Get income statement data for this ticker
            inc_data = fundamentals_data[fundamentals_data['ticker'] == ticker]
            if inc_data.empty:
                continue
                
            # Get balance sheet data for this ticker
            bs_data = balance_data[balance_data['ticker'] == ticker]
            
            # Get derived ratios for this ticker
            ratio_data = ratios_data[ratios_data['ticker'] == ticker]
            if ratio_data.empty:
                continue
                
            latest_ratio = ratio_data.iloc[0]
            
            # Extract key metrics
            net_income = self._get_field_value(inc_data, 'Net Income')
            ebit = self._get_field_value(inc_data, 'EBIT') or net_income  # fallback to net income
            revenue = self._get_field_value(inc_data, 'Total Revenue')
            
            # Balance sheet items for EV calculation
            total_debt = None
            total_cash = None
            book_value = None
            
            if not bs_data.empty:
                total_debt = self._get_field_value(bs_data, 'Total Debt')
                cash_and_equivalents = self._get_field_value(bs_data, 'Cash And Cash Equivalents') or \
                                     self._get_field_value(bs_data, 'Cash Financial')
                total_cash = cash_and_equivalents
                book_value = self._get_field_value(bs_data, 'Total Equity Gross Minority Interest') or \
                           self._get_field_value(bs_data, 'Stockholders Equity')
            
            # Enterprise Value = Market Cap + Total Debt - Cash
            ev = None
            if market_cap is not None:
                ev_components = [market_cap]
                if total_debt is not None:
                    ev_components.append(total_debt)
                if total_cash is not None:
                    ev_components.append(-total_cash)
                ev = sum(ev_components) if all(x is not None for x in ev_components) else None
            
            # Calculate sub-factors
            
            # 1. Earnings yield (inverse of P/E)
            earnings_yield = None
            if net_income is not None and market_cap is not None and market_cap > 0:
                pe_ratio = market_cap / net_income if net_income != 0 else None
                if pe_ratio is not None and pe_ratio > 0:
                    earnings_yield = 1 / pe_ratio
                    
            # 2. Book-to-price
            book_to_price = None
            if book_value is not None and market_cap is not None and market_cap > 0:
                book_to_price = book_value / market_cap
                
            # 3. FCF yield
            fcf_yield = latest_ratio['fcf_yield'] if not pd.isna(latest_ratio['fcf_yield']) else None
            
            # 4. EV/EBITDA (we'll invert this for scoring)
            ev_ebitda = None
            if ev is not None and ebit is not None and ebit != 0:
                # We need EBITDA = EBIT + Depreciation & Amortization
                depreciation = self._get_field_value(inc_data, 'Depreciation & Amortization') or \
                             self._get_field_value(inc_data, 'Depreciation And Amortization')
                ebitda = ebit + depreciation if depreciation is not None else ebit
                if ebitda is not None and ebitda != 0:
                    ev_ebitda = ev / ebitda
                    
            # 5. Shareholder yield (TTM buybacks + dividends / market cap)
            shareholder_yield = None
            if market_cap is not None and market_cap > 0:
                dividends = latest_ratio['dividends_paid'] if not pd.isna(latest_ratio['dividends_paid']) else 0
                buybacks = latest_ratio['buybacks'] if not pd.isna(latest_ratio['buybacks']) else 0
                total_returns = (abs(dividends) + abs(buybacks)) if dividends is not None and buybacks is not None else 0
                shareholder_yield = total_returns / market_cap if total_returns > 0 else None
                
            # 6. Sales-to-EV
            sales_to_ev = None
            if revenue is not None and ev is not None and ev > 0:
                sales_to_ev = revenue / ev
                
            results.append({
                'ticker': ticker,
                'sector': sector,
                'earnings_yield': earnings_yield,
                'book_to_price': book_to_price,
                'fcf_yield': fcf_yield,
                'ev_ebitda': ev_ebitda,
                'shareholder_yield': shareholder_yield,
                'sales_to_ev': sales_to_ev
            })
        
        result_df = pd.DataFrame(results)
        logger.info(f"Value sub-factors calculated for {len(result_df)} tickers")
        return result_df

    def score_sub_factors(self, sub_factors_df: pd.DataFrame) -> pd.DataFrame:
        """Convert value sub-factors to percentile scores (0-100) within each sector."""
        if sub_factors_df.empty:
            return pd.DataFrame()
            
        scores_df = sub_factors_df[['ticker', 'sector']].copy()
        
        # Score each sub-factor (higher is better for all value metrics)
        # Note: For ratios like P/E, we want lower values = higher scores, so we use ascending=False
        scores_df['score_earnings_yield'] = self.calculate_percentile_scores(sub_factors_df, 'earnings_yield', ascending=True)
        scores_df['score_book_to_price'] = self.calculate_percentile_scores(sub_factors_df, 'book_to_price', ascending=True)
        scores_df['score_fcf_yield'] = self.calculate_percentile_scores(sub_factors_df, 'fcf_yield', ascending=True)
        scores_df['score_ev_ebitda'] = self.calculate_percentile_scores(sub_factors_df, 'ev_ebitda', ascending=False)  # Lower EV/EBITDA is better
        scores_df['score_shareholder_yield'] = self.calculate_percentile_scores(sub_factors_df, 'shareholder_yield', ascending=True)
        scores_df['score_sales_to_ev'] = self.calculate_percentile_scores(sub_factors_df, 'sales_to_ev', ascending=True)
        
        # Composite score (equal weights)
        weights = {
            'score_earnings_yield': 0.1667,
            'score_book_to_price': 0.1667,
            'score_fcf_yield': 0.1667,
            'score_ev_ebitda': 0.1667,
            'score_shareholder_yield': 0.1667,
            'score_sales_to_ev': 0.1667
        }
        
        scores_df['composite_score'] = self.composite_score(scores_df, weights)
        
        return scores_df

    def _get_field_value(self, df: pd.DataFrame, field_name: str) -> float:
        """Extract a field value from fundamentals DataFrame."""
        field_row = df[df['field'] == field_name]
        if not field_row.empty:
            value = field_row.iloc[0]['value']
            return value if not pd.isna(value) else None
        return None


# Convenience function to score value
def score_value(universe: pd.DataFrame, db: Any) -> pd.DataFrame:
    """Score all stocks on value factor."""
    scorer = ValueScorer()
    sub_factors = scorer.calculate_sub_factors(universe, db)
    scores = scorer.score_sub_factors(sub_factors)
    return scores
