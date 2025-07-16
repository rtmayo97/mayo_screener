# Comprehensive AI-Powered Stock Screener & Trade Advisor with Streamlit Interface - Enhanced with Protective Filters

import sys
import requests
import pandas as pd
from datetime import datetime
import pandas_ta as ta
import yfinance as yf
from textblob import TextBlob
import streamlit as st
import os
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATIONS ---
PRICE_MIN = 20
PRICE_MAX = 175
PREMARKET_VOLUME_MIN = 1000000
GAP_UP_MIN = 2.0
GAP_UP_MAX = 10.0
RVOL_THRESHOLD = 1.5
ATR_MIN = 1
ATR_MAX = 3
PREMARKET_RANGE_MIN = 0.5
EMA_SHORT = 9
EMA_LONG = 20
ATR_MULTIPLIER = 1.5
RISK_PERCENTAGE = 0.02
MIN_FLOAT = 50_000_000
RSI_MIN, RSI_MAX = 40, 70
EXCLUDED_TICKERS = ['ALLY']

# --- FUNCTIONS ---
def get_premarket_top_gainers():
    fmp_api = st.secrets["FMP_Key"]
    url = f'https://financialmodelingprep.com/api/v3/stock_market/actives?apikey={fmp_api}'
    response = requests.get(url)
    tickers = [item['symbol'] for item in response.json()[:50] if 'symbol' in item and item['symbol'] not in EXCLUDED_TICKERS]
    return tickers


def get_premarket_data():
    tickers = get_premarket_top_gainers()
    data = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d", interval="5m", prepost=True)
            premarket_volume = hist['Volume'][:30].sum()

            if hist.empty:
                continue

            close_prices = hist['Close'].dropna().tail(5)
            avg_premarket_price = close_prices.mean()

            if not (PRICE_MIN <= avg_premarket_price <= PRICE_MAX):
                continue

            prev_close = stock.history(period='2d')['Close'][-2]
            gap_up = ((avg_premarket_price - prev_close) / prev_close) * 100
            rvol = premarket_volume / (stock.info['averageVolume'] or 1)

            premarket_range = hist['High'].max() - hist['Low'].min()

            data.append({
                'ticker': ticker,
                'price': avg_premarket_price,
                'premarket_volume': premarket_volume,
                'gap_up': gap_up,
                'rvol': rvol,
                'float': stock.info.get('sharesOutstanding', 1),
                'sector': stock.info.get('sector', 'Unknown'),
                'premarket_range': premarket_range,
            })
        except Exception:
            continue
    return pd.DataFrame(data)


def get_news_sentiment(ticker):
    api_key = st.secrets["NewsAPI_Key"]
    url = f'https://newsapi.org/v2/everything?q={ticker}&apiKey={api_key}'
    response = requests.get(url)

    if response.status_code != 200:
        return 0

    articles = response.json().get('articles', [])
    headlines = [article['title'] for article in articles]
    sentiment_scores = [TextBlob(headline).sentiment.polarity for headline in headlines if headline]
    return sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0


def get_atr(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="14d", interval="1h")
    atr = ta.atr(hist['High'], hist['Low'], hist['Close'], length=14)
    return atr.iloc[-1] if not atr.empty else 1


def get_ema_signals(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="10d", interval="15m")
    if hist.empty:
        return False

    ema_short = ta.ema(hist['Close'], length=EMA_SHORT).iloc[-1]
    ema_long = ta.ema(hist['Close'], length=EMA_LONG).iloc[-1]

    return ema_short > ema_long


def get_rsi(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="10d", interval="15m")
    rsi = ta.rsi(hist['Close'], length=14)
    return rsi.iloc[-1] if not rsi.empty else 50


def score_stock(row):
    score = 0
    if row['premarket_volume'] >= PREMARKET_VOLUME_MIN:
        score += 1
    if GAP_UP_MIN <= row['gap_up'] <= GAP_UP_MAX:
        score += 1
    if row['rvol'] >= RVOL_THRESHOLD:
        score += 1
    if row['float'] >= MIN_FLOAT:
        score += 1
    if ATR_MIN <= get_atr(row['ticker']) <= ATR_MAX:
        score += 1
    if row['premarket_range'] >= PREMARKET_RANGE_MIN:
        score += 1
    if get_ema_signals(row['ticker']):
        score += 1
    rsi = get_rsi(row['ticker'])
    if RSI_MIN <= rsi <= RSI_MAX:
        score += 1
    if get_news_sentiment(row['ticker']) >= 0:
        score += 1

    return score


def get_trade_plan(ticker, price):
    atr = get_atr(ticker)
    stop_loss = price - (ATR_MULTIPLIER * atr)
    target = price + (ATR_MULTIPLIER * atr)
    return price, round(stop_loss, 2), round(target, 2)


def calculate_shares(investment_amount, price, stop_loss):
    risk_amount = investment_amount * RISK_PERCENTAGE
    per_share_risk = price - stop_loss
    return int(risk_amount // per_share_risk) if per_share_risk > 0 else 0


def run_screener(investment_amount):
    data = get_premarket_data()
    if data.empty:
        return []

    data['score'] = data.apply(score_stock, axis=1)
    data = data.sort_values('score', ascending=False).head(10)

    plans = []
    for _, row in data.iterrows():
        entry, stop, target = get_trade_plan(row['ticker'], row['price'])
        shares = calculate_shares(investment_amount, entry, stop)
        total_invested = shares * entry
        potential_profit = shares * (target - entry)
        potential_loss = shares * (entry - stop)

        plans.append({
            'ticker': row['ticker'],
            'score': row['score'],
            'entry': round(entry, 2),
            'stop_loss': stop,
            'target': target,
            'shares': shares,
            'total_invested': round(total_invested, 2),
            'potential_profit': round(potential_profit, 2),
            'potential_loss': round(potential_loss, 2)
        })
    return plans


# --- STREAMLIT INTERFACE ---
st.title('Mayo Stock Screener & Trade Planner')

investment_amount = st.number_input('Enter Investment Amount ($):', min_value=10.0, value=1000.0, step=100.0)

if st.button('Run Screener'):
    trade_plans = run_screener(investment_amount)
    if not trade_plans:
        st.error("No qualifying stocks found.")
    for plan in trade_plans:
        st.subheader(plan['ticker'])
        st.write(f"Score: {plan['score']}")
        st.write(f"Entry Price: ${plan['entry']}")
        st.write(f"Stop Loss: ${plan['stop_loss']}")
        st.write(f"Target Price: ${plan['target']}")
        st.write(f"Suggested Shares to Buy: {plan['shares']}")
        st.write(f"Total Investment: ${plan['total_invested']}")
        st.write(f"Potential Profit: ${plan['potential_profit']}")
        st.write(f"Potential Loss: ${plan['potential_loss']}")
