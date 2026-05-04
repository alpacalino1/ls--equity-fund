"""
Meridian Capital Partners · analysis/api_client.py
─────────────────────────────────────────────────────────────────
Anthropic SDK wrapper with caching, retries, and JSON extraction.
"""

import os
import json
import logging
import time
import re
from typing import Dict, Any, Optional
import anthropic
from dotenv import load_dotenv

from .cost_tracker import CostTracker

load_dotenv()

logger = logging.getLogger("meridian.analysis.api_client")

# Default configuration
DEFAULT_MODEL = "claude-3-sonnet-20240229"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.0  # Deterministic for analysis


class APIClient:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize Anthropic API client with caching and retry support."""
        if config is None:
            config = {}
            
        self.api_key = os.getenv("ANTHROPIC_API_KEY") or config.get("api_key")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env or config")
            
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = config.get("model", DEFAULT_MODEL)
        self.max_tokens = config.get("max_tokens", DEFAULT_MAX_TOKENS)
        self.temperature = config.get("temperature", DEFAULT_TEMPERATURE)
        self.cost_tracker = CostTracker(config.get("cost_tracker", {}))
        
        logger.info(f"API Client initialized with model: {self.model}")

    def call_with_retry(self, messages: list, system_prompt: str = "", max_retries: int = 3) -> Dict[str, Any]:
        """
        Call Claude API with exponential backoff retry logic.
        Includes prompt caching and cost tracking.
        """
        cache_control = {"type": "ephemeral"}  # Enable prompt caching
        
        for attempt in range(max_retries):
            try:
                # Add cache control to system prompt if provided
                if system_prompt:
                    system_message = {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": cache_control
                    }
                else:
                    system_message = None
                
                # Prepare messages with cache control for first message
                anthropic_messages = []
                for i, msg in enumerate(messages):
                    if i == 0 and isinstance(msg, dict) and "role" in msg:
                        # Add cache control to first message
                        anthropic_msg = msg.copy()
                        if "cache_control" not in anthropic_msg:
                            anthropic_msg["cache_control"] = cache_control
                        anthropic_messages.append(anthropic_msg)
                    else:
                        anthropic_messages.append(msg)
                
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=[system_message] if system_message else None,
                    messages=anthropic_messages
                )
                
                # Track costs
                if hasattr(response, 'usage'):
                    self.cost_tracker.track_usage(response.usage)
                
                return {
                    "response": response,
                    "content": response.content[0].text if response.content else "",
                    "usage": getattr(response, 'usage', None)
                }
                
            except anthropic.RateLimitError as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 10  # Exponential backoff: 10s, 20s, 40s
                    logger.warning(f"Rate limit hit. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                    time.sleep(wait_time)
                else:
                    raise e
                    
            except anthropic.APIError as e:
                if attempt < max_retries - 1:
                    wait_time = 5
                    logger.warning(f"API error: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise e
                    
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    raise e
        
        raise Exception("Max retries exceeded")

    def extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON from Claude response.
        Handles raw JSON, ```json fences, and prose-wrapped JSON.
        """
        if not text:
            return None
            
        # Case 1: Pure JSON
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Case 2: JSON in ```json fence
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Case 3: JSON in any code fence
        code_match = re.search(r"```(?:\w+)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Case 4: Braced JSON in free text
        brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(1))
            except json.JSONDecodeError:
                pass
        
        logger.warning("Failed to extract JSON from response")
        return None

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for cost prediction."""
        # Very rough estimation: ~4 chars per token
        return len(text) // 4

    def check_cost_ceiling(self) -> bool:
        """Check if we're approaching cost ceiling."""
        return self.cost_tracker.get_total_cost() < self.cost_tracker.cost_ceiling


# Convenience function
def get_api_client(config: Dict[str, Any] = None) -> APIClient:
    """Get configured API client instance."""
    return APIClient(config)
