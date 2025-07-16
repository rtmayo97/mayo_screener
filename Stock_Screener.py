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

# --- CONFIGURATIONS ---
PRICE_MIN = 20
PRICE_MAX = 175
PREMARKET_VOLUME_MIN = 1000000
GAP_UP_MIN = 2.0
GAP_UP_MAX = 10.0
RVOL_THRESHOLD = 1.5
ATR_MIN = 1
ATR_MAX = 3
PREMARKET_RANGE_MIN_PERCENT = 1.0
EMA_SHORT = 9
EMA_LONG = 20
ATR_MULTIPLIER = 1.5
RISK_PERCENTAGE = 0.02
MIN_FLOAT = 50_000_000
MAX_FLOAT = 200_000_000
RSI_MIN, RSI_MAX = 40, 70
EXCLUDED_TICKERS = ['ALLY']
MIN_SENTIMENT_SCORE = 0.2
MAX_SPREAD_PERCENT = 0.005  # 0.5%
EARNINGS_LOOKAHEAD_DAYS = 3

# --- FUNCTIONS ---
def get_vwap_status(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period='1d', interval='5m')
    if hist.empty:
        return False
    vwap = hist['Close'].mean()
    current_price = hist['Close'].iloc[-1]
    return current_price > vwap


def get_spread(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    ask = info.get('ask', 0)
    bid = info.get('bid', 0)
    if ask > 0 and bid > 0:
        return (ask - bid) / ((ask + bid) / 2)
    return 0


def get_market_trend():
    spy = yf.Ticker('SPY').history(period='1d', interval='5m')
    qqq = yf.Ticker('QQQ').history(period='1d', interval='5m')

    spy_above_vwap = spy['Close'].iloc[-1] > spy['Close'].mean()
    qqq_above_vwap = qqq['Close'].iloc[-1] > qqq['Close'].mean()

    return spy_above_vwap, qqq_above_vwap


def get_earnings_date(ticker):
    stock = yf.Ticker(ticker)
    cal = stock.calendar
    if 'Earnings Date' in cal.index:
        earnings_date = cal.loc['Earnings Date'][0]
        if isinstance(earnings_date, pd.Timestamp):
            days_until_earnings = (earnings_date - datetime.now()).days
            return days_until_earnings
    return None


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

            premarket_range_percent = ((hist['High'].max() - hist['Low'].min()) / prev_close) * 100

            days_until_earnings = get_earnings_date(ticker)
            if days_until_earnings is not None and days_until_earnings <= EARNINGS_LOOKAHEAD_DAYS:
                continue

            data.append({
                'ticker': ticker,
                'price': avg_premarket_price,
                'premarket_volume': premarket_volume,
                'gap_up': gap_up,
                'rvol': rvol,
                'float': stock.info.get('sharesOutstanding', 1),
                'sector': stock.info.get('sector', 'Unknown'),
                'premarket_range_percent': premarket_range_percent,
                'spread_percent': get_spread(ticker),
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


def get_trade_plan(ticker, price):
    atr = get_atr(ticker)
    stop_loss = price - (ATR_MULTIPLIER * atr)
    target = price + (ATR_MULTIPLIER * atr)
    return price, round(stop_loss, 2), round(target, 2)


def get_atr(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="14d", interval="1h")
    atr = ta.atr(hist['High'], hist['Low'], hist['Close'], length=14)
    return atr.iloc[-1] if not atr.empty else 1


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
            'potential_loss': round(potential_loss, 2),
            'vwap_status': get_vwap_status(row['ticker'])
        })
    return plans


# --- STREAMLIT INTERFACE ---
st.title('Mayo Stock Screener & Trade Planner')

investment_amount = st.number_input('Enter Investment Amount ($):', min_value=10.0, value=1000.0, step=100.0, format="%0.2f")

if st.button('Run Screener'):
    spy_trend, qqq_trend = get_market_trend()
    st.write(f"SPY Above VWAP: {'Yes' if spy_trend else 'No'}")
    st.write(f"QQQ Above VWAP: {'Yes' if qqq_trend else 'No'}")

    trade_plans = run_screener(investment_amount)
    if not trade_plans:
        st.error("No qualifying stocks found.")
    for plan in trade_plans:
        st.subheader(plan['ticker'])
        st.write(f"Score: {plan['score']}")
        st.write(f"Entry Price: ${plan['entry']:,}")
        st.write(f"Stop Loss: ${plan['stop_loss']:,}")
        st.write(f"Target Price: ${plan['target']:,}")
        st.write(f"Suggested Shares to Buy: {plan['shares']:,}")
        st.write(f"Total Investment: ${plan['total_invested']:,}")
        st.write(f"Potential Profit: ${plan['potential_profit']:,}")
        st.write(f"Potential Loss: ${plan['potential_loss']:,}")

        if spy_trend and qqq_trend and plan['vwap_status']:
            st.write("Trending WITH the Market")
        elif not spy_trend and not qqq_trend and plan['vwap_status']:
            st.write("Trending ABOVE the Market")
        else:
            st.write("Trending AGAINST the Market")
