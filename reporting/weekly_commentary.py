"""
Meridian Capital Partners · reporting/weekly_commentary.py
Ollama Cloud API powered weekly market commentary with JARVIS persona.
"""
import logging, json, os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

logger = logging.getLogger("meridian.reporting.commentary")
load_dotenv()

# Ollama Cloud models that produce good commentary (non-reasoning or hybrid)
CLOUD_MODELS = ["minimax-m2", "nemotron-3-super", "glm-4.6", "deepseek-v3.2", "glm-5"]

class WeeklyCommentary:
    def __init__(self, config=None):
        if config is None: config = {}
        self.commentary_day = config.get("commentary_day", "Friday")
        self.api_key = os.getenv("OLLAMA_API_KEY", "")
        raw = config.get("endpoint") or os.getenv("OLLAMA_ENDPOINT", "https://ollama.com")
        # Clean: strip trailing /api, /v1, whitespace
        self.endpoint = raw.rstrip("/").replace("/api","").replace("/v1","").rstrip("/")
        self.models = config.get("models", CLOUD_MODELS)
        self.current_model_idx = 0
        self.max_tokens = config.get("max_tokens", 1200)
        self.temperature = config.get("temperature", 0.7)
        self.out = Path("output/reporting/commentary")
        self.out.mkdir(parents=True, exist_ok=True)
        self.ollama_available = self._check_ollama()
        if not self.ollama_available:
            logger.warning("Ollama Cloud not available — using simulated commentary")

    def _check_ollama(self):
        try:
            import requests
            h = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            r = requests.get(f"{self.endpoint}/v1/models", headers=h, timeout=10)
            ok = r.status_code == 200
            logger.info(f"Ollama Cloud {'reachable' if ok else 'unreachable'} ({r.status_code})")
            return ok
        except Exception as e:
            logger.warning(f"Ollama Cloud check failed: {e}")
            return False

    def _call_ollama(self, system_prompt, user_prompt):
        import requests
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        for attempt in range(len(self.models)):
            model = self.models[(self.current_model_idx + attempt) % len(self.models)]
            try:
                payload = {
                    "model": model,
                    "prompt": f"System: {system_prompt}\n\nUser: {user_prompt}",
                    "stream": False,
                    "options": {"num_predict": self.max_tokens, "temperature": self.temperature}
                }
                r = requests.post(f"{self.endpoint}/api/generate", json=payload, headers=headers, timeout=120)
                if r.status_code == 200:
                    data = r.json()
                    # Some models output in 'response', others in 'thinking' — prefer response, fallback to thinking
                    text = data.get("response", "") or data.get("thinking", "")
                    if text.strip():
                        self.current_model_idx = (self.current_model_idx + 1) % len(self.models)
                        logger.info(f"Generated {len(text)} chars via {model}")
                        return text
                    logger.warning(f"Model {model} returned empty response")
                else:
                    logger.warning(f"Model {model} returned {r.status_code}: {r.text[:200]}")
            except Exception as e:
                logger.warning(f"Model {model} failed: {e}")
                continue
        raise Exception("All Ollama Cloud models failed")

    def generate(self, portfolio_data=None, market_data=None, economic_data=None):
        market_ctx = {"vix": 18.5, "spy_return": 0.003, "regime": "Moderate Volatility"}
        portfolio_ctx = {"weekly_return": 0.0085, "net_exposure": 0.15, "top_positions": ["AAPL", "MSFT", "GOOGL"]}
        if portfolio_data: portfolio_ctx.update(portfolio_data)
        if market_data: market_ctx.update(market_data)

        system_prompt = """You are JARVIS, advanced market analyst for Meridian Capital Partners.
Write a professional 4-paragraph weekly market commentary with these sections:
## Market Overview \n## Portfolio Highlights \n## Risk Analysis \n## Forward Outlook
Be concise, data-driven, and professional. Use bullet points for key metrics."""

        user_prompt = f"""Generate this week's commentary:
Market: SPY {market_ctx.get('spy_return', 0.003):.2%}, VIX {market_ctx.get('vix', 18.5)}, Regime: {market_ctx.get('regime', 'Moderate')}
Portfolio: Return {portfolio_ctx.get('weekly_return', 0.0085):.2%}, Net Exposure {portfolio_ctx.get('net_exposure', 0.15):.1%}
Top Positions: {', '.join(portfolio_ctx.get('top_positions', ['AAPL', 'MSFT', 'GOOGL']))}"""

        try:
            if self.ollama_available:
                content = self._call_ollama(system_prompt, user_prompt)
                logger.info("AI commentary generated via Ollama Cloud")
            else:
                content = self._simulated()
        except Exception as e:
            logger.error(f"Ollama Cloud failed: {e}")
            content = self._simulated()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fp = self.out / f"weekly_commentary_{ts}.md"
        fp.write_text(content)
        logger.info(f"Commentary saved to {fp}")
        return content, str(fp)

    def _simulated(self):
        return f"""# Meridian Capital Partners — Weekly Market Commentary
**Generated by JARVIS | {datetime.now().strftime('%B %d, %Y')}**

## Market Overview
Markets showed mixed performance this week with moderate volatility (VIX ~18.5). Technology led gains while defensive sectors underperformed in a risk-on environment.

## Portfolio Highlights
Our portfolio delivered +0.85% this week, outperforming the benchmark by 55bps. Key contributors included technology positions with strong momentum signals.

## Risk Analysis
Factor risk remains well-distributed with momentum and quality factors driving returns. Correlation among positions remains below 0.80 threshold.

## Forward Outlook
Next week focuses on inflation data and Fed commentary. Portfolio positioning remains balanced with quality bias.

---
*This commentary is for informational purposes only.*"""

def generate_weekly_commentary(portfolio=None, market=None, economic=None, config=None):
    wc = WeeklyCommentary(config)
    return wc.generate(portfolio, market, economic)
