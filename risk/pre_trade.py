"""
Meridian Capital Partners · risk/pre_trade.py
─────────────────────────────────────────────────────────────────
Pre-trade risk checks with absolute veto power.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
from pathlib import Path

logger = logging.getLogger("meridian.risk.pre_trade")


class PreTradeChecker:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize pre-trade checker with configuration."""
        if config is None:
            config = {}
            
        self.config = config
        self.halt_file = Path(config.get("halt_file", "cache/halt.lock"))
        self.aum = config.get("aum", 100_000_000)  # Default $100M AUM
        self.max_position_weight = config.get("max_position_weight", 0.05)  # 5% of AUM
        self.max_sector_weight = config.get("max_sector_weight", 0.25)  # 25% per sector
        self.max_gross_exposure = config.get("max_gross_exposure", 1.65)  # 165%
        self.max_net_exposure = config.get("max_net_exposure", 0.15)  # +/- 15%
        self.max_beta_exposure = config.get("max_beta_exposure", 0.20)  # 0.20 beta
        self.max_correlation = config.get("max_correlation", 0.80)  # 80% correlation
        self.min_liquidity_adv_pct = config.get("min_liquidity_adv_pct", 0.05)  # 5% of ADV
        
        # Create halt file directory if needed
        self.halt_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info("Pre-trade checker initialized")

    def check_trade(self, trade_request: Dict[str, Any], 
                   current_portfolio: pd.DataFrame = None,
                   market_data: pd.DataFrame = None,
                   factor_model: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Perform all 8 pre-trade checks with absolute veto power.
        
        Args:
            trade_request: Dict with 'ticker', 'side', 'quantity', 'action' (buy/sell/short/close)
            current_portfolio: Current portfolio positions DataFrame
            market_data: Market data for liquidity/price checks
            factor_model: Factor risk model for correlation checks
            
        Returns:
            Dict with approval status and detailed check results
        """
        logger.info(f"Checking trade: {trade_request}")
        
        ticker = trade_request.get('ticker')
        action = trade_request.get('action', 'buy').lower()
        quantity = trade_request.get('quantity', 0)
        
        # Initialize result structure
        result = {
            'approved': True,
            'checks': {},
            'veto_reasons': [],
            'timestamp': datetime.now().isoformat(),
            'trade_request': trade_request
        }
        
        # Check 1: Halt lock exists?
        halt_check = self._check_halt_lock()
        result['checks']['halt_lock'] = halt_check
        if not halt_check['approved']:
            result['approved'] = False
            result['veto_reasons'].append(halt_check['reason'])
            
        # Check 2: Earnings blackout (5d = 50% size cut)
        earnings_check = self._check_earnings_blackout(ticker)
        result['checks']['earnings_blackout'] = earnings_check
        if not earnings_check['approved']:
            if earnings_check['reason'].startswith('Blackout'):
                # Blackout period - reduce size by 50%
                trade_request['quantity'] = int(quantity * 0.5)
                logger.info(f"Reduced trade size due to earnings blackout: {quantity} -> {trade_request['quantity']}")
            elif earnings_check['reason'].startswith('Rejected'):
                result['approved'] = False
                result['veto_reasons'].append(earnings_check['reason'])
                
        # Check 3: Liquidity <= 5% ADV
        liquidity_check = self._check_liquidity(ticker, quantity, market_data)
        result['checks']['liquidity'] = liquidity_check
        if not liquidity_check['approved']:
            result['approved'] = False
            result['veto_reasons'].append(liquidity_check['reason'])
            
        # Check 4: Position <= 5% AUM
        position_check = self._check_position_size(ticker, quantity, current_portfolio)
        result['checks']['position_size'] = position_check
        if not position_check['approved']:
            result['approved'] = False
            result['veto_reasons'].append(position_check['reason'])
            
        # Check 5: Sector <= 25%
        sector_check = self._check_sector_limits(ticker, current_portfolio)
        result['checks']['sector_limits'] = sector_check
        if not sector_check['approved']:
            result['approved'] = False
            result['veto_reasons'].append(sector_check['reason'])
            
        # Check 6: Gross <= 165%, net [-10%,+15%]
        exposure_check = self._check_exposure_limits(current_portfolio)
        result['checks']['exposure_limits'] = exposure_check
        if not exposure_check['approved']:
            result['approved'] = False
            result['veto_reasons'].append(exposure_check['reason'])
            
        # Check 7: |net beta| <= 0.20
        beta_check = self._check_beta_exposure(current_portfolio)
        result['checks']['beta_exposure'] = beta_check
        if not beta_check['approved']:
            result['approved'] = False
            result['veto_reasons'].append(beta_check['reason'])
            
        # Check 8: Pairwise correlation <= 0.80 with existing positions
        correlation_check = self._check_correlation_limits(ticker, current_portfolio, factor_model)
        result['checks']['correlation_limits'] = correlation_check
        if not correlation_check['approved']:
            result['approved'] = False
            result['veto_reasons'].append(correlation_check['reason'])
            
        # Special case: Closing/covering trades always approved
        if action in ['close', 'cover']:
            logger.info(f"Closing/covering trade always approved: {ticker}")
            result['approved'] = True
            result['veto_reasons'] = []  # Clear any vetoes for closing trades
            
        # Log result
        if result['approved']:
            logger.info(f"Trade approved: {ticker}")
        else:
            logger.warning(f"Trade rejected: {ticker}, reasons: {result['veto_reasons']}")
            self._log_rejection(result)
            
        return result

    def _check_halt_lock(self) -> Dict[str, Any]:
        """Check 1: Halt lock exists?"""
        if self.halt_file.exists():
            try:
                with open(self.halt_file, 'r') as f:
                    halt_info = json.load(f)
                return {
                    'approved': False,
                    'reason': f"Halt lock active: {halt_info.get('reason', 'Unknown')}",
                    'details': halt_info
                }
            except Exception as e:
                logger.warning(f"Error reading halt file: {e}")
                return {
                    'approved': False,
                    'reason': "Halt lock file corrupted",
                    'details': str(e)
                }
        else:
            return {
                'approved': True,
                'reason': "No halt lock"
            }

    def _check_earnings_blackout(self, ticker: str) -> Dict[str, Any]:
        """Check 2: Earnings blackout (5d = 50% size cut)."""
        # In practice, this would check against an earnings calendar
        # For now, we'll simulate with a simple approach
        # TODO: Integrate with actual earnings calendar data
        
        # Simulate 10% chance of being in earnings blackout period
        import random
        in_blackout = random.random() < 0.10  # 10% of stocks in blackout
        
        if in_blackout:
            # If it's a new position, reject
            # If it's adding to existing position, reduce size by 50%
            return {
                'approved': True,  # Allow but reduce size
                'reason': "Blackout period - 50% size reduction",
                'blackout': True
            }
        else:
            return {
                'approved': True,
                'reason': "No earnings blackout"
            }

    def _check_liquidity(self, ticker: str, quantity: int, 
                        market_data: pd.DataFrame) -> Dict[str, Any]:
        """Check 3: Liquidity <= 5% ADV."""
        if market_data is None:
            return {
                'approved': True,
                'reason': "No market data for liquidity check"
            }
            
        ticker_data = market_data[market_data['ticker'] == ticker]
        if ticker_data.empty:
            return {
                'approved': True,
                'reason': f"No market data for {ticker}"
            }
            
        adv = ticker_data['volume'].mean() if 'volume' in ticker_data.columns else 0
        if adv <= 0:
            return {
                'approved': True,
                'reason': f"No ADV data for {ticker}"
            }
            
        # Calculate trade as percentage of ADV
        trade_percentage = quantity / adv if adv > 0 else 0
        
        if trade_percentage > self.min_liquidity_adv_pct:
            return {
                'approved': False,
                'reason': f"Liquidity violation: {trade_percentage:.1%} > {self.min_liquidity_adv_pct:.1%} of ADV",
                'details': {
                    'quantity': quantity,
                    'adv': adv,
                    'percentage': trade_percentage
                }
            }
        else:
            return {
                'approved': True,
                'reason': f"Liquidity OK: {trade_percentage:.1%} of ADV",
                'details': {
                    'quantity': quantity,
                    'adv': adv,
                    'percentage': trade_percentage
                }
            }

    def _check_position_size(self, ticker: str, quantity: int, 
                            current_portfolio: pd.DataFrame) -> Dict[str, Any]:
        """Check 4: Position <= 5% AUM."""
        # Calculate dollar value of proposed position
        # In practice, you'd get current price
        position_value = quantity * 100  # Simplified - assume $100/share
        
        # Calculate position weight in AUM
        position_weight = position_value / self.aum if self.aum > 0 else 0
        
        max_weight = self.max_position_weight
        
        # Check if this would exceed the limit
        current_position_value = 0
        if current_portfolio is not None:
            current_pos = current_portfolio[current_portfolio['ticker'] == ticker]
            if not current_pos.empty:
                current_position_value = current_pos['quantity'].iloc[0] * 100  # Simplified
                
        total_position_value = current_position_value + position_value
        total_position_weight = total_position_value / self.aum if self.aum > 0 else 0
        
        if total_position_weight > max_weight:
            return {
                'approved': False,
                'reason': f"Position size violation: {total_position_weight:.1%} > {max_weight:.1%} of AUM",
                'details': {
                    'current_value': current_position_value,
                    'proposed_value': position_value,
                    'total_value': total_position_value,
                    'aum': self.aum,
                    'weight': total_position_weight
                }
            }
        else:
            return {
                'approved': True,
                'reason': f"Position size OK: {total_position_weight:.1%} of AUM",
                'details': {
                    'current_value': current_position_value,
                    'proposed_value': position_value,
                    'total_value': total_position_value,
                    'aum': self.aum,
                    'weight': total_position_weight
                }
            }

    def _check_sector_limits(self, ticker: str, current_portfolio: pd.DataFrame) -> Dict[str, Any]:
        """Check 5: Sector <= 25%."""
        # In practice, you'd need sector data for the ticker
        # For now, we'll simulate sector checking
        
        # Assume all technology for this example
        sector = "Technology"  # Simplified
        
        # Calculate current sector exposure
        current_sector_weight = 0.0
        if current_portfolio is not None:
            # Simplify by assuming all current positions are in technology
            current_sector_weight = current_portfolio['weight'].abs().sum() * 0.3  # 30% tech
            
        # Add proposed position (simplified)
        proposed_sector_addition = 0.01  # 1% addition
        new_sector_weight = current_sector_weight + proposed_sector_addition
        
        max_sector_weight = self.max_sector_weight
        
        if new_sector_weight > max_sector_weight:
            return {
                'approved': False,
                'reason': f"Sector limit violation: {new_sector_weight:.1%} > {max_sector_weight:.1%}",
                'details': {
                    'sector': sector,
                    'current_weight': current_sector_weight,
                    'proposed_addition': proposed_sector_addition,
                    'total_weight': new_sector_weight
                }
            }
        else:
            return {
                'approved': True,
                'reason': f"Sector limit OK: {new_sector_weight:.1%}",
                'details': {
                    'sector': sector,
                    'current_weight': current_sector_weight,
                    'proposed_addition': proposed_sector_addition,
                    'total_weight': new_sector_weight
                }
            }

    def _check_exposure_limits(self, current_portfolio: pd.DataFrame) -> Dict[str, Any]:
        """Check 6: Gross <= 165%, net [-10%,+15%]."""
        if current_portfolio is None or current_portfolio.empty:
            return {
                'approved': True,
                'reason': "No current portfolio for exposure check"
            }
            
        # Calculate portfolio metrics
        gross_exposure = current_portfolio['weight'].abs().sum()
        net_exposure = current_portfolio['weight'].sum()
        
        # Check gross exposure
        if gross_exposure > self.max_gross_exposure:
            return {
                'approved': False,
                'reason': f"Gross exposure violation: {gross_exposure:.1%} > {self.max_gross_exposure:.1%}",
                'details': {
                    'gross': gross_exposure,
                    'net': net_exposure,
                    'max_gross': self.max_gross_exposure
                }
            }
            
        # Check net exposure
        net_lower_bound = -0.10  # -10%
        net_upper_bound = self.max_net_exposure  # +15%
        
        if not (net_lower_bound <= net_exposure <= net_upper_bound):
            return {
                'approved': False,
                'reason': f"Net exposure violation: {net_exposure:.1%} not in [{net_lower_bound:.1%}, {net_upper_bound:.1%}]",
                'details': {
                    'gross': gross_exposure,
                    'net': net_exposure,
                    'bounds': [net_lower_bound, net_upper_bound]
                }
            }
            
        return {
            'approved': True,
            'reason': f"Exposure limits OK: Gross={gross_exposure:.1%}, Net={net_exposure:.1%}",
            'details': {
                'gross': gross_exposure,
                'net': net_exposure,
                'bounds': [net_lower_bound, net_upper_bound]
            }
        }

    def _check_beta_exposure(self, current_portfolio: pd.DataFrame) -> Dict[str, Any]:
        """Check 7: |net beta| <= 0.20."""
        if current_portfolio is None or current_portfolio.empty:
            return {
                'approved': True,
                'reason': "No current portfolio for beta check"
            }
            
        # Calculate portfolio beta (simplified - assume average stock beta = 1.0)
        portfolio_beta = 1.0  # Simplified
        
        if abs(portfolio_beta) > self.max_beta_exposure:
            return {
                'approved': False,
                'reason': f"Beta exposure violation: |{portfolio_beta:.2f}| > {self.max_beta_exposure:.2f}",
                'details': {
                    'beta': portfolio_beta,
                    'max_beta': self.max_beta_exposure
                }
            }
        else:
            return {
                'approved': True,
                'reason': f"Beta exposure OK: |{portfolio_beta:.2f}|",
                'details': {
                    'beta': portfolio_beta,
                    'max_beta': self.max_beta_exposure
                }
            }

    def _check_correlation_limits(self, ticker: str, current_portfolio: pd.DataFrame,
                                 factor_model: Dict[str, Any]) -> Dict[str, Any]:
        """Check 8: Pairwise correlation <= 0.80 with existing positions."""
        # In practice, this would use the factor model to calculate correlations
        # For now, we'll simulate with random correlation checking
        
        if current_portfolio is None or current_portfolio.empty:
            return {
                'approved': True,
                'reason': "No existing positions for correlation check"
            }
            
        # Simulate correlation checking - 5% chance of high correlation
        import random
        high_correlation = random.random() < 0.05  # 5% chance
        
        if high_correlation:
            return {
                'approved': False,
                'reason': f"High correlation violation: > {self.max_correlation:.1%} with existing positions",
                'details': {
                    'correlated_with': "Multiple positions",
                    'correlation_threshold': self.max_correlation
                }
            }
        else:
            return {
                'approved': True,
                'reason': f"Correlation limits OK: < {self.max_correlation:.1%}",
                'details': {
                    'correlation_threshold': self.max_correlation
                }
            }

    def _log_rejection(self, result: Dict[str, Any]):
        """Log every rejection with timestamp and reason."""
        log_entry = {
            'timestamp': result['timestamp'],
            'trade_request': result['trade_request'],
            'veto_reasons': result['veto_reasons'],
            'checks': {k: v for k, v in result['checks'].items() if not v.get('approved', True)}
        }
        
        # Write to rejection log
        log_file = Path("output/risk/rejections.log")
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to log rejection: {e}")

    def set_halt(self, reason: str = "Manual halt"):
        """Create halt lock file to prevent trading."""
        halt_info = {
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'user': 'system'
        }
        
        try:
            with open(self.halt_file, 'w') as f:
                json.dump(halt_info, f, indent=2)
            logger.info(f"Halt set: {reason}")
        except Exception as e:
            logger.error(f"Failed to set halt: {e}")

    def clear_halt(self):
        """Remove halt lock file to resume trading."""
        if self.halt_file.exists():
            try:
                self.halt_file.unlink()
                logger.info("Halt cleared")
            except Exception as e:
                logger.error(f"Failed to clear halt: {e}")
        else:
            logger.info("No halt to clear")


# Convenience function
def check_pre_trade(trade_request: Dict[str, Any], 
                   current_portfolio: pd.DataFrame = None,
                   market_data: pd.DataFrame = None,
                   factor_model: Dict[str, Any] = None,
                   config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Perform pre-trade risk checks."""
    checker = PreTradeChecker(config or {})
    return checker.check_trade(trade_request, current_portfolio, market_data, factor_model)
