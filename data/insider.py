"""
Meridian Capital Partners · data/insider.py
─────────────────────────────────────────────────────────────────
Source 4/5 — Insider transactions (SEC Form 4).
Scrapes OpenInsider or SEC EDGAR Form 4 RSS for recent trades.
Stores in insider_transactions table.
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd
import csv

from .db import MeridianDB

logger = logging.getLogger("meridian.insider")

# OpenInsider provides a convenient CSV endpoint for recent insider trades.
OPEN_INSIDER_URL = "http://openinsider.com/screener"


def _fetch_openinsider(tickers: list[str], lookback_days: int) -> list[dict]:
    """
    Scrape insider transactions from OpenInsider for a set of tickers.
    Uses the CSV export endpoint.
    Returns parsed records.
    """
    rows = []

    # We use OpenInsider's export. The API is finicky so we batch by ticker.
    for ticker in tickers:
        try:
            params = {
                "s": ticker,
                "o": "",
                "pl": "",
                "ph": "",
                "ll": "",
                "lh": "",
                "fd": str(lookback_days),
                "fdr": str(datetime.now().strftime("%m/%d/%Y")),
                "td": "0",
                "tdr": "",
                "fdlyl": "",
                "fdlyh": "",
                "daysago": "",
                "xp": "1",   # Excel/CSV export
                "vl": "",
                "vh": "",
                "ocl": "",
                "och": "",
                "sic1": "-1",
                "sicl": "100",
                "sich": "9999",
                "grp": "0",
                "nfl": "",
                "nfh": "",
                "nil": "",
                "nih": "",
                "nol": "",
                "noh": "",
                "v2l": "",
                "v2h": "",
                "oc2l": "",
                "oc2h": "",
                "sortcol": "0",
                "cnt": "100",
                "page": "1",
            }

            resp = requests.get(OPEN_INSIDER_URL, params=params, timeout=30)
            if resp.status_code != 200 or not resp.text.strip():
                continue

            # Parse CSV
            lines = resp.text.strip().split("\n")
            if len(lines) < 2:
                continue

            reader = csv.DictReader(lines)
            for row in reader:
                try:
                    filing_date = row.get("Filing Date", "")
                    trade_date = row.get("Trade Date", "") or filing_date
                    insider_name = row.get("Insider Name", "")
                    title = row.get("Title", "")
                    trade_type = row.get("Trade Type", "")
                    price = float(row.get("Price", 0) or 0)
                    qty = float(row.get("Qty", 0) or 0)
                    owned = float(row.get("Owned", 0) or 0)
                    value = price * qty

                    rows.append({
                        "ticker": ticker,
                        "filing_date": filing_date,
                        "insider_name": insider_name,
                        "title": title,
                        "transaction_type": trade_type,
                        "shares": qty,
                        "price": price,
                        "value": value,
                        "shares_owned_after": owned,
                        "accession_number": f"OI-{ticker}-{filing_date}-{insider_name[:20]}",
                    })
                except Exception:
                    continue

        except Exception as e:
            logger.debug("OpenInsider error for %s: %s", ticker, e)

        time.sleep(0.3)  # be polite

    logger.info("Fetched %d insider transactions from OpenInsider.", len(rows))
    return rows


def update_insider(tickers: list[str], config: dict, db: MeridianDB):
    """
    Fetch insider transactions for all tickers.
    Caches locally, upserts into SQLite.
    """
    data_cfg = config["data"]["insider"]
    lookback_years = data_cfg["lookback_years"]
    lookback_days = lookback_years * 365
    cache_path = data_cfg["cache_path"]
    refresh_days = data_cfg["refresh_days"]

    # Only fetch for S&P 500 tickers (not benchmarks / indices)
    stock_tickers = [t for t in tickers if not t.startswith("^") and t not in (
        "SPY", "QQQ", "IWM", "DIA", "TLT", "HYG",
        "XLK", "XLF", "XLV", "XLE", "XLI", "XLC",
        "XLY", "XLP", "XLB", "XLRE", "XLU",
    )]

    # Check cache
    cache_file = Path(cache_path)
    use_cache = False
    if cache_file.exists():
        age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        if age < timedelta(days=refresh_days):
            use_cache = True

    if use_cache:
        df = pd.read_csv(cache_path)
        rows = df.to_dict(orient="records")
        logger.info("Using cached insider data (%d rows).", len(rows))
    else:
        rows = _fetch_openinsider(stock_tickers, lookback_days)
        if rows:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).to_csv(cache_path, index=False)

    if rows:
        db.upsert_insider(rows)

    logger.info("Insider update complete — %d transactions stored.", len(rows))
    return len(rows)
