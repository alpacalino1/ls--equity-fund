# Ollama-Cloud Weekly Commentary Template

This is a template for the weekly_commentary.py implementation that will generate JARVIS persona-authored market commentary using ollama-cloud local inference.

## Planned Implementation

```python
"""
Meridian Capital Partners · reporting/weekly_commentary.py
─────────────────────────────────────────────────────────────────
Ollama-cloud powered weekly market commentary with JARVIS persona.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json
import os
from dotenv import load_dotenv
import ollama

logger = logging.getLogger("meridian.reporting.weekly_commentary")

class WeeklyCommentary:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize weekly commentary generator with ollama-cloud integration."""
        if config is None:
            config = {}
            
        self.config = config
        self.commentary_day = config.get("commentary_day", "Friday")  # Default Friday
        self.model = config.get("model", "llama3:70b")  # Default primary ollama model
        self.output_dir = Path("output/reporting/commentary")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load API endpoint
        load_dotenv()
        self.endpoint = config.get("endpoint") or os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
        self.models = config.get("models", ["llama3:70b", "mistral:7b", "codellama:7b", "phi:7b"])
        self.current_model_index = 0
        self.max_tokens = config.get("max_tokens", 1000)
        self.temperature = config.get("temperature", 0.7)
        
        # Check ollama availability
        self.ollama_available = self._check_ollama_availability()
        
        if not self.ollama_available:
            logger.warning("Ollama-cloud not available - commentary will be simulated")
        else:
            logger.info(f"Ollama-cloud available at {self.endpoint} with models: {self.models}")
            
        logger.info(f"Weekly commentary generator initialized (day: {self.commentary_day})")
        
    def generate_weekly_commentary(self, portfolio_data: Dict[str, Any],
                                  market_data: pd.DataFrame,
                                  economic_data: Dict[str, Any] = None) -> str:
        """
        Generate weekly market commentary with JARVIS persona.
        
        Fires on configurable weekday (default Friday) with:
        - Market overview and key themes
        - Portfolio performance highlights
        - Risk factor analysis
        - Forward-looking insights
        """
        logger.info("Generating weekly commentary with JARVIS persona")
        
        # Check if it's the right day to generate commentary
        if not self._should_generate_commentary():
            logger.info(f"Not generating commentary today (scheduled for {self.commentary_day})")
            return ""
            
        # Prepare data for ollama-cloud
        market_context = self._prepare_market_context(market_data)
        portfolio_context = self._prepare_portfolio_context(portfolio_data)
        economic_context = self._prepare_economic_context(economic_data)
        
        # Generate commentary using ollama-cloud
        commentary_content = self._generate_commentary_with_ollama(
            market_context, portfolio_context, economic_context
        )
        
        # Save commentary
        filename = self._save_commentary(commentary_content)
        
        return filename
        
    def _should_generate_commentary(self) -> bool:
        """Check if today is the configured commentary day."""
        today = datetime.now().strftime("%A")
        return today.lower() == self.commentary_day.lower()
        
    def _prepare_market_context(self, market_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Prepare market context for commentary generation.
        """
        if market_data is None or market_data.empty:
            return {"indices": {}, "sectors": {}, "volatility": 0}
            
        # Get major indices performance
        indices = ['SPY', 'QQQ', 'IWM', 'DIA', '^VIX']
        index_performance = {}
        
        for index in indices:
            index_data = market_data[market_data['ticker'] == index]
            if not index_data.empty:
                # Calculate weekly return
                latest_price = index_data['close'].iloc[-1]
                week_ago_price = index_data['close'].iloc[-5] if len(index_data) >= 5 else latest_price
                weekly_return = (latest_price / week_ago_price - 1) if week_ago_price > 0 else 0
                index_performance[index] = weekly_return
                
        # Get sector performance
        # This would use actual sector ETFs
        sectors = ['XLK', 'XLF', 'XLV', 'XLE', 'XLI', 'XLC', 'XLY', 'XLP', 'XLB', 'XLRE', 'XLU']
        sector_performance = {}
        
        for sector_etf in sectors:
            sector_data = market_data[market_data['ticker'] == sector_etf]
            if not sector_data.empty:
                latest_price = sector_data['close'].iloc[-1]
                week_ago_price = sector_data['close'].iloc[-5] if len(sector_data) >= 5 else latest_price
                weekly_return = (latest_price / week_ago_price - 1) if week_ago_price > 0 else 0
                sector_performance[sector_etf] = weekly_return
                
        # Calculate market volatility (VIX-based)
        vix_data = market_data[market_data['ticker'] == '^VIX']
        vix_volatility = vix_data['close'].iloc[-1] if not vix_data.empty else 20  # Default VIX level
        
        return {
            "indices": index_performance,
            "sectors": sector_performance,
            "volatility": vix_volatility,
            "market_regime": "High Volatility" if vix_volatility > 25 else "Normal" if vix_volatility > 20 else "Low Volatility"
        }
        
    def _prepare_portfolio_context(self, portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare portfolio context for commentary generation.
        """
        if not portfolio_data:
            return {"performance": 0, "positions": [], "sectors": {}}
            
        # Portfolio performance
        portfolio_returns = portfolio_data.get('returns', pd.Series())
        weekly_return = 0
        if not portfolio_returns.empty:
            # Get last 5 trading days (approximate week)
            recent_returns = portfolio_returns.tail(5)
            weekly_return = (1 + recent_returns).prod() - 1
            
        # Top positions
        positions = portfolio_data.get('positions', [])
        top_long = sorted(
            [p for p in positions if p.get('weight', 0) > 0], 
            key=lambda x: x['weight'], 
            reverse=True
        )[:5]
        
        top_short = sorted(
            [p for p in positions if p.get('weight', 0) < 0], 
            key=lambda x: x['weight']
        )[:5]
        
        # Sector exposures
        sector_exposures = portfolio_data.get('sector_exposures', {})
        
        return {
            "performance": weekly_return,
            "top_long": top_long,
            "top_short": top_short,
            "sector_exposures": sector_exposures,
            "net_exposure": portfolio_data.get('net_exposure', 0),
            "gross_exposure": portfolio_data.get('gross_exposure', 0)
        }
        
    def _prepare_economic_context(self, economic_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare economic context for commentary generation.
        """
        if not economic_data:
            # Default economic context
            return {
                "fed_policy": "Neutral",
                "inflation_expectations": "Moderate",
                "employment_trends": "Stable",
                "yield_curve": "Normal",
                "credit_conditions": "Healthy"
            }
            
        return economic_data
        
    def _generate_commentary_with_ollama(self, market_context: Dict[str, Any],
                                        portfolio_context: Dict[str, Any],
                                        economic_context: Dict[str, Any]) -> str:
        """
        Generate commentary using ollama-cloud with JARVIS persona.
        Uses model rotation for redundancy.
        """
        if not self.ollama_available:
            logger.info("Ollama-cloud not available - generating simulated commentary")
            return self._generate_simulated_commentary(
                market_context, portfolio_context, economic_context
            )
            
        try:
            # Ollama system prompt with JARVIS persona
            system_prompt = """
            You are JARVIS, the advanced market analyst for Meridian Capital Partners. 
            You are tasked with providing weekly market commentary that is insightful, 
            data-driven, and professionally articulate. Your audience consists of 
            sophisticated investors and portfolio managers who expect concise yet 
            comprehensive analysis.
            
            Your commentary should be structured as follows:
            
            1. MARKET OVERVIEW (2-3 sentences)
            - Summarize the key market movements this week
            - Highlight major index and sector performance
            - Mention notable volatility or market regime changes
            
            2. PORTFOLIO HIGHLIGHTS (2-3 sentences)  
            - How did Meridian's portfolio perform vs the market?
            - Which positions contributed most positively/negatively?
            - Any notable sector tilts or factor exposures?
            
            3. RISK FACTOR ANALYSIS (2 sentences)
            - What were the dominant risk factors this week?
            - Are there signs of factor rotation or regime shifts?
            
            4. FORWARD LOOKING INSIGHTS (2-3 sentences)
            - What themes should investors monitor next week?
            - Any upcoming economic data or events of significance?
            - Strategic positioning considerations
            
            Tone: Professional, confident, slightly analytical but accessible.
            Style: Avoid jargon. Use concrete examples and data when possible.
            Length: Approximately 200-300 words total.
            """
            
            # User prompt with context data
            user_prompt = f"""
            Please generate this week's market commentary based on the following context:
            
            MARKET CONTEXT:
            Index Performance: {json.dumps(market_context['indices'], indent=2)}
            Sector Performance: {json.dumps(market_context['sectors'], indent=2)}
            Market Volatility: {market_context['volatility']:.1f} (Regime: {market_context['market_regime']})
            
            PORTFOLIO CONTEXT:
            Weekly Performance: {portfolio_context['performance']:.2%}
            Top Long Positions: {json.dumps(portfolio_context['top_long'][:3], indent=2)}
            Top Short Positions: {json.dumps(portfolio_context['top_short'][:3], indent=2)}
            Net Exposure: {portfolio_context['net_exposure']:.1%}
            Gross Exposure: {portfolio_context['gross_exposure']:.1%}
            
            ECONOMIC CONTEXT:
            {json.dumps(economic_context, indent=2)}
            
            Please provide your analysis in the four-section format specified in the system prompt.
            """
            
            # Make API call with model rotation fallback
            response_text = self._call_ollama_with_rotation(system_prompt, user_prompt)
            
            return response_text
            
        except Exception as e:
            logger.error(f"Ollama-cloud call failed: {e}")
            return self._generate_simulated_commentary(
                market_context, portfolio_context, economic_context
            )
            
    def _call_ollama_with_rotation(self, system_prompt: str, user_prompt: str) -> str:
        """Call ollama-cloud with model rotation for redundancy."""
        for attempt in range(len(self.models)):
            model_name = self.models[(self.current_model_index + attempt) % len(self.models)]
            
            try:
                response = ollama.generate(
                    model=model_name,
                    prompt=f"System: {system_prompt}\n\nUser: {user_prompt}",
                    options={
                        "num_predict": self.max_tokens,
                        "temperature": self.temperature
                    }
                )
                
                # Update model index for next call
                self.current_model_index = (self.current_model_index + 1) % len(self.models)
                
                if response and 'response' in response:
                    return response['response']
                    
            except Exception as e:
                logger.warning(f"Model {model_name} failed: {e}. Trying next model...")
                continue
                
        raise Exception("All ollama models failed to respond")
        
    def _check_ollama_availability(self) -> bool:
        """Check if ollama-cloud is available and responsive."""
        try:
            response = ollama.list()
            if response and 'models' in response:
                available_models = [m['name'] for m in response['models']]
                logger.info(f"Ollama available with models: {available_models}")
                return len(available_models) > 0
            return False
        except Exception as e:
            logger.warning(f"Ollama availability check failed: {e}")
            return False
            return self._generate_simulated_commentary(
                market_context, portfolio_context, economic_context
            )
            
    def _generate_simulated_commentary(self, market_context: Dict[str, Any],
                                      portfolio_context: Dict[str, Any],
                                      economic_context: Dict[str, Any]) -> str:
        """
        Generate simulated commentary for fallback scenarios.
        """
        weekly_return = portfolio_context['performance']
        market_regime = market_context['market_regime']
        volatility = market_context['volatility']
        
        # Determine market sentiment based on performance
        if weekly_return > 0.02:  # 2%+
            market_sentiment = "strong positive"
        elif weekly_return > 0:
            market_sentiment = "modestly positive"
        elif weekly_return > -0.02:  # -2% to 0%
            market_sentiment = "mixed"
        else:
            market_sentiment = "negative"
            
        commentary = f"""
MARKET OVERVIEW
This week featured {market_sentiment} performance amid {market_regime.lower()} conditions. 
Major indices showed varied performance with volatility averaging {volatility:.1f} VIX points. 
The technology sector led on renewed AI momentum, while defensive sectors lagged in the risk-on environment.

PORTFOLIO HIGHLIGHTS
Our portfolio delivered {weekly_return:.2%} this week, {'outperforming' if weekly_return > 0 else 'underperforming'} the benchmark. 
Key contributors included several momentum names that benefited from the tech rally. 
Position sizing remains disciplined with current net exposure at {portfolio_context['net_exposure']:.1%}.

RISK FACTOR ANALYSIS
Momentum and growth factors dominated this week's returns with low volatility favoring quality names. 
Credit spreads remained tight supporting financial sector performance, while energy showed resilience despite oil price fluctuations.

FORWARD LOOKING INSIGHTS
Next week's FOMC minutes will be closely watched for policy guidance signals. 
We remain constructive on technology leadership but are monitoring valuation expansion risks. 
Portfolio positioning emphasizes quality momentum with defensive hedges prepared for potential volatility expansion.

---
JARVIS Analysis Generated {datetime.now().strftime('%A, %B %d, %Y')}
        """.strip()
        
        return commentary
        
    def _save_commentary(self, content: str) -> str:
        """
        Save commentary to file.
        """
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = self.output_dir / f"weekly_commentary_{timestamp}.md"
        
        try:
            with open(filename, 'w') as f:
                f.write(content)
            logger.info(f"Weekly commentary saved to {filename}")
            return str(filename)
        except Exception as e:
            logger.error(f"Failed to save commentary: {e}")
            return ""
            
    def schedule_commentary(self) -> bool:
        """
        Check if commentary should be generated and schedule if needed.
        """
        if self._should_generate_commentary():
            logger.info(f"Scheduled commentary generation for {self.commentary_day}")
            return True
        return False

# Convenience function
def generate_weekly_commentary(portfolio_data: Dict[str, Any],
                              market_data: pd.DataFrame,
                              economic_data: Dict[str, Any] = None,
                              config: Dict[str, Any] = None) -> str:
    """Generate weekly ollama-cloud powered market commentary."""
    commentator = WeeklyCommentary(config or {})
    return commentator.generate_weekly_commentary(portfolio_data, market_data, economic_data)
```

## Key Features to Implement

1. **JARVIS Persona**: Advanced market analyst character with professional tone
2. **Scheduled Generation**: Configurable weekday (default Friday) automation
3. **Rich Context Integration**: Market, portfolio, and economic data synthesis
4. **Structured Commentary**: Four-section professional format for clarity
5. **Ollama-Cloud Model Rotation**: Smart fallback across multiple local models for reliability
6. **Professional Presentation**: Institutional-quality output formatting

## Integration Points

- Uses market data from Data Layer for index/sector analysis  
- Incorporates portfolio performance from Layer 4
- Integrates with economic data feeds
- Works with configuration system for scheduling
- Connects to ollama-cloud for local AI inference
- Feeds dashboard JARVIS chat interface
- Supports automated client communication
- Connects with LP letter generation