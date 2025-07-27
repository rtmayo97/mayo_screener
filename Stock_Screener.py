# scalping_screener_app.py
# Streamlit app to scan and rank top 10 scalping candidates using Polygon.io API

import streamlit as st
import requests
import pandas as pd

# --- PAGE SETUP ---
st.set_page_config(page_title="Top 10 Scalping Screener", layout="wide")
st.title("🚀 Real-Time Scalping Screener (Top 10 Picks)")

# --- SECRETS ---
POLYGON_API_KEY = st.secrets["Polygon_Key"]

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

# --- SCORING FUNCTION ---
def score_ticker(ticker):
    try:
        price = ticker['lastTrade']['p']
        percent_change = ticker['todaysChangePerc']
        volume = ticker['day']['v']
        rvol = volume / (ticker['prevDay']['v'] if ticker['prevDay']['v'] > 0 else 1)

        if not (40 <= price <= 75 and percent_change >= 1.5 and volume > 2_000_000):
            return None

        score = 0
        score += min((percent_change / 10), 1.5)  # Max 1.5
        score += min((volume / 5_000_000), 2.5)    # Max 2.5
        score += min((rvol / 2), 2)               # Max 2
        score += 4                                 # Base for meeting core criteria

        return {
            "Ticker": ticker['ticker'],
            "Price": round(price, 2),
            "% Change": round(percent_change, 2),
            "Volume": f"{volume:,}",
            "RVOL": round(rvol, 2),
            "Score (1-10)": round(min(score, 10.0), 2)
        }

    except:
        return None

# --- MAIN ---
with st.spinner("Scanning entire market... this may take a few seconds..."):
    tickers = get_polygon_snapshot()
    scored = [score_ticker(t) for t in tickers]
    top_10 = sorted([s for s in scored if s], key=lambda x: x['Score (1-10)'], reverse=True)[:10]

if top_10:
    df = pd.DataFrame(top_10)
    st.success("Top 10 trade ideas ready ✅")
    st.dataframe(df, use_container_width=True)
else:
    st.warning("No qualifying trades found at the moment. Check back shortly.")
