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
st.title("📈 PR356 Stock Screener")

# --- Refresh Button ---
if st.button("🔁 Run Screener"):
    st.write("Fetching data and calculating indicators...")

    # --- 1. Pull Snapshot Data from Polygon ---
    snapshot_url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?apiKey={POLYGON_API_KEY}"
    snap = requests.get(snapshot_url).json()
    tickers = pd.json_normalize(snap['tickers'])
    tickers = tickers.rename(columns={
    'lastTrade.p': 'price',
    'day.v': 'volume',
    'todaysChangePerc': 'percent_change'
})

    # --- 2. Filter Tickers by Price and Volume ---
    filtered = tickers[
        (tickers['price'] >= 45) &
        (tickers['price'] <= 70) &
        (tickers['volume'] > 2_000_000) &
        (tickers['percent_change'] >= 2.0)
    ].head(TICKERS_TO_PULL)

    # --- Sort by % change and volume descending ---
    filtered = filtered.sort_values(
    by=['percent_change', 'volume'],
    ascending=[False, False]
    ).head(TICKERS_TO_PULL)

    result_rows = []

    # Create a copy for display formatting only
    filtered_display = filtered.copy()
    
    # Format volume with commas
    filtered_display['volume'] = filtered_display['volume'].apply(lambda x: f"{int(x):,}")
    
    # Format percent change as percentage with 2 decimal places
    filtered_display['percent_change'] = filtered_display['percent_change'].apply(lambda x: f"{x:.2f}%")
    
    # Optional: format price with 2 decimals as well
    filtered_display['price'] = filtered_display['price'].apply(lambda x: f"${x:.2f}")
    
    st.subheader("🔍 Filtered Tickers")
    st.dataframe(filtered[['ticker', 'price', 'percent_change','volume']])
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
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
    df = pd.DataFrame(result_rows)

    if df.empty:
        st.warning("⚠️ No valid tickers returned. Try increasing the sample size or check API limit.")
        st.stop()

    # Drop rows with missing data
    df = df.dropna()

    # Keep only the expected columns
    required_columns = [
        "ticker", "price", "volume", "macd_hist", "rsi_2", "rsi_5",
        "ema_9", "ema_21", "atr", "vwap", "bb_width", "ema_crossover"
    ]
    df = df[[col for col in required_columns if col in df.columns]]

    # Force all types
    for col in df.columns:
        if col == "ticker":
            df[col] = df[col].astype(str)
        elif col == "ema_crossover":
            df[col] = df[col].fillna(0).astype(int)
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna()

    # --- Write to SQLite ---
    conn = sqlite3.connect(":memory:")
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
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # --- 8. Display in Streamlit ---
    st.subheader("🏆 Top Ranked Stocks (SQL Scored)")
    st.dataframe(top_stocks)

    with st.expander("📊 Full Data Table"):
        st.dataframe(df)
