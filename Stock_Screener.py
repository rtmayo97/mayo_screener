# Comprehensive AI-Powered Stock Screener & Trade Advisor with Streamlit Interface - Full Version with API Integrations, Scaling Logic, and Protective Filters
# Now enhanced to use Polygon.io for real-time price/volume and Finnhub for news/sentiment analysis
# Also includes a simple password protection gate for secure access

import sys
import requests
import pandas as pd
from datetime import datetime
import streamlit as st
import os

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

def get_realtime_price_volume(ticker):
    """Fetch real-time price and volume from Polygon.io."""
    url = f"https://api.polygon.io/v2/last/trade/{ticker}?apiKey={POLYGON_API_KEY}"
    response = requests.get(url).json()

    price = response.get('last', {}).get('price', 0)
    volume = response.get('last', {}).get('size', 0)
    return price, volume


def get_previous_close(ticker):
    """Fetch previous close price from Polygon.io."""
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_API_KEY}"
    response = requests.get(url).json()
    return response.get('results', [{}])[0].get('c', 0)


def get_news_sentiment(ticker):
    """Fetch news sentiment from Finnhub API."""
    url = f"https://finnhub.io/api/v1/news-sentiment?symbol={ticker}&token={FINNHUB_API_KEY}"
    response = requests.get(url).json()

    sentiment_score = response.get('sentiment', {}).get('score', 0)
    return sentiment_score


def calculate_percent_change(current_price, previous_close):
    """Calculate percent change between current price and previous close."""
    if previous_close == 0:
        return 0
    return ((current_price - previous_close) / previous_close) * 100


def calculate_shares(investment_amount, price, stop_loss):
    """Calculate the number of shares to buy based on risk tolerance."""
    risk_amount = investment_amount * RISK_PERCENTAGE
    per_share_risk = price - stop_loss
    if per_share_risk <= 0:
        return 0

    max_shares_by_risk = int(risk_amount // per_share_risk)
    max_shares_by_investment = int(investment_amount // price)

    return min(max_shares_by_risk, max_shares_by_investment, MAX_SHARES_PER_TRADE)


def get_market_trend():
    """Determine market trend using SPY and QQQ prices via Polygon.io."""
    spy_price, _ = get_realtime_price_volume('SPY')
    qqq_price, _ = get_realtime_price_volume('QQQ')
    spy_prev = get_previous_close('SPY')
    qqq_prev = get_previous_close('QQQ')

    spy_trend = calculate_percent_change(spy_price, spy_prev)
    qqq_trend = calculate_percent_change(qqq_price, qqq_prev)

    return spy_trend, qqq_trend


def run_screener(investment_amount, tickers):
    """Run the screener logic across a list of tickers using real-time data."""
    trade_plans = []
    spy_trend, qqq_trend = get_market_trend()
    market_avg_trend = (spy_trend + qqq_trend) / 2

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

        stop_loss = price * 0.98  # Example 2% stop loss below price
        target = price * 1.05     # Example 5% target above price

        shares = calculate_shares(investment_amount, price, stop_loss)
        if shares == 0:
            continue

        trend_vs_market = "WITH the market"
        if percent_change > market_avg_trend:
            trend_vs_market = "HIGHER than the market"
        elif percent_change < market_avg_trend:
            trend_vs_market = "LOWER than the market"

        trade_plans.append({
            'ticker': ticker,
            'price': price,
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
