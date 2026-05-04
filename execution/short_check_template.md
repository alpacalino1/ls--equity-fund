# Short Availability Checker Template

This is a template for the short_check.py implementation that will handle short availability verification.

## Planned Implementation

```python
"""
Meridian Capital Partners · execution/short_check.py
─────────────────────────────────────────────────────────────────
Short availability checking for Alpaca trading.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import json
from pathlib import Path

logger = logging.getLogger("meridian.execution.short_check")

class ShortAvailabilityChecker:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize short availability checker with caching."""
        if config is None:
            config = {}
            
        self.config = config
        self.cache_days = config.get("cache_days", 7)
        self.cache_file = Path("cache/short_availability.json")
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load cached short availability data
        self.short_cache = self._load_cache()
        
        logger.info("Short availability checker initialized")
        
    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        """Load short availability cache from file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    
                # Convert string dates back to datetime objects
                converted_cache = {}
                for ticker, data in cache_data.items():
                    if 'timestamp' in data:
                        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
                    converted_cache[ticker] = data
                    
                return converted_cache
            except Exception as e:
                logger.warning(f"Failed to load short availability cache: {e}")
                return {}
        return {}
        
    def _save_cache(self):
        """Save short availability cache to file."""
        try:
            # Clean expired entries
            cutoff_date = datetime.now() - timedelta(days=self.cache_days)
            cleaned_cache = {
                ticker: data for ticker, data in self.short_cache.items()
                if data.get('timestamp', datetime.min) > cutoff_date
            }
            
            # Convert datetime objects to strings for JSON serialization
            serializable_cache = {}
            for ticker, data in cleaned_cache.items():
                data_copy = data.copy()
                if 'timestamp' in data_copy:
                    data_copy['timestamp'] = data_copy['timestamp'].isoformat()
                serializable_cache[ticker] = data_copy
                
            with open(self.cache_file, 'w') as f:
                json.dump(serializable_cache, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save short availability cache: {e}")
            
    def is_shortable(self, ticker: str, force_refresh: bool = False) -> bool:
        """
        Check if a ticker is shortable and easy to borrow.
        
        Args:
            ticker: Stock symbol to check
            force_refresh: Bypass cache and force API check
            
        Returns:
            bool: True if shortable and easy to borrow
        """
        # Check cache first (unless forcing refresh)
        if not force_refresh and ticker in self.short_cache:
            cached_data = self.short_cache[ticker]
            cache_age = datetime.now() - cached_data.get('timestamp', datetime.min)
            
            if cache_age < timedelta(days=self.cache_days):
                # Return cached result
                is_shortable = cached_data.get('shortable', False)
                is_easy_to_borrow = cached_data.get('easy_to_borrow', False)
                
                logger.debug(f"Short check for {ticker}: cached result = {is_shortable and is_easy_to_borrow}")
                return is_shortable and is_easy_to_borrow
                
        # Check with broker API
        try:
            short_info = self._check_short_availability_api(ticker)
            
            # Cache the result
            self.short_cache[ticker] = {
                'shortable': short_info.get('shortable', False),
                'easy_to_borrow': short_info.get('easy_to_borrow', False),
                'timestamp': datetime.now()
            }
            
            # Save updated cache
            self._save_cache()
            
            # Return combined result
            result = short_info.get('shortable', False) and short_info.get('easy_to_borrow', False)
            
            if not result:
                logger.info(f"Short not available for {ticker}: shortable={short_info.get('shortable', False)}, easy_to_borrow={short_info.get('easy_to_borrow', False)}")
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to check short availability for {ticker}: {e}")
            # On API failure, check if we have recent cached data we can use
            if ticker in self.short_cache:
                cached_data = self.short_cache[ticker]
                cache_age = datetime.now() - cached_data.get('timestamp', datetime.min)
                if cache_age < timedelta(days=self.cache_days * 2):  # Allow double cache time on API failure
                    logger.warning(f"Using stale cache data for {ticker} due to API failure")
                    return cached_data.get('shortable', False) and cached_data.get('easy_to_borrow', False)
                    
            # No cache or stale cache, assume not shortable
            logger.warning(f"Assuming {ticker} not shortable due to API failure and no valid cache")
            return False
            
    def _check_short_availability_api(self, ticker: str) -> Dict[str, Any]:
        """
        Check short availability with Alpaca API.
        
        This would typically use the Alpaca assets endpoint or other short availability endpoints.
        """
        # This is where we'd integrate with Alpaca's short availability API
        # For now, returning mock data structure showing what the real implementation would do
        
        # Example of what real API call might look like:
        # asset = self.broker.client.get_asset(ticker)
        # shortable = getattr(asset, 'shortable', False)
        # easy_to_borrow = getattr(asset, 'easy_to_borrow', False)
        
        # Mock implementation for template:
        return {
            'shortable': True,  # Would come from Alpaca API
            'easy_to_borrow': True  # Would come from Alpaca API
        }
        
    def get_short_info(self, ticker: str) -> Dict[str, Any]:
        """Get detailed short availability information."""
        if ticker in self.short_cache:
            cached_data = self.short_cache[ticker]
            cache_age = datetime.now() - cached_data.get('timestamp', datetime.min)
            
            if cache_age < timedelta(days=self.cache_days):
                return {
                    'ticker': ticker,
                    'shortable': cached_data.get('shortable', False),
                    'easy_to_borrow': cached_data.get('easy_to_borrow', False),
                    'cached': True,
                    'cache_age_hours': cache_age.total_seconds() / 3600
                }
                
        # Force fresh check
        try:
            short_info = self._check_short_availability_api(ticker)
            short_info['ticker'] = ticker
            short_info['cached'] = False
            return short_info
        except Exception as e:
            return {
                'ticker': ticker,
                'shortable': False,
                'easy_to_borrow': False,
                'error': str(e)
            }
            
    def refresh_all_cache(self):
        """Force refresh of all cached short availability data."""
        tickers_to_refresh = list(self.short_cache.keys())
        refreshed_count = 0
        
        for ticker in tickers_to_refresh:
            try:
                if self.is_shortable(ticker, force_refresh=True):
                    refreshed_count += 1
            except Exception as e:
                logger.error(f"Failed to refresh short availability for {ticker}: {e}")
                
        logger.info(f"Refreshed short availability for {refreshed_count}/{len(tickers_to_refresh)} tickers")
        
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about short availability cache."""
        total_cached = len(self.short_cache)
        expired_count = 0
        shortable_count = 0
        
        cutoff_date = datetime.now() - timedelta(days=self.cache_days)
        
        for ticker, data in self.short_cache.items():
            cache_age = datetime.now() - data.get('timestamp', datetime.min)
            if data.get('timestamp', datetime.min) < cutoff_date:
                expired_count += 1
            if data.get('shortable', False) and data.get('easy_to_borrow', False):
                shortable_count += 1
                
        return {
            'total_cached': total_cached,
            'expired': expired_count,
            'shortable': shortable_count,
            'cache_days': self.cache_days
        }

# Convenience function
def check_short_availability(ticker: str, config: Dict[str, Any] = None) -> bool:
    """Check if a ticker is shortable."""
    checker = ShortAvailabilityChecker(config or {})
    return checker.is_shortable(ticker)
```

## Key Features to Implement

1. **Alpaca API Integration** - Check `shortable` and `easy_to_borrow` flags via Alpaca assets endpoint
2. **7-Day Caching** - Store results locally to avoid excessive API calls
3. **Cache Management** - Automatic cleanup of expired entries, JSON persistence
4. **Graceful Degradation** - Use cached data when API fails, with extended validity periods
5. **Detailed Information** - Return comprehensive short availability status for logging
6. **Batch Refresh** - Capability to refresh all cached data programmatically

## Integration Points

- Called by OrderExecutor before placing short sell orders
- Uses AlpacaBroker for actual API communication
- Maintains persistent cache across sessions
- Provides detailed logging for unavailable shorts