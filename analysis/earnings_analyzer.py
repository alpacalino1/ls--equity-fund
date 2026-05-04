"""
Meridian Capital Partners · analysis/earnings_analyzer.py
─────────────────────────────────────────────────────────────────
Earnings call transcript analyzer using Claude.
"""

import logging
import json
from typing import Dict, Any, Optional
import pandas as pd

from .api_client import get_api_client
from .cache import AnalysisCache

logger = logging.getLogger("meridian.analysis.earnings")


class EarningsAnalyzer:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize earnings analyzer with API client and cache."""
        if config is None:
            config = {}
            
        self.api_client = get_api_client(config.get("api", {}))
        self.cache = AnalysisCache(**config.get("cache", {}))
        self.max_chars = config.get("max_chars", 120000)  # 120K chars limit

    def analyze_transcript(self, ticker: str, transcript_text: str, 
                          transcript_date: str = None) -> Optional[Dict[str, Any]]:
        """
        Analyze earnings call transcript and return structured scores.
        
        Args:
            ticker: Stock ticker symbol
            transcript_text: Earnings call transcript text
            transcript_date: Date of transcript (for caching)
            
        Returns:
            Dict with scores and analysis, or None if no transcript
        """
        if not transcript_text:
            logger.info(f"No transcript for {ticker}")
            return None
            
        artifact_id = transcript_date or "latest"
        
        # Check cache first
        cached_result = self.cache.get("earnings_analyzer", ticker, artifact_id)
        if cached_result is not None:
            logger.info(f"Cache hit for {ticker} earnings analysis")
            return cached_result
            
        # Truncate if too long
        if len(transcript_text) > self.max_chars:
            logger.warning(f"Truncating transcript for {ticker} from {len(transcript_text)} to {self.max_chars} chars")
            transcript_text = transcript_text[:self.max_chars]
            
        logger.info(f"Analyzing earnings transcript for {ticker} ({len(transcript_text)} chars)")
        
        # Check cost ceiling before proceeding
        if not self.api_client.check_cost_ceiling():
            logger.warning(f"Cost ceiling exceeded, skipping {ticker}")
            return None
            
        try:
            result = self._call_claude_analysis(ticker, transcript_text)
            
            # Cache the result
            if result:
                self.cache.put("earnings_analyzer", ticker, artifact_id, result)
                logger.info(f"Cached earnings analysis for {ticker}")
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze earnings transcript for {ticker}: {e}")
            return None

    def _call_claude_analysis(self, ticker: str, transcript_text: str) -> Dict[str, Any]:
        """Call Claude API to analyze transcript."""
        system_prompt = """
        You are a forensic financial analyst specializing in earnings call analysis.
        Your task is to analyze earnings call transcripts and provide objective scores 
        across six critical dimensions. Always respond with valid JSON in this exact format:
        
        {
            "management_confidence": 1-10 score with reasoning,
            "revenue_guidance": 1-10 score with reasoning,
            "margin_trajectory": 1-10 score with reasoning,
            "competitive_position": 1-10 score with reasoning,
            "risk_factors": 1-10 score with reasoning,
            "capital_allocation": 1-10 score with reasoning,
            "bull_case": "Bullish thesis based on the call",
            "bear_case": "Bearish concerns raised in the call",
            "key_quotes": ["Quote 1", "Quote 2", "Quote 3"],
            "one_line_summary": "Concise summary of the call's key takeaway"
        }
        
        Scoring guidelines:
        - 1 = Extremely negative/weak
        - 5 = Neutral/Average
        - 10 = Extremely positive/strong
        
        For reasoning fields, provide 1-2 concise sentences explaining the score.
        For key_quotes, extract 2-4 representative quotes from management.
        """
        
        user_prompt = f"""
        Please analyze this earnings call transcript for {ticker}:
        
        <transcript>
        {transcript_text}
        </transcript>
        
        Focus on management tone, guidance clarity, competitive positioning, margin outlook,
        risk acknowledgment, and capital allocation priorities. Provide specific evidence
        from the transcript to support each score.
        """
        
        messages = [{"role": "user", "content": user_prompt}]
        
        response = self.api_client.call_with_retry(messages, system_prompt)
        result = self.api_client.extract_json(response["content"])
        
        if not result:
            logger.warning(f"Failed to extract JSON from Claude response for {ticker}")
            # Return a basic structure with error indication
            return {
                "error": "Failed to parse Claude response",
                "raw_response": response["content"][:500] + "..." if len(response["content"]) > 500 else response["content"]
            }
            
        # Ensure all required fields are present
        required_fields = [
            "management_confidence", "revenue_guidance", "margin_trajectory",
            "competitive_position", "risk_factors", "capital_allocation",
            "bull_case", "bear_case", "key_quotes", "one_line_summary"
        ]
        
        for field in required_fields:
            if field not in result:
                result[field] = "Not analyzed"
                
        # Ensure key_quotes is a list
        if not isinstance(result.get("key_quotes", []), list):
            result["key_quotes"] = []
            
        return result

    def analyze_multiple_transcripts(self, ticker: str, 
                                   transcripts_data: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
        """
        Analyze multiple earnings transcripts for a single ticker.
        
        Args:
            ticker: Stock ticker symbol
            transcripts_data: Dict mapping dates to transcript texts
            
        Returns:
            Dict mapping dates to analysis results
        """
        results = {}
        for transcript_date, transcript_text in transcripts_data.items():
            try:
                result = self.analyze_transcript(ticker, transcript_text, transcript_date)
                results[transcript_date] = result
            except Exception as e:
                logger.error(f"Failed to analyze transcript for {ticker} on {transcript_date}: {e}")
                results[transcript_date] = {"error": str(e)}
                
        return results


# Convenience function
def analyze_earnings_calls(ticker: str, transcript_text: str, 
                          transcript_date: str = None, config: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    """Analyze earnings call transcript."""
    analyzer = EarningsAnalyzer(config or {})
    return analyzer.analyze_transcript(ticker, transcript_text, transcript_date)
