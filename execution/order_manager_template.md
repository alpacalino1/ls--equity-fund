# Order Manager Template

This is a template for the order_manager.py implementation that will handle order state tracking and lifecycle management.

## Planned Implementation

```python
"""
Meridian Capital Partners · execution/order_manager.py
─────────────────────────────────────────────────────────────────
Order state tracking and lifecycle management.
"""

import logging
import signal
import sys
from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime
import json
from pathlib import Path

logger = logging.getLogger("meridian.execution.order_manager")

class OrderStatus(Enum):
    """Order status enumeration."""
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"
    ERROR = "error"

class OrderManager:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize order manager."""
        if config is None:
            config = {}
            
        self.config = config
        self.orders = {}  # Track all orders by ID
        self.output_dir = Path("output/execution")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load persisted order state
        self._load_order_state()
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info("Order manager initialized")
        
    def _load_order_state(self):
        """Load persisted order state from file."""
        state_file = self.output_dir / "order_state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    state_data = json.load(f)
                    
                # Convert string timestamps back to datetime objects
                for order_id, order_data in state_data.items():
                    if 'created_at' in order_data:
                        order_data['created_at'] = datetime.fromisoformat(order_data['created_at'])
                    if 'updated_at' in order_data:
                        order_data['updated_at'] = datetime.fromisoformat(order_data['updated_at'])
                        
                self.orders = state_data
                logger.info(f"Loaded {len(self.orders)} orders from persistent state")
                
            except Exception as e:
                logger.warning(f"Failed to load order state: {e}")
                
    def _save_order_state(self):
        """Save order state to file."""
        state_file = self.output_dir / "order_state.json"
        try:
            # Convert datetime objects to strings for JSON serialization
            serializable_orders = {}
            for order_id, order_data in self.orders.items():
                data_copy = order_data.copy()
                if 'created_at' in data_copy:
                    data_copy['created_at'] = data_copy['created_at'].isoformat()
                if 'updated_at' in data_copy:
                    data_copy['updated_at'] = data_copy['updated_at'].isoformat()
                serializable_orders[order_id] = data_copy
                
            with open(state_file, 'w') as f:
                json.dump(serializable_orders, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save order state: {e}")
            
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self._handle_shutdown()
            sys.exit(0)
            
        # Handle SIGINT (Ctrl+C) and SIGTERM
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
    def _handle_shutdown(self):
        """Handle graceful shutdown by cancelling pending orders."""
        pending_orders = self.get_orders_by_status(OrderStatus.PENDING)
        
        if pending_orders:
            logger.info(f"Cancelling {len(pending_orders)} pending orders...")
            
            for order_id in pending_orders:
                try:
                    # This would call the broker to cancel the order
                    # self.broker.cancel_order(order_id)
                    logger.info(f"Would cancel order {order_id} (mock)")
                    
                    # Update order status
                    self.update_order_status(order_id, OrderStatus.CANCELLED, 
                                           reason="Shutdown cancellation")
                                           
                except Exception as e:
                    logger.error(f"Failed to cancel order {order_id}: {e}")
        else:
            logger.info("No pending orders to cancel")
            
        # Save final state
        self._save_order_state()
        logger.info("Order manager shutdown complete")
        
    def create_order(self, order_params: Dict[str, Any]) -> str:
        """Create and track a new order."""
        import uuid
        order_id = str(uuid.uuid4())
        
        order_record = {
            'order_id': order_id,
            'params': order_params,
            'status': OrderStatus.PENDING.value,
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
            'fills': [],
            'metadata': {}
        }
        
        self.orders[order_id] = order_record
        self._save_order_state()
        
        logger.info(f"Created order {order_id}: {order_params['side']} {order_params['qty']} {order_params['symbol']}")
        return order_id
        
    def update_order_status(self, order_id: str, status: OrderStatus, 
                           reason: str = None, fill_data: Dict[str, Any] = None):
        """Update order status and metadata."""
        if order_id not in self.orders:
            logger.warning(f"Attempt to update non-existent order {order_id}")
            return
            
        order = self.orders[order_id]
        old_status = order.get('status', 'unknown')
        
        order['status'] = status.value
        order['updated_at'] = datetime.now()
        
        if reason:
            if 'status_history' not in order:
                order['status_history'] = []
            order['status_history'].append({
                'timestamp': datetime.now().isoformat(),
                'from_status': old_status,
                'to_status': status.value,
                'reason': reason
            })
            
        if fill_data:
            order['fills'].append(fill_data)
            
        self._save_order_state()
        
        logger.debug(f"Order {order_id} status updated: {old_status} -> {status.value}")
        
    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get current status and details for an order."""
        return self.orders.get(order_id)
        
    def get_orders_by_status(self, status: OrderStatus) -> List[str]:
        """Get all order IDs with specified status."""
        return [
            order_id for order_id, order_data in self.orders.items()
            if order_data.get('status') == status.value
        ]
        
    def get_active_orders(self) -> List[str]:
        """Get all non-terminal orders (pending, partially filled)."""
        active_statuses = [OrderStatus.PENDING.value, OrderStatus.PARTIALLY_FILLED.value]
        return [
            order_id for order_id, order_data in self.orders.items()
            if order_data.get('status') in active_statuses
        ]
        
    def add_order_fill(self, order_id: str, fill_data: Dict[str, Any]):
        """Add fill information to an order."""
        if order_id not in self.orders:
            logger.warning(f"Attempt to add fill to non-existent order {order_id}")
            return
            
        order = self.orders[order_id]
        order['fills'].append(fill_data)
        order['updated_at'] = datetime.now()
        
        # Update status if needed
        total_filled = sum(fill.get('qty', 0) for fill in order['fills'])
        ordered_qty = order['params'].get('qty', 0)
        
        if total_filled > 0 and total_filled < ordered_qty:
            self.update_order_status(order_id, OrderStatus.PARTIALLY_FILLED)
        elif total_filled >= ordered_qty:
            self.update_order_status(order_id, OrderStatus.FILLED)
            
        self._save_order_state()
        
    def cancel_all_pending(self) -> int:
        """Cancel all pending orders and return count cancelled."""
        pending_orders = self.get_orders_by_status(OrderStatus.PENDING)
        cancelled_count = 0
        
        for order_id in pending_orders:
            try:
                # This would call the broker to cancel the order
                # self.broker.cancel_order(order_id)
                logger.info(f"Would cancel order {order_id} (mock)")
                
                self.update_order_status(order_id, OrderStatus.CANCELLED, 
                                       reason="Manual cancellation")
                cancelled_count += 1
                
            except Exception as e:
                logger.error(f"Failed to cancel order {order_id}: {e}")
                
        logger.info(f"Cancelled {cancelled_count} pending orders")
        return cancelled_count
        
    def get_order_summary(self) -> Dict[str, int]:
        """Get summary of order counts by status."""
        summary = {}
        for order_id, order_data in self.orders.items():
            status = order_data.get('status', 'unknown')
            summary[status] = summary.get(status, 0) + 1
            
        return summary
        
    def get_recent_orders(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get most recently updated orders."""
        sorted_orders = sorted(
            self.orders.items(),
            key=lambda x: x[1].get('updated_at', datetime.min),
            reverse=True
        )
        
        return [order_data for _, order_data in sorted_orders[:count]]
        
    def archive_completed_orders(self, days_old: int = 30) -> int:
        """Archive old completed orders to reduce memory footprint."""
        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days_old)
        archived_count = 0
        
        # In a real implementation, you'd move old orders to an archive file
        # For now, we'll just log which orders would be archived
        terminal_statuses = [
            OrderStatus.FILLED.value, 
            OrderStatus.CANCELLED.value, 
            OrderStatus.EXPIRED.value, 
            OrderStatus.REJECTED.value,
            OrderStatus.ERROR.value
        ]
        
        for order_id, order_data in self.orders.items():
            if (order_data.get('status') in terminal_statuses and
                order_data.get('updated_at', datetime.min) < cutoff_date):
                logger.debug(f"Would archive completed order {order_id}")
                archived_count += 1
                
        return archived_count

# Global instance for convenience
_order_manager = None

def get_order_manager(config: Dict[str, Any] = None) -> OrderManager:
    """Get singleton order manager instance."""
    global _order_manager
    if _order_manager is None:
        _order_manager = OrderManager(config or {})
    return _order_manager

# Convenience functions
def create_order(order_params: Dict[str, Any], config: Dict[str, Any] = None) -> str:
    """Create and track a new order."""
    manager = get_order_manager(config)
    return manager.create_order(order_params)

def cancel_all_pending_orders(config: Dict[str, Any] = None) -> int:
    """Cancel all pending orders."""
    manager = get_order_manager(config)
    return manager.cancel_all_pending()
```

## Key Features to Implement

1. **Order State Tracking** - Maintain complete lifecycle from pending to filled/cancelled
2. **Persistent Storage** - Save order state to disk for recovery across sessions
3. **Signal Handling** - Graceful shutdown with automatic pending order cancellation
4. **Status History** - Track all state transitions with timestamps and reasons
5. **Fill Aggregation** - Associate partial fills with orders and calculate completion
6. **Batch Operations** - Cancel all pending orders, get status summaries
7. **Order Archiving** - Automatic cleanup of old completed orders

## Integration Points

- Works with OrderExecutor to track all placed orders
- Integrates with AlpacaBroker for actual order management
- Provides SIGINT handling for safe shutdown procedures
- Maintains execution logs for audit trail and debugging