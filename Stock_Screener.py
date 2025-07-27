# pr356_screener.py

import streamlit as st
import pandas as pd
import pandas_ta as ta
import requests
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
    result_rows = []  # <-- define early and clearly
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

    # Create a copy for display formatting only
    filtered_display = filtered.copy()
    
    # Format volume with commas
    filtered_display['volume'] = filtered_display['volume'].apply(lambda x: f"{int(x):,}")
    
    # Format percent change as percentage with 2 decimal places
    filtered_display['percent_change'] = filtered_display['percent_change'].apply(lambda x: f"{x:.2f}%")
    
    # Optional: format price with 2 decimals as well
    filtered_display['price'] = filtered_display['price'].apply(lambda x: f"${x:.2f}")
    
    # Display the formatted table
    st.subheader("🔍 Filtered Tickers")
    st.dataframe(filtered_display[['ticker', 'price', 'percent_change','volume']])
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # --- 3. Loop Through Each Ticker and Get 5-Min Candles ---
    from_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    to_date = datetime.now().strftime('%Y-%m-%d')
    
result_rows = []
    
for symbol in filtered['ticker']:
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/5/minute/{from_date}/{to_date}?adjusted=true&sort=asc&limit=1000&apiKey={POLYGON_API_KEY}"
        r = requests.get(url)
        data = r.json()
    
        # Parse and validate candles
        candles = pd.DataFrame(data.get("results", []))
        
        if candles.empty or not all(col in candles.columns for col in ['c', 'v', 'h', 'l']):
            continue  # Skip tickers with missing data
    
        # Rename columns
        candles.rename(columns={
            'v': 'volume', 'o': 'open', 'c': 'close',
            'h': 'high', 'l': 'low', 't': 'timestamp'
        }, inplace=True)
    
        candles['timestamp'] = pd.to_datetime(candles['timestamp'], unit='ms')
        candles.set_index('timestamp', inplace=True)
    
        # Make sure there's enough data for indicators
        if len(candles) < 20:
            continue
    
        # --- 4. Add Technical Indicators ---
        candles['ema_9'] = ta.ema(candles['close'], length=9)
        candles['ema_21'] = ta.ema(candles['close'], length=21)
        candles['macd_hist'] = ta.macd(candles['close'])['MACDh_12_26_9']
        candles['rsi_2'] = ta.rsi(candles['close'], length=2)
        candles['rsi_5'] = ta.rsi(candles['close'], length=5)
        candles['atr'] = ta.atr(candles['high'], candles['low'], candles['close'], length=14)
        candles['vwap'] = ta.vwap(candles['high'], candles['low'], candles['close'], candles['volume'])
        candles['bb_width'] = ta.bbands(candles['close'])['BBU_20_2.0'] - ta.bbands(candles['close'])['BBL_20_2.0']
    
        # --- Bollinger Bands with Append ---
        # Compute Bollinger Bands just once
        bbands = ta.bbands(candles['close'])
        
        # Check if expected columns are present
        if bbands is not None and all(x in bbands.columns for x in ['BBU_20_2.0', 'BBL_20_2.0']):
            candles['bb_width'] = bbands['BBU_20_2.0'] - bbands['BBL_20_2.0']
        else:
            st.warning(f"⚠️ Missing Bollinger Bands for {symbol}")
            continue
    

    # Get percent change from snapshot
    latest = candles.iloc[-1]
    percent = filtered.loc[filtered['ticker'] == symbol, 'percent_change'].values
    percent = percent[0] if len(percent) > 0 else 0

    # Save snapshot with indicators
    result_rows.append({
        "ticker": symbol,
        "price": latest['close'],
        "volume": latest['volume'],
        "percent_change": percent,
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

# --- 5. Convert result list to DataFrame ---
df = pd.DataFrame(result_rows)

# Stop if no data returned
if df.empty:
    st.warning("⚠️ No valid tickers with candle data.")
    st.stop()

# --- 6. Filter using snapshot + indicator criteria ---
df_filtered = df[
    (df['price'] >= 45) &
    (df['price'] <= 70) &
    (df['volume'] > 2_000_000) &
    (df['percent_change'] >= 2.0) &
    (df['macd_hist'] > 0) &
    (df['rsi_2'] < 10) &
    (df['atr'] >= 3) &
    (df['atr'] <= 6)
]

# Stop if no tickers passed the technical filters
if df_filtered.empty:
    st.warning("⚠️ No tickers passed the technical filters.")
    st.stop()

# --- 7. Score each stock using pandas ---
df_filtered['score'] = (
    (df_filtered['macd_hist'] > 0).astype(int) +
    (df_filtered['rsi_2'] < 10).astype(int) +
    (df_filtered['ema_9'] > df_filtered['ema_21']).astype(int)
)
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# --- 8. Sort and Display Top Ranked Stocks ---
top_display = df_filtered.copy()
top_display['price'] = pd.to_numeric(top_display['price'], errors='coerce')
top_display['volume'] = pd.to_numeric(top_display['volume'], errors='coerce')
top_display['percent_change'] = pd.to_numeric(top_display['percent_change'], errors='coerce')

top_display = top_display.sort_values(by=["score", "percent_change", "volume"], ascending=[False, False, False])

top_display['price'] = top_display['price'].apply(lambda x: f"${x:.2f}")
top_display['volume'] = top_display['volume'].apply(lambda x: f"{int(x):,}")
top_display['percent_change'] = top_display['percent_change'].apply(lambda x: f"{x:.2f}%")

st.subheader("🏆 Top Ranked Stocks (Filtered + Scored)")
st.dataframe(top_display[['ticker', 'price', 'percent_change', 'volume', 'score']])

# Optional: show all passing tickers
with st.expander("📊 All Filtered Stocks"):
    st.dataframe(df_filtered)
