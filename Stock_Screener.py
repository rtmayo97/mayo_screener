# scalping_screener_app.py
# Streamlit app to scan and rank top 10 scalping candidates using Polygon.io API

import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import numpy as np

# --- PAGE SETUP ---
st.set_page_config(page_title="Top 10 Scalping Screener", layout="wide")
st.title("🚀 Real-Time Scalping Screener (Top 10 Picks)")

# --- SECRETS ---
POLYGON_API_KEY = st.secrets["Polygon_Key"]

# --- MODE TOGGLE ---
use_live_data = st.toggle("Use Live Market Data", value=False)

# --- SNAPSHOT FETCH ---
@st.cache_data(ttl=60)
def get_polygon_snapshot():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?apiKey={POLYGON_API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        return data['tickers']
    except Exception as e:
        st.error(f"Error fetching data from Polygon.io: {e}")
        return []

# --- HISTORICAL DATA FETCH ---
def get_5min_data(ticker):
    to_date = datetime.utcnow()
    from_date = to_date - timedelta(days=2)
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/5/minute/{from_date.date()}/{to_date.date()}?adjusted=true&sort=desc&limit=1000&apiKey={POLYGON_API_KEY}"
    try:
        response = requests.get(url)
        bars = response.json().get("results", [])
        if not bars:
            return None
        df = pd.DataFrame(bars)
        df['t'] = pd.to_datetime(df['t'], unit='ms')
        df = df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
        df.set_index('t', inplace=True)
        return df.sort_index()
    except:
        return None

# --- SCORING FUNCTION ---
def score_ticker(ticker):
    try:
        price = ticker['lastTrade']['p']
        prev_close = ticker['prevDay']['c']
        volume = ticker['prevDay']['v']

        if use_live_data:
            percent_change = ticker['todaysChangePerc']
            volume = ticker['day']['v']
        else:
            percent_change = ((price - prev_close) / prev_close) * 100

        rvol = volume / (ticker['prevDay']['v'] if ticker['prevDay']['v'] > 0 else 1)

        if not (40 <= price <= 75 and percent_change >= 1.5 and volume > 2_000_000):
            return None

        score = 0
        score += 4  # base for passing core filters
        score += min((percent_change / 10), 1.5)
        score += min((volume / 5_000_000), 2.5)
        score += min((rvol / 2), 2)

        hist_df = get_5min_data(ticker['ticker'])
        if hist_df is None or len(hist_df) < 50:
            return None

        # Add technical indicators
        hist_df.ta.atr(length=14, append=True)
        hist_df.ta.rsi(length=2, append=True)
        hist_df.ta.macd(append=True)
        hist_df.ta.ema(length=9, append=True)
        hist_df.ta.ema(length=21, append=True)
        hist_df.ta.vwap(append=True)

        latest = hist_df.iloc[-1]

        # ATR-based trade levels
        atr = latest['ATR_14']
        entry = price
        target = entry + (atr * 1.5)
        stop = entry - (atr * 1.0)

        # Scoring indicators
        if price > latest['VWAP_D']: score += 1
        if latest['MACDh_12_26_9'] > 0 and hist_df['MACDh_12_26_9'].iloc[-2] < 0: score += 1
        if latest['RSI_2'] > 90 or latest['RSI_2'] < 10: score += 0.5
        if latest['EMA_9'] > latest['EMA_21']: score += 1

        return {
            "Ticker": ticker['ticker'],
            "Price": round(price, 2),
            "% Change": round(percent_change, 2),
            "Volume": f"{volume:,}",
            "RVOL": round(rvol, 2),
            "Score": round(score, 2),
            "Entry": round(entry, 2),
            "Target": round(target, 2),
            "Stop": round(stop, 2)
        }

    except:
        return None

# --- MAIN ---
with st.spinner("Scanning entire market... this may take a few seconds..."):
    tickers = get_polygon_snapshot()
    scored = [score_ticker(t) for t in tickers]
    top_10 = sorted([s for s in scored if s], key=lambda x: x['Score'], reverse=True)[:10]

if top_10:
    df = pd.DataFrame(top_10)
    st.success("Top 10 trade ideas ready ✅")
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No qualifying trades found at the moment. Check back shortly.")
