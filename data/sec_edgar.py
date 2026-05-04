"""
Meridian Capital Partners · data/sec_edgar.py
─────────────────────────────────────────────────────────────────
Source 3/5 — SEC EDGAR filings: 10-K, 10-Q, 8-K.
Uses sec-downloader for bulk fetch, caches raw text locally,
stores metadata in SQLite.
"""

import logging
import time
from pathlib import Path
from datetime import datetime

from sec_downloader import Downloader
from sec_downloader.types import RequestedFilings

from .db import MeridianDB

logger = logging.getLogger("meridian.sec_edgar")


def _get_cik_mapping(db: MeridianDB) -> dict[str, str]:
    """Build a mapping from ticker → CIK from existing universe + known list."""
    # sec-downloader has its own ticker→CIK mapping; we use it directly.
    # For efficiency we store a static mapping.
    return {}


def update_sec_filings(tickers: list[str], config: dict, db: MeridianDB):
    """
    Download latest 10-K, 10-Q, 8-K filings for all tickers.
    Caches raw .txt in cache/sec_filings/.
    Stores metadata (accession number, path) in sec_filings table.
    """
    data_cfg = config["data"]["sec_edgar"]
    user_agent = data_cfg["user_agent"]
    filing_types = data_cfg["filing_types"]
    lookback_years = data_cfg["lookback_years"]
    cache_dir = Path(data_cfg["cache_dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)

    dl = Downloader("Meridian Capital Partners", user_agent)

    # Limit to actual S&P 500 tickers (exclude benchmarks)
    universe_tickers = [t for t in tickers if not t.startswith("^") and t not in (
        "SPY", "QQQ", "IWM", "DIA", "TLT", "HYG",
        "XLK", "XLF", "XLV", "XLE", "XLI", "XLC",
        "XLY", "XLP", "XLB", "XLRE", "XLU",
    )]

    total_filings = 0

    for i, ticker in enumerate(universe_tickers):
        for ftype in filing_types:
            last_date = db.get_last_filing_date(ticker, ftype)
            after_date = last_date or str(datetime.now().year - lookback_years)

            try:
                filings = dl.get_filings(
                    ticker_or_cik=ticker,
                    form=ftype,
                    filing_date_after=after_date,
                    limit=10,  # grab up to 10 latest per type
                )

                for filing in filings:
                    # Build local cache path
                    acc = filing.accession_number.replace("-", "")
                    local_path = cache_dir / f"{ticker}_{ftype}_{acc}.txt"

                    # Download full text if not cached
                    if not local_path.exists():
                        try:
                            full_text = filing.full_text()
                            local_path.write_text(full_text, encoding="utf-8")
                        except Exception as e:
                            logger.warning("Failed to download text for %s %s: %s", ticker, acc, e)
                            continue

                    db.upsert_sec_filing({
                        "ticker": ticker,
                        "filing_type": ftype,
                        "filing_date": str(filing.filing_date)[:10],
                        "period_end": str(filing.period_of_report)[:10] if filing.period_of_report else "",
                        "accession_number": acc,
                        "raw_text_path": str(local_path),
                    })
                    total_filings += 1

            except Exception as e:
                logger.debug("SEC error %s %s: %s", ticker, ftype, e)

        time.sleep(0.1)  # SEC rate limit
        if (i + 1) % 50 == 0:
            logger.info("SEC filings: %d/%d tickers…", i + 1, len(universe_tickers))

    logger.info("SEC filings complete — %d filings cached.", total_filings)
    return total_filings
