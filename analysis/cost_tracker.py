"""
Meridian Capital Partners · analysis/cost_tracker.py
─────────────────────────────────────────────────────────────────
Tracks API usage costs with hard ceiling enforcement.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("meridian.analysis.cost_tracker")

# Anthropic pricing (as of 2024 - update as needed)
# Claude Sonnet 3.5: $3/1M input tokens, $15/1M output tokens
# Claude Opus: $15/1M input tokens, $75/1M output tokens
PRICING = {
    "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0, "cache_write": 18.75, "cache_read": 1.50},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25, "cache_write": 0.30, "cache_read": 0.03},
}

# Default ceiling: $25 per run
DEFAULT_COST_CEILING = 25.0


@dataclass
class UsageRecord:
    """Record of API usage for cost tracking."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


class CostTracker:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize cost tracker with configuration."""
        if config is None:
            config = {}
            
        self.cost_ceiling = config.get("cost_ceiling", DEFAULT_COST_CEILING)
        self.model = config.get("model", "claude-3-sonnet-20240229")
        self.pricing = PRICING.get(self.model, PRICING["claude-3-sonnet-20240229"])
        self.usage_records: list[UsageRecord] = []
        self.total_cost = 0.0
        
        logger.info(f"Cost tracker initialized with ceiling: ${self.cost_ceiling}")

    def track_usage(self, usage: Any) -> float:
        """
        Track API usage and calculate cost.
        Usage object from Anthropic response should have token counts.
        """
        if not usage:
            return 0.0
            
        record = UsageRecord()
        
        # Extract token counts from usage object
        if hasattr(usage, 'input_tokens'):
            record.input_tokens = usage.input_tokens
        if hasattr(usage, 'output_tokens'):
            record.output_tokens = usage.output_tokens
        if hasattr(usage, 'cache_creation_input_tokens'):
            record.cache_creation_input_tokens = usage.cache_creation_input_tokens
        if hasattr(usage, 'cache_read_input_tokens'):
            record.cache_read_input_tokens = usage.cache_read_input_tokens
            
        self.usage_records.append(record)
        
        # Calculate cost
        cost = self._calculate_cost(record)
        self.total_cost += cost
        
        logger.debug(f"Usage tracked: input={record.input_tokens}, output={record.output_tokens}, "
                    f"cache_write={record.cache_creation_input_tokens}, cache_read={record.cache_read_input_tokens}, "
                    f"cost=${cost:.4f}, total=${self.total_cost:.4f}")
        
        # Check ceiling
        if self.total_cost > self.cost_ceiling:
            logger.warning(f"Cost ceiling exceeded: ${self.total_cost:.4f} > ${self.cost_ceiling}")
            
        return cost

    def _calculate_cost(self, record: UsageRecord) -> float:
        """Calculate cost based on usage record and pricing."""
        input_cost = (record.input_tokens * self.pricing["input"]) / 1_000_000
        output_cost = (record.output_tokens * self.pricing["output"]) / 1_000_000
        cache_write_cost = (record.cache_creation_input_tokens * self.pricing["cache_write"]) / 1_000_000
        cache_read_cost = (record.cache_read_input_tokens * self.pricing["cache_read"]) / 1_000_000
        
        return input_cost + output_cost + cache_write_cost + cache_read_cost

    def get_total_cost(self) -> float:
        """Get total accumulated cost."""
        return self.total_cost

    def get_token_usage(self) -> Dict[str, int]:
        """Get total token usage across all calls."""
        totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0
        }
        
        for record in self.usage_records:
            totals["input_tokens"] += record.input_tokens
            totals["output_tokens"] += record.output_tokens
            totals["cache_creation_input_tokens"] += record.cache_creation_input_tokens
            totals["cache_read_input_tokens"] += record.cache_read_input_tokens
            
        return totals

    def reset(self):
        """Reset cost tracking."""
        self.usage_records = []
        self.total_cost = 0.0
        logger.info("Cost tracker reset")

    def check_ceiling(self) -> bool:
        """Check if we're within cost ceiling."""
        return self.total_cost <= self.cost_ceiling

    def remaining_budget(self) -> float:
        """Get remaining budget before ceiling."""
        return max(0.0, self.cost_ceiling - self.total_cost)
