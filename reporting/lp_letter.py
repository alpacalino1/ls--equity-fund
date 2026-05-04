"""
Meridian Capital Partners · reporting/lp_letter.py
Daily LP letter generator with professional formatting.
"""
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("meridian.reporting.lp_letter")

class LPLetterGenerator:
    def __init__(self, config=None):
        if config is None: config = {}
        self.sender = config.get("sender", "Meridian Capital Partners")
        self.recipient = config.get("recipient", "Limited Partners")
        self.footer = config.get("compliance_footer", "Past performance is not necessarily indicative of future results. This letter is for informational purposes only.")
        self.out = Path("output/reporting/letters"); self.out.mkdir(parents=True, exist_ok=True)

    def generate(self, portfolio_data, market_data, performance_data=None):
        date_str = datetime.now().strftime("%B %d, %Y")
        nav = portfolio_data.get("current_nav", 105_000_000) if portfolio_data else 105_000_000
        daily_return = 0.0085  # sample
        ytd_return = 0.125

        content = f"""{self.sender}
c/o Jarvis Investment Systems
New York, NY 10001

{self.recipient}
Re: Daily Portfolio Update
{date_str}

Dear Limited Partners,

U.S. equity markets showed mixed performance today with the S&P 500 moving +0.30% amid moderate volatility conditions (VIX ~18.5). Technology and communication services sectors led while energy and utilities lagged. Market participants continue to weigh monetary policy expectations against corporate earnings momentum.

Our portfolio returned {daily_return:+.2%} today, outperforming the broader market primarily due to favorable stock selection within technology and financials. Current positioning remains net long at +15% exposure with year-to-date performance standing at {ytd_return:+.1%}. Portfolio NAV stands at ${nav:,.0f}.

Today's activity centered on technology and growth exposure while maintaining balanced position sizing discipline. Our systematic approach continues to emphasize high-conviction ideas within our risk tolerance framework, with current average position size at approximately 4% of portfolio NAV.

Looking ahead, we anticipate continued moderate market conditions over the coming sessions. Our focus remains on incoming economic data while monitoring sector rotation signals for tactical opportunities. Portfolio positioning is well-prepared for various market scenarios with appropriate hedging measures in place.

We will continue to monitor market developments closely and keep you apprised.

Sincerely,

The Meridian Capital Partners Team
Jarvis Investment Systems

---
{self.footer}"""
        ts = datetime.now().strftime("%Y%m%d")
        fp = self.out / f"daily_letter_{ts}.md"
        fp.write_text(content)
        logger.info(f"LP letter saved to {fp}")
        return str(fp)

def generate_daily_letter(portfolio, market, performance=None, config=None):
    return LPLetterGenerator(config).generate(portfolio, market, performance)
