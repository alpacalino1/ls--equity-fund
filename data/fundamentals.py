"""
Meridian Capital Partners · data/fundamentals.py
─────────────────────────────────────────────────────────────────
Source 2b/5 — Financial statements + 24 derived ratios via yfinance.
Quarterly + annual: income statement, balance sheet, cash flow.
"""

import logging
import time

import yfinance as yf
import pandas as pd
import numpy as np

from .db import MeridianDB

logger = logging.getLogger("meridian.fundamentals")


def _safe_float(val) -> float | None:
    """Convert to float, returning None for NaN/inf."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) or np.isinf(f) else f
    except (TypeError, ValueError):
        return None


def _get_quarterly_statements(ticker_obj) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (income, balance, cashflow) quarterly DataFrames."""
    income = ticker_obj.quarterly_income_stmt if hasattr(ticker_obj, "quarterly_income_stmt") else ticker_obj.quarterly_financials
    balance = ticker_obj.quarterly_balance_sheet
    cashflow = ticker_obj.quarterly_cashflow
    return income, balance, cashflow


def _extract_fundamentals(ticker_obj, ticker: str, period_type: str,
                          income: pd.DataFrame, balance: pd.DataFrame,
                          cashflow: pd.DataFrame) -> list[dict]:
    """
    Flatten financial statements into (ticker, period, statement_type, field, value) rows.
    period_type is 'Q' or 'FY'.
    """
    rows = []

    def _add(df: pd.DataFrame, stype: str):
        if df is None or df.empty:
            return
        for col in df.columns:
            period_str = str(col).split(" ")[0] if " " in str(col) else str(col)[:10]
            for field in df.index:
                val = _safe_float(df.loc[field, col])
                if val is not None:
                    rows.append({
                        "ticker": ticker,
                        "period": f"{period_str}{period_type}",
                        "statement_type": stype,
                        "field": str(field),
                        "value": val,
                    })

    _add(income, "income")
    _add(balance, "balance")
    _add(cashflow, "cashflow")
    return rows


def _compute_derived_ratios(income: pd.DataFrame, balance: pd.DataFrame,
                            cashflow: pd.DataFrame, period_type: str) -> list[dict]:
    """
    Compute 24 derived ratios per period.
    Returns list of dicts keyed by ticker + period.
    """
    # We'll build these iteratively per period column.
    # For simplicity we work off the income columns as the period set.
    if income is None or income.empty:
        return []

    results = []
    columns = income.columns

    for i, col in enumerate(columns):
        period_str = str(col).split(" ")[0] if " " in str(col) else str(col)[:10]
        period_key = f"{period_str}{period_type}"

        def _get(df, field):
            if df is None or field not in df.index:
                return None
            return _safe_float(df.loc[field, col])

        # Income statement fields
        revenue = _get(income, "Total Revenue")
        gross_profit = _get(income, "Gross Profit")
        operating_income = _get(income, "Operating Income")
        net_income = _get(income, "Net Income")
        ebit = _get(income, "EBIT") or _get(income, "Operating Income")
        rd_expense = _get(income, "Research And Development") or _get(income, "Research & Development")
        depreciation = _get(income, "Depreciation & Amortization") or _get(income, "Depreciation And Amortization")

        # Balance sheet fields
        total_assets = _get(balance, "Total Assets")
        total_equity = _get(balance, "Total Equity Gross Minority Interest") or _get(balance, "Stockholders Equity")
        total_debt = _get(balance, "Total Debt") or _get(balance, "Long Term Debt And Capital Lease Obligation")
        current_assets = _get(balance, "Current Assets")
        current_liabilities = _get(balance, "Current Liabilities")
        retained_earnings = _get(balance, "Retained Earnings")
        working_capital = _get(balance, "Working Capital")  # sometimes directly available
        total_liabilities = _get(balance, "Total Liabilities Net Minority Interest") or _get(balance, "Total Liabilities")
        shares_outstanding = _get(balance, "Ordinary Shares Number") or _get(balance, "Share Issued")

        # If working_capital not directly available, compute
        if working_capital is None and current_assets is not None and current_liabilities is not None:
            working_capital = current_assets - current_liabilities

        # Cash flow fields
        operating_cf = _get(cashflow, "Operating Cash Flow")
        capex = _get(cashflow, "Capital Expenditure")
        dividends_paid = _get(cashflow, "Dividends Paid")
        buybacks = _get(cashflow, "Repurchase Of Capital Stock") or _get(cashflow, "Common Stock Issuance")
        # buybacks are negative in Repurchase Of Capital Stock; we store absolute
        if buybacks is not None:
            buybacks = abs(buybacks)

        # Free cash flow
        fcf = None
        if operating_cf is not None and capex is not None:
            fcf = operating_cf + capex  # capex is negative

        # ── Compute ratios ──────────────────────────────────────

        def _ratio(num, den) -> float | None:
            if num is not None and den is not None and den != 0:
                return num / den
            return None

        roe = _ratio(net_income, total_equity)
        roa = _ratio(net_income, total_assets)
        gross_margin = _ratio(gross_profit, revenue)
        operating_margin = _ratio(operating_income, revenue)
        net_margin = _ratio(net_income, revenue)
        debt_to_equity = _ratio(total_debt, total_equity)
        fcf_yield_val = None
        # FCF yield needs market cap; we skip here (available in L2 with price data)
        if fcf is not None and shares_outstanding is not None and shares_outstanding > 0:
            fcf_per_share = fcf / shares_outstanding
            # We store FCF per share as a rough proxy; market price needed for yield
            fcf_yield_val = fcf_per_share  # placeholder

        current_ratio = _ratio(current_assets, current_liabilities)
        # AR/Revenue: AR not directly available in yfinance standard fields; skip
        ar_to_revenue = None

        cfo_to_ni = _ratio(operating_cf, net_income)

        # Accruals ratio = (Net Income - Operating CF) / Total Assets
        accruals_ratio = None
        if net_income is not None and operating_cf is not None and total_assets is not None and total_assets != 0:
            accruals_ratio = (net_income - operating_cf) / total_assets

        asset_turnover = _ratio(revenue, total_assets)

        # ── Growth rates (need prior period) ────────────────────
        # We compute growth YoY (index i-4) and QoQ (i-1) where available.
        rev_growth_yoy = rev_growth_qoq = earn_growth_yoy = earn_growth_qoq = None

        def _prior_val(df, field, offset):
            if df is None or field not in df.index:
                return None
            idx = i - offset
            if 0 <= idx < len(df.columns):
                return _safe_float(df.loc[field, df.columns[idx]])
            return None

        prior_rev_q = _prior_val(income, "Total Revenue", 1)
        prior_rev_y = _prior_val(income, "Total Revenue", 4)
        prior_ni_q = _prior_val(income, "Net Income", 1)
        prior_ni_y = _prior_val(income, "Net Income", 4)

        rev_growth_qoq = _ratio(revenue - prior_rev_q if revenue and prior_rev_q else None, abs(prior_rev_q)) if prior_rev_q else None
        rev_growth_yoy = _ratio(revenue - prior_rev_y if revenue and prior_rev_y else None, abs(prior_rev_y)) if prior_rev_y else None
        earn_growth_qoq = _ratio(net_income - prior_ni_q if net_income and prior_ni_q else None, abs(prior_ni_q)) if prior_ni_q else None
        earn_growth_yoy = _ratio(net_income - prior_ni_y if net_income and prior_ni_y else None, abs(prior_ni_y)) if prior_ni_y else None

        results.append({
            "ticker": "",  # filled by caller
            "period": period_key,
            "roe": roe, "roa": roa,
            "gross_margin": gross_margin, "operating_margin": operating_margin, "net_margin": net_margin,
            "revenue_growth_yoy": rev_growth_yoy, "revenue_growth_qoq": rev_growth_qoq,
            "earnings_growth_yoy": earn_growth_yoy, "earnings_growth_qoq": earn_growth_qoq,
            "debt_to_equity": debt_to_equity, "fcf_yield": fcf_yield_val,
            "current_ratio": current_ratio, "ar_to_revenue": ar_to_revenue,
            "cfo_to_ni": cfo_to_ni, "accruals_ratio": accruals_ratio,
            "retained_earnings": retained_earnings, "working_capital": working_capital,
            "total_liabilities": total_liabilities, "ebit": ebit,
            "rd_expense": rd_expense, "shares_outstanding": shares_outstanding,
            "dividends_paid": dividends_paid, "buybacks": buybacks,
            "asset_turnover": asset_turnover,
        })

    return results


