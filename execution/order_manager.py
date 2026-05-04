"""
Meridian Capital Partners · execution/order_manager.py
Order state tracking and lifecycle management.
"""
import logging, json, signal, sys, uuid
from datetime import datetime
from pathlib import Path
from enum import Enum

logger = logging.getLogger("meridian.execution.order_manager")

class OrderStatus(Enum):
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"
    ERROR = "error"

class OrderManager:
    def __init__(self, config=None):
        if config is None: config = {}
        self.orders = {}
        self.output_dir = Path("output/execution")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._load_state()
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _load_state(self):
        sf = self.output_dir / "order_state.json"
        if sf.exists():
            try:
                with open(sf) as f:
                    data = json.load(f)
                for oid, od in data.items():
                    if "created_at" in od: od["created_at"] = datetime.fromisoformat(od["created_at"])
                    if "updated_at" in od: od["updated_at"] = datetime.fromisoformat(od["updated_at"])
                self.orders = data
            except: pass

    def _save_state(self):
        try:
            clean = {}
            for oid, od in self.orders.items():
                d = od.copy()
                if "created_at" in d: d["created_at"] = d["created_at"].isoformat()
                if "updated_at" in d: d["updated_at"] = d["updated_at"].isoformat()
                clean[oid] = d
            with open(self.output_dir / "order_state.json", "w") as f:
                json.dump(clean, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save order state: {e}")

    def _handle_shutdown(self, signum, frame):
        logger.info(f"Signal {signum} — cancelling pending orders, saving state...")
        self.cancel_all_pending()
        self._save_state()
        sys.exit(0)

    def create_order(self, params):
        oid = str(uuid.uuid4())[:8]
        self.orders[oid] = {"order_id": oid, "params": params, "status": OrderStatus.PENDING.value, "created_at": datetime.now(), "updated_at": datetime.now(), "fills": [], "metadata": {}}
        self._save_state()
        return oid

    def update_status(self, oid, status, reason=None, fill_data=None):
        if oid not in self.orders: return
        old = self.orders[oid]["status"]
        self.orders[oid]["status"] = status.value if isinstance(status, OrderStatus) else status
        self.orders[oid]["updated_at"] = datetime.now()
        if reason:
            self.orders[oid].setdefault("status_history", []).append({"timestamp": datetime.now().isoformat(), "from": old, "to": status.value if isinstance(status, OrderStatus) else status, "reason": reason})
        if fill_data: self.orders[oid]["fills"].append(fill_data)
        self._save_state()

    def get_orders_by_status(self, status):
        s = status.value if isinstance(status, OrderStatus) else status
        return [oid for oid, od in self.orders.items() if od.get("status") == s]

    def cancel_all_pending(self):
        count = 0
        for oid in self.get_orders_by_status(OrderStatus.PENDING):
            self.update_status(oid, OrderStatus.CANCELLED, "Shutdown")
            count += 1
        return count

    def get_summary(self):
        s = {}
        for od in self.orders.values():
            st = od.get("status", "unknown")
            s[st] = s.get(st, 0) + 1
        return s

_order_manager = None
def get_order_manager(config=None):
    global _order_manager
    if _order_manager is None: _order_manager = OrderManager(config)
    return _order_manager
