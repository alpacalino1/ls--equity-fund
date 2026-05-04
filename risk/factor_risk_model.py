"""
Meridian Capital Partners · risk/factor_risk_model.py
─────────────────────────────────────────────────────────────────
Barra-style factor risk model for portfolio risk decomposition.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from scipy.linalg import LinAlgError
import warnings

logger = logging.getLogger("meridian.risk.factor_model")


class FactorRiskModel:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize factor risk model with configuration."""
        if config is None:
            config = {}
            
        self.lookback_days = config.get("lookback_days", 120)
        self.factor_weights = config.get("factor_weights", {})
        self.aum = config.get("aum", 100_000_000)  # Default $100M AUM
        
        logger.info(f"Factor risk model initialized with {self.lookback_days}-day lookback")

    def build_factor_model(self, factor_data: pd.DataFrame, price_data: pd.DataFrame, 
                          market_data: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Build Barra-style factor risk model.
        
        Args:
            factor_data: DataFrame with factor exposures for stocks
            price_data: Historical price data for returns calculation
            market_data: Additional market data (optional)
            
        Returns:
            Dict with factor returns, covariance matrix, and specific variance
        """
        if factor_data.empty or price_data.empty:
            logger.warning("Empty input data for factor model")
            return self._create_empty_model()
            
        logger.info(f"Building factor risk model with {len(factor_data)} stocks")
        
        try:
            # 1. Calculate stock returns
            returns_data = self._calculate_returns(price_data)
            
            # 2. Prepare factor exposures (z-scored sector ranks)
            factor_exposures = self._prepare_factor_exposures(factor_data)
            
            # 3. Run cross-sectional regression for each day
            regression_results = self._run_factor_regression(returns_data, factor_exposures)
            
            # 4. Calculate factor returns and covariance
            factor_returns = regression_results['factor_returns']
            factor_cov_matrix = self._calculate_factor_covariance(factor_returns)
            
            # 5. Calculate specific variance
            specific_variance = regression_results['specific_variance']
            
            return {
                'factor_returns': factor_returns,
                'factor_covariance': factor_cov_matrix,
                'specific_variance': specific_variance,
                'factor_exposures': factor_exposures,
                'model_dates': returns_data.index.tolist(),
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Factor model construction failed: {e}")
            return self._create_empty_model(error=str(e))

    def _calculate_returns(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """Calculate daily returns from price data."""
        # Pivot to wide format
        price_wide = price_data.pivot(index='date', columns='ticker', values='close')
        
        # Calculate daily returns
        returns = price_wide.pct_change().dropna()
        
        # Limit to lookback period
        if len(returns) > self.lookback_days:
            returns = returns.tail(self.lookback_days)
            
        logger.info(f"Calculated returns for {len(returns)} days, {len(returns.columns)} stocks")
        return returns

    def _prepare_factor_exposures(self, factor_data: pd.DataFrame) -> pd.DataFrame:
        """Prepare factor exposures (z-scored within sectors)."""
        if factor_data.empty:
            return pd.DataFrame()
            
        # Select key factor columns (excluding metadata)
        factor_columns = [col for col in factor_data.columns if col.endswith('_score') and col != 'composite_score']
        
        if not factor_columns:
            # If no individual factor scores, use composite score
            factor_columns = ['composite_score']
            
        # Merge with sector data if not already present
        exposure_data = factor_data.copy()
        
        # Z-score each factor within sectors
        for factor_col in factor_columns:
            if factor_col in exposure_data.columns:
                # Standardize within each sector
                exposure_data[f'{factor_col}_z'] = exposure_data.groupby('sector')[factor_col].transform(
                    lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0
                )
            else:
                exposure_data[f'{factor_col}_z'] = 0
                
        # Select standardized factors
        z_factor_columns = [f'{col}_z' for col in factor_columns]
        final_columns = ['ticker', 'sector'] + z_factor_columns
        
        # Keep only needed columns
        result = exposure_data[final_columns].copy()
        
        logger.info(f"Prepared factor exposures for {len(result)} stocks with {len(z_factor_columns)} factors")
        return result

    def _run_factor_regression(self, returns_data: pd.DataFrame, 
                              factor_exposures: pd.DataFrame) -> Dict[str, Any]:
        """
        Run cross-sectional regression to estimate factor returns.
        
        r_i,t = alpha_t + sum_k beta_k,t * F_k,i + epsilon_i,t
        """
        if returns_data.empty or factor_exposures.empty:
            return {
                'factor_returns': pd.DataFrame(),
                'specific_variance': pd.Series(dtype=float)
            }
            
        # Merge returns with factor exposures
        factor_cols = [col for col in factor_exposures.columns if col.endswith('_z')]
        
        # Store results
        factor_returns_list = []
        specific_variances = {}
        
        # Run regression for each date
        for date in returns_data.index:
            daily_returns = returns_data.loc[date]
            # Remove stocks with missing returns
            valid_returns = daily_returns.dropna()
            
            if len(valid_returns) < 10:  # Minimum stocks for meaningful regression
                continue
                
            # Get factor exposures for valid stocks
            valid_tickers = valid_returns.index.tolist()
            daily_exposures = factor_exposures[factor_exposures['ticker'].isin(valid_tickers)]
            
            if len(daily_exposures) < len(valid_tickers):
                # Some stocks missing factor data
                valid_tickers = daily_exposures['ticker'].tolist()
                valid_returns = valid_returns[valid_tickers]
                
            if len(valid_tickers) < 10:
                continue
                
            # Prepare matrices for regression
            X = daily_exposures[factor_cols].values  # Factor exposures
            y = valid_returns.values  # Returns
            
            try:
                # Add intercept term
                X_with_intercept = np.column_stack([np.ones(len(X)), X])
                
                # Solve: beta = (X'X)^(-1)X'y
                beta = np.linalg.solve(X_with_intercept.T @ X_with_intercept, X_with_intercept.T @ y)
                
                # Extract factor returns (skip intercept)
                factor_returns_today = pd.Series(beta[1:], index=[col.replace('_z', '') for col in factor_cols])
                factor_returns_list.append(factor_returns_today)
                
                # Calculate residuals (specific returns)
                fitted = X_with_intercept @ beta
                residuals = y - fitted
                specific_var = np.var(residuals) * 252  # Annualized
                
                # Store specific variance for each stock (simplified)
                for i, ticker in enumerate(valid_tickers):
                    if ticker not in specific_variances:
                        specific_variances[ticker] = []
                    specific_variances[ticker].append(residuals[i]**2)
                    
            except LinAlgError as e:
                logger.warning(f"Regression failed for {date}: {e}")
                continue
            except Exception as e:
                logger.warning(f"Regression error for {date}: {e}")
                continue
                
        # Aggregate results
        if factor_returns_list:
            factor_returns_df = pd.DataFrame(factor_returns_list, index=returns_data.index[:len(factor_returns_list)])
        else:
            factor_returns_df = pd.DataFrame()
            
        # Calculate average specific variance per stock
        specific_variance_series = pd.Series({
            ticker: np.mean(vars) * 252 if vars else 0  # Annualized
            for ticker, vars in specific_variances.items()
        })
        
        return {
            'factor_returns': factor_returns_df,
            'specific_variance': specific_variance_series
        }

    def _calculate_factor_covariance(self, factor_returns: pd.DataFrame) -> np.ndarray:
        """Calculate annualized factor covariance matrix."""
        if factor_returns.empty:
            logger.warning("Empty factor returns, returning identity matrix")
            return np.eye(0)
            
        # Calculate covariance matrix
        cov_matrix = factor_returns.cov()
        
        # Annualize (252 trading days)
        annualized_cov = cov_matrix * 252
        
        logger.info(f"Calculated factor covariance matrix: {cov_matrix.shape}")
        return annualized_cov.values if hasattr(annualized_cov, 'values') else annualized_cov

    def calculate_portfolio_risk(self, portfolio_weights: pd.Series, 
                                factor_model: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate portfolio risk using factor model.
        
        factor_var = w'XFX'w, specific_var = sum(w_i^2 * spec_var_i)
        total_var = factor_var + specific_var
        """
        if portfolio_weights.empty or not factor_model.get('status') == 'success':
            return {
                'factor_variance': 0.0,
                'specific_variance': 0.0,
                'total_variance': 0.0,
                'total_volatility': 0.0,
                'sharpe_ratio': 0.0
            }
            
        try:
            # Extract model components
            factor_cov = factor_model['factor_covariance']
            specific_var = factor_model['specific_variance']
            factor_exposures = factor_model['factor_exposures']
            
            if factor_cov.size == 0 or specific_var.empty:
                return {
                    'factor_variance': 0.0,
                    'specific_variance': 0.0,
                    'total_variance': 0.0,
                    'total_volatility': 0.0,
                    'sharpe_ratio': 0.0
                }
            
            # Align weights with factor exposures
            weights_aligned = portfolio_weights.reindex(factor_exposures['ticker']).fillna(0)
            
            # Get factor exposures for portfolio stocks
            factor_cols = [col for col in factor_exposures.columns if col.endswith('_z')]
            if not factor_cols:
                factor_cols = [col for col in factor_exposures.columns if '_score_z' in col]
                
            if not factor_cols:
                # Create unit exposure if no factors
                X = np.ones((len(weights_aligned), 1))
            else:
                X = factor_exposures.set_index('ticker')[factor_cols].reindex(weights_aligned.index).fillna(0).values
            
            # Calculate factor variance: w'XFX'w
            w = weights_aligned.values
            factor_variance = w.T @ X @ factor_cov @ X.T @ w if factor_cov.shape[0] > 0 else 0
            
            # Calculate specific variance: sum(w_i^2 * spec_var_i)
            specific_variance = 0.0
            for ticker, weight in weights_aligned.items():
                if ticker in specific_var.index:
                    specific_variance += weight**2 * specific_var[ticker]
                    
            total_variance = factor_variance + specific_variance
            total_volatility = np.sqrt(total_variance) if total_variance > 0 else 0
            
            return {
                'factor_variance': factor_variance,
                'specific_variance': specific_variance,
                'total_variance': total_variance,
                'total_volatility': total_volatility,
                'sharpe_ratio': 0.0  # Would need expected returns to calculate
            }
            
        except Exception as e:
            logger.error(f"Portfolio risk calculation failed: {e}")
            return {
                'factor_variance': 0.0,
                'specific_variance': 0.0,
                'total_variance': 0.0,
                'total_volatility': 0.0,
                'sharpe_ratio': 0.0,
                'error': str(e)
            }

    def calculate_mctr(self, portfolio_weights: pd.Series, factor_model: Dict[str, Any]) -> pd.Series:
        """
        Calculate Marginal Contribution to Tracking Risk (MCTR).
        
        MCTR_i = w_i * cov(r_i, r_p) / sigma_p
        
        Flag where MCTR% > 1.5x weight%
        """
        if portfolio_weights.empty or not factor_model.get('status') == 'success':
            return pd.Series(dtype=float)
            
        try:
            # Extract model components
            factor_cov = factor_model['factor_covariance']
            specific_var = factor_model['specific_variance']
            factor_exposures = factor_model['factor_exposures']
            
            if factor_cov.size == 0 or specific_var.empty:
                return pd.Series(dtype=float)
            
            # Align weights with factor exposures
            weights_aligned = portfolio_weights.reindex(factor_exposures['ticker']).fillna(0)
            
            # Get factor exposures
            factor_cols = [col for col in factor_exposures.columns if col.endswith('_z')]
            if not factor_cols:
                factor_cols = [col for col in factor_exposures.columns if '_score_z' in col]
                
            if not factor_cols:
                # Create unit exposure if no factors
                X = np.ones((len(weights_aligned), 1))
            else:
                X = factor_exposures.set_index('ticker')[factor_cols].reindex(weights_aligned.index).fillna(0).values
            
            # Portfolio risk
            portfolio_risk_result = self.calculate_portfolio_risk(portfolio_weights, factor_model)
            portfolio_vol = portfolio_risk_result['total_volatility']
            
            if portfolio_vol <= 0:
                return pd.Series(0.0, index=weights_aligned.index)
            
            # Calculate MCTR for each position
            mctr_series = pd.Series(index=weights_aligned.index, dtype=float)
            
            for ticker in weights_aligned.index:
                if weights_aligned[ticker] == 0:
                    mctr_series[ticker] = 0.0
                    continue
                    
                # Get stock's factor exposure
                ticker_idx = weights_aligned.index.get_loc(ticker)
                stock_exposure = X[ticker_idx:ticker_idx+1, :]  # Shape (1, n_factors)
                
                # Portfolio factor exposures
                portfolio_exposures = X.T @ weights_aligned.values  # Shape (n_factors,)
                
                # Covariance between stock and portfolio
                if factor_cov.shape[0] > 0:
                    stock_portfolio_cov = stock_exposure @ factor_cov @ portfolio_exposures
                else:
                    stock_portfolio_cov = 0
                    
                # Add specific risk component (simplified)
                specific_component = 0
                if ticker in specific_var.index:
                    specific_component = weights_aligned[ticker] * specific_var[ticker]
                    
                total_cov = stock_portfolio_cov + specific_component
                
                # MCTR calculation
                mctr = weights_aligned[ticker] * total_cov / portfolio_vol if portfolio_vol > 0 else 0
                mctr_series[ticker] = mctr
                
            return mctr_series
            
        except Exception as e:
            logger.error(f"MCTR calculation failed: {e}")
            return pd.Series(dtype=float)

    def identify_risky_positions(self, portfolio_weights: pd.Series, 
                                factor_model: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Identify positions where MCTR% > 1.5x weight%.
        """
        mctr_series = self.calculate_mctr(portfolio_weights, factor_model)
        
        if mctr_series.empty:
            return []
            
        risky_positions = []
        
        for ticker in mctr_series.index:
            weight = portfolio_weights.get(ticker, 0)
            if weight == 0:
                continue
                
            mctr_percentage = mctr_series[ticker] * 100  # Convert to percentage
            weight_percentage = abs(weight) * 100  # Convert to percentage
            
            if mctr_percentage > 1.5 * weight_percentage:
                risky_positions.append({
                    'ticker': ticker,
                    'weight': weight,
                    'mctr_percentage': mctr_percentage,
                    'weight_percentage': weight_percentage,
                    'risk_ratio': mctr_percentage / weight_percentage if weight_percentage > 0 else 0
                })
                
        return risky_positions

    def _create_empty_model(self, error: str = None) -> Dict[str, Any]:
        """Create empty model structure."""
        return {
            'factor_returns': pd.DataFrame(),
            'factor_covariance': np.array([]),
            'specific_variance': pd.Series(dtype=float),
            'factor_exposures': pd.DataFrame(),
            'model_dates': [],
            'status': 'failed',
            'error': error
        }


# Convenience function
def build_factor_risk_model(factor_data: pd.DataFrame, price_data: pd.DataFrame,
                           market_data: pd.DataFrame = None,
                           config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Build Barra-style factor risk model."""
    model = FactorRiskModel(config or {})
    return model.build_factor_model(factor_data, price_data, market_data)
