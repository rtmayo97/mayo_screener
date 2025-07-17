# Comprehensive AI-Powered Stock Screener & Trade Advisor with Streamlit Interface - Full Version with API Integrations, Scaling Logic, and Protective Filters
# Enhanced with Polygon.io for market data, Benzinga for real-time news, StockTwits for social sentiment,
# ATR-based filtering, RVOL, scoring system, market trend comparison, and full trade planning.
# Includes a simple password protection gate for secure access.

import sys
import requests
import pandas as pd
from datetime import datetime
import streamlit as st
import os
import pandas_ta as ta

# --- CONFIGURATIONS ---
PRICE_MIN = 20                     # Minimum stock price to scan
INITIAL_PRICE_MAX = 175            # Default max price ceiling
VOLUME_MIN = 2_000_000             # Minimum intraday volume
PERCENT_CHANGE_MIN = 2.0           # Minimum intraday % change since open
PERCENT_CHANGE_MAX = 10.0          # Max % change to avoid overextended stocks
RISK_PERCENTAGE = 0.02             # Risk 2% of capital per trade
MAX_SHARES_PER_TRADE = 2000        # Cap position size per trade
MIN_SENTIMENT_SCORE = 0.2          # Sentiment score threshold
EXCLUDED_TICKERS = ['ALLY']        # Exclude specific tickers
ATR_MIN = 2                        # Minimum acceptable ATR value
ATR_MAX = 5                        # Maximum acceptable ATR value
RVOL_THRESHOLD = 1.5               # Minimum Relative Volume threshold
ATR_MULTIPLIER = 1.5               # ATR Multiplier for stop loss and target calculation

# --- API KEYS ---
POLYGON_API_KEY = st.secrets['Polygon_Key']
FINNHUB_API_KEY = st.secrets['Finnhub_Key']
BENZINGA_API_KEY = st.secrets['Benzinga_Key']
STOCKTWITS_CLIENT_ID = st.secrets['StockTwits_Key']
APP_PASSWORD = st.secrets['APP_PASSWORD']

# --- SIMPLE PASSWORD CHECK ---
# (unchanged password check function)

# --- CORE FUNCTIONS ---
# (unchanged price/percent change, RVOL, ATR, news sentiment, market trend, shares calculation, score calculation)


def get_benzinga_news(ticker):
    """Fetch latest Benzinga news headline for the ticker."""
    url = f"https://api.benzinga.com/api/v2/news?token={BENZINGA_API_KEY}&symbols={ticker}&channels=stock"
    response = requests.get(url).json()
    news = response.get('news', [])
    if news:
        return news[0].get('title', 'No headline')
    return 'No recent Benzinga news.'


def get_stocktwits_sentiment(ticker):
    """Fetch social sentiment from StockTwits."""
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
    response = requests.get(url).json()
    messages = response.get('messages', [])
    return len(messages)


def run_screener(investment_amount, tickers):
    trade_plans = []
    market_trend = get_market_trend()

    for ticker in tickers:
        if ticker in EXCLUDED_TICKERS:
            continue

        percent_change, current_price = get_percent_change(ticker)
        if percent_change < PERCENT_CHANGE_MIN or percent_change > PERCENT_CHANGE_MAX:
            continue

        rvol = get_rvol(ticker)
        if rvol < RVOL_THRESHOLD:
            continue

        atr = get_atr(ticker)
        if atr < ATR_MIN or atr > ATR_MAX:
            continue

        sentiment = get_news_sentiment(ticker)
        if sentiment < MIN_SENTIMENT_SCORE:
            continue

        benzinga_news = get_benzinga_news(ticker)
        stocktwits_activity = get_stocktwits_sentiment(ticker)

        stop_loss = current_price - (ATR_MULTIPLIER * atr)
        target = current_price + (ATR_MULTIPLIER * atr)
        shares = calculate_shares(investment_amount, current_price, stop_loss)

        if shares == 0:
            continue

        trend_vs_market = "WITH the market"
        if percent_change > market_trend:
            trend_vs_market = "HIGHER than the market"
        elif percent_change < market_trend:
            trend_vs_market = "LOWER than the market"

        score = calculate_score(percent_change, rvol, atr, sentiment)

        trade_plans.append({
            'ticker': ticker,
            'score': score,
            'price': current_price,
            'percent_change': percent_change,
            'RVOL': rvol,
            'ATR': atr,
            'sentiment': sentiment,
            'benzinga_news': benzinga_news,
            'stocktwits_activity': stocktwits_activity,
            'stop_loss': round(stop_loss, 2),
            'target': round(target, 2),
            'shares': shares,
            'total_invested': round(current_price * shares, 2),
            'trend_vs_market': trend_vs_market
        })

    return sorted(trade_plans, key=lambda x: (x['score'], x['ATR']), reverse=True)


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
                st.subheader(f"{plan['ticker']} (Score: {plan['score']}/10)")
                st.write(plan)
                st.write(f"Stock is trending {plan['trend_vs_market']}")
