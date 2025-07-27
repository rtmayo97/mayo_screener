# streamlit_sql_screener.py
# Unified SQL Screener with Polygon Snapshot + Technical Indicators (Top 50)

import streamlit as st
import requests
import pandas as pd
import pandas_ta as ta
import sqlite3
from datetime import datetime, timedelta

# --- PAGE SETUP ---
st.set_page_config(page_title="Unified SQL Screener", layout="wide")
st.title("📊 Polygon SQL Screener with Technical Indicators")

# --- SECRETS ---
POLYGON_API_KEY = st.secrets["Polygon_Key"]
APP_PASSWORD = st.secrets['APP_PASSWORD']

# --- PASSWORD CHECK ---
def check_password():
    def password_entered():
        if st.session_state["password"] == APP_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
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

if not check_password():
    st.stop()

# --- FETCH SNAPSHOT ---
@st.cache_data(ttl=300)
def fetch_snapshot():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?apiKey={POLYGON_API_KEY}"
    response = requests.get(url)
    data = response.json()
    df = pd.json_normalize(data['tickers'])
    df.columns = [col.replace('.', '_') for col in df.columns]
    df = df[[col for col in df.columns if df[col].apply(lambda x: isinstance(x, (list, dict))).sum() == 0]]
    df = df.loc[:, ~df.columns.str.lower().duplicated()]
    return df

# --- FETCH HISTORICAL + INDICATORS FOR ONE TICKER ---
def fetch_indicators(ticker):
    try:
        end = datetime.utcnow()
        start = end - timedelta(days=3)
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/5/minute/{start.date()}/{end.date()}?adjusted=true&sort=desc&limit=500&apiKey={POLYGON_API_KEY}"
        response = requests.get(url)
        data = response.json().get("results", [])
        if not data:
            return None
        df = pd.DataFrame(data)
        df['t'] = pd.to_datetime(df['t'], unit='ms')
        df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume'}, inplace=True)
        df.ta.macd(append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.atr(length=14, append=True)
        df.ta.vwap(append=True)
        df.ta.ema(length=9, append=True)
        df.ta.ema(length=21, append=True)
        df.ta.bbands(length=20, append=True)
        return df.iloc[-1:].assign(ticker=ticker)  # Return most recent row
    except:
        return None

# --- COMBINE SNAPSHOT + INDICATORS ---
st.subheader("🔄 Building unified data table...")
snapshot_df = fetch_snapshot()
snapshot_df = snapshot_df.sort_values("day_v", ascending=False).head(50)  # Top 50 by volume

indicator_rows = []
progress = st.progress(0)

for i, ticker in enumerate(snapshot_df['ticker']):
    ind_df = fetch_indicators(ticker)
    if ind_df is not None:
        indicator_rows.append(ind_df)
    progress.progress((i + 1) / len(snapshot_df))

if not indicator_rows:
    st.error("❌ No indicator data found.")
    st.stop()

indicators_df = pd.concat(indicator_rows, ignore_index=True)
combined_df = pd.merge(snapshot_df, indicators_df, on="ticker", how="inner")

# --- LOAD INTO SQLITE ---
conn = sqlite3.connect(":memory:")
combined_df.to_sql("stocks", conn, index=False, if_exists="replace")

st.success(f"✅ Combined dataset loaded with {len(combined_df)} tickers")
st.dataframe(combined_df[['ticker', 'lastTrade_p', 'todaysChangePerc', 'day_v', 'RSI_14', 'MACDh_12_26_9', 'ATR_14', 'VWAP_D']].head(), use_container_width=True)

# --- SQL EDITOR ---
st.subheader("🧠 Unified SQL Query Editor")
def run_query(q):
    try:
        return pd.read_sql_query(q, conn)
    except Exception as e:
        st.error(f"SQL Error: {e}")
        return None

example_sql = """
SELECT *
FROM stocks
WHERE lastTrade_p BETWEEN 40 AND 75
ORDER BY todaysChangePerc DESC
LIMIT 35
"""

query_input = st.text_area("Write your SQL query below:", value=example_sql, height=200)
if st.button("Run Query"):
    result = run_query(query_input)
    if result is not None:
        st.dataframe(result, use_container_width=True)
