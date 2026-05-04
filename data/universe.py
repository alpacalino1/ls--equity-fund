"""
Meridian Capital Partners · data/universe.py
─────────────────────────────────────────────────────────────────
Source 1/5 — S&P 500 constituents scraped from Wikipedia.
Caches locally, refreshes weekly.
"""

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .db import MeridianDB

logger = logging.getLogger("meridian.universe")

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

BENCHMARK_TICKERS = [
    # Indices
    "^GSPC", "^VIX",
    # Broad ETFs
    "SPY", "QQQ", "IWM", "DIA",
    # Bonds
    "TLT", "HYG",
    # Sector ETFs
    "XLK", "XLF", "XLV", "XLE", "XLI",
    "XLC", "XLY", "XLP", "XLB", "XLRE", "XLU",
]

BENCHMARK_NAMES = {
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust",
    "IWM": "iShares Russell 2000 ETF",
    "DIA": "SPDR Dow Jones Industrial Average ETF",
    "XLK": "Technology Select Sector SPDR",
    "XLF": "Financial Select Sector SPDR",
    "XLV": "Health Care Select Sector SPDR",
    "XLE": "Energy Select Sector SPDR",
    "XLI": "Industrial Select Sector SPDR",
    "XLC": "Communication Services Select Sector SPDR",
    "XLY": "Consumer Discretionary Select Sector SPDR",
    "XLP": "Consumer Staples Select Sector SPDR",
    "XLB": "Materials Select Sector SPDR",
    "XLRE": "Real Estate Select Sector SPDR",
    "XLU": "Utilities Select Sector SPDR",
    "TLT": "iShares 20+ Year Treasury Bond ETF",
    "HYG": "iShares iBoxx $ High Yield Corporate Bond ETF",
    "^GSPC": "S&P 500 Index",
    "^VIX": "CBOE Volatility Index",
}


def fetch_sp500() -> list[dict]:
    """Scrape the S&P 500 table from Wikipedia. Returns list of {ticker, company_name, gics_sector, sub_industry}."""
    logger.info("Scraping S&P 500 constituents from Wikipedia…")
    headers = {"User-Agent": "MeridianCapitalPartners/1.0 (research@meridian.example.com)"}
    resp = requests.get(SP500_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    table = soup.find("table", {"id": "constituents"})
    if not table:
        raise RuntimeError("Could not find S&P 500 constituents table on Wikipedia")

    rows_data = []
    for tr in table.find_all("tr")[1:]:
        cols = tr.find_all("td")
        if len(cols) < 5:
            continue
        rows_data.append({
            "ticker": cols[0].text.strip().replace(".", "-"),
            "company_name": cols[1].text.strip(),
            "gics_sector": cols[3].text.strip(),
            "sub_industry": cols[4].text.strip(),
            "date_added": datetime.now().strftime("%Y-%m-%d"),
        })

    logger.info("Scraped %d S&P 500 constituents.", len(rows_data))
    return rows_data


def _cache_needs_refresh(cache_path: str, refresh_days: int) -> bool:
    p = Path(cache_path)
    if not p.exists():
        return True
    age = datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)
    return age > timedelta(days=refresh_days)


def update_universe(db: MeridianDB, config: dict) -> list[dict]:
    """
    Full universe update:
      1. Scrape S&P 500 from Wikipedia (with local cache).
      2. Append benchmark tickers.
      3. Upsert everything into SQLite.
    Returns the complete list of tickers.
    """
    data_cfg = config["data"]["universe"]
    cache_path = data_cfg["cache_path"]
    refresh_days = data_cfg["refresh_days"]

    # ── S&P 500 constituents ──────────────────────────────────────
    if _cache_needs_refresh(cache_path, refresh_days):
        rows = fetch_sp500()
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["ticker", "company_name", "gics_sector", "sub_industry", "date_added"])
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(cache_path, newline="") as f:
            rows = list(csv.DictReader(f))
        logger.info("Using cached universe (%d tickers).", len(rows))

    db.upsert_universe(rows)

    # ── Benchmarks ────────────────────────────────────────────────
    bench_rows = []
    for t in BENCHMARK_TICKERS:
        bench_rows.append({
            "ticker": t,
            "company_name": BENCHMARK_NAMES.get(t, t),
            "gics_sector": "Benchmark",
            "sub_industry": "Benchmark",
            "date_added": datetime.now().strftime("%Y-%m-%d"),
        })
    db.upsert_universe(bench_rows)

    all_tickers = [r["ticker"] for r in rows] + BENCHMARK_TICKERS
    logger.info("Universe updated: %d stocks + %d benchmarks.", len(rows), len(bench_rows))
    return all_tickers


def get_universe_tickers(db: MeridianDB, exclude_benchmarks: bool = False) -> list[str]:
    """Return just the ticker list from the universe table."""
    records = db.get_universe()
    if exclude_benchmarks:
        records = [r for r in records if r["gics_sector"] != "Benchmark"]
    return [r["ticker"] for r in records]
