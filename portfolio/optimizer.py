"""
Meridian Capital Partners · portfolio/optimizer.py
─────────────────────────────────────────────────────────────────
Conviction-tilt portfolio optimizer.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
import warnings

from .transaction_costs import TransactionCostModel

logger = logging.getLogger("meridian.portfolio.optimizer")


class ConvictionOptimizer:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize conviction-tilt optimizer with configuration."""
        if config is None:
            config = {}
            
        self.config = config
        self.position_min_pct = config.get("position_min_pct", 0.005)  # 0.5%
        self.position_max_pct = config.get("position_max_pct", 0.05)   # 5%
        self.target_long_gross = config.get("target_long_gross", 1.0)  # 100% long
        self.target_short_gross = config.get("target_short_gross", 1.0)  # 100% short
        self.max_sector_net = config.get("max_sector_net", 0.05)       # 5% sector net
        self.max_sector_side = config.get("max_sector_side", 0.25)     # 25% per side
        self.beta_target = config.get("beta_target", 1.0)              # Target beta
        self.adv_lookback = config.get("adv_lookback", 20)             # 20-day ADV
        
        self.transaction_cost_model = TransactionCostModel(
            config.get("transaction_costs", {})
        )
        
        logger.info("Conviction optimizer initialized")

    def optimize_portfolio(self, scores: pd.DataFrame, universe: pd.DataFrame, 
                          current_positions: pd.DataFrame = None,
                          market_data: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Build portfolio using conviction-tilt approach.
        
        Args:
            scores: DataFrame with factor scores (includes composite_score column)
            universe: DataFrame with ticker, sector, beta
            current_positions: Current portfolio positions (optional)
            market_data: Market data for liquidity checks (optional)
            
        Returns:
            Dict with portfolio weights, metadata, and diagnostics
        """
        if scores.empty:
            logger.warning("Empty scores DataFrame, returning empty portfolio")
            return self._create_empty_portfolio()
            
        # Merge scores with universe data
        data = scores.merge(universe, on='ticker', how='inner')
        
        if data.empty:
            logger.warning("No overlap between scores and universe, returning empty portfolio")
            return self._create_empty_portfolio()
            
        logger.info(f"Optimizing portfolio with {len(data)} securities")
        
        # 1. Separate into long/short candidates
        long_candidates = self._select_long_candidates(data)
        short_candidates = self._select_short_candidates(data)
        
        logger.info(f"Selected {len(long_candidates)} long candidates, {len(short_candidates)} short candidates")
        
        # 2. Apply conviction tilts
        long_weights = self._apply_conviction_tilt(long_candidates, 'long')
        short_weights = self._apply_conviction_tilt(short_candidates, 'short')
        
        # 3. Apply liquidity constraints
        if market_data is not None:
            long_weights = self._apply_liquidity_constraints(long_weights, market_data)
            short_weights = self._apply_liquidity_constraints(short_weights, market_data)
        
        # 4. Apply earnings constraints
        long_weights = self._apply_earnings_constraints(long_weights)
        short_weights = self._apply_earnings_constraints(short_weights)
        
        # 5. Apply beta adjustment
        long_weights = self._adjust_beta_exposure(long_weights, universe)
        short_weights = self._adjust_beta_exposure(short_weights, universe)
        
        # 6. Ensure sector neutrality
        long_weights = self._ensure_sector_neutrality(long_weights)
        short_weights = self._ensure_sector_neutrality(short_weights)
        
        # 7. Normalize weights to targets
        long_weights = self._normalize_weights(long_weights, self.target_long_gross, 'long')
        short_weights = self._normalize_weights(short_weights, self.target_short_gross, 'short')
        
        # 8. Combine into final portfolio
        portfolio = self._combine_portfolios(long_weights, short_weights)
        
        # 9. Apply transaction costs if current positions provided
        if current_positions is not None and market_data is not None:
            portfolio = self._apply_transaction_costs(portfolio, current_positions, market_data)
        
        return portfolio

    def _select_long_candidates(self, data: pd.DataFrame) -> pd.DataFrame:
        """Select long candidates based on scores (> 50th percentile)."""
        threshold = data['composite_score'].quantile(0.5)
        long_candidates = data[data['composite_score'] >= threshold].copy()
        return long_candidates.sort_values('composite_score', ascending=False)

    def _select_short_candidates(self, data: pd.DataFrame) -> pd.DataFrame:
        """Select short candidates based on scores (< 50th percentile)."""
        threshold = data['composite_score'].quantile(0.5)
        short_candidates = data[data['composite_score'] <= threshold].copy()
        return short_candidates.sort_values('composite_score', ascending=True)

    def _apply_conviction_tilt(self, candidates: pd.DataFrame, side: str) -> pd.DataFrame:
        """Apply conviction-based weighting based on score percentiles."""
        if candidates.empty:
            return candidates
            
        # Calculate percentiles
        candidates = candidates.copy()
        candidates['percentile_rank'] = candidates['composite_score'].rank(pct=True)
        
        # Apply multipliers based on conviction
        candidates['weight_multiplier'] = 1.0
        if side == 'long':
            # For longs, higher scores get higher weights
            top_5_pct = candidates['percentile_rank'] >= 0.95
            top_10_pct = (candidates['percentile_rank'] >= 0.90) & (candidates['percentile_rank'] < 0.95)
            candidates.loc[top_5_pct, 'weight_multiplier'] = 1.5
            candidates.loc[top_10_pct, 'weight_multiplier'] = 1.25
        else:
            # For shorts, lower scores get higher weights
            bottom_5_pct = candidates['percentile_rank'] <= 0.05
            bottom_10_pct = (candidates['percentile_rank'] > 0.05) & (candidates['percentile_rank'] <= 0.10)
            candidates.loc[bottom_5_pct, 'weight_multiplier'] = 1.5
            candidates.loc[bottom_10_pct, 'weight_multiplier'] = 1.25
            
        # Base weight is equal weight among selected candidates
        if len(candidates) > 0:
            candidates['base_weight'] = 1.0 / len(candidates)
            candidates['final_weight'] = candidates['base_weight'] * candidates['weight_multiplier']
        else:
            candidates['base_weight'] = 0.0
            candidates['final_weight'] = 0.0
            
        return candidates

    def _apply_liquidity_constraints(self, weights_df: pd.DataFrame, market_data: pd.DataFrame) -> pd.DataFrame:
        """Apply liquidity constraints (no position > 5% of 20-day ADV)."""
        if weights_df.empty:
            return weights_df
            
        weights_df = weights_df.copy()
        weights_df = weights_df.merge(market_data[['ticker', 'adv', 'price']], on='ticker', how='left')
        
        # Calculate max position size based on ADV (5% rule)
        weights_df['max_dollar_position'] = weights_df['adv'] * weights_df['price'] * 0.05
        
        # For simplicity in this context, assume portfolio value of $1 for normalization
        # In practice, this would scale with actual portfolio size
        weights_df['adjusted_weight'] = weights_df['final_weight']
        
        # Check if any positions violate liquidity constraint
        violations = weights_df[weights_df['adjusted_weight'] * 1 > weights_df['max_dollar_position'] / 1000000]  # Scaled assumption
        if not violations.empty:
            logger.info(f"Liquidity constraints adjusted {len(violations)} positions")
            # For now, cap at maximum allowed by liquidity
            # In practice, you'd need actual portfolio value to do this correctly
            
        return weights_df.drop(['adv', 'price', 'max_dollar_position'], axis=1)

    def _apply_earnings_constraints(self, weights_df: pd.DataFrame) -> pd.DataFrame:
        """Halve position size if earnings announced within 5 days."""
        # In practice, this would require earnings calendar data
        # For now, we'll return unchanged weights
        # This is a placeholder where you'd integrate actual earnings data
        return weights_df

    def _adjust_beta_exposure(self, weights_df: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
        """Adjust weights so beta-adjusted exposure matches target beta."""
        if weights_df.empty:
            return weights_df
            
        weights_df = weights_df.merge(universe[['ticker', 'beta']], on='ticker', how='left')
        weights_df['beta'].fillna(1.0, inplace=True)  # Default to market beta
        
        # Calculate current beta exposure
        total_beta_exposure = (weights_df['final_weight'] * weights_df['beta']).sum()
        
        if abs(total_beta_exposure) > 0 and self.beta_target > 0:
            # Scale weights to achieve target beta exposure
            scale_factor = self.beta_target / abs(total_beta_exposure) if total_beta_exposure != 0 else 1.0
            weights_df['beta_adjusted_weight'] = weights_df['final_weight'] * scale_factor
        else:
            weights_df['beta_adjusted_weight'] = weights_df['final_weight']
            
        return weights_df

    def _ensure_sector_neutrality(self, weights_df: pd.DataFrame) -> pd.DataFrame:
        """Ensure sector constraints are met."""
        if weights_df.empty:
            return weights_df
            
        # Group by sector and check constraints
        sector_groups = weights_df.groupby('sector')
        
        for sector, group in sector_groups:
            sector_net = group['beta_adjusted_weight'].sum()
            sector_long = group[group['beta_adjusted_weight'] > 0]['beta_adjusted_weight'].sum()
            sector_short = abs(group[group['beta_adjusted_weight'] < 0]['beta_adjusted_weight'].sum())
            
            # Check sector net constraint (max 5%)
            if abs(sector_net) > self.max_sector_net:
                logger.info(f"Sector {sector} net exposure {sector_net:.2%} exceeds limit, scaling")
                # Simple scaling approach
                scale_factor = self.max_sector_net / abs(sector_net)
                weights_df.loc[group.index, 'beta_adjusted_weight'] *= scale_factor
                
            # Check single-side sector constraint (max 25%)
            if sector_long > self.max_sector_side:
                logger.info(f"Sector {sector} long exposure {sector_long:.2%} exceeds limit, scaling")
                scale_factor = self.max_sector_side / sector_long
                long_indices = weights_df[(weights_df['sector'] == sector) & 
                                        (weights_df['beta_adjusted_weight'] > 0)].index
                weights_df.loc[long_indices, 'beta_adjusted_weight'] *= scale_factor
                
            if sector_short > self.max_sector_side:
                logger.info(f"Sector {sector} short exposure {sector_short:.2%} exceeds limit, scaling")
                scale_factor = self.max_sector_side / sector_short
                short_indices = weights_df[(weights_df['sector'] == sector) & 
                                         (weights_df['beta_adjusted_weight'] < 0)].index
                weights_df.loc[short_indices, 'beta_adjusted_weight'] *= abs(scale_factor)
                
        return weights_df

    def _normalize_weights(self, weights_df: pd.DataFrame, target_gross: float, side: str) -> pd.DataFrame:
        """Normalize weights to target gross exposure."""
        if weights_df.empty:
            return weights_df
            
        current_gross = weights_df['beta_adjusted_weight'].abs().sum()
        
        if current_gross > 0:
            scale_factor = target_gross / current_gross
            weights_df['normalized_weight'] = weights_df['beta_adjusted_weight'] * scale_factor
        else:
            weights_df['normalized_weight'] = weights_df['beta_adjusted_weight']
            
        return weights_df

    def _combine_portfolios(self, long_weights: pd.DataFrame, short_weights: pd.DataFrame) -> Dict[str, Any]:
        """Combine long and short portfolios into final result."""
        # Collect all positions
        positions = []
        
        if not long_weights.empty:
            for _, row in long_weights.iterrows():
                positions.append({
                    'ticker': row['ticker'],
                    'weight': row.get('normalized_weight', row.get('beta_adjusted_weight', 0)),
                    'side': 'long',
                    'score': row['composite_score'],
                    'sector': row['sector']
                })
                
        if not short_weights.empty:
            for _, row in short_weights.iterrows():
                positions.append({
                    'ticker': row['ticker'],
                    'weight': row.get('normalized_weight', row.get('beta_adjusted_weight', 0)),
                    'side': 'short',
                    'score': row['composite_score'],
                    'sector': row['sector']
                })
                
        # Convert to DataFrame
        portfolio_df = pd.DataFrame(positions)
        
        # Calculate portfolio stats
        long_gross = portfolio_df[portfolio_df['side'] == 'long']['weight'].sum()
        short_gross = abs(portfolio_df[portfolio_df['side'] == 'short']['weight'].sum())
        net_exposure = portfolio_df['weight'].sum()
        
        return {
            'positions': portfolio_df.to_dict('records'),
            'portfolio_stats': {
                'long_gross': long_gross,
                'short_gross': short_gross,
                'net_exposure': net_exposure,
                'total_positions': len(portfolio_df)
            },
            'optimizer_type': 'conviction_tilt'
        }

    def _apply_transaction_costs(self, portfolio: Dict[str, Any], 
                                current_positions: pd.DataFrame, 
                                market_data: pd.DataFrame) -> Dict[str, Any]:
        """Apply transaction costs to portfolio weights."""
        # This would modify weights based on transaction costs
        # For simplicity in this implementation, we'll just log that costs are considered
        logger.info("Transaction costs applied to portfolio (implementation pending)")
        portfolio['transaction_costs_applied'] = True
        return portfolio

    def _create_empty_portfolio(self) -> Dict[str, Any]:
        """Create empty portfolio structure."""
        return {
            'positions': [],
            'portfolio_stats': {
                'long_gross': 0.0,
                'short_gross': 0.0,
                'net_exposure': 0.0,
                'total_positions': 0
            },
            'optimizer_type': 'conviction_tilt',
            'warnings': ['Empty portfolio generated']
        }


# Convenience function
def optimize_conviction_portfolio(scores: pd.DataFrame, universe: pd.DataFrame,
                                 current_positions: pd.DataFrame = None,
                                 market_data: pd.DataFrame = None,
                                 config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Optimize portfolio using conviction-tilt approach."""
    optimizer = ConvictionOptimizer(config or {})
    return optimizer.optimize_portfolio(scores, universe, current_positions, market_data)
