# Comprehensive AI-Powered Stock Screener & Trade Advisor with Streamlit Interface - Final Benzinga-Only Version
# Now includes Polygon.io for market data, Benzinga for real-time news and sentiment (if available),
# ATR-based filtering, RVOL, scoring system, market trend comparison, and full trade planning.
# Password-protected access.

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
PERCENT_CHANGE_MIN = 2.0           # Minimum intraday % change since open
PERCENT_CHANGE_MAX = 10.0          # Max % change to avoid overextended stocks
RISK_PERCENTAGE = 0.02             # Risk 2% of capital per trade
MAX_SHARES_PER_TRADE = 2000        # Cap position size per trade
EXCLUDED_TICKERS = ['ALLY']        # Exclude specific tickers
ATR_MIN = 2                        # Minimum acceptable ATR value
ATR_MAX = 5                        # Maximum acceptable ATR value
RVOL_THRESHOLD = 1.5               # Minimum Relative Volume threshold
ATR_MULTIPLIER = 1.5               # ATR Multiplier for stop loss and target calculation

# --- API KEYS ---
POLYGON_API_KEY = st.secrets['Polygon_Key']
BENZINGA_API_KEY = st.secrets['Benzinga_Key']
APP_PASSWORD = st.secrets['APP_PASSWORD']

# --- PASSWORD CHECK ---
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

def get_market_top_gainers():
    """Fetch top market gainers from Polygon.io."""
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={POLYGON_API_KEY}"
    response = requests.get(url).json()
    return [item['ticker'] for item in response.get('tickers', [])]

def get_percent_change(ticker):
    """Safely fetch percent change and current price."""
    try:
        url_trade = f"https://api.polygon.io/v2/last/trade/{ticker}?apiKey={POLYGON_API_KEY}"
        url_prev = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_API_KEY}"

        trade = requests.get(url_trade).json()
        prev = requests.get(url_prev).json()

        current_price = trade.get('last', {}).get('price', 0)
        prev_close = prev.get('results', [{}])[0].get('c', 0)

        if current_price == 0 and prev_close != 0:
            current_price = prev_close  # fallback to previous close if current is 0

        percent_change = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0
        return round(percent_change, 2), round(current_price, 2)

    except Exception as e:
        print(f"Error fetching percent change for {ticker}: {e}")
        return 0, 0



def get_rvol(ticker):
    """Fetch RVOL, safely handle API errors."""
    try:
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/30/2023-01-01/2023-12-31?adjusted=true&sort=desc&limit=30&apiKey={POLYGON_API_KEY}"
        response = requests.get(url)
        data = response.json().get('results', [])
    except Exception as e:
        print(f"Error fetching RVOL for {ticker}: {e}")
        return 0  # fallback if API fails

    if len(data) < 21:
        return 0

    current_vol = data[0]['v']
    avg_vol = sum(day['v'] for day in data[1:21]) / 20

    return round(current_vol / avg_vol, 2) if avg_vol else 0



def get_atr(ticker):
    """Fetch ATR for the ticker with error handling to avoid JSON decode errors."""
    try:
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/30/2023-01-01/2023-12-31?adjusted=true&sort=desc&limit=14&apiKey={POLYGON_API_KEY}"
        response = requests.get(url)
        data = response.json().get('results', [])
    except Exception as e:
        print(f"Error fetching ATR for {ticker}: {e}")
        return 0  # fallback value

    if not data:
        return 0

    df = pd.DataFrame({'High': [d['h'] for d in data], 'Low': [d['l'] for d in data], 'Close': [d['c'] for d in data]})
    atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)

    return round(atr.iloc[-1], 2) if not atr.empty else 0



def get_benzinga_news(ticker):
    """Fetch latest Benzinga news headline and sentiment for the ticker with error handling."""
    try:
        url = f"https://api.benzinga.com/api/v2/news?token={BENZINGA_API_KEY}&symbols={ticker}&channels=stock"
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Benzinga API error for {ticker}: Status Code {response.status_code}")
            return 'No recent Benzinga news.', 0

        data = response.json()
    except Exception as e:
        print(f"Error fetching Benzinga news for {ticker}: {e}")
        return 'No recent Benzinga news.', 0

    news = data.get('news', [])
    if news:
        headline = news[0].get('title', 'No headline')
        sentiment = news[0].get('sentiment', 0)
        return headline, sentiment

    return 'No recent Benzinga news.', 0




