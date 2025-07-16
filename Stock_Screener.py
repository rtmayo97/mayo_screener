# Comprehensive AI-Powered Stock Screener & Trade Advisor with Streamlit Interface - Enhanced with Protective Filters and Scaling Logic

import sys
import requests
import pandas as pd
from datetime import datetime
import pandas_ta as ta
import yfinance as yf
from textblob import TextBlob
import streamlit as st
import os

load_dotenv()

# --- CONFIGURATIONS ---
PRICE_MIN = 20
DYNAMIC_PRICE_MAX = True  # Enable scaling of PRICE_MAX based on capital
INITIAL_PRICE_MAX = 175
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
MAX_SPREAD_PERCENT = 0.005
EARNINGS_LOOKAHEAD_DAYS = 3
MAX_SHARES_PER_TRADE = 2000  # Limit share count to reduce slippage


def determine_price_max(capital):
    if not DYNAMIC_PRICE_MAX:
        return INITIAL_PRICE_MAX
    scaling_factor = capital * RISK_PERCENTAGE
    return scaling_factor / 5  # Target up to 5 shares at max price


def calculate_shares(investment_amount, price, stop_loss):
    risk_amount = investment_amount * RISK_PERCENTAGE
    per_share_risk = price - stop_loss
    if per_share_risk <= 0:
        return 0
    shares = int(risk_amount // per_share_risk)
    return min(shares, MAX_SHARES_PER_TRADE)


def get_premarket_data(price_max):
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

            if not (PRICE_MIN <= avg_premarket_price <= price_max):
                continue

            prev_close = stock.history(period='2d')['Close'][-2]
            gap_up = ((avg_premarket_price - prev_close) / prev_close) * 100
            rvol = premarket_volume / (stock.info['averageVolume'] or 1)

            premarket_range_percent = ((hist['High'].max() - hist['Low'].min()) / prev_close) * 100

            data.append({
                'ticker': ticker,
                'price': avg_premarket_price,
                'premarket_volume': premarket_volume,
                'gap_up': gap_up,
                'rvol': rvol,
                'float': stock.info.get('sharesOutstanding', 1),
                'sector': stock.info.get('sector', 'Unknown'),
                'premarket_range_percent': premarket_range_percent,
            })
        except Exception:
            continue
    return pd.DataFrame(data)


st.title('Mayo Stock Screener & Trade Planner')
investment_amount = st.number_input('Enter Investment Amount ($):', min_value=10.0, value=1000.0, step=100.0)
st.write(f'Investment Amount Entered: ${investment_amount:,.2f}')



def run_screener(investment_amount):
    price_max = determine_price_max(investment_amount)
    data = get_premarket_data(price_max)
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

def get_market_trend():
    spy = yf.Ticker('SPY').history(period='1d', interval='5m')
    qqq = yf.Ticker('QQQ').history(period='1d', interval='5m')

    spy_above_vwap = spy['Close'].iloc[-1] > spy['Close'].mean()
    qqq_above_vwap = qqq['Close'].iloc[-1] > qqq['Close'].mean()

    return spy_above_vwap, qqq_above_vwap


# Add to your existing STREAMLIT interface:

if st.button('Run Screener'):
    spy_trend, qqq_trend = get_market_trend()
    st.write(f"SPY Above VWAP: {'Yes' if spy_trend else 'No'}")
    st.write(f"QQQ Above VWAP: {'Yes' if qqq_trend else 'No'}")

    trade_plans = run_screener(investment_amount)
    if not trade_plans:
        st.error("No qualifying stocks found.")
    for plan in trade_plans:
        st.subheader(plan['ticker'])
        st.write(f"Entry Price: ${plan['entry']:,}")
        st.write(f"Stop Loss: ${plan['stop_loss']:,}")
        st.write(f"Target Price: ${plan['target']:,}")
        st.write(f"Suggested Shares to Buy: {plan['shares']:,}")
        st.write(f"Total Investment: ${plan['total_invested']:,}")
        st.write(f"Potential Profit: ${plan['potential_profit']:,}")
        st.write(f"Potential Loss: ${plan['potential_loss']:,}")

        if spy_trend and qqq_trend:
            st.write("Trending WITH the Market")
        elif not spy_trend and plan['vwap_status']:
            st.write("Trending ABOVE the Market")
        else:
            st.write("Trending AGAINST the Market")
