# Comprehensive AI-Powered Stock Screener & Trade Advisor with Streamlit Interface - Full Version with API Integrations, Scaling Logic, and Protective Filters

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
PRICE_MIN = 20                     # Minimum stock price
DYNAMIC_PRICE_MAX = True           # Dynamically set max price based on market data if True
INITIAL_PRICE_MAX = 175            # Max stock price ceiling if DYNAMIC is False
VOLUME_MIN = 2_000_000             # Minimum **intraday volume**, NOT premarket
PERCENT_CHANGE_MIN = 2.0           # Intraday % change since open (NOT Percent Change Up)
PERCENT_CHANGE_MAX = 10.0          # Max % move to avoid overextended stocks
RVOL_THRESHOLD = 1.5               # Relative volume compared to average volume
ATR_MIN = 1                        # Minimum ATR (avoid too stable/flat stocks)
ATR_MAX = 3.5                      # Max ATR (avoid excessive volatility)
market_RANGE_MIN_PERCENT = 1.0     # Minimum intraday price range % to ensure movement
EMA_SHORT = 9                      # For trend confirmation
EMA_LONG = 20                      # For trend confirmation
ATR_MULTIPLIER = 1.5               # For price target bounds over historical highs/lows
RISK_PERCENTAGE = 0.02             # Risk per trade (2% of capital)
MIN_FLOAT = 50_000_000             # Exclude low float stocks (avoid pump/dumps)
MAX_FLOAT = 200_000_000            # Cap float for mid-cap range stocks
RSI_MIN = 40 
RSI_MAX = 70                       # RSI window for 'neutral to bullish' zone
EXCLUDED_TICKERS = ['ALLY']        # Exclude personal or illiquid tickers
MIN_SENTIMENT_SCORE = 0.2          # Optional: ensure positive news/sentiment
MAX_SPREAD_PERCENT = 0.005         # Max bid/ask spread (0.5%) of price
# E.g. $100 stock = max $0.50 spread
EARNINGS_LOOKAHEAD_DAYS = 3        # Filter out stocks with earnings upcoming in X days
MAX_SHARES_PER_TRADE = 2000        # Position sizing cap per trade


def get_market_top_gainers():
    fmp_api = st.secrets['FMP_Key']
    url = f'https://financialmodelingprep.com/api/v3/stock_market/actives?apikey={fmp_api}'
    response = requests.get(url)
    tickers = [item['symbol'] for item in response.json()[:50] if 'symbol' in item and item['symbol'] not in EXCLUDED_TICKERS]
    return tickers

def get_news_sentiment(ticker):
    api_key = st.secrets['NewsAPI_Key']
    url = f'https://newsapi.org/v2/everything?q={ticker}&apiKey={api_key}'
    response = requests.get(url)

    if response.status_code != 200:
        return 0

    articles = response.json().get('articles', [])
    headlines = [article['title'] for article in articles]
    sentiment_scores = [TextBlob(headline).sentiment.polarity for headline in headlines if headline]
    return sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0


def determine_price_max(capital):
    if not DYNAMIC_PRICE_MAX:
        return INITIAL_PRICE_MAX
    scaling_factor = capital * RISK_PERCENTAGE
    return scaling_factor / 5


