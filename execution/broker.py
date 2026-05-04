"""
Meridian Capital Partners · execution/broker.py
Alpaca API connection with paper trading default.
"""
import os, logging, time
from typing import Dict, Any, Optional
from dotenv import load_dotenv

logger = logging.getLogger("meridian.execution.broker")
load_dotenv()

class AlpacaBroker:
    def __init__(self, config: Dict[str, Any] = None):
        if config is None: config = {}
        self.mode = config.get("mode", "paper")
        self.paper_url = config.get("api_url_paper", "https://paper-api.alpaca.markets")
        self.live_url = config.get("api_url_live", "https://api.alpaca.markets")
        self.api_key = os.getenv("ALPACA_API_KEY", "")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        self.base_url = self.paper_url if self.mode != "live" else self.live_url
        if not self.api_key:
            logger.warning("No ALPACA_API_KEY set — broker will run in mock mode")
        logger.info(f"Alpaca broker initialized in {self.mode} mode")

    def _headers(self):
        return {"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.secret_key}

    def _request(self, method, path, **kw):
        import requests
        url = f"{self.base_url}/v2/{path}"
        for attempt in range(3):
            try:
                resp = requests.request(method, url, headers=self._headers(), timeout=30, **kw)
                if resp.status_code == 429:
                    time.sleep((2**attempt) * 2)
                    continue
                resp.raise_for_status()
                return resp.json() if resp.text else {}
            except Exception as e:
                if attempt == 2: raise e
                time.sleep(2**attempt)

    def get_account(self): return self._request("GET", "account") if self.api_key else {"buying_power": "1000000", "cash": "500000"}
    def get_positions(self): return self._request("GET", "positions") if self.api_key else []
    def place_order(self, symbol, qty, side, type="limit", limit_price=None, time_in_force="day"):
        if not self.api_key:
            logger.info(f"MOCK ORDER: {side} {qty} {symbol} @ {limit_price}")
            return {"id": "mock-"+str(time.time()), "status": "filled", "filled_avg_price": limit_price or 100.0, "filled_qty": qty}
        return self._request("POST", "orders", json={"symbol": symbol, "qty": qty, "side": side, "type": type, "limit_price": limit_price, "time_in_force": time_in_force})
    def get_order(self, order_id): return self._request("GET", f"orders/{order_id}") if self.api_key else {"id": order_id, "status": "filled", "filled_avg_price": 100.0}
    def cancel_order(self, order_id): return self._request("DELETE", f"orders/{order_id}") if self.api_key else {}

def get_broker(config=None): return AlpacaBroker(config)