def update_fundamentals(tickers: list[str], config: dict, db: MeridianDB):
    """
    Fetch quarterly + annual financials for every ticker.
    Flatten into fundamentals table, compute derived ratios.
    """
    max_retries = config["data"]["fundamentals"]["max_retries"]

    total_stmt_rows = 0
    total_ratio_rows = 0

    for i, ticker in enumerate(tickers):
        try:
            t = yf.Ticker(ticker)

            # ── Quarterly ───────────────────────────────────────
            q_income, q_balance, q_cashflow = _get_quarterly_statements(t)
            stmt_rows = _extract_fundamentals(t, ticker, "Q", q_income, q_balance, q_cashflow)
            if stmt_rows:
                db.upsert_fundamentals(stmt_rows)
                total_stmt_rows += len(stmt_rows)

            ratio_rows = _compute_derived_ratios(q_income, q_balance, q_cashflow, "Q")
            for r in ratio_rows:
                r["ticker"] = ticker
            if ratio_rows:
                db.upsert_derived_ratios(ratio_rows)
                total_ratio_rows += len(ratio_rows)

            # ── Annual ─────────────────────────────────────────
            a_income = t.income_stmt if hasattr(t, "income_stmt") else t.financials
            a_balance = t.balance_sheet
            a_cashflow = t.cashflow

            stmt_rows = _extract_fundamentals(t, ticker, "FY", a_income, a_balance, a_cashflow)
            if stmt_rows:
                db.upsert_fundamentals(stmt_rows)
                total_stmt_rows += len(stmt_rows)

            ratio_rows = _compute_derived_ratios(a_income, a_balance, a_cashflow, "FY")
            for r in ratio_rows:
                r["ticker"] = ticker
            if ratio_rows:
                db.upsert_derived_ratios(ratio_rows)
                total_ratio_rows += len(ratio_rows)

        except Exception as e:
            logger.warning("Fundamentals error for %s: %s", ticker, e)

        time.sleep(0.15)
        if (i + 1) % 50 == 0:
            logger.info("Fundamentals: %d/%d tickers…", i + 1, len(tickers))

    logger.info("Fundamentals complete — %d statement rows, %d ratio rows.", total_stmt_rows, total_ratio_rows)