def calculate_shares(investment_amount, price, stop_loss):
    risk_amount = investment_amount * RISK_PERCENTAGE
    per_share_risk = price - stop_loss
    if per_share_risk <= 0:
        return 0

    max_shares_by_risk = int(risk_amount // per_share_risk)
    max_shares_by_investment = int(investment_amount // price)

    shares = min(max_shares_by_risk, max_shares_by_investment, MAX_SHARES_PER_TRADE)
    return shares



def get_atr(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="14d", interval="1h")
    atr = ta.atr(hist['High'], hist['Low'], hist['Close'], length=14)
    return atr.iloc[-1] if not atr.empty else 1

def get_spread(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    ask = info.get('ask', 0)
    bid = info.get('bid', 0)
    if ask > 0 and bid > 0:
        return (ask - bid) / ((ask + bid) / 2)
    return 0

def get_trade_plan(ticker, price):
    atr = get_atr(ticker)
    stop_loss = price - (ATR_MULTIPLIER * atr)
    target = price + (ATR_MULTIPLIER * atr)
    return price, round(stop_loss, 2), round(target, 2)

def validate_price_target(target_price, historical_high, atr, buffer_multiplier=1.5):
    max_reasonable_price = historical_high + (atr * buffer_multiplier)
    return min(target_price, max_reasonable_price)

def is_within_recent_range(current_price, historical_high, historical_low, atr, buffer_multiplier=1.5):
    upper_bound = historical_high + (atr * buffer_multiplier)
    lower_bound = historical_low - (atr * buffer_multiplier)
    return lower_bound <= current_price <= upper_bound

def get_recent_high_low(price_data, days=5):
    recent_data = price_data[-(days * 78:]  # Adjust periods per day
    highs = [bar['high'] for bar in recent_data]
    lows = [bar['low'] for bar in recent_data]
    return max(highs), min(lows)

def score_stock(row):
    score = 0
    max_score = 10

    
    # Weights total 10
    weights = {
        'market_volume': 1.0,
        'percent_change_up': 1.5,
        'rvol': 1.0,
        'float': 1.0,
        'atr': 1.0,
        'market_range': 1.0,
        'sentiment': 1.5,
        'spread': 1.0,
        'price': 1.0
    }

    # 1. market Volume
    if row['market_volume'] >= MARKET_VOLUME_MIN:
        score += weights['market_volume']

    # 2. Percent Change Up %
    if PERCENT_CHANGE_MIN <= row['percent_change_up'] <= PERCENT_CHANGE_MAX:
        score += weights['percent_change_up']

    # 3. RVOL
    if row['rvol'] >= RVOL_THRESHOLD:
        score += weights['rvol']

    # 4. Float
    if MIN_FLOAT <= row['float'] <= MAX_FLOAT:
        score += weights['float']

    # 5. ATR
    atr = get_atr(row['ticker'])
    if ATR_MIN <= atr <= ATR_MAX:
        score += weights['atr']

    # 6. Market Range %
    if row['market_range_percent'] >= market_RANGE_MIN_PERCENT:
        score += weights['market_range']

    # 7. Sentiment
    sentiment = get_news_sentiment(row['ticker'])
    if sentiment >= MIN_SENTIMENT_SCORE:
        score += weights['sentiment']

    # 8. Spread
    spread = get_spread(row['ticker'])
    if spread <= MAX_SPREAD_PERCENT:
        score += weights['spread']

    # 9. Price
    if PRICE_MIN <= row['price'] <= determine_price_max(investment_amount):
        score += weights['price']

    return round(score, 2)


def get_market_trend():
    spy = yf.Ticker('SPY').history(period='1d', interval='5m')
    qqq = yf.Ticker('QQQ').history(period='1d', interval='5m')

    spy_above_vwap = spy['Close'].iloc[-1] > spy['Close'].mean()
    qqq_above_vwap = qqq['Close'].iloc[-1] > qqq['Close'].mean()

    return spy_above_vwap, qqq_above_vwap


def get_market_data(price_max):
    tickers = get_market_top_gainers()
    data = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d", interval="5m", prepost=True)
            market_volume = hist['Volume'][:30].sum()

            if hist.empty:
                continue

            close_prices = hist['Close'].dropna().tail(5)
            avg_market_price = close_prices.mean()

            if not (PRICE_MIN <= avg_market_price <= price_max):
                continue

            prev_close = stock.history(period='2d')['Close'][-2]
            percent_change_up = ((avg_market_price - prev_close) / prev_close) * 100
            rvol = market_volume / (stock.info['averageVolume'] or 1)

            market_range_percent = ((hist['High'].max() - hist['Low'].min()) / prev_close) * 100

            data.append({
                'ticker': ticker,
                'price': avg_market_price,
                'market_volume': market_volume,
                'percent_change_up': percent_change_up,
                'rvol': rvol,
                'float': stock.info.get('sharesOutstanding', 1),
                'sector': stock.info.get('sector', 'Unknown'),
                'market_range_percent': market_range_percent,
            })
        except Exception:
            continue
    return pd.DataFrame(data)

def run_screener(investment_amount):
    price_max = determine_price_max(investment_amount)
    data = get_market_data(price_max)
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

st.write(f'Investment Amount Entered: ${investment_amount:,.2f}')


if st.button('Run Screener'):
    spy_trend, qqq_trend = get_market_trend()

    trade_plans = run_screener(investment_amount)
    if not trade_plans:
        st.error("No qualifying stocks found.")
    for plan in trade_plans:
        st.subheader(plan['ticker'])
        st.write(f"Score: {plan['score']}/10")
        st.write(f"Entry Price: ${plan['entry']:,}")
        st.write(f"Stop Loss: ${plan['stop_loss']:,}")
        st.write(f"Target Price: ${plan['target']:,}")
        st.write(f"Suggested Shares to Buy: {plan['shares']:,}")
        st.write(f"Total Investment: ${plan['total_invested']:,}")
        st.write(f"Potential Profit: ${plan['potential_profit']:,}")
        st.write(f"Potential Loss: ${plan['potential_loss']:,}")

        if spy_trend and qqq_trend:
            st.write("Trending WITH the Market")
        elif not spy_trend:
            st.write("Trending LOWER than the Market")
        else:
            st.write("Trending ABOVE the Market")