def get_market_trend():
    spy, _ = get_percent_change('SPY')
    qqq, _ = get_percent_change('QQQ')
    return (spy + qqq) / 2


def calculate_shares(investment_amount, price, stop_loss):
    risk_amount = investment_amount * RISK_PERCENTAGE
    per_share_risk = price - stop_loss
    if per_share_risk <= 0:
        return 0

    max_shares_by_risk = int(risk_amount // per_share_risk)
    max_shares_by_investment = int(investment_amount // price)

    return min(max_shares_by_risk, max_shares_by_investment, MAX_SHARES_PER_TRADE)


def calculate_score(percent_change, rvol, atr, sentiment):
    score = 0
    if PERCENT_CHANGE_MIN <= percent_change <= PERCENT_CHANGE_MAX:
        score += 2
    if rvol >= RVOL_THRESHOLD:
        score += 2
    if ATR_MIN <= atr <= ATR_MAX:
        score += 2
    if sentiment > 0:
        score += 2
    score += 2  # base score for passing all filters
    return min(score, 10)


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

        benzinga_news, sentiment = get_benzinga_news(ticker)

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
            'benzinga_news': benzinga_news,
            'sentiment': sentiment,
            'stop_loss': round(stop_loss, 2),
            'target': round(target, 2),
            'shares': shares,
            'total_invested': round(current_price * shares, 2),
            'trend_vs_market': trend_vs_market
        })

    return sorted(trade_plans, key=lambda x: (x['score'], x['ATR']), reverse=True)

def get_market_top_gainers():
    """Fetch top market gainers from Polygon.io."""
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={POLYGON_API_KEY}"
    response = requests.get(url).json()
    return [item['ticker'] for item in response.get('tickers', []) if item['ticker'] not in EXCLUDED_TICKERS]


# --- STREAMLIT UI ---
if check_password():
    st.title('Mayo Stock Screener & Trade Planner')

    investment_amount = st.number_input('Enter Investment Amount ($):', min_value=10.0, value=50000.0, step=1000.0)
    formatted_investment = "{:,}".format(investment_amount)
    st.write(f"Investment Amount: ${formatted_investment}")

    mode = st.selectbox('Select Mode:', ['Screen Full Market', 'Top 10 Market Gainers', 'Search Individual Tickers'])

    tickers = []
    if mode == 'Top 10 Market Gainers':
        tickers = get_market_top_gainers()[:10]

    elif mode == 'Search Individual Tickers':
        tickers_input = st.text_input('Enter tickers separated by commas (e.g. AAPL,MSFT,NVDA):')
        if tickers_input:
            tickers = [ticker.strip().upper() for ticker in tickers_input.split(',') if ticker.strip()]

    if st.button('Run Screener') and tickers:
        if mode == 'Screen Full Market':
            trade_plans = run_screener(investment_amount, tickers)
            if not trade_plans:
                st.error("No qualifying stocks found.")
            else:
                for plan in trade_plans:
                    st.subheader(f"{plan['ticker']} (Score: {plan['score']}/10)")
                    st.write(plan)
                    st.write(f"Stock is trending {plan['trend_vs_market']}")

        else:
            for ticker in tickers:
                percent_change, current_price = get_percent_change(ticker)
                rvol = get_rvol(ticker)
                atr = get_atr(ticker)
                benzinga_news, sentiment = get_benzinga_news(ticker)

                st.subheader(f"{ticker} Snapshot")
                st.write({
                    'Price': f\"${current_price:.2f}\",
                    'Percent Change': f\"{percent_change:.2f}%\",
                    'RVOL': rvol,
                    'ATR': atr,
                    'Benzinga News': benzinga_news,
                    'Sentiment': sentiment
                })

