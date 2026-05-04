"""
Meridian Capital Partners · analysis/filing_analyzer.py
─────────────────────────────────────────────────────────────────
SEC filing analyzer for forensic accounting review using Claude.
"""

import logging
import json
from typing import Dict, Any, Optional, List
import pandas as pd

from .api_client import get_api_client
from .cache import AnalysisCache

logger = logging.getLogger("meridian.analysis.filing")


class FilingAnalyzer:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize filing analyzer with API client and cache."""
        if config is None:
            config = {}
            
        self.api_client = get_api_client(config.get("api", {}))
        self.cache = AnalysisCache(**config.get("cache", {}))

    def analyze_filings(self, ticker: str, fundamental_metrics: pd.DataFrame, 
                       filing_texts: List[str], filing_dates: List[str]) -> Optional[Dict[str, Any]]:
        """
        Analyze SEC filings for forensic accounting signs.
        
        Args:
            ticker: Stock ticker symbol
            fundamental_metrics: DataFrame with 8 quarters of metrics
            filing_texts: List of filing texts (10-K, 10-Q)
            filing_dates: Corresponding filing dates
            
        Returns:
            Dict with forensic analysis, or None if no data
        """
        if fundamental_metrics.empty or not filing_texts:
            logger.info(f"No filings or metrics for {ticker}")
            return None
            
        # Use most recent filing date as artifact ID
        artifact_id = max(filing_dates) if filing_dates else "latest"
        
        # Check cache first
        cached_result = self.cache.get("filing_analyzer", ticker, artifact_id)
        if cached_result is not None:
            logger.info(f"Cache hit for {ticker} filing analysis")
            return cached_result
            
        logger.info(f"Analyzing {len(filing_texts)} filings for {ticker}")
        
        # Check cost ceiling before proceeding
        if not self.api_client.check_cost_ceiling():
            logger.warning(f"Cost ceiling exceeded, skipping {ticker}")
            return None
            
        try:
            result = self._call_claude_analysis(ticker, fundamental_metrics, filing_texts)
            
            # Cache the result
            if result:
                self.cache.put("filing_analyzer", ticker, artifact_id, result)
                logger.info(f"Cached filing analysis for {ticker}")
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze filings for {ticker}: {e}")
            return None

    def _prepare_fundamental_metrics(self, df: pd.DataFrame) -> str:
        """Format fundamental metrics for analysis."""
        if df.empty:
            return "No fundamental metrics available."
            
        # Select key metrics for forensic analysis
        key_metrics = [
            'revenue', 'net_income', 'total_assets', 'total_liabilities', 
            'cash_flow_from_operating_activities', 'accounts_receivable',
            'inventory', 'gross_profit', 'operating_income'
        ]
        
        # Filter to available metrics
        available_metrics = [m for m in key_metrics if m in df.columns]
        
        # Create a readable format
        metrics_text = "Quarterly Fundamental Metrics:\n"
        for _, row in df.tail(8).iterrows():  # Last 8 quarters
            period = row.get('period', 'N/A')
            metrics_text += f"\nPeriod: {period}\n"
            for metric in available_metrics:
                if metric in row and pd.notna(row[metric]):
                    metrics_text += f"  {metric}: {row[metric]:,.0f}\n"
                    
        return metrics_text

    def _call_claude_analysis(self, ticker: str, fundamental_metrics: pd.DataFrame, 
                             filing_texts: List[str]) -> Dict[str, Any]:
        """Call Claude API to analyze filings."""
        system_prompt = """
        You are a forensic accounting expert tasked with detecting financial anomalies 
        and assessing accounting quality in SEC filings. Your analysis should be 
        objective, evidence-based, and conservative in assigning high scores.

        Always respond with valid JSON in this exact format:
        
        {
            "earnings_quality_score": 1-10,
            "balance_sheet_score": 1-10,
            "revenue_quality_score": 1-10,
            "red_flags": ["Flag 1 explanation", "Flag 2 explanation"],
            "green_flags": ["Positive signal 1", "Positive signal 2"],
            "risk_level": "Low|Medium|High",
            "suspicious_patterns": ["Pattern 1", "Pattern 2"],
            "accounting_strengths": ["Strength 1", "Strength 2"],
            "key_risks": ["Risk 1", "Risk 2"],
            "audit_concerns": ["Concern 1", "Concern 2"],
            "summary": "Concise overview of findings"
        }
        
        Scoring guidelines:
        - 1 = Severe concerns/weaknesses
        - 5 = Average/typical quality
        - 10 = Exceptional quality/strength
        
        Focus areas:
        1. Earnings Quality: CFO vs Net Income divergence, accrual anomalies, irregularities
        2. Revenue Quality: AR growth vs revenue, deferred revenue patterns, channel stuffing
        3. Balance Sheet Health: asset quality, liability transparency, off-balance-sheet items
        4. Cash Flow Patterns: Operating CF vs reported earnings consistency
        
        Look for red flags like:
        - Increasing accounts receivable without revenue growth
        - Declining gross margins with stable revenues
        - CFO consistently below net income
        - Growing deferred costs/current liabilities
        - Related party transactions
        - Complex accounting policies or frequent restatements
        """
        
        # Prepare metrics text
        metrics_text = self._prepare_fundamental_metrics(fundamental_metrics)
        
        # Combine filing texts (up to 200K chars total)
        combined_filing_text = "\n\n--- NEW FILING ---\n\n".join(filing_texts)[:200000]
        
        user_prompt = f"""
        Please conduct a forensic accounting review for {ticker}.
        
        <metrics>
        {metrics_text}
        </metrics>
        
        <filings>
        {combined_filing_text}
        </filings>
        
        Identify any accounting irregularities, assess the quality of financial reporting,
        and highlight both concerning patterns and strengths. Pay special attention to:
        - Cash flow from operations vs net income trends
        - Accounts receivable and inventory growth rates
        - Gross margin and operating margin stability
        - Balance sheet leverage and liquidity indicators
        - Management discussion consistency with financial results
        - Audit opinions and qualifications
        
        Provide specific evidence from the metrics and filings to support your assessment.
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
            "earnings_quality_score", "balance_sheet_score", "revenue_quality_score",
            "red_flags", "green_flags", "risk_level", "suspicious_patterns",
            "accounting_strengths", "key_risks", "audit_concerns", "summary"
        ]
        
        for field in required_fields:
            if field not in result:
                if field in ["red_flags", "green_flags", "suspicious_patterns", 
                           "accounting_strengths", "key_risks", "audit_concerns"]:
                    result[field] = []
                else:
                    result[field] = "Not analyzed"
                    
        # Ensure list fields are actually lists
        list_fields = ["red_flags", "green_flags", "suspicious_patterns", 
                      "accounting_strengths", "key_risks", "audit_concerns"]
        for field in list_fields:
            if not isinstance(result.get(field, []), list):
                result[field] = []
                
        return result

    def get_filing_text_from_db(self, db_connection, ticker: str, filing_type: str = None, 
                               limit: int = 3) -> tuple[List[str], List[str]]:
        """
        Extract filing texts from database for analysis.
        
        Returns:
            Tuple of (filing_texts, filing_dates)
        """
        try:
            query = "SELECT filing_date, raw_text_path FROM sec_filings WHERE ticker = ?"
            params = [ticker]
            
            if filing_type:
                query += " AND filing_type = ?"
                params.append(filing_type)
                
            query += " ORDER BY filing_date DESC LIMIT ?"
            params.append(limit)
            
            rows = db_connection.execute(query, params).fetchall()
            
            filing_texts = []
            filing_dates = []
            
            for row in rows:
                filing_date = row[0]
                file_path = row[1]
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                        filing_texts.append(text)
                        filing_dates.append(filing_date)
                except Exception as e:
                    logger.warning(f"Failed to read filing text from {file_path}: {e}")
                    
            return filing_texts, filing_dates
            
        except Exception as e:
            logger.error(f"Failed to get filing texts for {ticker}: {e}")
            return [], []


# Convenience function
def analyze_sec_filings(ticker: str, fundamental_metrics: pd.DataFrame, 
                       filing_texts: List[str], filing_dates: List[str],
                       config: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    """Analyze SEC filings for forensic accounting signs."""
    analyzer = FilingAnalyzer(config or {})
    return analyzer.analyze_filings(ticker, fundamental_metrics, filing_texts, filing_dates)
