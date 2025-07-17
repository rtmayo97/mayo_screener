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
PRICE_MIN = 20                     # Minimum stock price to scan
DYNAMIC_PRICE_MAX = True           # Enable dynamic price ceiling based on capital
INITIAL_PRICE_MAX = 175            # Default max price if dynamic is off
VOLUME_MIN = 2_000_000             # Minimum intraday volume
PERCENT_CHANGE_MIN = 2.0           # Minimum intraday % change since open
PERCENT_CHANGE_MAX = 10.0          # Max % change to avoid overextended stocks
RVOL_THRESHOLD = 1.5               # Minimum Relative Volume threshold
ATR_MIN = 1                        # Minimum ATR to ensure volatility
ATR_MAX = 3.5                      # Max ATR to avoid overly volatile stocks
market_RANGE_MIN_PERCENT = 1.0     # Minimum intraday price range percent
ATR_MULTIPLIER = 1.5               # Multiplier to calculate stop loss & target
RISK_PERCENTAGE = 0.02             # Risk 2% of capital per trade
MIN_FLOAT = 50_000_000             # Exclude micro/low float stocks
MAX_FLOAT = 200_000_000            # Cap float for mid-caps
MAX_SPREAD_PERCENT = 0.005         # Max bid/ask spread as percent of price
MAX_SHARES_PER_TRADE = 2000        # Cap position size per trade
MARKET_VOLUME_MIN = 2_000_000      # Market volume threshold
MIN_SENTIMENT_SCORE = 0.2          # Positive sentiment threshold
EXCLUDED_TICKERS = ['ALLY']        # Exclude specific tickers

# --- CORE FUNCTIONS ---

def determine_price_max(capital):
    """Determine the maximum stock price based on available capital and risk percentage."""
    if not DYNAMIC_PRICE_MAX:
        return INITIAL_PRICE_MAX
    scaling_factor = capital * RISK_PERCENTAGE
    return scaling_factor / 5


def get_atr(ticker):
    """Calculate the Average True Range (ATR) to measure volatility."""
    stock = yf.Ticker(ticker)
    hist = stock.history(period="14d", interval="1h")
    atr = ta.atr(hist['High'], hist['Low'], hist['Close'], length=14)
    return atr.iloc[-1] if not atr.empty else 1


def get_spread(ticker):
    """Calculate the bid/ask spread as a percent of price."""
    stock = yf.Ticker(ticker)
    info = stock.info
    ask = info.get('ask', 0)
    bid = info.get('bid', 0)
    if ask > 0 and bid > 0:
        return (ask - bid) / ((ask + bid) / 2)
    return 1


def get_news_sentiment(ticker):
    """Analyze sentiment from news headlines."""
    api_key = st.secrets['NewsAPI_Key']
    url = f'https://newsapi.org/v2/everything?q={ticker}&apiKey={api_key}'
    response = requests.get(url)

    if response.status_code != 200:
        return 0

    articles = response.json().get('articles', [])
    headlines = [article['title'] for article in articles]
    sentiment_scores = [TextBlob(headline).sentiment.polarity for headline in headlines if headline]
    return sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0


def get_recent_high_low(price_data, days=5):
    """Retrieve the recent high and low prices over the past N days."""
    recent_data = price_data[-(days * 78):]
    highs = recent_data['High']
    lows = recent_data['Low']
    return highs.max(), lows.min()


def is_within_recent_range(current_price, historical_high, historical_low, atr, buffer_multiplier=1.5):
    upper_bound = historical_high + (atr * buffer_multiplier)
    lower_bound = historical_low - (atr * buffer_multiplier)
    return lower_bound <= current_price <= upper_bound


def validate_price_target(target_price, historical_high, atr, buffer_multiplier=1.5):
    max_reasonable_price = historical_high + (atr * buffer_multiplier)
    return min(target_price, max_reasonable_price)


def get_trade_plan(ticker, price):
    """Generate entry, stop loss, and target prices with historical validation."""
    atr = get_atr(ticker)
    stop_loss = price - (ATR_MULTIPLIER * atr)
    target = price + (ATR_MULTIPLIER * atr)

    stock = yf.Ticker(ticker)
    hist = stock.history(period="5d", interval="5m")
    if not hist.empty:
        recent_high, recent_low = get_recent_high_low(hist)
        target = validate_price_target(target, recent_high, atr)
    return price, round(stop_loss, 2), round(target, 2)


