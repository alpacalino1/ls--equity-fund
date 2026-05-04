"""
Meridian Capital Partners · data/db.py
─────────────────────────────────────────────────────────────────
SQLite database manager. All 5 data sources write through this.
Provides the schema + a thin query/insert layer.
"""

import sqlite3
import os
import logging
from pathlib import Path

logger = logging.getLogger("meridian.db")


class MeridianDB:
    """Manages the SQLite warehouse for all fund data."""

    def __init__(self, db_path: str = "cache/meridian.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        """Create all tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            logger.info("Schema initialized at %s", self.db_path)

    # ── Universe ────────────────────────────────────────────────────

    def upsert_universe(self, rows: list[dict]):
        """Insert/replace universe records (ticker is PK)."""
        with self._connect() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO universe
                   (ticker, company_name, gics_sector, sub_industry, date_added)
                   VALUES (:ticker, :company_name, :gics_sector, :sub_industry, :date_added)""",
                rows,
            )

    def get_universe(self) -> list[dict]:
        """Return all current S&P 500 constituents."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM universe ORDER BY ticker").fetchall()
            return [dict(r) for r in rows]

    # ── Daily Prices ────────────────────────────────────────────────

    def upsert_daily_prices(self, rows: list[dict]):
        """Insert/replace price rows. PK = (ticker, date)."""
        with self._connect() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO daily_prices
                   (ticker, date, open, high, low, close, adj_close, volume)
                   VALUES (:ticker, :date, :open, :high, :low, :close, :adj_close, :volume)""",
                rows,
            )

    def get_last_price_date(self, ticker: str) -> str | None:
        """Latest date of price data for a ticker, for incremental updates."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM daily_prices WHERE ticker = ?", (ticker,)
            ).fetchone()
            return row[0] if row and row[0] else None

    # ── Fundamentals ────────────────────────────────────────────────

    def upsert_fundamentals(self, rows: list[dict]):
        """Insert/replace fundamental records. PK = (ticker, period, statement_type)."""
        with self._connect() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO fundamentals
                   (ticker, period, statement_type, field, value)
                   VALUES (:ticker, :period, :statement_type, :field, :value)""",
                rows,
            )

    def upsert_derived_ratios(self, rows: list[dict]):
        """Insert/replace derived ratio records. PK = (ticker, period)."""
        with self._connect() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO derived_ratios
                   (ticker, period, roe, roa, gross_margin, operating_margin, net_margin,
                    revenue_growth_yoy, revenue_growth_qoq, earnings_growth_yoy, earnings_growth_qoq,
                    debt_to_equity, fcf_yield, current_ratio, ar_to_revenue, cfo_to_ni,
                    accruals_ratio, retained_earnings, working_capital, total_liabilities,
                    ebit, rd_expense, shares_outstanding, dividends_paid, buybacks, asset_turnover)
                   VALUES (:ticker, :period, :roe, :roa, :gross_margin, :operating_margin, :net_margin,
                           :revenue_growth_yoy, :revenue_growth_qoq, :earnings_growth_yoy, :earnings_growth_qoq,
                           :debt_to_equity, :fcf_yield, :current_ratio, :ar_to_revenue, :cfo_to_ni,
                           :accruals_ratio, :retained_earnings, :working_capital, :total_liabilities,
                           :ebit, :rd_expense, :shares_outstanding, :dividends_paid, :buybacks, :asset_turnover)""",
                rows,
            )

    # ── SEC Filings ─────────────────────────────────────────────────

    def upsert_sec_filing(self, row: dict):
        """Insert/replace a single SEC filing record."""
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sec_filings
                   (ticker, filing_type, filing_date, period_end, accession_number, raw_text_path)
                   VALUES (:ticker, :filing_type, :filing_date, :period_end, :accession_number, :raw_text_path)""",
                row,
            )

    def get_last_filing_date(self, ticker: str, filing_type: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(filing_date) FROM sec_filings WHERE ticker=? AND filing_type=?",
                (ticker, filing_type),
            ).fetchone()
            return row[0] if row and row[0] else None

    # ── Insider Transactions ────────────────────────────────────────

    def upsert_insider(self, rows: list[dict]):
        """Insert/replace insider transaction rows. PK = accession_number."""
        with self._connect() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO insider_transactions
                   (ticker, filing_date, insider_name, title, transaction_type,
                    shares, price, value, shares_owned_after, accession_number)
                   VALUES (:ticker, :filing_date, :insider_name, :title, :transaction_type,
                           :shares, :price, :value, :shares_owned_after, :accession_number)""",
                rows,
            )

    def get_last_insider_date(self, ticker: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(filing_date) FROM insider_transactions WHERE ticker=?",
                (ticker,),
            ).fetchone()
            return row[0] if row and row[0] else None

    # ── Institutional Holdings ──────────────────────────────────────

    def upsert_institutional(self, rows: list[dict]):
        with self._connect() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO institutional_holdings
                   (ticker, fund_name, cik, filing_date, quarter_end, shares, value, change_shares)
                   VALUES (:ticker, :fund_name, :cik, :filing_date, :quarter_end, :shares, :value, :change_shares)""",
                rows,
            )

    def get_last_13f_date(self, ticker: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(filing_date) FROM institutional_holdings WHERE ticker=?",
                (ticker,),
            ).fetchone()
            return row[0] if row and row[0] else None


# ── SQL Schema ──────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS universe (
    ticker       TEXT PRIMARY KEY,
    company_name TEXT,
    gics_sector  TEXT,
    sub_industry TEXT,
    date_added   TEXT DEFAULT (date('now'))
);
CREATE INDEX IF NOT EXISTS idx_universe_sector ON universe(gics_sector);

CREATE TABLE IF NOT EXISTS daily_prices (
    ticker    TEXT,
    date      TEXT,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL,
    adj_close REAL,
    volume    INTEGER,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_prices_date ON daily_prices(date);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker         TEXT,
    period         TEXT,          -- e.g. '2024Q4', '2024FY'
    statement_type TEXT,          -- 'income', 'balance', 'cashflow'
    field          TEXT,
    value          REAL,
    PRIMARY KEY (ticker, period, statement_type, field)
);

CREATE TABLE IF NOT EXISTS derived_ratios (
    ticker             TEXT,
    period             TEXT,      -- e.g. '2024Q4'
    roe                REAL,
    roa                REAL,
    gross_margin       REAL,
    operating_margin   REAL,
    net_margin         REAL,
    revenue_growth_yoy REAL,
    revenue_growth_qoq REAL,
    earnings_growth_yoy REAL,
    earnings_growth_qoq REAL,
    debt_to_equity     REAL,
    fcf_yield          REAL,
    current_ratio      REAL,
    ar_to_revenue      REAL,
    cfo_to_ni          REAL,
    accruals_ratio     REAL,
    retained_earnings  REAL,
    working_capital    REAL,
    total_liabilities  REAL,
    ebit               REAL,
    rd_expense         REAL,
    shares_outstanding REAL,
    dividends_paid     REAL,
    buybacks           REAL,
    asset_turnover     REAL,
    PRIMARY KEY (ticker, period)
);

CREATE TABLE IF NOT EXISTS sec_filings (
    ticker           TEXT,
    filing_type      TEXT,       -- '10-K', '10-Q', '8-K'
    filing_date      TEXT,
    period_end       TEXT,
    accession_number TEXT PRIMARY KEY,
    raw_text_path    TEXT        -- local path to cached filing text
);
CREATE INDEX IF NOT EXISTS idx_sec_ticker_type ON sec_filings(ticker, filing_type);

CREATE TABLE IF NOT EXISTS insider_transactions (
    ticker            TEXT,
    filing_date       TEXT,
    insider_name      TEXT,
    title             TEXT,
    transaction_type  TEXT,      -- 'Buy', 'Sale', 'Grant', 'Option Exercise', etc.
    shares            REAL,
    price             REAL,
    value             REAL,
    shares_owned_after REAL,
    accession_number  TEXT PRIMARY KEY
);
CREATE INDEX IF NOT EXISTS idx_insider_ticker ON insider_transactions(ticker);

CREATE TABLE IF NOT EXISTS institutional_holdings (
    ticker       TEXT,
    fund_name    TEXT,
    cik          TEXT,
    filing_date  TEXT,
    quarter_end  TEXT,
    shares       REAL,
    value        REAL,
    change_shares REAL,
    PRIMARY KEY (ticker, fund_name, quarter_end)
);
CREATE INDEX IF NOT EXISTS idx_inst_ticker ON institutional_holdings(ticker);
"""
