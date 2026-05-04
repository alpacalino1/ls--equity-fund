"""
Meridian Capital Partners · data/institutional.py
─────────────────────────────────────────────────────────────────
Source 5/5 — Institutional holdings (SEC 13F filings).
Uses SEC EDGAR to pull latest 13F filings for major funds
(Citadel, Bridgewater, Point72, etc.) and extracts S&P 500 positions.
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd

from .db import MeridianDB

logger = logging.getLogger("meridian.institutional")

# Major funds we want to track (CIK numbers)
TRACKED_FUNDS = {
    "Citadel Advisors": "0001423053",
    "Bridgewater Associates": "0001350694",
    "Point72 Asset Management": "0001603466",
    "Renaissance Technologies": "0001037389",
    "Two Sigma Investments": "0001179392",
    "DE Shaw & Co": "0001009207",
    "Millennium Management": "0001273087",
    "Baupost Group": "0001061768",
    "Appaloosa Management": "0000895921",
    "Tiger Global Management": "0001167483",
}


def _fetch_13f_filings(cik: str, fund_name: str, lookback_years: int) -> list[dict]:
    """
    Fetch latest 13F holdings for a fund from SEC EDGAR.
    Uses the SEC's submission API to find latest 13F-HR filings,
    then downloads the primary_document.xml.
    """
    results = []

    # Get list of 13F-HR filings for this CIK
    try:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        headers = {"User-Agent": "Meridian Capital Partners research@meridian.example.com"}
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        accessions = filings.get("accessionNumber", [])
        primary_docs = filings.get("primaryDocument", [])

        # Find 13F-HR within lookback
        cutoff = datetime.now() - timedelta(days=lookback_years * 365)

        for i, form in enumerate(forms):
            if form != "13F-HR":
                continue
            filing_date_str = dates[i]
            try:
                filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if filing_date < cutoff:
                continue

            acc = accessions[i].replace("-", "")
            doc = primary_docs[i]
            # Determine quarter end (13F filings are ~45 days after quarter end)
            # Estimate from filing date
            quarter_end = _estimate_quarter_end(filing_date)

            # Download the information table (XML)
            # The actual holdings are in a separate XML file (form13fInfoTable.xml)
            # or embedded as primaryDocument.xml for some filings.
            info_table_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

            try:
                xml_resp = requests.get(info_table_url, headers=headers, timeout=30)
                if xml_resp.status_code != 200:
                    continue
                xml_text = xml_resp.text

                # Try to fetch the info table if primary doc is just the cover
                if "<informationTable>" not in xml_text:
                    # Try form13fInfoTable.xml
                    info_table_xml = info_table_url.rsplit("/", 1)[0] + "/form13fInfoTable.xml"
                    xml_resp2 = requests.get(info_table_xml, headers=headers, timeout=30)
                    if xml_resp2.status_code == 200:
                        xml_text = xml_resp2.text

                # Parse XML for holdings
                holdings = _parse_13f_xml(xml_text)
                for h in holdings:
                    h["fund_name"] = fund_name
                    h["cik"] = cik
                    h["filing_date"] = filing_date_str
                    h["quarter_end"] = quarter_end
                results.extend(holdings)

            except Exception as e:
                logger.debug("Failed to fetch 13F doc %s: %s", acc, e)
                continue

            time.sleep(0.1)  # SEC rate limit
            # Only grab latest filing per fund
            break

    except Exception as e:
        logger.warning("13F fetch error for %s: %s", fund_name, e)

    return results


def _estimate_quarter_end(filing_date: datetime) -> str:
    """Estimate quarter-end date from filing date (13F filed ~45 days after quarter end)."""
    # Quarters end March, June, September, December
    # Filing is typically 45 days after quarter end
    adjusted = filing_date - timedelta(days=45)
    month = adjusted.month
    if month <= 3:
        q_end = datetime(adjusted.year - 1, 12, 31) if month < 3 else datetime(adjusted.year, 3, 31)
    elif month <= 6:
        q_end = datetime(adjusted.year, 6, 30)
    elif month <= 9:
        q_end = datetime(adjusted.year, 9, 30)
    else:
        q_end = datetime(adjusted.year, 12, 31)
    return q_end.strftime("%Y-%m-%d")


def _parse_13f_xml(xml_text: str) -> list[dict]:
    """Extract holdings from 13F XML."""
    holdings = []
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)

        # Find all infoTable entries
        ns = {"ns": "http://www.sec.gov/edgar/document/thirteenf/informationtable"}
        tables = root.findall(".//ns:infoTable", ns)
        if not tables:
            # Try without namespace
            tables = root.findall(".//infoTable")

        for table in tables:
            def _text(tag):
                el = table.find(f"ns:{tag}", ns) or table.find(tag)
                return el.text.strip() if el is not None and el.text else ""

            ticker = _text("titleOfClass").upper()
            if not ticker:
                continue

            try:
                shares = float(_text("sshPrnamt") or 0)
                value = float(_text("value") or 0) * 1000  # values in thousands
            except ValueError:
                continue

            # Get change type from voting authority
            change = 0  # 0 = no change, we approximate
            holdings.append({
                "ticker": ticker,
                "shares": shares,
                "value": value,
                "change_shares": change,
            })

    except ET.ParseError as e:
        logger.debug("XML parse error: %s", e)
    except Exception as e:
        logger.debug("13F parse error: %s", e)

    return holdings


def update_institutional(tickers: list[str], config: dict, db: MeridianDB):
    """
    Fetch latest 13F holdings for tracked funds.
    Filter to S&P 500 tickers, upsert into institutional_holdings table.
    """
    data_cfg = config["data"]["institutional"]
    lookback_years = data_cfg["lookback_years"]
    cache_path = data_cfg["cache_path"]
    refresh_days = data_cfg["refresh_days"]

    cache_file = Path(cache_path)
    use_cache = False
    if cache_file.exists():
        age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        if age < timedelta(days=refresh_days):
            use_cache = True

    if use_cache:
        df = pd.read_csv(cache_path)
        all_rows = df.to_dict(orient="records")
        logger.info("Using cached institutional data (%d rows).", len(all_rows))
    else:
        all_rows = []
        for fund_name, cik in TRACKED_FUNDS.items():
            logger.info("Fetching 13F for %s…", fund_name)
            rows = _fetch_13f_filings(cik, fund_name, lookback_years)
            all_rows.extend(rows)
            time.sleep(0.3)

        if all_rows:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(all_rows).to_csv(cache_path, index=False)

    # Filter to S&P 500 tickers (case-insensitive)
    sp500_tickers = set(t.upper() for t in tickers)
    filtered = [r for r in all_rows if r["ticker"].upper() in sp500_tickers]

    if filtered:
        db.upsert_institutional(filtered)

    logger.info("Institutional update complete — %d holdings stored (%d total fetched).", len(filtered), len(all_rows))
    return len(filtered)
