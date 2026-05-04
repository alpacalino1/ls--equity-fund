# Order Executor Template

This is a template for the executor.py implementation that will handle order execution logic.

## Planned Implementation

```python
"""
Meridian Capital Partners · execution/executor.py
─────────────────────────────────────────────────────────────────
Order execution with safety checks and risk management integration.
"""

import logging
import time
from typing import Dict, Any, List, Optional
import pandas as pd

from .broker import AlpacaBroker
from .short_check import ShortAvailabilityChecker
from risk.pre_trade import PreTradeChecker

logger = logging.getLogger("meridian.execution.executor")

class OrderExecutor:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize order executor with safety components."""
        if config is None:
            config = {}
            
        self.config = config
        self.broker = AlpacaBroker(config.get("broker", {}))
        self.short_checker = ShortAvailabilityChecker(config.get("short_check", {}))
        self.pre_trade_checker = PreTradeChecker(config.get("risk", {}).get("pre_trade", {}))
        
        # Configuration
        self.limit_offset_bps = config.get("limit_offset_bps", 5)
        self.order_timeout_seconds = config.get("order_timeout_seconds", 120)
        self.poll_interval_seconds = config.get("poll_interval_seconds", 5)
        self.max_retry_attempts = config.get("max_retry_attempts", 3)
        self.adv_limit_percentage = config.get("adv_limit_percentage", 0.02)  # 2% of ADV
        
        logger.info("Order executor initialized")
        
    def execute_trades(self, trades: List[Dict[str, Any]], market_data: pd.DataFrame, 
                      current_portfolio: pd.DataFrame = None) -> List[Dict[str, Any]]:
        """Execute a list of trades with all safety checks."""
        results = []
        
        for trade in trades:
            try:
                result = self.execute_single_trade(trade, market_data, current_portfolio)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to execute trade {trade}: {e}")
                results.append({
                    'trade': trade,
                    'status': 'error',
                    'error': str(e)
                })
                
        return results
        
    def execute_single_trade(self, trade: Dict[str, Any], market_data: pd.DataFrame,
                            current_portfolio: pd.DataFrame = None) -> Dict[str, Any]:
        """Execute a single trade with full safety validation."""
        ticker = trade['ticker']
        side = trade['side']  # 'buy', 'sell', 'short', 'cover'
        quantity = trade['quantity']
        
        logger.info(f"Executing trade: {side} {quantity} {ticker}")
        
        # 1. Pre-trade veto check
        pre_trade_result = self.pre_trade_checker.check_trade(
            trade, current_portfolio, market_data
        )
        
        if not pre_trade_result['approved']:
            logger.warning(f"Pre-trade check failed for {ticker}: {pre_trade_result['veto_reasons']}")
            return {
                'trade': trade,
                'status': 'rejected',
                'reason': 'pre_trade_veto',
                'veto_reasons': pre_trade_result['veto_reasons']
            }
            
        # 2. Short availability check (for short sells)
        if side == 'short':
            if not self.short_checker.is_shortable(ticker):
                logger.warning(f"Short not available for {ticker}")
                return {
                    'trade': trade,
                    'status': 'rejected',
                    'reason': 'short_not_available'
                }
                
        # 3. Get limit price
        limit_price = self._calculate_limit_price(ticker, side, market_data)
        if limit_price is None:
            logger.error(f"Could not determine limit price for {ticker}")
            return {
                'trade': trade,
                'status': 'rejected',
                'reason': 'no_limit_price'
            }
            
        # 4. Chunk large orders based on ADV
        orders_to_place = self._chunk_order(ticker, quantity, side, market_data)
        
        # 5. Place orders with timeout and retry logic
        execution_results = []
        for order_chunk in orders_to_place:
            result = self._place_order_with_retry(order_chunk, limit_price)
            execution_results.append(result)
            
        # 6. Aggregate results
        overall_result = self._aggregate_execution_results(execution_results, trade)
        
        return overall_result
        
    def _calculate_limit_price(self, ticker: str, side: str, market_data: pd.DataFrame) -> Optional[float]:
        """Calculate limit price with offset."""
        # Get current price from market data
        ticker_data = market_data[market_data['ticker'] == ticker]
        if ticker_data.empty:
            return None
            
        current_price = ticker_data['close'].iloc[0]
        
        # Apply limit offset (bps to decimal)
        offset = self.limit_offset_bps / 10000
        
        if side in ['buy', 'cover']:
            # Buy limit below market
            limit_price = current_price * (1 - offset)
        else:  # sell, short
            # Sell limit above market
            limit_price = current_price * (1 + offset)
            
        return round(limit_price, 2)
        
    def _chunk_order(self, ticker: str, quantity: int, side: str, market_data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Chunk large orders based on ADV limits."""
        ticker_data = market_data[market_data['ticker'] == ticker]
        if ticker_data.empty:
            # If no market data, place single order
            return [{'ticker': ticker, 'quantity': quantity, 'side': side}]
            
        adv = ticker_data['volume'].mean() if 'volume' in ticker_data.columns else 0
        if adv <= 0:
            return [{'ticker': ticker, 'quantity': quantity, 'side': side}]
            
        # Calculate maximum order size (2% of ADV)
        max_order_size = int(adv * self.adv_limit_percentage)
        
        if quantity <= max_order_size:
            # Order is small enough, no chunking needed
            return [{'ticker': ticker, 'quantity': quantity, 'side': side}]
            
        # Chunk the order
        chunks = []
        remaining_quantity = quantity
        
        while remaining_quantity > 0:
            chunk_size = min(remaining_quantity, max_order_size)
            chunks.append({
                'ticker': ticker,
                'quantity': chunk_size,
                'side': side
            })
            remaining_quantity -= chunk_size
            
        logger.info(f"Chunked order {quantity} {ticker} into {len(chunks)} pieces of {max_order_size} each")
        return chunks
        
    def _place_order_with_retry(self, order_params: Dict[str, Any], limit_price: float) -> Dict[str, Any]:
        """Place order with timeout and retry logic."""
        for attempt in range(self.max_retry_attempts):
            try:
                # Place the order
                order_id = self.broker.place_order({
                    'symbol': order_params['ticker'],
                    'qty': order_params['quantity'],
                    'side': order_params['side'],
                    'type': 'limit',
                    'limit_price': limit_price,
                    'time_in_force': 'day',  # Will handle timeout manually
                    'extended_hours': False
                })
                
                if order_id is None:
                    raise Exception("Failed to place order")
                    
                # Record signal price for slippage calculation
                signal_price = limit_price
                
                # Wait for order to fill or timeout
                result = self._wait_for_order_fill(order_id, signal_price)
                
                if result['status'] == 'filled':
                    return result
                elif result['status'] == 'timeout' and attempt < self.max_retry_attempts - 1:
                    # Cancel and retry
                    logger.info(f"Order timeout, cancelling and retrying (attempt {attempt + 1})")
                    self.broker.cancel_order(order_id)
                    time.sleep(1)  # Brief pause before retry
                    continue
                else:
                    # Final attempt or other status
                    return result
                    
            except Exception as e:
                logger.error(f"Order attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retry_attempts - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    return {
                        'status': 'error',
                        'error': str(e),
                        'order_params': order_params
                    }
                    
        return {
            'status': 'max_retries_exceeded',
            'attempts': self.max_retry_attempts
        }
        
    def _wait_for_order_fill(self, order_id: str, signal_price: float) -> Dict[str, Any]:
        """Wait for order to fill with timeout."""
        start_time = time.time()
        
        while time.time() - start_time < self.order_timeout_seconds:
            try:
                order_status = self.broker.get_order_status(order_id)
                
                if order_status.get('status') == 'filled':
                    # Calculate slippage
                    fill_price = float(order_status.get('filled_avg_price', signal_price))
                    slippage_bps = ((fill_price - signal_price) / signal_price) * 10000
                    
                    return {
                        'status': 'filled',
                        'order_id': order_id,
                        'fill_price': fill_price,
                        'signal_price': signal_price,
                        'slippage_bps': slippage_bps,
                        'filled_qty': order_status.get('filled_qty', 0),
                        'order_status': order_status
                    }
                elif order_status.get('status') in ['cancelled', 'expired', 'rejected']:
                    return {
                        'status': order_status.get('status'),
                        'order_id': order_id,
                        'order_status': order_status
                    }
                    
                # Wait before polling again
                time.sleep(self.poll_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error checking order status: {e}")
                time.sleep(self.poll_interval_seconds)
                
        # Timeout reached
        return {
            'status': 'timeout',
            'order_id': order_id,
            'elapsed_time': time.time() - start_time
        }
        
    def _aggregate_execution_results(self, results: List[Dict[str, Any]], 
                                    original_trade: Dict[str, Any]) -> Dict[str, Any]:
        """Aggregate multiple execution results into single result."""
        filled_results = [r for r in results if r.get('status') == 'filled']
        
        if not filled_results:
            # No fills, return first error/rejection
            for result in results:
                if result.get('status') != 'filled':
                    return {
                        'trade': original_trade,
                        'status': result.get('status', 'unknown'),
                        'details': result
                    }
                    
        # Calculate aggregate metrics
        total_filled_qty = sum(r.get('filled_qty', 0) for r in filled_results)
        weighted_avg_price = sum(r.get('fill_price', 0) * r.get('filled_qty', 0) 
                                for r in filled_results) / total_filled_qty if total_filled_qty > 0 else 0
                                
        total_slippage_cost = sum(r.get('slippage_bps', 0) * r.get('filled_qty', 0) 
                                 for r in filled_results) / total_filled_qty if total_filled_qty > 0 else 0
                                 
        return {
            'trade': original_trade,
            'status': 'partially_filled' if len(filled_results) < len(results) else 'filled',
            'total_filled_qty': total_filled_qty,
            'average_fill_price': weighted_avg_price,
            'average_slippage_bps': total_slippage_cost,
            'chunk_results': results
        }

# Convenience function
def execute_trades(trades: List[Dict[str, Any]], market_data: pd.DataFrame,
                  current_portfolio: pd.DataFrame = None,
                  config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Execute trades with full safety validation."""
    executor = OrderExecutor(config or {})
    return executor.execute_trades(trades, market_data, current_portfolio)
```

## Key Features to Implement

1. **Pre-trade Veto Integration** - Check with Layer 5 risk system before executing
2. **Short Availability Checking** - Verify shorts can be placed before attempting
3. **Limit Price Calculation** - Apply configurable offset from market price
4. **Order Chunking** - Split large orders based on ADV limits for liquidity
5. **Timeout Handling** - 120s time-in-force with active monitoring
6. **Retry Logic** - Automatic cancel/retry on timeout (max 3 attempts)
7. **Signal Price Recording** - Track for accurate slippage calculation
8. **Comprehensive Logging** - Log all execution details for analysis

## Integration Points

- Calls Layer 5 PreTradeChecker for safety validation
- Uses ShortAvailabilityChecker for short validation
- Works with AlpacaBroker for actual order placement
- Feeds execution data to SlippageTracker for cost analysis