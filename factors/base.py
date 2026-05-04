"""
Meridian Capital Partners · factors/base.py
─────────────────────────────────────────────────────────────────
Base factor scorer with sector-relative percentile ranking.
All factor scores are 0-100 percentiles within GICS sectors.
"""

import logging
import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, List, Any

logger = logging.getLogger("meridian.factors.base")


class BaseFactorScorer(ABC):
    """Abstract base class for factor scorers."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def calculate_sub_factors(self, universe: pd.DataFrame, db: Any) -> pd.DataFrame:
        """
        Calculate sub-factor values for all stocks.
        Should return DataFrame with columns [ticker, sector, sub_factor1, sub_factor2, ...]
        Missing values should be NaN.
        """
        pass

    @abstractmethod
    def score_sub_factors(self, sub_factors_df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert sub-factor values to percentile scores (0-100) within each sector.
        Should return DataFrame with columns [ticker, sector, score_1, score_2, ..., composite_score]
        """
        pass

    def normalize_scores(self, scores: pd.Series) -> pd.Series:
        """Normalize scores to 0-100 range."""
        if scores.empty:
            return pd.Series([], dtype=float)
        
        min_score = scores.min()
        max_score = scores.max()
        
        if min_score == max_score:
            return pd.Series([50.0] * len(scores), index=scores.index)
            
        return (scores - min_score) / (max_score - min_score) * 100

    def calculate_percentile_scores(self, df: pd.DataFrame, value_column: str, ascending: bool = True) -> pd.Series:
        """
        Calculate percentile scores (0-100) for a value column within each sector.
        
        Args:
            df: DataFrame with 'sector' and value_column
            value_column: column name to score
            ascending: True if higher values are better, False if lower values are better
            
        Returns:
            Series of percentile scores indexed by original DataFrame index
        """
        if df.empty:
            return pd.Series([], dtype=float)
            
        scores = pd.Series(index=df.index, dtype=float)
        
        for sector in df['sector'].unique():
            sector_mask = df['sector'] == sector
            sector_data = df[sector_mask]
            
            if sector_data.empty:
                continue
                
            values = sector_data[value_column]
            valid_mask = pd.notna(values)
            
            if valid_mask.sum() == 0:
                continue
                
            # Rank values (percentile calculation)
            sector_values = values[valid_mask]
            if ascending:
                # Higher values get higher percentiles
                ranks = sector_values.rank(method='average', pct=True) * 100
            else:
                # Lower values get higher percentiles (like P/E ratios)
                ranks = (1 - sector_values.rank(method='average', pct=True)) * 100
                
            scores.loc[sector_values.index] = ranks
            
        return scores

    def composite_score(self, df: pd.DataFrame, weights: Dict[str, float]) -> pd.Series:
        """
        Calculate weighted composite score from individual sub-factor scores.
        
        Args:
            df: DataFrame with sub-factor score columns
            weights: dict mapping column names to weights (must sum to 1.0)
            
        Returns:
            Series of composite scores
        """
        if df.empty:
            return pd.Series([], dtype=float)
            
        # Normalize weights to sum to 1.0
        total_weight = sum(weights.values())
        if total_weight == 0:
            weights = {k: 1.0/len(weights) for k in weights}
        else:
            weights = {k: v/total_weight for k, v in weights.items()}
            
        # Calculate weighted sum
        composite = pd.Series(0.0, index=df.index)
        for col, weight in weights.items():
            if col in df.columns and weight > 0:
                valid_scores = df[col].fillna(0)  # Fill NaN with 0 to avoid dropping
                composite += valid_scores * weight
                
        return composite
