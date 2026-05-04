# Slippage Tracker Template

This is a template for the costs.py implementation that will handle slippage tracking and cost analysis.

## Planned Implementation

```python
"""
Meridian Capital Partners · execution/costs.py
─────────────────────────────────────────────────────────────────
Slippage tracking and execution cost analysis.
"""

import logging
import pandas as pd
from typing import Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path
import json

logger = logging.getLogger("meridian.execution.costs")

class SlippageTracker:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize slippage tracker."""
        if config is None:
            config = {}
            
        self.config = config
        self.cache_days = config.get("cache_days", 30)
        self.output_dir = Path("output/execution")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load historical execution data
        self.execution_history = self._load_execution_history()
        
        logger.info("Slippage tracker initialized")
        
    def _load_execution_history(self) -> List[Dict[str, Any]]:
        """Load historical execution data from cache."""
        history_file = self.output_dir / "execution_history.json"
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load execution history: {e}")
                return []
        return []
        
    def _save_execution_history(self):
        """Save execution history to cache."""
        history_file = self.output_dir / "execution_history.json"
        try:
            # Keep only recent history
            cutoff_date = datetime.now() - timedelta(days=self.cache_days)
            filtered_history = [
                record for record in self.execution_history
                if datetime.fromisoformat(record.get('timestamp', datetime.now().isoformat())) > cutoff_date
            ]
            
            with open(history_file, 'w') as f:
                json.dump(filtered_history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save execution history: {e}")
            
    def record_execution(self, execution_record: Dict[str, Any]):
        """Record execution details for slippage analysis."""
        execution_record['timestamp'] = datetime.now().isoformat()
        self.execution_history.append(execution_record)
        
        # Save updated history
        self._save_execution_history()
        
        # Log significant slippage
        slippage_bps = execution_record.get('slippage_bps', 0)
        if abs(slippage_bps) > 10:  # More than 10 bps slippage
            logger.warning(f"Significant slippage: {slippage_bps:.1f} bps for {execution_record.get('ticker', 'UNKNOWN')}")
            
    def calculate_slippage(self, fill_price: float, signal_price: float) -> float:
        """
        Calculate slippage in basis points.
        
        Slippage = (fill_price - signal_price) / signal_price * 10,000
        """
        if signal_price == 0:
            return 0.0
            
        return ((fill_price - signal_price) / signal_price) * 10000
        
    def get_rolling_metrics(self, days: int = 30) -> Dict[str, float]:
        """Calculate rolling slippage metrics over specified period."""
        if not self.execution_history:
            return {
                'avg_slippage_bps': 0.0,
                'median_slippage_bps': 0.0,
                'p95_slippage_bps': 0.0,
                'total_dollar_cost': 0.0,
                'execution_count': 0
            }
            
        # Filter to recent executions
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_executions = [
            record for record in self.execution_history
            if datetime.fromisoformat(record.get('timestamp', datetime.now().isoformat())) > cutoff_date
        ]
        
        if not recent_executions:
            return {
                'avg_slippage_bps': 0.0,
                'median_slippage_bps': 0.0,
                'p95_slippage_bps': 0.0,
                'total_dollar_cost': 0.0,
                'execution_count': 0
            }
            
        # Extract slippage values
        slippage_values = [
            record.get('slippage_bps', 0) 
            for record in recent_executions 
            if 'slippage_bps' in record
        ]
        
        if not slippage_values:
            return {
                'avg_slippage_bps': 0.0,
                'median_slippage_bps': 0.0,
                'p95_slippage_bps': 0.0,
                'total_dollar_cost': 0.0,
                'execution_count': len(recent_executions)
            }
            
        # Calculate statistics
        import numpy as np
        slippage_array = np.array(slippage_values)
        
        # Calculate dollar costs (assuming we have quantity and price data)
        total_dollar_cost = 0.0
        for record in recent_executions:
            if 'slippage_bps' in record and 'filled_qty' in record and 'signal_price' in record:
                slippage_decimal = record['slippage_bps'] / 10000
                dollar_cost = abs(slippage_decimal * record['filled_qty'] * record['signal_price'])
                total_dollar_cost += dollar_cost
                
        return {
            'avg_slippage_bps': float(np.mean(slippage_array)),
            'median_slippage_bps': float(np.median(slippage_array)),
            'p95_slippage_bps': float(np.percentile(slippage_array, 95)),
            'total_dollar_cost': total_dollar_cost,
            'execution_count': len(recent_executions)
        }
        
    def get_worst_fills(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get the worst performing fills for dashboard display."""
        if not self.execution_history:
            return []
            
        # Sort by absolute slippage (worst first)
        sorted_executions = sorted(
            self.execution_history,
            key=lambda x: abs(x.get('slippage_bps', 0)),
            reverse=True
        )
        
        # Return top N worst fills
        return sorted_executions[:count]
        
    def generate_cost_report(self, period_days: int = 30) -> Dict[str, Any]:
        """Generate comprehensive cost analysis report."""
        metrics = self.get_rolling_metrics(period_days)
        worst_fills = self.get_worst_fills(5)
        
        return {
            'period_days': period_days,
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics,
            'worst_fills': worst_fills,
            'summary': {
                'total_executions': metrics['execution_count'],
                'avg_slippage': f"{metrics['avg_slippage_bps']:.2f} bps",
                'total_cost': f"${metrics['total_dollar_cost']:,.2f}",
                'severe_slippage_events': len([
                    record for record in self.execution_history
                    if abs(record.get('slippage_bps', 0)) > 20  # More than 20 bps
                ])
            }
        }

# Global instance for convenience
_slippage_tracker = None

def get_slippage_tracker(config: Dict[str, Any] = None) -> SlippageTracker:
    """Get singleton slippage tracker instance."""
    global _slippage_tracker
    if _slippage_tracker is None:
        _slippage_tracker = SlippageTracker(config or {})
    return _slippage_tracker

# Convenience functions
def record_execution(execution_record: Dict[str, Any], config: Dict[str, Any] = None):
    """Record execution for slippage analysis."""
    tracker = get_slippage_tracker(config)
    tracker.record_execution(execution_record)

def get_cost_report(period_days: int = 30, config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Generate cost analysis report."""
    tracker = get_slippage_tracker(config)
    return tracker.generate_cost_report(period_days)
```

## Key Features to Implement

1. **Slippage Calculation** - Precise calculation using (fill - signal) / signal * 10,000
2. **Rolling Statistics** - 30-day averages: avg, median, p95, total dollar cost
3. **Worst Fill Identification** - Surface top 5 worst executions for dashboard review
4. **Historical Tracking** - Persistent storage of execution history with date-based pruning
5. **Cost Reporting** - Comprehensive execution quality metrics for performance analysis
6. **Alert System** - Warning logs for significant slippage events (>10 bps)

## Integration Points

- Receives data from OrderExecutor for each filled trade
- Provides cost metrics to run_execution.py for reporting
- Supplies worst fills data to dashboard for visualization
- Maintains persistent history across sessions