# pr356_screener.py

import streamlit as st
import pandas as pd
import pandas_ta as ta
import requests
import sqlite3
from datetime import datetime, timedelta

# --- Configuration ---
POLYGON_API_KEY = st.secrets['Polygon_Key']  # Put your Polygon API Key in Streamlit secrets
APP_PASSWORD = st.secrets['APP_PASSWORD']
TICKERS_TO_PULL = 50  # You can increase this later


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

# --- Streamlit Setup ---
st.set_page_config(page_title="PR356 Screener", layout="wide")
st.title("📈 PR356 Stock Screener – Phase 1")

# --- Refresh Button ---
if st.button("🔁 Run Screener"):
    st.write("Fetching data and calculating indicators...")

    # --- 1. Pull Snapshot Data from Polygon ---
    snapshot_url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?apiKey={POLYGON_API_KEY}"
    snap = requests.get(snapshot_url).json()
    tickers = pd.json_normalize(snap['tickers'])

    # --- 2. Filter Tickers by Price and Volume ---
    filtered = tickers[
        (tickers['lastTrade.p'] >= 45) &
        (tickers['lastTrade.p'] <= 70) &
        (tickers['day.v'] > 2_000_000)
    ].head(TICKERS_TO_PULL)

    result_rows = []

    # --- 3. Loop Through Each Ticker and Get 1-Min Candles ---
    for symbol in filtered['ticker']:
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')}/{datetime.now().strftime('%Y-%m-%d')}?adjusted=true&sort=desc&limit=100&apiKey={POLYGON_API_KEY}"
        r = requests.get(url)
        data = r.json()
        candles = pd.DataFrame(data.get("results", []))

        if len(candles) < 20:
            continue  # Skip if not enough data

        # --- Rename and Clean ---
        candles.rename(columns={
            'v': 'volume', 'o': 'open', 'c': 'close',
            'h': 'high', 'l': 'low', 't': 'timestamp'
        }, inplace=True)
        candles['timestamp'] = pd.to_datetime(candles['timestamp'], unit='ms')
        candles.set_index('timestamp', inplace=True)

        # --- 4. Add Technical Indicators ---
        candles['ema_9'] = ta.ema(candles['close'], length=9)
        candles['ema_21'] = ta.ema(candles['close'], length=21)
        candles['macd_hist'] = ta.macd(candles['close'])['MACDh_12_26_9']
        candles['rsi_2'] = ta.rsi(candles['close'], length=2)
        candles['rsi_5'] = ta.rsi(candles['close'], length=5)
        candles['atr'] = ta.atr(candles['high'], candles['low'], candles['close'], length=14)
        candles['vwap'] = ta.vwap(candles['high'], candles['low'], candles['close'], candles['volume'])
        candles['bb_width'] = ta.bbands(candles['close'])['BBU_20_2.0'] - ta.bbands(candles['close'])['BBL_20_2.0']

        latest = candles.iloc[-1]

        # --- 5. Save Latest Indicator Snapshot ---
        result_rows.append({
            "ticker": symbol,
            "price": latest['close'],
            "volume": latest['volume'],
            "macd_hist": latest['macd_hist'],
            "rsi_2": latest['rsi_2'],
            "rsi_5": latest['rsi_5'],
            "ema_9": latest['ema_9'],
            "ema_21": latest['ema_21'],
            "atr": latest['atr'],
            "vwap": latest['vwap'],
            "bb_width": latest['bb_width'],
            "ema_crossover": int(latest['ema_9'] > latest['ema_21']),
        })

    # --- 6. Load Data to SQLite ---
    conn = sqlite3.connect(":memory:")
    df = pd.DataFrame(result_rows)
    # Step 1: Convert list to DataFrame
df = pd.DataFrame(result_rows)

# Step 2: Drop any rows with missing or invalid data
df = df.dropna()

# Step 3: Keep only valid, known columns
expected_columns = [
    "ticker", "price", "volume", "macd_hist", "rsi_2", "rsi_5",
    "ema_9", "ema_21", "atr", "vwap", "bb_width", "ema_crossover"
]
df = df[expected_columns]

# Step 4: Force all columns to the correct data types
df = df.astype({
    "ticker": str,
    "price": float,
    "volume": float,
    "macd_hist": float,
    "rsi_2": float,
    "rsi_5": float,
    "ema_9": float,
    "ema_21": float,
    "atr": float,
    "vwap": float,
    "bb_width": float,
    "ema_crossover": int,
})

# Now safe to write to SQLite

st.write("✅ Data cleaned. Preview:")
st.dataframe(df.head())
st.write("🔍 Column types:")
st.write(df.dtypes)

df.to_sql("stocks", conn, index=False, if_exists="replace")
    df.to_sql("stocks", conn, index=False, if_exists="replace")

    # --- 7. Score and Rank Using SQL ---
    query = """
    SELECT *,
      (CASE WHEN macd_hist > 0 THEN 1 ELSE 0 END) +
      (CASE WHEN rsi_2 < 10 THEN 1 ELSE 0 END) +
      (CASE WHEN ema_crossover = 1 THEN 1 ELSE 0 END)
      AS score
    FROM stocks
    ORDER BY score DESC
    LIMIT 10;
    """
    top_stocks = pd.read_sql_query(query, conn)

    # --- 8. Display in Streamlit ---
    st.subheader("🏆 Top Ranked Stocks (SQL Scored)")
    st.dataframe(top_stocks)

    # Optional full table
    with st.expander("📊 Full Data Table"):
        st.dataframe(df)