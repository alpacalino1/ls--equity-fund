"""
Meridian Capital Partners · dashboard/app.py
JARVIS Interactive Dashboard — Streamlit.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(page_title="JARVIS Dashboard", page_icon="🤖", layout="wide")

# Sample data
dates = pd.date_range(datetime.now() - timedelta(days=90), datetime.now(), freq="D")
np.random.seed(42)
portfolio = np.cumsum(np.random.randn(len(dates)) * 0.012) + 0.06
benchmark = np.cumsum(np.random.randn(len(dates)) * 0.010) + 0.04

# Header
col1, col2, col3 = st.columns([1, 3, 1])
with col1: st.image("https://raw.githubusercontent.com/streamlit/streamlit/master/static/images/logo.png", width=80)
with col2:
    st.title("🤖 JARVIS Investment Dashboard")
    st.markdown("*Meridian Capital Partners — Advanced Quantitative Analytics*")
with col3:
    st.metric("Portfolio Value", "$105M", "+0.85%")
    st.caption(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# Sidebar
page = st.sidebar.radio("Navigation", ["Overview", "Performance", "Positions", "Risk", "Reports"])
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ Settings")
period = st.sidebar.selectbox("Period", ["1M", "3M", "6M", "YTD"], index=1)
st.sidebar.button("🔄 Refresh")

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
    fig.add_trace(go.Scatter(x=dates, y=portfolio, mode="lines", name="Portfolio", line=dict(color="#1f77b4", width=3)))
    fig.add_trace(go.Scatter(x=dates, y=benchmark, mode="lines", name="SPY", line=dict(color="#ff7f0e", width=2, dash="dash")))
    fig.update_layout(title="Portfolio vs Benchmark", xaxis_title="Date", yaxis_title="Cumulative Return", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
    st.subheader("Recent Performance")
    st.dataframe(pd.DataFrame({"Date": dates[-5:], "Portfolio": np.round(np.random.randn(5)*0.005+0.002, 4), "SPY": np.round(np.random.randn(5)*0.004+0.001, 4)}).set_index("Date"))

elif page == "Performance":
    st.header("📊 Performance Analysis")
    tab1, tab2 = st.tabs(["Returns", "Attribution"])
    with tab1: st.write("Daily returns analysis and distribution charts")
    with tab2:
        st.write("### P&L Attribution")
        st.write("Beta: 0.15% | Sector: 0.08% | Factor: 0.12% | Alpha: 0.50%")

elif page == "Positions":
    st.header("💼 Portfolio Positions")
    pos_data = pd.DataFrame({"Ticker": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "JPM", "V", "JNJ", "PG"],
        "Weight": [0.08, 0.07, 0.06, 0.05, 0.04, 0.04, 0.03, 0.03, 0.02, 0.02],
        "Sector": ["Tech", "Tech", "Comm", "Consumer", "Comm", "Tech", "Financial", "Financial", "Health", "Consumer"],
        "Return": [0.012, 0.009, 0.015, -0.003, 0.021, 0.018, 0.005, -0.002, 0.008, -0.001]})
    st.dataframe(pos_data.style.format({"Weight": "{:.1%}", "Return": "{:+.2%}"}), use_container_width=True)
    st.subheader("Sector Exposure")
    sectors = {"Technology": 0.35, "Financial": 0.12, "Health": 0.08, "Consumer": 0.10, "Industrial": 0.08, "Energy": 0.07, "Utilities": 0.06, "Materials": 0.05, "Real Estate": 0.04, "Comm": 0.05}
    st.bar_chart(pd.Series(sectors))

elif page == "Risk":
    st.header("⚠️ Risk Analytics")
    c1, c2, c3 = st.columns(3)
    c1.metric("Max Drawdown", "-8.5%", "⚠️")
    c2.metric("VaR (95%)", "-2.3%", "📉")
    c3.metric("Beta", "0.95", "📊")
    st.markdown("---")
    st.write("### Factor Risk Decomposition")
    st.write("Factor Risk: 22% | Specific Risk: 78%")

elif page == "Reports":
    st.header("📋 Reports")
    st.download_button("📥 Download Tear Sheet", "Sample tear sheet content...", "tear_sheet.txt")
    st.download_button("📥 Download LP Letter", "Dear Limited Partners...", "lp_letter.txt")
    st.download_button("📥 Download Attribution CSV", "date,alpha,beta...", "attribution.csv")

# Footer
st.markdown("---")
st.caption(f"🤖 JARVIS Dashboard v1.0 | Meridian Capital Partners | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
