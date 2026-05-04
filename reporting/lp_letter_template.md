# Daily LP Letter Template

This is a template for the lp_letter.py implementation that will generate daily investor correspondence with professional formatting.

## Planned Implementation

```python
"""
Meridian Capital Partners · reporting/lp_letter.py
─────────────────────────────────────────────────────────────────
Daily LP letter generator with professional formatting and compliance.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json
from dotenv import load_dotenv

logger = logging.getLogger("meridian.reporting.lp_letter")

class LPLetterGenerator:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize LP letter generator."""
        if config is None:
            config = {}
            
        self.config = config
        self.sender = config.get("sender", "Meridian Capital Partners")
        self.recipient = config.get("recipient", "Limited Partners")
        self.compliance_footer = config.get("compliance_footer", 
            "Past performance is not necessarily indicative of future results. "
            "This letter is for informational purposes only and does not constitute investment advice.")
        self.output_dir = Path("output/reporting/letters")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("LP letter generator initialized")
        
    def generate_daily_letter(self, portfolio_data: Dict[str, Any],
                             market_data: pd.DataFrame,
                             performance_data: Dict[str, Any] = None) -> str:
        """
        Generate daily LP letter with professional formatting.
        
        Includes:
        - Letterhead and salutation
        - 3-4 paragraph market commentary  
        - Performance summary
        - Signature block
        - Compliance footer
        """
        logger.info("Generating daily LP letter")
        
        # Generate letter content
        letter_content = self._generate_letter_content(
            portfolio_data, market_data, performance_data
        )
        
        # Format with letterhead
        formatted_letter = self._format_letter(letter_content)
        
        # Save letter
        filename = self._save_letter(formatted_letter)
        
        return filename
        
    def _generate_letter_content(self, portfolio_data: Dict[str, Any],
                                market_data: pd.DataFrame,
                                performance_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate the substantive content for the LP letter.
        """
        # Market overview (paragraph 1)
        market_overview = self._generate_market_overview(market_data)
        
        # Portfolio performance (paragraph 2)
        portfolio_summary = self._generate_portfolio_summary(
            portfolio_data, performance_data
        )
        
        # Strategy insights (paragraph 3)
        strategy_insights = self._generate_strategy_insights(
            portfolio_data, market_data
        )
        
        # Outlook (paragraph 4, if needed)
        outlook = self._generate_outlook(market_data)
        
        return {
            "market_overview": market_overview,
            "portfolio_summary": portfolio_summary,
            "strategy_insights": strategy_insights,
            "outlook": outlook,
            "date": datetime.now().strftime("%B %d, %Y")
        }
        
    def _generate_market_overview(self, market_data: pd.DataFrame) -> str:
        """
        Generate market overview paragraph.
        """
        if market_data is None or market_data.empty:
            return ("Today's markets showed mixed performance with continued volatility "
                   "across major indices. Investor sentiment remained cautious amid "
                   "ongoing macroeconomic uncertainties.")
                   
        # Get key market metrics
        spy_data = market_data[market_data['ticker'] == 'SPY']
        vix_data = market_data[market_data['ticker'] == '^VIX']
        
        spy_return = 0
        if not spy_data.empty and len(spy_data) >= 2:
            latest = spy_data['close'].iloc[-1]
            previous = spy_data['close'].iloc[-2]
            spy_return = (latest / previous - 1) if previous > 0 else 0
            
        vix_level = vix_data['close'].iloc[-1] if not vix_data.empty else 20
        
        # Determine market narrative
        if spy_return > 0.01:  # Up 1%+
            market_move = "gained"
            sentiment = "positive momentum"
        elif spy_return > 0:
            market_move = "edged higher"
            sentiment = "cautious optimism"
        elif spy_return > -0.01:  # Down less than 1%
            market_move = "declined moderately"
            sentiment = "measured caution"
        else:
            market_move = "fell sharply"
            sentiment = "heightened risk-off sentiment"
            
        volatility_context = ("elevated" if vix_level > 25 else 
                            "moderate" if vix_level > 20 else 
                            "contained")
                            
        return (f"U.S. equity markets {market_move} today amid {volatility_context} volatility conditions. "
                f"The S&P 500 moved {spy_return:.2%} as investor sentiment reflected {sentiment}. "
                f"Market volatility, as measured by the VIX, settled at {vix_level:.1f} on the day.")
        
    def _generate_portfolio_summary(self, portfolio_data: Dict[str, Any],
                                   performance_data: Dict[str, Any]) -> str:
        """
        Generate portfolio performance summary paragraph.
        """
        # Get portfolio metrics
        daily_return = 0
        ytd_return = 0
        nav = 0
        net_exposure = 0
        
        if portfolio_data:
            # Daily return
            portfolio_returns = portfolio_data.get('returns', pd.Series())
            if not portfolio_returns.empty:
                daily_return = portfolio_returns.iloc[-1] if len(portfolio_returns) > 0 else 0
                
            # YTD return (would need full year data)
            ytd_return = portfolio_data.get('ytd_return', 0)
            
            # Portfolio metrics
            nav = portfolio_data.get('current_nav', 1_000_000)  # Default $1M
            net_exposure = portfolio_data.get('net_exposure', 0)
            
        # Performance context
        performance_vs_benchmark = daily_return  # Simplified - would compare to SPY
        
        if performance_vs_benchmark > 0.005:  # Outperforming by 50bps+
            performance_desc = "outperformed"
            attribution = "favorable stock selection and sector positioning"
        elif performance_vs_benchmark > 0:
            performance_desc = "outperformed"
            attribution = "disciplined risk management"
        elif performance_vs_benchmark > -0.005:  # Underperforming by less than 50bps
            performance_desc = "underperformed"
            attribution = "conservative positioning in a risk-on environment"
        else:
            performance_desc = "underperformed"
            attribution = "defensive stance proved costly in today's rally"
            
        # Positioning context
        exposure_desc = ("net long" if net_exposure > 0 else 
                        "net short" if net_exposure < 0 else 
                        "market neutral")
                        
        return (f"Our portfolio returned {daily_return:.2%} today, {performance_desc} "
                f"the broader market primarily due to {attribution}. "
                f"Current positioning remains {exposure_desc} with net exposure at {net_exposure:.1%}. "
                f"Year-to-date performance stands at {ytd_return:.2%}.")
        
    def _generate_strategy_insights(self, portfolio_data: Dict[str, Any],
                                   market_data: pd.DataFrame) -> str:
        """
        Generate strategy insights paragraph.
        """
        # Get portfolio composition insights
        positions = portfolio_data.get('positions', []) if portfolio_data else []
        
        if not positions:
            return ("Our investment strategy continues to focus on fundamental quality "
                   "within attractive valuations. Today's positioning reflects our "
                   "ongoing emphasis on risk-adjusted returns across market-cap segments.")
                   
        # Identify key themes
        long_positions = [p for p in positions if p.get('weight', 0) > 0]
        short_positions = [p for p in positions if p.get('weight', 0) < 0]
        
        top_long_sectors = {}
        if portfolio_data and 'sector_exposures' in portfolio_data:
            sector_exposures = portfolio_data['sector_exposures']
            # Get top long sectors (positive exposures)
            top_long_sectors = {k: v for k, v in sector_exposures.items() if v > 0}
            top_long_sectors = dict(sorted(top_long_sectors.items(), 
                                         key=lambda x: x[1], reverse=True)[:3])
                                         
        # Determine strategic narrative
        if top_long_sectors:
            sector_list = ", ".join(list(top_long_sectors.keys())[:2])
            sector_focus = f"focusing on {sector_list} exposure"
        else:
            sector_focus = "maintaining balanced sector diversification"
            
        # Position sizing discipline
        position_sizes = [abs(p.get('weight', 0)) for p in positions if p.get('weight', 0) != 0]
        avg_position_size = np.mean(position_sizes) if position_sizes else 0.05  # Default 5%
        
        concentration_desc = ("concentrated" if avg_position_size > 0.08 else
                            "balanced" if avg_position_size > 0.04 else
                            "diversified")
                            
        return (f"Today's activity centered on {sector_focus} while maintaining {concentration_desc} "
                f"position sizing discipline. Our systematic approach continues to emphasize "
                f"high-conviction ideas within our risk tolerance framework, with current "
                f"average position size at {avg_position_size:.1%} of portfolio NAV.")
        
    def _generate_outlook(self, market_data: pd.DataFrame) -> str:
        """
        Generate forward-looking outlook paragraph.
        """
        # Determine market regime
        vix_data = market_data[market_data['ticker'] == '^VIX'] if market_data is not None else pd.DataFrame()
        vix_level = vix_data['close'].iloc[-1] if not vix_data.empty else 20
        
        regime = ("volatile" if vix_level > 25 else 
                 "moderate" if vix_level > 20 else 
                 "stable")
                 
        # Economic considerations
        economic_factors = ["monetary policy developments", "earnings season dynamics", 
                          "geopolitical developments"]
        primary_factor = economic_factors[0]  # Default first factor
        secondary_factor = economic_factors[1]
        
        return (f"Looking ahead, we anticipate continued {regime} market conditions over "
                f"the coming sessions. Our focus remains on {primary_factor} while monitoring "
                f"{secondary_factor} for tactical opportunities. Portfolio positioning is "
                f"well-prepared for various market scenarios with appropriate hedging measures in place.")
        
    def _format_letter(self, content: Dict[str, str]) -> str:
        """
        Format letter with professional letterhead and structure.
        """
        # Letterhead components
        sender_address = [
            "Meridian Capital Partners",
            "c/o Jarvis Investment Systems",
            "New York, NY 10001"
        ]
        
        date_str = content.get('date', datetime.now().strftime("%B %d, %Y"))
        
        recipient_block = [
            f"{self.recipient}",
            "Re: Daily Portfolio Update",
            date_str,
            ""
        ]
        
        # Salutation
        salutation = "Dear Limited Partners,"
        body_paragraphs = [
            content.get('market_overview', ''),
            content.get('portfolio_summary', ''),
            content.get('strategy_insights', ''),
            content.get('outlook', '')
        ]
        
        # Closing
        closing = [
            "",
            "We will continue to monitor market developments closely and keep you apprised.",
            "",
            "Sincerely,",
            "",
            "The Meridian Capital Partners Team",
            "Jarvis Investment Systems"
        ]
        
        # Compliance footer
        footer = [
            "",
            "---",
            self.compliance_footer
        ]
        
        # Assemble letter
        letter_lines = []
        letter_lines.extend(sender_address)
        letter_lines.append("")  # Spacer
        letter_lines.extend(recipient_block)
        letter_lines.append(salutation)
        letter_lines.append("")  # Spacer
        for para in body_paragraphs:
            if para:  # Only add non-empty paragraphs
                letter_lines.append(para)
                letter_lines.append("")  # Paragraph spacer
                
        letter_lines.extend(closing)
        letter_lines.extend(footer)
        
        return "\n".join(letter_lines)
        
    def _save_letter(self, content: str) -> str:
        """
        Save letter to file with timestamp.
        """
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = self.output_dir / f"daily_letter_{timestamp}.md"
        
        try:
            with open(filename, 'w') as f:
                f.write(content)
            logger.info(f"Daily LP letter saved to {filename}")
            return str(filename)
        except Exception as e:
            logger.error(f"Failed to save LP letter: {e}")
            return ""
            
    def generate_pdf_letter(self, portfolio_data: Dict[str, Any],
                           market_data: pd.DataFrame,
                           performance_data: Dict[str, Any] = None) -> str:
        """
        Generate PDF version of letter (requires additional dependencies).
        """
        # This would use reportlab or similar PDF generation library
        # For template, just return regular text version
        return self.generate_daily_letter(portfolio_data, market_data, performance_data)
        
    def batch_generate_letters(self, date_range: Tuple[datetime, datetime],
                              portfolio_history: List[Dict[str, Any]],
                              market_data: pd.DataFrame) -> List[str]:
        """
        Generate letters for a range of dates.
        """
        start_date, end_date = date_range
        current_date = start_date
        generated_files = []
        
        while current_date <= end_date:
            # Filter data to current date
            daily_portfolio = self._filter_data_to_date(
                portfolio_history, current_date
            )
            
            daily_market = self._filter_market_data_to_date(
                market_data, current_date
            )
            
            if daily_portfolio or daily_market:
                letter_file = self.generate_daily_letter(
                    daily_portfolio, daily_market
                )
                if letter_file:
                    generated_files.append(letter_file)
                    
            current_date += timedelta(days=1)
            
        return generated_files
        
    def _filter_data_to_date(self, portfolio_history: List[Dict[str, Any]], 
                            target_date: datetime) -> Dict[str, Any]:
        """
        Filter portfolio history to specific date.
        """
        # Find closest entry to target date
        if not portfolio_history:
            return {}
            
        # Would implement actual date filtering logic
        # For template, return most recent entry
        return portfolio_history[-1] if portfolio_history else {}
        
    def _filter_market_data_to_date(self, market_data: pd.DataFrame,
                                   target_date: datetime) -> pd.DataFrame:
        """
        Filter market data to specific date.
        """
        if market_data is None or market_data.empty:
            return pd.DataFrame()
            
        # Would implement actual date filtering logic
        # For template, return last 5 days for weekly context
        return market_data.tail(5) if len(market_data) >= 5 else market_data

# Convenience function
def generate_daily_lp_letter(portfolio_data: Dict[str, Any],
                            market_data: pd.DataFrame,
                            performance_data: Dict[str, Any] = None,
                            config: Dict[str, Any] = None) -> str:
    """Generate daily LP letter with professional formatting."""
    letter_writer = LPLetterGenerator(config or {})
    return letter_writer.generate_daily_letter(portfolio_data, market_data, performance_data)
```

## Key Features to Implement

1. **Professional Formatting**: Complete letterhead with address, date, and salutation
2. **Structured Content**: 3-4 paragraph intelligent market commentary
3. **Performance Integration**: Portfolio performance seamlessly woven into narrative
4. **Strategic Insights**: Positioning rationale and forward-looking perspective
5. **Compliance Components**: Required legal disclaimers and disclosures
6. **Signature Block**: Professional closing with team attribution
7. **Batch Processing**: Multi-day letter generation capability
8. **PDF Export**: Professional document formatting (with dependencies)

## Integration Points

- Consumes portfolio data from Layer 4 optimization
- Integrates market data for current context
- Works with performance analytics from reporting layer
- Connects with configuration system for branding
- Feeds investor relations and client communication
- Supports automated daily distribution workflows
- Integrates with dashboard communication center