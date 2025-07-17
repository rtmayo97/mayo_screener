# Comprehensive AI-Powered Stock Screener & Trade Advisor with Streamlit Interface - Full Version with API Integrations, Scaling Logic, and Protective Filters
# Now enhanced to use Polygon.io for real-time price/volume and Finnhub for news/sentiment analysis
# Also includes a simple password protection gate for secure access, ATR-based stock filtering, and market trend comparison

import sys
import requests
import pandas as pd
from datetime import datetime
import streamlit as st
import os
import pandas_ta as ta

# --- CONFIGURATIONS ---
PRICE_MIN = 20                     # Minimum stock price to scan
DYNAMIC_PRICE_MAX = True           # Enable dynamic price ceiling based on capital
INITIAL_PRICE_MAX = 175            # Default max price if dynamic is off
VOLUME_MIN = 2_000_000             # Minimum intraday volume
PERCENT_CHANGE_MIN = 2.0           # Minimum intraday % change since open
PERCENT_CHANGE_MAX = 10.0          # Max % change to avoid overextended stocks
RISK_PERCENTAGE = 0.02             # Risk 2% of capital per trade
MAX_SHARES_PER_TRADE = 2000        # Cap position size per trade
MARKET_VOLUME_MIN = 2_000_000      # Market volume threshold
MAX_SPREAD_PERCENT = 0.005         # Max bid/ask spread as percent of price
MIN_SENTIMENT_SCORE = 0.2          # Sentiment score threshold
EXCLUDED_TICKERS = ['ALLY']        # Exclude specific tickers
ATR_MIN = 2                        # Minimum acceptable ATR value
ATR_MAX = 5                        # Maximum acceptable ATR value

# --- API KEYS ---
POLYGON_API_KEY = st.secrets['Polygon_Key']
FINNHUB_API_KEY = st.secrets['Finnhub_Key']
APP_PASSWORD = st.secrets['APP_PASSWORD']

# --- SIMPLE PASSWORD CHECK ---
def check_password():
    def password_entered():
        if st.session_state["password"] == APP_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # clear for security
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Enter password:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Enter password:", type="password", on_change=password_entered, key="password")
        st.error("Password incorrect")
        return False
    else:
        return True

# --- CORE FUNCTIONS ---

def get_percent_change(ticker):
    """Calculate percent change for a ticker based on Polygon.io real-time data."""
    url_trade = f"https://api.polygon.io/v2/last/trade/{ticker}?apiKey={POLYGON_API_KEY}"
    url_prev = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_API_KEY}"

    trade_response = requests.get(url_trade).json()
    prev_response = requests.get(url_prev).json()

    current_price = trade_response.get('last', {}).get('price', 0)
    prev_close = prev_response.get('results', [{}])[0].get('c', 0)

    if prev_close == 0:
        return 0
    return ((current_price - prev_close) / prev_close) * 100


def get_market_trend():
    """Calculate the average percent change of SPY and QQQ to represent market trend."""
    spy_change = get_percent_change('SPY')
    qqq_change = get_percent_change('QQQ')
    market_trend = (spy_change + qqq_change) / 2
    return market_trend


def run_screener(investment_amount, tickers):
    """Run the screener logic across a list of tickers using real-time data."""
    trade_plans = []
    market_trend = get_market_trend()

    for ticker in tickers:
        if ticker in EXCLUDED_TICKERS:
            continue

        price, volume = get_realtime_price_volume(ticker)
        prev_close = get_previous_close(ticker)
        percent_change = calculate_percent_change(price, prev_close)

        if percent_change < PERCENT_CHANGE_MIN or percent_change > PERCENT_CHANGE_MAX:
            continue

        sentiment = get_news_sentiment(ticker)
        if sentiment < MIN_SENTIMENT_SCORE:
            continue

        atr_value = get_atr(ticker)

        # --- Filter based on ATR range ---
        if atr_value < ATR_MIN or atr_value > ATR_MAX:
            continue

        stop_loss = price * 0.98  # Example 2% stop loss below price
        target = price * 1.05     # Example 5% target above price

        shares = calculate_shares(investment_amount, price, stop_loss)
        if shares == 0:
            continue

        # --- Determine stock trend relative to market ---
        if percent_change > market_trend:
            trend_vs_market = "HIGHER than the market"
        elif percent_change < market_trend:
            trend_vs_market = "LOWER than the market"
        else:
            trend_vs_market = "WITH the market"

        trade_plans.append({
            'ticker': ticker,
            'price': price,
            'ATR': atr_value,
            'percent_change': percent_change,
            'sentiment': sentiment,
            'stop_loss': round(stop_loss, 2),
            'target': round(target, 2),
            'shares': shares,
            'total_invested': round(price * shares, 2),
            'trend_vs_market': trend_vs_market
        })

    return trade_plans

# --- STREAMLIT UI ---
if check_password():
    st.title('Mayo Stock Screener & Trade Planner')

    investment_amount = st.number_input('Enter Investment Amount ($):', min_value=10.0, value=50000.0, step=1000.0)
    formatted_investment = "{:,}".format(investment_amount)
    st.write(f"Investment Amount: ${formatted_investment}")

    tickers_input = st.text_input('Enter tickers separated by commas (e.g. AAPL,MSFT,NVDA):')

    if st.button('Run Screener'):
        tickers = [ticker.strip().upper() for ticker in tickers_input.split(',') if ticker.strip()]

        trade_plans = run_screener(investment_amount, tickers)

        if not trade_plans:
            st.error("No qualifying stocks found.")
        else:
            for plan in trade_plans:
                st.subheader(plan['ticker'])
                st.write(plan)
                st.write(f"Stock is trending {plan['trend_vs_market']}")
