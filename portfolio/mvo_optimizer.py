"""
Meridian Capital Partners · portfolio/mvo_optimizer.py
─────────────────────────────────────────────────────────────────
Mean-Variance Optimization portfolio optimizer.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import warnings
from scipy.optimize import minimize
from scipy.linalg import LinAlgError

from .transaction_costs import TransactionCostModel

logger = logging.getLogger("meridian.portfolio.mvo_optimizer")


class MVPOptimizer:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize MVO optimizer with configuration."""
        if config is None:
            config = {}
            
        self.config = config
        self.risk_aversion = config.get("risk_aversion", 1.0)
        self.position_min_pct = config.get("position_min_pct", 0.005)  # 0.5%
        self.position_max_pct = config.get("position_max_pct", 0.05)   # 5%
        self.target_long_gross = config.get("target_long_gross", 1.0)  # 100% long
        self.target_short_gross = config.get("target_short_gross", 1.0)  # 100% short
        self.max_sector_net = config.get("max_sector_net", 0.05)       # 5% sector net
        self.max_sector_side = config.get("max_sector_side", 0.25)     # 25% per side
        self.max_beta_exposure = config.get("max_beta_exposure", 0.15) # Beta exposure limit
        self.covariance_lookback = config.get("covariance_lookback", 120)  # 120-day lookback
        
        self.transaction_cost_model = TransactionCostModel(
            config.get("transaction_costs", {})
        )
        
        logger.info("MVO optimizer initialized with risk_aversion=%f", self.risk_aversion)

    def optimize_portfolio(self, scores: pd.DataFrame, universe: pd.DataFrame, 
                          price_data: pd.DataFrame,
                          current_positions: pd.DataFrame = None,
                          market_data: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Build portfolio using Mean-Variance Optimization.
        
        Args:
            scores: DataFrame with factor scores (includes composite_score column)
            universe: DataFrame with ticker, sector, beta
            price_data: Historical price data for covariance matrix
            current_positions: Current portfolio positions (optional)
            market_data: Market data for transaction costs (optional)
            
        Returns:
            Dict with portfolio weights, metadata, and diagnostics
        """
        if scores.empty or universe.empty:
            logger.warning("Empty input data, returning empty portfolio")
            return self._create_empty_portfolio()
            
        # Merge scores with universe data
        data = scores.merge(universe, on='ticker', how='inner')
        
        if data.empty:
            logger.warning("No overlap between scores and universe, returning empty portfolio")
            return self._create_empty_portfolio()
            
        logger.info(f"Optimizing MVO portfolio with {len(data)} securities")
        
        try:
            # 1. Map scores to expected returns
            expected_returns = self._map_scores_to_returns(data)
            
            # 2. Calculate covariance matrix
            covariance_matrix = self._calculate_covariance_matrix(
                data['ticker'].tolist(), price_data
            )
            
            # 3. Apply transaction costs to expected returns
            if current_positions is not None and market_data is not None:
                expected_returns = self.transaction_cost_model.apply_costs_to_returns(
                    expected_returns, current_positions, market_data
                )
            
            # 4. Set up optimization constraints
            constraints = self._setup_constraints(data)
            
            # 5. Set up bounds
            bounds = self._setup_bounds(len(data))
            
            # 6. Run optimization
            result = self._run_optimization(
                expected_returns, covariance_matrix, constraints, bounds
            )
            
            # 7. Process results
            if result.success:
                portfolio = self._process_optimization_result(
                    result, data, expected_returns, covariance_matrix
                )
                portfolio['optimizer_type'] = 'mvo'
                return portfolio
            else:
                logger.warning("MVO optimization failed: %s", result.message)
                # Fall back to conviction tilt
                logger.info("Falling back to conviction-tilt optimizer")
                from .optimizer import ConvictionOptimizer
                conviction_optimizer = ConvictionOptimizer(self.config)
                return conviction_optimizer.optimize_portfolio(
                    scores, universe, current_positions, market_data
                )
                
        except Exception as e:
            logger.error(f"MVO optimization failed: {e}")
            # Fall back to conviction tilt
            logger.info("Falling back to conviction-tilt optimizer")
            from .optimizer import ConvictionOptimizer
            conviction_optimizer = ConvictionOptimizer(self.config)
            return conviction_optimizer.optimize_portfolio(
                scores, universe, current_positions, market_data
            )

    def _map_scores_to_returns(self, data: pd.DataFrame) -> pd.Series:
        """
        Map composite scores to expected returns.
        Score 100 = +15%/yr, Score 0 = -15%/yr (linear mapping).
        """
        # Linear mapping: return = (score / 100) * 30% - 15%
        # So score 100 -> +15%, score 0 -> -15%
        returns = (data['composite_score'] / 100.0) * 30.0 - 15.0
        return pd.Series(returns.values, index=data['ticker'])

    def _calculate_covariance_matrix(self, tickers: List[str], 
                                   price_data: pd.DataFrame) -> np.ndarray:
        """
        Calculate covariance matrix from historical price data.
        
        Args:
            tickers: List of ticker symbols
            price_data: DataFrame with historical prices (ticker, date, close)
            
        Returns:
            Covariance matrix as numpy array
        """
        # Filter to relevant tickers
        price_subset = price_data[price_data['ticker'].isin(tickers)]
        
        if price_subset.empty:
            logger.warning("No price data for covariance calculation, using identity matrix")
            return np.eye(len(tickers))
        
        # Pivot to wide format
        price_wide = price_subset.pivot(index='date', columns='ticker', values='close')
        
        # Calculate returns
        returns = price_wide.pct_change().dropna()
        
        if len(returns) < 10:  # Minimum observations
            logger.warning("Insufficient return data for covariance, using identity matrix")
            return np.eye(len(tickers))
        
        # Calculate covariance matrix
        cov_matrix = returns.cov().values
        
        # Handle singularity
        try:
            # Add small diagonal to ensure positive definiteness
            cov_matrix += np.eye(cov_matrix.shape[0]) * 1e-8
        except LinAlgError:
            logger.warning("Covariance matrix singular, using diagonal matrix")
            cov_matrix = np.diag(np.diag(cov_matrix))
            
        return cov_matrix

    def _setup_constraints(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Set up optimization constraints."""
        constraints = []
        n_assets = len(data)
        
        # Constraint 1: Long weights sum to target_long_gross
        def long_constraint(w):
            return np.sum(np.maximum(w, 0)) - self.target_long_gross
        
        constraints.append({
            'type': 'eq',
            'fun': long_constraint
        })
        
        # Constraint 2: Short weights sum to target_short_gross
        def short_constraint(w):
            return np.sum(np.maximum(-w, 0)) - self.target_short_gross
        
        constraints.append({
            'type': 'eq',
            'fun': short_constraint
        })
        
        # Constraint 3: Beta exposure limit
        betas = data['beta'].fillna(1.0).values
        def beta_constraint(w):
            return np.abs(np.dot(w, betas)) - self.max_beta_exposure
        
        constraints.append({
            'type': 'ineq',
            'fun': beta_constraint
        })
        
        # Note: Sector constraints would normally be added here
        # For simplicity in this implementation, they're handled post-optimization
        
        return constraints

    def _setup_bounds(self, n_assets: int) -> List[Tuple[float, float]]:
        """Set up weight bounds for each asset."""
        # Bounds: [-max_pct, max_pct] for each asset
        max_weight = self.position_max_pct
        return [(-max_weight, max_weight) for _ in range(n_assets)]

    def _run_optimization(self, expected_returns: pd.Series, 
                         cov_matrix: np.ndarray,
                         constraints: List[Dict[str, Any]], 
                         bounds: List[Tuple[float, float]]) -> Any:
        """
        Run the MVO optimization.
        
        Objective: maximize w'*mu - lambda * w'*Sigma*w
        Which is equivalent to minimizing: lambda * w'*Sigma*w - w'*mu
        """
        n_assets = len(expected_returns)
        
        # Initial guess (equal weight long/short)
        x0 = np.zeros(n_assets)
        
        # Objective function
        def objective(w):
            # Minimize: lambda * w'*Sigma*w - w'*mu
            portfolio_variance = np.dot(w.T, np.dot(cov_matrix, w))
            portfolio_return = np.dot(w, expected_returns.values)
            return self.risk_aversion * portfolio_variance - portfolio_return
            
        # Objective gradient (Jacobian)
        def objective_jac(w):
            # Gradient of: lambda * w'*Sigma*w - w'*mu
            # = 2 * lambda * Sigma * w - mu
            grad_var = 2 * self.risk_aversion * np.dot(cov_matrix, w)
            grad_ret = -expected_returns.values
            return grad_var + grad_ret
            
        try:
            result = minimize(
                objective,
                x0,
                method='SLSQP',
                jac=objective_jac,
                bounds=bounds,
                constraints=constraints,
                options={'maxiter': 1000, 'disp': False}
            )
            return result
        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            # Return failed result
            return type('FailedResult', (), {'success': False, 'message': str(e)})()

    def _process_optimization_result(self, result: Any, data: pd.DataFrame, 
                                   expected_returns: pd.Series, 
                                   cov_matrix: np.ndarray) -> Dict[str, Any]:
        """Process optimization results into portfolio format."""
        weights = result.x
        tickers = data['ticker'].values
        
        # Create positions DataFrame
        positions_df = pd.DataFrame({
            'ticker': tickers,
            'weight': weights,
            'expected_return': expected_returns.values,
            'sector': data['sector'].values
        })
        
        # Add side classification
        positions_df['side'] = np.where(positions_df['weight'] > 0, 'long', 
                                      np.where(positions_df['weight'] < 0, 'short', 'neutral'))
        
        # Apply sector constraints post-optimization if needed
        positions_df = self._apply_sector_constraints(positions_df, data)
        
        # Calculate portfolio statistics
        portfolio_return = np.dot(weights, expected_returns.values)
        portfolio_variance = np.dot(weights.T, np.dot(cov_matrix, weights))
        portfolio_volatility = np.sqrt(portfolio_variance)
        
        sharpe_ratio = portfolio_return / portfolio_volatility if portfolio_volatility > 0 else 0
        
        # Filter out near-zero positions
        positions_df = positions_df[abs(positions_df['weight']) > 1e-6]
        
        return {
            'positions': positions_df.to_dict('records'),
            'portfolio_stats': {
                'expected_return': portfolio_return,
                'volatility': portfolio_volatility,
                'sharpe_ratio': sharpe_ratio,
                'long_gross': positions_df[positions_df['weight'] > 0]['weight'].sum(),
                'short_gross': abs(positions_df[positions_df['weight'] < 0]['weight'].sum()),
                'net_exposure': positions_df['weight'].sum(),
                'total_positions': len(positions_df)
            },
            'optimization_details': {
                'success': result.success,
                'message': result.message,
                'iterations': getattr(result, 'nit', 0)
            }
        }

    def _apply_sector_constraints(self, positions_df: pd.DataFrame, 
                                universe_df: pd.DataFrame) -> pd.DataFrame:
        """Apply sector neutrality constraints to optimized portfolio."""
        positions_df = positions_df.copy()
        
        # Group by sector and check constraints
        sector_groups = positions_df.groupby('sector')
        
        for sector, group in sector_groups:
            sector_net = group['weight'].sum()
            sector_long = group[group['weight'] > 0]['weight'].sum()
            sector_short = abs(group[group['weight'] < 0]['weight'].sum())
            
            # Check sector net constraint (max 5%)
            if abs(sector_net) > self.max_sector_net:
                # Simple proportional scaling
                scale_factor = self.max_sector_net / abs(sector_net)
                positions_df.loc[group.index, 'weight'] *= scale_factor
                
            # Check single-side sector constraint (max 25%)
            if sector_long > self.max_sector_side:
                scale_factor = self.max_sector_side / sector_long
                long_indices = positions_df[(positions_df['sector'] == sector) & 
                                          (positions_df['weight'] > 0)].index
                positions_df.loc[long_indices, 'weight'] *= scale_factor
                
            if sector_short > self.max_sector_side:
                scale_factor = self.max_sector_side / sector_short
                short_indices = positions_df[(positions_df['sector'] == sector) & 
                                           (positions_df['weight'] < 0)].index
                positions_df.loc[short_indices, 'weight'] *= abs(scale_factor)
                
        return positions_df

    def _create_empty_portfolio(self) -> Dict[str, Any]:
        """Create empty portfolio structure."""
        return {
            'positions': [],
            'portfolio_stats': {
                'expected_return': 0.0,
                'volatility': 0.0,
                'sharpe_ratio': 0.0,
                'long_gross': 0.0,
                'short_gross': 0.0,
                'net_exposure': 0.0,
                'total_positions': 0
            },
            'optimization_details': {
                'success': False,
                'message': 'Empty portfolio generated',
                'iterations': 0
            },
            'optimizer_type': 'mvo',
            'warnings': ['Empty portfolio generated']
        }


# Convenience function
def optimize_mvo_portfolio(scores: pd.DataFrame, universe: pd.DataFrame,
                          price_data: pd.DataFrame,
                          current_positions: pd.DataFrame = None,
                          market_data: pd.DataFrame = None,
                          config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Optimize portfolio using Mean-Variance Optimization."""
    optimizer = MVPOptimizer(config or {})
    return optimizer.optimize_portfolio(scores, universe, price_data, 
                                       current_positions, market_data)
