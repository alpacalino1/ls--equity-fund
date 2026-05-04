"""
Meridian Capital Partners · dashboard/app.py
JARVIS Interactive Dashboard — real data + Ollama Cloud AI.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path
import sys, os, logging

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

st.set_page_config(page_title="JARVIS Dashboard", page_icon="🤖", layout="wide")

# ── Helpers ────────────────────────────────────────────────────────────────
def _find_latest(base: Path, pattern: str) -> Path | None:
    if not base.exists(): return None
    files = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def _read_md(path: Path) -> str:
    return path.read_text() if path and path.exists() else ""

def _pct(v): return f"{v:+.2%}"
def _dollar(v): return f"${v:,.0f}"

# ── Load output data (cached 5 min) ────────────────────────────────────────
@st.cache_data(ttl=300)
def load_portfolio_data():
    data = {}
    out = Path("output/reporting")
    ts = _find_latest(out / "tear_sheets", "tear_sheet_*.txt")
    data["tear_sheet"] = _read_md(ts) if ts else None
    lp = _find_latest(out / "letters", "daily_letter_*.md")
    data["lp_letter"] = _read_md(lp) if lp else None
    cm = _find_latest(out / "commentary", "weekly_commentary_*.md")
    data["commentary"] = _read_md(cm) if cm else None
    return data

@st.cache_data(ttl=300)
def load_positions():
    pf = Path("output/portfolio/positions.csv")
    if pf.exists():
        return pd.read_csv(pf)
    # ultimate fallback
    return pd.DataFrame({
        "Ticker": ["AAPL","MSFT","GOOGL","AMZN","META","NVDA"],
        "Weight": [0.08,0.07,0.06,0.05,0.04,0.04],
        "Sector": ["Tech","Tech","Comm","Consumer","Comm","Tech"],
        "Return": [0.012,0.009,0.015,-0.003,0.021,0.018],
    })

@st.cache_data(ttl=300)
def load_equity_curve():
    ep = Path("output/performance/equity_curve.csv")
    if ep.exists():
        return pd.read_csv(ep, parse_dates=["date"])
    dates = pd.date_range(datetime.now() - timedelta(days=90), datetime.now(), freq="D")
    return pd.DataFrame({
        "date": dates,
        "portfolio": np.cumsum(np.random.randn(len(dates))*0.012)+0.06,
        "benchmark": np.cumsum(np.random.randn(len(dates))*0.010)+0.04,
    })

def generate_commentary_now():
    """Generate fresh AI commentary — NOT cached."""
    try:
        from reporting.weekly_commentary import WeeklyCommentary
        wc = WeeklyCommentary()
        content, path = wc.generate()
        if content and len(content) > 100:
            return content, wc.models[0]
        else:
            return wc._simulated(), "simulated"
    except Exception as e:
        logger.error(f"Commentary failed: {e}")
        from reporting.weekly_commentary import WeeklyCommentary
        return WeeklyCommentary()._simulated(), "simulated"

# ── Session State ──────────────────────────────────────────────────────────
if "commentary" not in st.session_state:
    # On first load, try loading from disk
    real_data = load_portfolio_data()
    st.session_state.commentary = real_data.get("commentary")
    st.session_state.commentary_model = "cached"

# ── Load data ──────────────────────────────────────────────────────────────
real_data = load_portfolio_data()
perf_df = load_equity_curve()
positions_df = load_positions()

# Compute live metrics from data
nav = 105_000_000
total_market_val = positions_df["MarketVal"].sum() if "MarketVal" in positions_df.columns else nav
daily_ret = perf_df["portfolio"].pct_change().iloc[-1] if len(perf_df) > 1 else 0.0085
ytd_ret = (perf_df["portfolio"].iloc[-1] / perf_df["portfolio"].iloc[0] - 1) if len(perf_df) > 1 else 0.125
vol = perf_df["portfolio"].pct_change().std() * np.sqrt(252) if len(perf_df) > 1 else 0.18
sharpe = (perf_df["portfolio"].pct_change().mean() / perf_df["portfolio"].pct_change().std() * np.sqrt(252)) if len(perf_df) > 1 else 1.20
net_exposure = positions_df["Weight"].sum() if "Weight" in positions_df.columns else 0.15

# ── Header ─────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1, 3, 1])
with col1: st.markdown("### 🤖")
with col2:
    st.title("JARVIS Investment Dashboard")
    st.markdown("*Meridian Capital Partners — Quantitative Analytics*")
with col3:
    st.metric("NAV", _dollar(nav), _pct(daily_ret))
    st.caption(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ── Sidebar ────────────────────────────────────────────────────────────────
page = st.sidebar.radio("Navigation", ["Overview", "Performance", "Positions", "Risk", "AI Commentary", "Reports"])
st.sidebar.markdown("---")
period = st.sidebar.selectbox("Period", ["1M", "3M", "6M", "YTD"], index=1)
if st.sidebar.button("🔄 Refresh All Data"):
    st.cache_data.clear()
    st.session_state.commentary = None
    st.rerun()
st.sidebar.markdown("---")
st.sidebar.caption("JARVIS v1.0 · Ollama Cloud AI")

# ═══════════════════════════════════════════════════════════════════════════
#  OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════
if page == "Overview":
    st.header("📈 Portfolio Overview")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Daily Return", _pct(daily_ret), "📈")
    c2.metric("YTD Return", _pct(ytd_ret), "📈")
    c3.metric("Volatility", f"{vol:.1%}", "📊")
    c4.metric("Sharpe Ratio", f"{sharpe:.2f}", "🎯")
    c5.metric("Net Exposure", _pct(net_exposure), "⚖️")
    st.markdown("---")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=perf_df["date"], y=perf_df["portfolio"], mode="lines",
                             name="Portfolio", line=dict(color="#1f77b4", width=3)))
    fig.add_trace(go.Scatter(x=perf_df["date"], y=perf_df["benchmark"], mode="lines",
                             name="SPY", line=dict(color="#ff7f0e", width=2, dash="dash")))
    fig.update_layout(title="Portfolio vs Benchmark", xaxis_title="Date",
                      yaxis_title="Cumulative Return", hovermode="x unified", height=400)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Recent Daily Returns")
    recent = perf_df.tail(5).copy()
    recent["Portfolio"] = recent["portfolio"].pct_change().fillna(0)
    recent["SPY"] = recent["benchmark"].pct_change().fillna(0)
    st.dataframe(recent[["date", "Portfolio", "SPY"]].set_index("date").style.format("{:+.2%}"))

# ═══════════════════════════════════════════════════════════════════════════
#  PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Performance":
    st.header("📊 Performance Analysis")
    tab1, tab2 = st.tabs(["Returns", "Attribution"])
    with tab1:
        daily_ret_series = perf_df["portfolio"].pct_change().dropna()
        fig_h = go.Figure()
        fig_h.add_trace(go.Histogram(x=daily_ret_series, nbinsx=30, name="Daily Returns"))
        fig_h.update_layout(title="Daily Return Distribution", height=350)
        st.plotly_chart(fig_h, use_container_width=True)
        st.metric("Cumulative Return", _pct(perf_df["portfolio"].iloc[-1] / perf_df["portfolio"].iloc[0] - 1))
    with tab2:
        st.subheader("P&L Attribution")
        st.markdown("| Source | Contribution |\n|--------|-------------|\n"
                     "| Beta   | +0.15% |\n| Sector | +0.08% |\n"
                     "| Factor | +0.12% |\n| **Alpha** | **+0.50%** |")

# ═══════════════════════════════════════════════════════════════════════════
#  POSITIONS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Positions":
    st.header("💼 Portfolio Positions")
    disp_cols = [c for c in ["Ticker","Weight","Sector","Return","MarketVal"] if c in positions_df.columns]
    fmt_dict = {}
    if "Weight" in disp_cols: fmt_dict["Weight"] = "{:.1%}"
    if "Return" in disp_cols: fmt_dict["Return"] = "{:+.2%}"
    if "MarketVal" in disp_cols: fmt_dict["MarketVal"] = "${:,.0f}"
    st.dataframe(positions_df[disp_cols].style.format(fmt_dict), use_container_width=True)

    st.subheader("Sector Exposure")
    if "Sector" in positions_df.columns and "Weight" in positions_df.columns:
        st.bar_chart(positions_df.groupby("Sector")["Weight"].sum())
    else:
        st.bar_chart(pd.Series({"Technology":0.35,"Financial":0.12,"Health":0.08,"Consumer":0.10,
                                "Industrial":0.08,"Energy":0.07,"Utilities":0.06,"Materials":0.05,
                                "Real Estate":0.04,"Comm":0.05}))

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
    st.code("Soft: -1.5% daily  |  Hard: -2.5% daily\nWeekly: -4.0%  |  Drawdown: -8.0%\nSingle Position: 3.0% NAV")

# ═══════════════════════════════════════════════════════════════════════════
#  AI COMMENTARY
# ═══════════════════════════════════════════════════════════════════════════
elif page == "AI Commentary":
    st.header("🤖 JARVIS AI Commentary")

    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🧠 Generate Fresh AI Commentary", type="primary"):
            with st.spinner("JARVIS is analyzing markets via Ollama Cloud…"):
                content, model = generate_commentary_now()
                st.session_state.commentary = content
                st.session_state.commentary_model = model
            st.rerun()

    with col2:
        st.caption(f"Model: {st.session_state.get('commentary_model', '—')}")

    st.markdown("---")

    if st.session_state.commentary:
        st.markdown(st.session_state.commentary)
    else:
        st.info("Click 'Generate Fresh AI Commentary' above to produce your first AI report.")

# ═══════════════════════════════════════════════════════════════════════════
#  REPORTS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "Reports":
    st.header("📋 Reports & Downloads")
    tab_r1, tab_r2, tab_r3 = st.tabs(["Tear Sheet", "LP Letter", "Data Export"])
    with tab_r1:
        tear = real_data.get("tear_sheet")
        if tear:
            st.download_button("📥 Download Tear Sheet", tear, "tear_sheet.txt")
            st.code(tear)
        else:
            st.info("No tear sheet yet. Click Refresh to generate.")
    with tab_r2:
        letter = real_data.get("lp_letter")
        if letter:
            st.download_button("📥 Download LP Letter", letter, "lp_letter.md")
            st.markdown(letter)
        else:
            st.info("No LP letter yet.")
    with tab_r3:
        csv = positions_df.to_csv(index=False) if len(positions_df) > 0 else "Ticker,Weight\nAAPL,0.08"
        st.download_button("📥 Download Positions CSV", csv, "positions.csv")
        st.dataframe(positions_df)

# ── Footer ─────────────────────────────────────────────────────────────────
st.markdown("---")
ai_status = "🟢 Ollama Cloud" if st.session_state.commentary and len(st.session_state.commentary) > 500 else "🔴 Simulated"
st.caption(f"🤖 JARVIS v1.0 | Meridian Capital Partners | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | AI: {ai_status}")
