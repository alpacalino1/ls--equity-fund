"""
Meridian Capital Partners · data/market_data.py
─────────────────────────────────────────────────────────────────
Source 2a/5 — Daily OHLCV via yfinance.
3-year lookback, incremental updates, stored in SQLite "daily_prices".
"""

import logging
import time
from datetime import datetime, date

import yfinance as yf

from .db import MeridianDB

logger = logging.getLogger("meridian.market_data")


def fetch_daily_prices(tickers: list[str], config: dict, db: MeridianDB):
    """
    Pull daily OHLCV for all tickers using yfinance.
    Incremental: for each ticker, fetches only data since the last stored date.
    Upserts into daily_prices table.
    """
    lookback = config["data"]["lookback_years"]
    start_default = str(date.today().replace(year=date.today().year - lookback))
    max_retries = config["data"]["market_data"]["max_retries"]
    retry_delay = config["data"]["market_data"]["retry_delay_sec"]

    total_rows = 0

    for i, ticker in enumerate(tickers):
        last_date = db.get_last_price_date(ticker)
        if last_date:
            # Incremental: fetch from day after last stored date
            start = last_date
            logger.debug("[%d/%d] %s — incremental from %s", i + 1, len(tickers), ticker, last_date)
        else:
            start = start_default
            logger.debug("[%d/%d] %s — full fetch from %s", i + 1, len(tickers), ticker, start_default)

        for attempt in range(max_retries):
            try:
                df = yf.download(ticker, start=start, progress=False, auto_adjust=False)
                if df.empty:
                    break

                # Flatten multi-level columns if any
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                rows = []
                for idx, row in df.iterrows():
                    rows.append({
                        "ticker": ticker,
                        "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10],
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "adj_close": float(row.get("Adj Close", row["Close"])),
                        "volume": int(row["Volume"]),
                    })

                if rows:
                    db.upsert_daily_prices(rows)
                    total_rows += len(rows)
                break  # success

            except Exception as e:
                logger.warning("Attempt %d/%d for %s failed: %s", attempt + 1, max_retries, ticker, e)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)

        # Polite delay between tickers
        time.sleep(0.2)

        if (i + 1) % 50 == 0:
            logger.info("Progress: %d/%d tickers processed…", i + 1, len(tickers))

    logger.info("Market data complete — %d rows upserted across %d tickers.", total_rows, len(tickers))
    return total_rows


# Need pandas imported at top level for the flatten check
import pandas as pd