def calculate_shares(investment_amount, price, stop_loss):
    """Calculate the number of shares to buy based on risk tolerance."""
    risk_amount = investment_amount * RISK_PERCENTAGE
    per_share_risk = price - stop_loss
    if per_share_risk <= 0:
        return 0

    max_shares_by_risk = int(risk_amount // per_share_risk)
    max_shares_by_investment = int(investment_amount // price)

    return min(max_shares_by_risk, max_shares_by_investment, MAX_SHARES_PER_TRADE)


def score_stock(row, investment_amount):
    """Score a stock based on multiple technical and sentiment criteria."""
    score = 0
    weights = {'market_volume': 1.0, 'percent_change': 1.5, 'rvol': 1.0, 'float': 1.0, 'atr': 1.0,
               'market_range': 1.0, 'sentiment': 1.5, 'spread': 1.0, 'price': 1.0}

    if row['market_volume'] >= MARKET_VOLUME_MIN:
        score += weights['market_volume']

    if PERCENT_CHANGE_MIN <= row['percent_change'] <= PERCENT_CHANGE_MAX:
        score += weights['percent_change']

    if row['rvol'] >= RVOL_THRESHOLD:
        score += weights['rvol']

    if MIN_FLOAT <= row['float'] <= MAX_FLOAT:
        score += weights['float']

    atr = get_atr(row['ticker'])
    if ATR_MIN <= atr <= ATR_MAX:
        score += weights['atr']

    if row['market_range_percent'] >= market_RANGE_MIN_PERCENT:
        score += weights['market_range']

    sentiment = get_news_sentiment(row['ticker'])
    if sentiment >= MIN_SENTIMENT_SCORE:
        score += weights['sentiment']

    spread = get_spread(row['ticker'])
    if spread <= MAX_SPREAD_PERCENT:
        score += weights['spread']

    if PRICE_MIN <= row['price'] <= determine_price_max(investment_amount):
        score += weights['price']

    return round(score, 2)


def get_market_top_gainers():
    """Fetch the top active gainers from the market."""
    fmp_api = st.secrets['FMP_Key']
    url = f'https://financialmodelingprep.com/api/v3/stock_market/actives?apikey={fmp_api}'
    response = requests.get(url)
    return [item['symbol'] for item in response.json()[:50] if 'symbol' in item and item['symbol'] not in EXCLUDED_TICKERS]


def get_market_data(price_max):
    """Compile real-time data for scoring from top gainers."""
    tickers = get_market_top_gainers()
    data = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d", interval="5m", prepost=False)  # prepost=False for market hours only
            if hist.empty:
                continue

            open_price = hist['Open'].iloc[0]
            current_price = hist['Close'].iloc[-1]
            percent_change = ((current_price - open_price) / open_price) * 100
            rvol = hist['Volume'].sum() / (stock.info.get('averageVolume', 1))
            market_range_percent = ((hist['High'].max() - hist['Low'].min()) / open_price) * 100

            if not (PRICE_MIN <= current_price <= price_max):
                continue

            data.append({'ticker': ticker, 'price': current_price, 'market_volume': hist['Volume'].sum(),
                         'percent_change': percent_change, 'rvol': rvol, 'float': stock.info.get('sharesOutstanding', 1),
                         'market_range_percent': market_range_percent})
        except Exception:
            continue
    return pd.DataFrame(data)


def get_market_trend():
    """Determine the trend of the SPY and QQQ indices."""
    spy = yf.Ticker('SPY').history(period='1d', interval='5m')
    qqq = yf.Ticker('QQQ').history(period='1d', interval='5m')

    spy_above_vwap = spy['Close'].iloc[-1] > spy['Close'].mean()
    qqq_above_vwap = qqq['Close'].iloc[-1] > qqq['Close'].mean()

    return spy_above_vwap, qqq_above_vwap


def run_screener(investment_amount):
    """Run the complete screener and generate trade plans."""
    price_max = determine_price_max(investment_amount)
    data = get_market_data(price_max)
    if data.empty:
        return []

    data['score'] = data.apply(lambda row: score_stock(row, investment_amount), axis=1)
    data = data.sort_values('score', ascending=False).head(10)

    plans = []
    for _, row in data.iterrows():
        entry, stop, target = get_trade_plan(row['ticker'], row['price'])
        shares = calculate_shares(investment_amount, entry, stop)
        plans.append({'ticker': row['ticker'], 'score': row['score'], 'entry': entry, 'stop_loss': stop,
                      'target': target, 'shares': shares,
                      'total_invested': shares * entry,
                      'potential_profit': shares * (target - entry),
                      'potential_loss': shares * (entry - stop)})
    return plans


# --- STREAMLIT INTERFACE ---
st.title('Mayo Stock Screener & Trade Planner')

investment_amount = st.number_input('Enter Investment Amount ($):', min_value=10.0, value=50000.0, step=1000.0)

if st.button('Run Screener'):
    spy_trend, qqq_trend = get_market_trend()
    trade_plans = run_screener(investment_amount)

    if not trade_plans:
        st.error("No qualifying stocks found.")
    else:
        for plan in trade_plans:
            st.subheader(plan['ticker'])
            st.write(plan)

            # Determine stock trend relative to market
            if spy_trend and qqq_trend:
                st.write("Stock is trending WITH the market")
            elif not spy_trend and not qqq_trend:
                st.write("Stock is trending LOWER than the market")
            else:
                st.write("Stock is trending HIGHER than the market")
