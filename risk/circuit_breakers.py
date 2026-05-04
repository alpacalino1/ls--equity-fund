"""
Meridian Capital Partners · risk/circuit_breakers.py
─────────────────────────────────────────────────────────────────
Circuit breakers that fire on actual dollar losses.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
from pathlib import Path

logger = logging.getLogger("meridian.risk.circuit_breakers")


class CircuitBreakers:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize circuit breakers with configuration."""
        if config is None:
            config = {}
            
        self.config = config
        self.daily_loss_threshold_soft = config.get("daily_loss_threshold_soft", -0.015)  # -1.5%
        self.daily_loss_threshold_hard = config.get("daily_loss_threshold_hard", -0.025)  # -2.5%
        self.weekly_loss_threshold = config.get("weekly_loss_threshold", -0.04)  # -4%
        self.drawdown_threshold = config.get("drawdown_threshold", -0.08)  # -8%
        self.single_position_threshold = config.get("single_position_threshold", 0.03)  # 3% NAV
        self.aum = config.get("aum", 100_000_000)  # Default $100M AUM
        self.halt_file = Path(config.get("halt_file", "cache/halt.lock"))
        
        # Performance tracking
        self.daily_pnl = []
        self.weekly_pnl = []
        
        # Create cache directory if needed
        self.halt_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info("Circuit breakers initialized")

    def check_daily_losses(self, daily_pnl: float, current_portfolio: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Check daily losses and apply circuit breaker actions.
        
        Daily > 1.5% -> SIZE_DOWN 30%
        Daily > 2.5% -> CLOSE_ALL_TODAY
        """
        logger.info(f"Checking daily losses: ${daily_pnl:,.2f} ({daily_pnl/self.aum:.2%})")
        
        daily_return = daily_pnl / self.aum if self.aum > 0 else 0
        
        result = {
            'daily_pnl': daily_pnl,
            'daily_return': daily_return,
            'actions': [],
            'halt_triggered': False,
            'timestamp': datetime.now().isoformat()
        }
        
        # Daily > 1.5% -> SIZE_DOWN 30%
        if daily_return < self.daily_loss_threshold_soft:
            reduction_factor = 0.7  # 30% size down
            result['actions'].append({
                'type': 'SIZE_DOWN',
                'factor': reduction_factor,
                'reason': f'Daily loss {-daily_return:.2%} > {-self.daily_loss_threshold_soft:.1%}'
            })
            logger.warning(f"Daily loss circuit breaker triggered: {-daily_return:.2%} > {-self.daily_loss_threshold_soft:.1%}")
            
        # Daily > 2.5% -> CLOSE_ALL_TODAY
        if daily_return < self.daily_loss_threshold_hard:
            result['actions'].append({
                'type': 'CLOSE_ALL_TODAY',
                'reason': f'Daily loss {-daily_return:.2%} > {-self.daily_loss_threshold_hard:.1%}'
            })
            result['halt_triggered'] = True
            logger.critical(f"Hard daily loss circuit breaker triggered: {-daily_return:.2%} > {-self.daily_loss_threshold_hard:.1%}")
            self._trigger_halt(f"Hard daily loss {-daily_return:.2%}")
            
        return result

    def check_weekly_losses(self, weekly_pnl: float) -> Dict[str, Any]:
        """
        Check weekly losses and apply circuit breaker actions.
        
        Weekly > 4% -> SIZE_DOWN 30%
        """
        logger.info(f"Checking weekly losses: ${weekly_pnl:,.2f} ({weekly_pnl/self.aum:.2%})")
        
        weekly_return = weekly_pnl / self.aum if self.aum > 0 else 0
        
        result = {
            'weekly_pnl': weekly_pnl,
            'weekly_return': weekly_return,
            'actions': [],
            'halt_triggered': False,
            'timestamp': datetime.now().isoformat()
        }
        
        # Weekly > 4% -> SIZE_DOWN 30%
        if weekly_return < self.weekly_loss_threshold:
            reduction_factor = 0.7  # 30% size down
            result['actions'].append({
                'type': 'SIZE_DOWN',
                'factor': reduction_factor,
                'reason': f'Weekly loss {-weekly_return:.2%} > {-self.weekly_loss_threshold:.1%}'
            })
            logger.warning(f"Weekly loss circuit breaker triggered: {-weekly_return:.2%} > {-self.weekly_loss_threshold:.1%}")
            
        return result

    def check_drawdown(self, current_nav: float, peak_nav: float) -> Dict[str, Any]:
        """
        Check drawdown and apply circuit breaker actions.
        
        Drawdown > 8% -> KILL_SWITCH (lock file, --clear-halt)
        """
        if peak_nav <= 0:
            return {
                'drawdown': 0.0,
                'actions': [],
                'halt_triggered': False,
                'timestamp': datetime.now().isoformat()
            }
            
        drawdown = (current_nav - peak_nav) / peak_nav
        
        logger.info(f"Checking drawdown: {drawdown:.2%} (NAV: ${current_nav:,.2f}, Peak: ${peak_nav:,.2f})")
        
        result = {
            'drawdown': drawdown,
            'current_nav': current_nav,
            'peak_nav': peak_nav,
            'actions': [],
            'halt_triggered': False,
            'timestamp': datetime.now().isoformat()
        }
        
        # Drawdown > 8% -> KILL_SWITCH
        if drawdown < self.drawdown_threshold:
            result['actions'].append({
                'type': 'KILL_SWITCH',
                'reason': f'Drawdown {-drawdown:.2%} > {-self.drawdown_threshold:.1%}'
            })
            result['halt_triggered'] = True
            logger.critical(f"Drawdown circuit breaker triggered: {-drawdown:.2%} > {-self.drawdown_threshold:.1%}")
            self._trigger_halt(f"Drawdown {-drawdown:.2%}")
            
        return result

    def check_single_position(self, ticker: str, position_value: float, 
                             nav: float = None) -> Dict[str, Any]:
        """
        Check single position size and apply circuit breaker actions.
        
        Single position > 3% NAV -> force-close immediately
        """
        nav = nav or self.aum
        position_pct = position_value / nav if nav > 0 else 0
        
        logger.info(f"Checking single position {ticker}: ${position_value:,.2f} ({position_pct:.2%} NAV)")
        
        result = {
            'ticker': ticker,
            'position_value': position_value,
            'position_pct': position_pct,
            'nav': nav,
            'actions': [],
            'halt_triggered': False,
            'timestamp': datetime.now().isoformat()
        }
        
        # Single position > 3% NAV -> force-close immediately
        if position_pct > self.single_position_threshold:
            result['actions'].append({
                'type': 'FORCE_CLOSE',
                'reason': f'Position {position_pct:.2%} > {self.single_position_threshold:.1%} NAV'
            })
            logger.warning(f"Single position circuit breaker triggered for {ticker}: {position_pct:.2%} > {self.single_position_threshold:.1%}")
            
        return result

    def check_portfolio(self, portfolio_stats: Dict[str, Any], 
                       historical_nav: List[float]) -> List[Dict[str, Any]]:
        """
        Check entire portfolio for circuit breaker violations.
        
        Returns list of actions to take.
        """
        actions = []
        
        # Current NAV and peak NAV
        current_nav = portfolio_stats.get('nav', self.aum)
        peak_nav = max(historical_nav) if historical_nav else current_nav
        
        # Check drawdown
        drawdown_result = self.check_drawdown(current_nav, peak_nav)
        if drawdown_result['actions']:
            actions.append(drawdown_result)
            
        # Check single positions (if provided)
        positions = portfolio_stats.get('positions', [])
        for position in positions:
            if isinstance(position, dict):
                ticker = position.get('ticker', '')
                weight = position.get('weight', 0)
                position_value = abs(weight) * current_nav
                single_result = self.check_single_position(ticker, position_value, current_nav)
                if single_result['actions']:
                    actions.append(single_result)
                    
        return actions

    def update_performance_tracking(self, daily_pnl: float = 0, weekly_pnl: float = 0):
        """
        Update internal performance tracking for circuit breaker monitoring.
        """
        if daily_pnl != 0:
            self.daily_pnl.append(daily_pnl)
            # Keep only last 30 days
            if len(self.daily_pnl) > 30:
                self.daily_pnl = self.daily_pnl[-30:]
                
        if weekly_pnl != 0:
            self.weekly_pnl.append(weekly_pnl)
            # Keep only last 52 weeks
            if len(self.weekly_pnl) > 52:
                self.weekly_pnl = self.weekly_pnl[-52:]

    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get summary of recent performance for circuit breaker monitoring.
        """
        return {
            'daily_pnl_history': self.daily_pnl,
            'weekly_pnl_history': self.weekly_pnl,
            'recent_daily_loss': sum(self.daily_pnl[-1:]) if self.daily_pnl else 0,
            'recent_weekly_loss': sum(self.weekly_pnl[-1:]) if self.weekly_pnl else 0,
            'rolling_7day_loss': sum(self.daily_pnl[-7:]) if len(self.daily_pnl) >= 7 else sum(self.daily_pnl),
            'timestamp': datetime.now().isoformat()
        }

    def _trigger_halt(self, reason: str):
        """
        Trigger system halt by creating halt lock file.
        """
        halt_info = {
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'type': 'circuit_breaker',
            'user': 'system'
        }
        
        try:
            with open(self.halt_file, 'w') as f:
                json.dump(halt_info, f, indent=2)
            logger.critical(f"Circuit breaker halt triggered: {reason}")
        except Exception as e:
            logger.error(f"Failed to create halt file: {e}")

    def clear_halt(self):
        """
        Clear circuit breaker halt condition.
        """
        from risk.pre_trade import PreTradeChecker
        checker = PreTradeChecker({'halt_file': str(self.halt_file)})
        checker.clear_halt()

    def load_performance_history(self, history_file: str = "cache/performance_history.json"):
        """
        Load performance history from file for continuity.
        """
        try:
            hist_path = Path(history_file)
            if hist_path.exists():
                with open(hist_path, 'r') as f:
                    history = json.load(f)
                self.daily_pnl = history.get('daily_pnl', [])
                self.weekly_pnl = history.get('weekly_pnl', [])
                logger.info(f"Loaded performance history: {len(self.daily_pnl)} daily, {len(self.weekly_pnl)} weekly records")
        except Exception as e:
            logger.warning(f"Failed to load performance history: {e}")

    def save_performance_history(self, history_file: str = "cache/performance_history.json"):
        """
        Save performance history to file.
        """
        try:
            hist_path = Path(history_file)
            hist_path.parent.mkdir(parents=True, exist_ok=True)
            
            history = {
                'daily_pnl': self.daily_pnl,
                'weekly_pnl': self.weekly_pnl,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(hist_path, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save performance history: {e}")


# Global circuit breaker instance
_circuit_breaker_instance = None


def get_circuit_breaker(config: Dict[str, Any] = None) -> CircuitBreakers:
    """Get singleton circuit breaker instance."""
    global _circuit_breaker_instance
    if _circuit_breaker_instance is None:
        _circuit_breaker_instance = CircuitBreakers(config or {})
    return _circuit_breaker_instance


# Convenience function
def check_all_circuit_breakers(portfolio_value: float, daily_pnl: float = 0, 
                              weekly_pnl: float = 0, drawdown_peak: float = None,
                              positions: List[Dict[str, Any]] = None,
                              config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Check all circuit breakers and return actions."""
    cb = get_circuit_breaker(config)
    cb.update_performance_tracking(daily_pnl, weekly_pnl)
    
    actions = []
    
    # Check daily losses
    if daily_pnl != 0:
        daily_actions = cb.check_daily_losses(daily_pnl)
        if daily_actions['actions']:
            actions.append(daily_actions)
            
    # Check weekly losses
    if weekly_pnl != 0:
        weekly_actions = cb.check_weekly_losses(weekly_pnl)
        if weekly_actions['actions']:
            actions.append(weekly_actions)
            
    # Check drawdown
    if drawdown_peak is not None:
        drawdown_actions = cb.check_drawdown(portfolio_value, drawdown_peak)
        if drawdown_actions['actions']:
            actions.append(drawdown_actions)
            
    # Check positions
    if positions:
        for position in positions:
            ticker = position.get('ticker', '')
            weight = position.get('weight', 0)
            position_value = abs(weight) * portfolio_value
            pos_actions = cb.check_single_position(ticker, position_value, portfolio_value)
            if pos_actions['actions']:
                actions.append(pos_actions)
                
    return actions
