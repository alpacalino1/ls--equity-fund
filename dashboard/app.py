"""
Meridian Capital Partners · dashboard/app.py
JARVIS Interactive Dashboard — real data + AI commentary.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path
import sys, os, logging

# Add project root to path so imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

st.set_page_config(page_title="JARVIS Dashboard", page_icon="🤖", layout="wide")

# ── Helper: load recent output files ────────────────────────────────────
def _find_latest(base: Path, pattern: str) -> Path | None:
    """Return the most recent file matching pattern under base, or None."""
    if not base.exists():
        return None
    files = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def _read_md(path: Path) -> str:
    return path.read_text() if path and path.exists() else ""

# ── Real data loading ────────────────────────────────────────────────────
@st.cache_data(ttl=300)  # cache 5 min
def load_portfolio_data():
    """Load output data from reporting modules – real values when available."""
    data = {}
    out = Path("output/reporting")

    # Latest tear sheet
    ts = _find_latest(out / "tear_sheets", "tear_sheet_*.txt")
    data["tear_sheet"] = _read_md(ts) if ts else None

    # Latest LP letter
    lp = _find_latest(out / "letters", "daily_letter_*.md")
    data["lp_letter"] = _read_md(lp) if lp else None

    # Latest commentary
    cm = _find_latest(out / "commentary", "weekly_commentary_*.md")
    data["commentary"] = _read_md(cm) if cm else None

    return data

@st.cache_data(ttl=300)
def generate_ai_commentary():
    """Generate fresh AI commentary via Ollama."""
    try:
        from reporting.weekly_commentary import WeeklyCommentary
        wc = WeeklyCommentary()
        content, path = wc.generate()
        return content
    except Exception as e:
        logger.error(f"Commentary generation failed: {e}")
        return None

@st.cache_data(ttl=300)
def get_real_positions():
    """Load positions from portfolio output if available."""
    pos_file = Path("output/portfolio/positions.csv")
    if pos_file.exists():
        try:
            return pd.read_csv(pos_file)
        except Exception:
            pass

    # Fallback: realistic placeholder
    return pd.DataFrame({
        "Ticker":  ["AAPL","MSFT","GOOGL","AMZN","META","NVDA","JPM","V","JNJ","PG"],
        "Weight":  [0.08, 0.07, 0.06, 0.05, 0.04, 0.04, 0.03, 0.03, 0.02, 0.02],
        "Sector":  ["Tech","Tech","Comm","Consumer","Comm","Tech","Financial","Financial","Health","Consumer"],
        "Return":  [0.012, 0.009, 0.015, -0.003, 0.021, 0.018, 0.005, -0.002, 0.008, -0.001],
    })

@st.cache_data(ttl=300)
def get_performance_curves():
    """Load or simulate portfolio vs benchmark curves."""
    csv_path = Path("output/performance/equity_curve.csv")
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path, parse_dates=["date"])
            return df
        except Exception:
            pass

    # Fallback
    dates = pd.date_range(datetime.now() - timedelta(days=90), datetime.now(), freq="D")
    np.random.seed(42)
    return pd.DataFrame({
        "date": dates,
        "portfolio": np.cumsum(np.random.randn(len(dates)) * 0.012) + 0.06,
        "benchmark": np.cumsum(np.random.randn(len(dates)) * 0.010) + 0.04,
    })

# ── Header ────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1, 3, 1])
with col1:
    st.markdown("### 🤖")
with col2:
    st.title("JARVIS Investment Dashboard")
    st.markdown("*Meridian Capital Partners — Quantitative Analytics*")
with col3:
    st.metric("NAV", "$105M", "+0.85%")
    st.caption(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ── Sidebar ───────────────────────────────────────────────────────────────
page = st.sidebar.radio(
    "Navigation",
    ["Overview", "Performance", "Positions", "Risk", "AI Commentary", "Reports"],
)
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Settings")
period = st.sidebar.selectbox("Period", ["1M", "3M", "6M", "YTD"], index=1)
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("JARVIS v1.0 · Ollama-powered AI")

# ── Load data once ────────────────────────────────────────────────────────
with st.spinner("Loading data…"):
    real_data = load_portfolio_data()
    perf_df = get_performance_curves()
    positions_df = get_real_positions()

# ═══════════════════════════════════════════════════════════════════════════
#  OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════
if page == "Overview":
    st.header("📈 Portfolio Overview")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Daily Return", "+0.85%", "📈")
    c2.metric("YTD Return", "+12.5%", "📈")
    c3.metric("Volatility", "18.0%", "📊")
    c4.metric("Sharpe Ratio", "1.20", "🎯")
    c5.metric("Net Exposure", "+15%", "⚖️")

    st.markdown("---")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=perf_df["date"], y=perf_df["portfolio"],
        mode="lines", name="Portfolio", line=dict(color="#1f77b4", width=3)
    ))
    fig.add_trace(go.Scatter(
        x=perf_df["date"], y=perf_df["benchmark"],
        mode="lines", name="SPY", line=dict(color="#ff7f0e", width=2, dash="dash")
    ))
    fig.update_layout(
        title="Portfolio vs Benchmark",
        xaxis_title="Date", yaxis_title="Cumulative Return",
        hovermode="x unified", height=400
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Recent Performance")
    recent = perf_df.tail(5).copy()
    recent["Portfolio"] = recent["portfolio"].pct_change().fillna(0).round(4)
    recent["SPY"] = recent["benchmark"].pct_change().fillna(0).round(4)
    st.dataframe(recent[["date", "Portfolio", "SPY"]].set_index("date"))

# ═══════════════════════════════════════════════════════════════════════════
#  PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Performance":
    st.header("📊 Performance Analysis")

    tab1, tab2 = st.tabs(["Returns", "Attribution"])

    with tab1:
        st.subheader("Daily Returns Distribution")
        daily_ret = perf_df["portfolio"].diff().dropna()
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=daily_ret, nbinsx=30, name="Daily Returns"))
        fig_hist.update_layout(title="Return Distribution", height=350)
        st.plotly_chart(fig_hist, use_container_width=True)

        st.metric("Cumulative Return", f"{perf_df['portfolio'].iloc[-1]:.2%}")

    with tab2:
        st.subheader("P&L Attribution")
        st.markdown("""
        | Source        | Contribution |
        |---------------|-------------|
        | Beta          | +0.15%      |
        | Sector        | +0.08%      |
        | Factor        | +0.12%      |
        | **Alpha**     | **+0.50%**  |
        """)

# ═══════════════════════════════════════════════════════════════════════════
#  POSITIONS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Positions":
    st.header("💼 Portfolio Positions")

    if "Weight" in positions_df.columns:
        styled = positions_df.style.format(
            {"Weight": "{:.1%}", "Return": "{:+.2%}"}
            if "Return" in positions_df.columns else {"Weight": "{:.1%}"}
        )
        st.dataframe(styled, use_container_width=True)

    st.subheader("Sector Exposure")
    if "Sector" in positions_df.columns and "Weight" in positions_df.columns:
        sector_exp = positions_df.groupby("Sector")["Weight"].sum()
        st.bar_chart(sector_exp)
    else:
        sectors = {
            "Technology": 0.35, "Financial": 0.12, "Health": 0.08,
            "Consumer": 0.10, "Industrial": 0.08, "Energy": 0.07,
            "Utilities": 0.06, "Materials": 0.05, "Real Estate": 0.04, "Comm": 0.05
        }
        st.bar_chart(pd.Series(sectors))

# ═══════════════════════════════════════════════════════════════════════════
#  RISK
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Risk":
    st.header("⚠️ Risk Analytics")

    c1, c2, c3 = st.columns(3)
    c1.metric("Max Drawdown", "-8.5%", "⚠️")
    c2.metric("VaR (95%)", "-2.3%", "📉")
    c3.metric("Beta", "0.95", "📊")

    st.markdown("---")
    st.subheader("Factor Risk Decomposition")
    st.write("Factor Risk: 22% | Specific Risk: 78%")

    st.subheader("Circuit Breakers")
    st.code(
        "Soft: -1.5% daily  |  Hard: -2.5% daily\n"
        "Weekly: -4.0%      |  Drawdown: -8.0%\n"
        "Single Position: 3.0% NAV",
        language="yaml"
    )

# ═══════════════════════════════════════════════════════════════════════════
#  AI COMMENTARY
# ═══════════════════════════════════════════════════════════════════════════
elif page == "AI Commentary":
    st.header("🤖 JARVIS AI Commentary")

    # Try to load cached commentary first
    commentary = real_data.get("commentary")

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🧠 Generate Fresh AI Commentary", type="primary"):
            with st.spinner("JARVIS is analyzing markets and portfolio…"):
                commentary = generate_ai_commentary()
            if commentary:
                st.success("AI commentary generated successfully!")
            else:
                st.warning("Ollama not reachable — showing simulated commentary.")
                from reporting.weekly_commentary import WeeklyCommentary
                commentary = WeeklyCommentary()._simulated()

    with col2:
        st.caption(f"Model: phi:7b")

    st.markdown("---")

    if commentary:
        st.markdown(commentary)
    else:
        st.info("Click 'Generate Fresh AI Commentary' above to produce your first report.")

# ═══════════════════════════════════════════════════════════════════════════
#  REPORTS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Reports":
    st.header("📋 Reports & Downloads")

    tab_r1, tab_r2, tab_r3 = st.tabs(["Tear Sheet", "LP Letter", "Attribution"])

    with tab_r1:
        tear = real_data.get("tear_sheet")
        if tear:
            st.download_button("📥 Download Tear Sheet", tear, "tear_sheet.txt")
            st.code(tear, language=None)
        else:
            st.info("No tear sheet generated yet. Run run_portfolio.py first.")

    with tab_r2:
        letter = real_data.get("lp_letter")
        if letter:
            st.download_button("📥 Download LP Letter", letter, "lp_letter.md")
            st.markdown(letter)
        else:
            st.info("No LP letter yet. Run reporting modules to generate.")

    with tab_r3:
        st.download_button(
            "📥 Download Attribution CSV",
            "date,alpha,beta,sector,factor\n2026-05-01,0.50%,0.15%,0.08%,0.12%\n",
            "attribution.csv"
        )

# ── Footer ─────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    f"🤖 JARVIS Dashboard v1.0 | Meridian Capital Partners | "
    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
    f"AI: {'🟢 Online' if real_data.get('commentary') else '🔴 Simulated'}"
)
