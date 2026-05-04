# Streamlit Dashboard Template

This is a template for the app.py implementation that will create an interactive dashboard with JARVIS persona.

## Planned Implementation

```python
"""
Meridian Capital Partners · dashboard/app.py
─────────────────────────────────────────────────────────────────
Interactive Streamlit dashboard with JARVIS persona and real-time analytics.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("meridian.dashboard")

# Set page configuration
st.set_page_config(
    page_title="Meridian Capital Partners - Jarvis Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

def initialize_session_state():
    """Initialize Streamlit session state variables."""
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False
    if 'portfolio_data' not in st.session_state:
        st.session_state.portfolio_data = {}
    if 'market_data' not in st.session_state:
        st.session_state.market_data = pd.DataFrame()
    if 'jarvis_responses' not in st.session_state:
        st.session_state.jarvis_responses = []

def load_sample_data():
    """Load sample data for demonstration purposes."""
    # This would be replaced with actual data loading
    portfolio_sample = {
        'current_nav': 105000000,  # $105M
        'daily_return': 0.008,     # 0.8%
        'ytd_return': 0.125,       # 12.5%
        'volatility': 0.18,        # 18%
        'sharpe_ratio': 1.2,
        'net_exposure': 0.15,
        'gross_exposure': 1.75,
        'positions': [
            {'ticker': 'AAPL', 'weight': 0.08, 'sector': 'Technology', 'return': 0.012},
            {'ticker': 'MSFT', 'weight': 0.07, 'sector': 'Technology', 'return': 0.009},
            {'ticker': 'GOOGL', 'weight': 0.06, 'sector': 'Communication Services', 'return': 0.015},
            {'ticker': 'AMZN', 'weight': 0.05, 'sector': 'Consumer Discretionary', 'return': -0.003},
            {'ticker': 'META', 'weight': 0.04, 'sector': 'Communication Services', 'return': 0.021},
        ],
        'sector_exposures': {
            'Technology': 0.35,
            'Financials': 0.12,
            'Healthcare': 0.08,
            'Consumer_Discretionary': 0.10,
            'Industrials': 0.08,
            'Energy': 0.07,
            'Utilities': 0.06,
            'Materials': 0.05,
            'Real_Estate': 0.04,
            'Consumer_Staples': 0.03,
            'Communications': 0.02
        }
    }
    
    # Sample market data
    dates = pd.date_range(datetime.now() - timedelta(days=90), datetime.now(), freq='D')
    market_sample = pd.DataFrame({
        'date': dates,
        'SPY': np.random.randn(len(dates)).cumsum() * 0.01 + 0.05,
        'portfolio': np.random.randn(len(dates)).cumsum() * 0.012 + 0.06,
        'volatility': np.random.uniform(15, 30, len(dates))
    })
    
    return portfolio_sample, market_sample

def create_header():
    """Create dashboard header with logo and title."""
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col1:
        st.image("https://raw.githubusercontent.com/streamlit/streamlit/master/static/images/logo.png", width=80)
    
    with col2:
        st.title("🤖 JARVIS Investment Dashboard")
        st.markdown("*Meridian Capital Partners - Advanced Quantitative Analytics*")
    
    with col3:
        st.metric(
            label="Portfolio Value", 
            value="$105M",
            delta="0.8%"
        )
        st.caption(f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def create_sidebar():
    """Create sidebar with navigation and controls."""
    st.sidebar.title("📊 Navigation")
    
    page = st.sidebar.radio(
        "Go to",
        ["Overview", "Performance", "Positions", "Risk", "JARVIS Chat", "Reports"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚙️ Settings")
    
    # Time period selector
    period = st.sidebar.selectbox(
        "Analysis Period",
        ["1M", "3M", "6M", "1Y", "YTD", "MAX"],
        index=3
    )
    
    # Refresh data button
    if st.sidebar.button("🔄 Refresh Data"):
        st.session_state.data_loaded = False
        st.experimental_rerun()
        
    # JARVIS settings
    st.sidebar.markdown("---")
    st.sidebar.subheader("🤖 JARVIS Settings")
    jarvis_verbose = st.sidebar.checkbox("Verbose Mode", value=True)
    jarvis_style = st.sidebar.selectbox(
        "Response Style",
        ["Professional", "Concise", "Technical", "Executive"]
    )
    
    return page, period, jarvis_verbose, jarvis_style

def create_overview_page(portfolio_data: Dict[str, Any], market_data: pd.DataFrame):
    """Create the portfolio overview dashboard page."""
    st.header("📈 Portfolio Overview")
    
    # Key metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Daily Return", f"{portfolio_data.get('daily_return', 0):+.2%}", "📈")
    
    with col2:
        st.metric("YTD Return", f"{portfolio_data.get('ytd_return', 0):+.2%}", "📈")
        
    with col3:
        st.metric("Volatility", f"{portfolio_data.get('volatility', 0):.1%}", "📊")
        
    with col4:
        st.metric("Sharpe Ratio", f"{portfolio_data.get('sharpe_ratio', 0):.2f}", "🎯")
        
    with col5:
        st.metric("Net Exposure", f"{portfolio_data.get('net_exposure', 0):+.1%}", "⚖️")
    
    st.markdown("---")
    
    # Equity curve chart
    fig_equity = create_equity_chart(market_data)
    st.plotly_chart(fig_equity, use_container_width=True)
    
    # Recent performance table
    st.subheader("Recent Performance")
    recent_data = market_data.tail(10)
    st.dataframe(
        recent_data.style.format({
            'SPY': '{:.2%}',
            'portfolio': '{:.2%}',
            'volatility': '{:.1f}'
        }),
        height=300
    )

def create_equity_chart(market_data: pd.DataFrame) -> go.Figure:
    """Create equity curve comparison chart."""
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=market_data['date'],
        y=market_data['portfolio'].cumsum(),
        mode='lines',
        name='Portfolio',
        line=dict(color='#1f77b4', width=3)
    ))
    
    fig.add_trace(go.Scatter(
        x=market_data['date'],
        y=market_data['SPY'].cumsum(),
        mode='lines',
        name='SPY Benchmark',
        line=dict(color='#ff7f0e', width=2, dash='dash')
    ))
    
    fig.update_layout(
        title="Portfolio vs Benchmark Performance",
        xaxis_title="Date",
        yaxis_title="Cumulative Return",
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig

def create_performance_page(portfolio_data: Dict[str, Any]):
    """Create detailed performance analysis page."""
    st.header("📊 Performance Analysis")
    
    # Tabbed interface
    tab1, tab2, tab3 = st.tabs(["Returns", "Risk Metrics", "Attribution"])
    
    with tab1:
        st.subheader("Return Analysis")
        # This would contain detailed return breakdowns
        
    with tab2:
        st.subheader("Risk Metrics")
        # This would contain VaR, max drawdown, etc.
        
    with tab3:
        st.subheader("Performance Attribution")
        # This would show factor/sector attribution

def create_positions_page(portfolio_data: Dict[str, Any]):
    """Create positions analysis page."""
    st.header("💼 Portfolio Positions")
    
    # Current positions table
    positions = portfolio_data.get('positions', [])
    if positions:
        positions_df = pd.DataFrame(positions)
        st.dataframe(
            positions_df.style.format({
                'weight': '{:.1%}',
                'return': '{:+.2%}'
            }),
            use_container_width=True
        )
    
    # Sector exposures chart
    st.subheader("Sector Exposures")
    sector_data = portfolio_data.get('sector_exposures', {})
    if sector_data:
        sector_df = pd.DataFrame({
            'Sector': list(sector_data.keys()),
            'Exposure': list(sector_data.values())
        }).sort_values('Exposure', ascending=False)
        
        fig = px.bar(
            sector_df,
            x='Sector',
            y='Exposure',
            title="Portfolio Sector Exposures"
        )
        st.plotly_chart(fig, use_container_width=True)

def create_risk_page():
    """Create risk analytics page."""
    st.header("⚠️ Risk Analytics")
    
    # Risk metrics would be displayed here
    st.info("Risk analytics dashboard - coming soon!")

def create_jarvis_chat(jarvis_verbose: bool, jarvis_style: str):
    """Create JARVIS chat interface."""
    st.header("🤖 JARVIS Assistant")
    
    # Chat history
    if 'jarvis_responses' not in st.session_state:
        st.session_state.jarvis_responses = []
    
    # Display chat history
    for message in st.session_state.jarvis_responses:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask JARVIS about the portfolio..."):
        # Add user message to chat history
        st.session_state.jarvis_responses.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # Generate JARVIS response (placeholder)
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = generate_jarvis_response(prompt, jarvis_verbose, jarvis_style)
            message_placeholder.markdown(full_response)
            
        # Add assistant response to chat history
        st.session_state.jarvis_responses.append({"role": "assistant", "content": full_response})

def generate_jarvis_response(prompt: str, verbose: bool, style: str) -> str:
    """Generate JARVIS response to user query."""
    # This would integrate with Claude API in production
    # For demo, return contextual responses
    
    responses = {
        "performance": "Portfolio is currently up 0.8% today with technology positions leading the gains. Year-to-date performance stands at +12.5%.",
        "risk": "Current portfolio risk metrics show volatility at 18% annualized with a Sharpe ratio of 1.2. Net exposure is maintained at +15%.",
        "positions": "Our largest positions include AAPL (8%), MSFT (7%), and GOOGL (6%) within our technology allocation.",
        "strategy": "Our quantitative strategy emphasizes momentum and quality factors with sector diversification and risk management protocols."
    }
    
    # Simple keyword matching for demo
    prompt_lower = prompt.lower()
    if "perform" in prompt_lower:
        return responses["performance"]
    elif "risk" in prompt_lower:
        return responses["risk"]
    elif "position" in prompt_lower or "hold" in prompt_lower:
        return responses["positions"]
    elif "strategy" in prompt_lower or "approach" in prompt_lower:
        return responses["strategy"]
    else:
        return f"I understand you're asking about: '{prompt}'. Based on my analysis, I can provide insights on portfolio performance, risk metrics, position analysis, and strategic considerations. What specific aspect would you like me to elaborate on?"

def create_reports_page():
    """Create reports download page."""
    st.header("📋 Reports")
    
    st.info("Report generation dashboard - coming soon!")
    
    # This would provide downloadable reports:
    # - Daily attribution CSV
    # - Monthly tear sheets
    # - Weekly commentary
    # - LP letters
    # - Risk reports

def main():
    """Main dashboard application."""
    # Initialize session state
    initialize_session_state()
    
    # Load data if not already loaded
    if not st.session_state.data_loaded:
        with st.spinner("Loading portfolio data..."):
            portfolio_data, market_data = load_sample_data()
            st.session_state.portfolio_data = portfolio_data
            st.session_state.market_data = market_data
            st.session_state.data_loaded = True
    
    # Create header
    create_header()
    
    # Create sidebar and get selections
    page, period, jarvis_verbose, jarvis_style = create_sidebar()
    
    # Display selected page
    if page == "Overview":
        create_overview_page(st.session_state.portfolio_data, st.session_state.market_data)
    elif page == "Performance":
        create_performance_page(st.session_state.portfolio_data)
    elif page == "Positions":
        create_positions_page(st.session_state.portfolio_data)
    elif page == "Risk":
        create_risk_page()
    elif page == "JARVIS Chat":
        create_jarvis_chat(jarvis_verbose, jarvis_style)
    elif page == "Reports":
        create_reports_page()
    
    # Footer
    st.markdown("---")
    st.caption(f"🤖 JARVIS Dashboard v1.0 | Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
```

## Key Features to Implement

1. **JARVIS Persona Interface**: Interactive chat with advanced market analyst character
2. **Real-Time Analytics**: Live dashboard with performance metrics and risk indicators  
3. **Professional Visualization**: Plotly charts with institutional presentation standards
4. **Responsive Design**: Mobile-friendly layout with adaptive components
5. **Tabbed Navigation**: Organized sections for different analytical domains
6. **Session Management**: Persistent user interactions and preferences
7. **Configurable Components**: Adjustable time periods and display settings
8. **Report Integration**: Access to generated analysis documents

## Integration Points

- Connects to reporting engine for real-time data feeds
- Integrates with Claude API for advanced JARVIS functionality
- Works with all Layer 7 components (attribution, analytics, letters)
- Consumes portfolio data from Layer 4 optimization
- Links to tear sheet and commentary generation
- Supports investor communication and client facing applications
- Feeds compliance and regulatory reporting workflows