"""
Meridian Capital Partners · execution/executor.py
Order execution with safety checks and retry logic.
"""
import logging, time
import pandas as pd
from typing import Dict, Any, List, Optional

from .broker import AlpacaBroker
from .short_check import ShortAvailabilityChecker
from .costs import get_tracker
from .order_manager import get_order_manager, OrderStatus

logger = logging.getLogger("meridian.execution.executor")

class OrderExecutor:
    def __init__(self, config=None):
        if config is None: config = {}
        self.cfg = config
        self.broker = AlpacaBroker(config.get("broker", {}))
        self.short_checker = ShortAvailabilityChecker(config.get("short_check", {}))
        self.limit_offset_bps = config.get("limit_offset_bps", 5)
        self.timeout = config.get("order_timeout_seconds", 120)
        self.poll = config.get("poll_interval_seconds", 5)
        self.max_retries = config.get("max_retry_attempts", 3)
        self.adv_limit = config.get("adv_limit_percentage", 0.02)

    def execute_trades(self, trades, market_data, current_portfolio=None):
        results = []
        for trade in trades:
            try:
                results.append(self._execute_single(trade, market_data, current_portfolio))
            except Exception as e:
                logger.error(f"Trade failed {trade}: {e}")
                results.append({"trade": trade, "status": "error", "error": str(e)})
        return results

    def _execute_single(self, trade, market_data, current_portfolio=None):
        ticker = trade.get("ticker", trade.get("symbol", "???"))
        side = trade.get("side", "buy")
        qty = trade.get("quantity", trade.get("qty", 0))
        logger.info(f"Executing: {side} {qty} {ticker}")

        # Short check
        if side == "short" and not self.short_checker.is_shortable(ticker):
            return {"trade": trade, "status": "rejected", "reason": "short_not_available"}

        # Limit price
        ticker_data = market_data[market_data["ticker"] == ticker] if market_data is not None else pd.DataFrame()
        if ticker_data.empty:
            limit_price = 100.0
        else:
            price = ticker_data["close"].iloc[-1] if "close" in ticker_data.columns else 100.0
            offset = self.limit_offset_bps / 10000
            limit_price = price * (1 - offset) if side in ["buy", "cover"] else price * (1 + offset)

        # Place with retry
        for attempt in range(self.max_retries):
            try:
                result = self.broker.place_order(symbol=ticker, qty=qty, side=side, type="limit", limit_price=round(limit_price, 2))
                oid = result.get("id", "mock-"+str(time.time()))

                # Wait for fill
                start = time.time()
                while time.time() - start < self.timeout:
                    status = self.broker.get_order(oid)
                    if status.get("status") == "filled":
                        fill_price = float(status.get("filled_avg_price", limit_price))
                        slip = ((fill_price - limit_price) / limit_price) * 10000
                        get_tracker().record({"ticker": ticker, "side": side, "qty": qty, "signal_price": limit_price, "fill_price": fill_price, "slippage_bps": slip, "filled_qty": int(status.get("filled_qty", qty)), "order_id": oid})
                        return {"trade": trade, "status": "filled", "fill_price": fill_price, "slippage_bps": slip, "filled_qty": int(status.get("filled_qty", qty))}
                    elif status.get("status") in ["cancelled", "expired", "rejected"]:
                        if attempt < self.max_retries - 1:
                            logger.info(f"Order {oid} {status['status']}, retrying...")
                            break
                        return {"trade": trade, "status": status.get("status"), "order_id": oid}
                    time.sleep(self.poll)

                # Timeout
                if attempt < self.max_retries - 1:
                    self.broker.cancel_order(oid)
                    time.sleep(1)
                else:
                    return {"trade": trade, "status": "timeout", "order_id": oid}
            except Exception as e:
                if attempt == self.max_retries - 1:
                    return {"trade": trade, "status": "error", "error": str(e)}
                time.sleep(2 ** attempt)
        return {"trade": trade, "status": "max_retries"}

def execute_trades(trades, market_data, current_portfolio=None, config=None):
    return OrderExecutor(config).execute_trades(trades, market_data, current_portfolio)
