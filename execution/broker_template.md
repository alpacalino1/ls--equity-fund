# Broker Module Template

This is a template for the broker.py implementation that will handle Alpaca API connections.

## Planned Implementation

```python
"""
Meridian Capital Partners · execution/broker.py
─────────────────────────────────────────────────────────────────
Alpaca API connection and portfolio synchronization.
"""

import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import alpaca

logger = logging.getLogger("meridian.execution.broker")

class AlpacaBroker:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize Alpaca broker connection."""
        if config is None:
            config = {}
            
        # Load environment variables
        load_dotenv()
        
        # Configuration
        self.mode = config.get("mode", "paper")  # "paper" or "live"
        self.paper_url = config.get("api_url_paper", "https://paper-api.alpaca.markets")
        self.live_url = config.get("api_url_live", "https://api.alpaca.markets")
        
        # API credentials
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        
        if not self.api_key or not self.secret_key:
            raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")
            
        # Initialize Alpaca API client
        self.client = self._initialize_client()
        
        logger.info(f"Alpaca broker initialized in {self.mode} mode")
        
    def _initialize_client(self):
        """Initialize Alpaca API client based on mode."""
        # Implementation will use alpaca-py SDK
        pass
        
    def sync_portfolio(self) -> Dict[str, Any]:
        """Sync current portfolio state from Alpaca."""
        # Implementation will fetch positions, orders, account info
        pass
        
    def place_order(self, order_params: Dict[str, Any]) -> Optional[str]:
        """Place order with Alpaca API."""
        # Implementation will handle order placement with safety checks
        pass
        
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get order status from Alpaca."""
        # Implementation will fetch order details
        pass
        
    def cancel_order(self, order_id: str) -> bool:
        """Cancel order with Alpaca API."""
        # Implementation will handle order cancellation
        pass
        
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information from Alpaca."""
        # Implementation will fetch buying power, cash, etc.
        pass

# Convenience function
def get_broker(config: Dict[str, Any] = None) -> AlpacaBroker:
    """Get configured broker instance."""
    return AlpacaBroker(config)
```

## Key Features to Implement

1. **Paper Trading Default** - Hardcoded paper URL unless explicitly set to live
2. **Live Trading Safety** - Require config setting AND user confirmation
3. **Environment Variables** - Load ALPACA_API_KEY and ALPACA_SECRET_KEY from .env
4. **Portfolio Sync** - Fetch current positions and account status on startup
5. **Order Management** - Place, check, and cancel orders with Alpaca
6. **Error Handling** - Exponential backoff and retry logic for API calls
7. **Logging** - Comprehensive logging of all broker activities

## Integration Points

- Works with order_executor.py for placing trades
- Provides account data to risk management
- Syncs positions for accurate portfolio tracking