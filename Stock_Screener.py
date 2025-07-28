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
        tickers_df = pd.json_normalize(snap['tickers'])
        tickers_df['dollar_volume'] = tickers_df['lastTrade.p'] * tickers_df['day.v']

        pre_filtered = tickers_df[
            (tickers_df['lastTrade.p'] >= 45) &
            (tickers_df['lastTrade.p'] <= 70) &
            (tickers_df['day.v'] > 2_000_000) &
            (tickers_df['dollar_volume'] > 100_000_000) &
            (tickers_df['todaysChangePerc'] >= 2.0)].copy()

        # Sort by % gain and volume
        pre_filtered = pre_filtered.sort_values(
            by=['todaysChangePerc', 'day.v'],
            ascending=[False, False]).head(150)  # Only the top 150

        st.write(f"Scanning {len(pre_filtered)} top candidates from {len(tickers_df)} total tickers...")

    #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        # --- 3. Loop Through Each Ticker and Get 5-Min Candles ---
        # Use ISO timestamps with time to pull a broader range
        end_time = datetime.now()
        start_time = end_time - timedelta(days=5)  # go back 5 days
        
        from_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        to_date = datetime.now().strftime('%Y-%m-%d')
    
        for symbol in pre_filtered['ticker']:
                url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/5/minute/{from_date}/{to_date}?adjusted=true&sort=asc&limit=1000&apiKey={POLYGON_API_KEY}"
                r = requests.get(url)
                data = r.json()
            
                # Parse and validate candles
                candles = pd.DataFrame(data.get("results", []))
                
                if candles.empty or not all(col in candles.columns for col in ['c', 'v', 'h', 'l']):
                    continue
                if len(candles) < 50:
                    st.warning(f"📉 Not enough candles for {symbol}")
                    continue
                if candles.empty:
                    st.warning(f"⛔ No candles for {symbol}")
                    continue
                
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

                # Ensure candle data is usable
                if candles['close'].isna().sum() > 0 or candles['close'].nunique() == 1:
                    st.warning(f"⚠️ Invalid or flat close data for {symbol}")
                    continue
                    
                # Skip if volume from actual candles is too low
                if candles['volume'].sum() < 2_000_000:
                    ##st.warning(f"⛔ {symbol} skipped due to low intraday volume ({candles['volume'].sum():,.0f})")
                    continue
                
                # Compute Bollinger Bands with correct length
                bbands = ta.bbands(candles['close'], length=20)
                
                # Debug check
                ###st.write(f"{symbol} bbands columns: {bbands.columns.tolist()}")
                
                # Safe check before using
                if bbands is not None and all(x in bbands.columns for x in ['BBU_20_2.0', 'BBL_20_2.0']):
                    candles['bb_width'] = bbands['BBU_20_2.0'] - bbands['BBL_20_2.0']
                else:
                    st.warning(f"⚠️ Missing Bollinger Bands for {symbol}")
                    continue

                # Get percent change from snapshot
                latest = candles.iloc[-1]
                percent = pre_filtered.loc[pre_filtered['ticker'] == symbol, 'todaysChangePerc'].values
                percent = percent[0] if len(percent) > 0 else 0
                entry_price = latest['close']
                atr = latest['atr']
                target_price = entry_price + (atr * 1.5)
                stop_loss = entry_price - (atr * 1.0)

            
                # Save snapshot with indicators
                result_rows.append({
                    "ticker": symbol,
                    "price": latest['close'],
                    "volume": int(candles['volume'].sum()),
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
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_loss": stop_loss,
                })

        # --- 5. Convert result list to DataFrame ---
        df = pd.DataFrame(result_rows)
        
        # Stop if no data returned
        if df.empty:
            st.warning("⚠️ No valid tickers with candle data.")
            st.stop()

        df_final_display['price'] = df_final_display['price'].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else "N/A")
        # Format prices for display
        for col in ['entry_price', 'target_price', 'stop_loss', 'price']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].map('${:,.2f}'.format)

        # Stop if no tickers passed the technical filters
        if df.empty:
            st.warning("⚠️ No tickers passed the technical filters.")
            st.stop()
        
        # --- 6. Score all stocks based on closeness to your criteria ---
        df['score'] = 0
        df['score'] += (df['macd_hist'] > 0).astype(int)
        df['score'] += (df['rsi_2'] < 10).astype(int)
        df['score'] += (df['ema_9'] > df['ema_21']).astype(int)
        df['score'] += ((df['atr'] >= 3) & (df['atr'] <= 6)).astype(int)
        df['score'] += (df['bb_width'] > df['bb_width'].mean()).astype(int)
        df['score'] += (df['vwap'] > df['ema_21']).astype(int)
        df['score'] += (df['percent_change'] > 3).astype(int)
        # Convert price and volume to numeric if needed (in case they've been formatted)
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        # Now calculate liquidity score
        df['liquidity_score'] = (df['price'] * df['volume']) / 1_000_000  # In millions
        df['score'] += (df['liquidity_score'] > 100).astype(int)  # or whatever threshold fits your style


        #----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        # --- 8. Sort and Display Top Ranked Stocks ---
        top_display = df.copy()
        top_display['price'] = pd.to_numeric(top_display['price'], errors='coerce')
        top_display['volume'] = pd.to_numeric(top_display['volume'], errors='coerce')
        top_display['percent_change'] = pd.to_numeric(top_display['percent_change'], errors='coerce')
        
        top_display = top_display.sort_values(by=["score", "percent_change", "volume"], ascending=[False, False, False])
        
        top_display['price'] = top_display['price'].apply(lambda x: f"${x:.2f}")
        top_display['volume'] = top_display['volume'].apply(lambda x: f"{int(x):,}")
        top_display['percent_change'] = top_display['percent_change'].apply(lambda x: f"{x:.2f}%")
        
        st.subheader("🏆 Top Ranked Stocks (Filtered + Scored)")
        st.dataframe(top_display[['ticker', 'price', 'percent_change', 'volume', 'score','entry_price','target_price','stop_loss']])
                        
        # Optional: show all passing tickers
        with st.expander("📊 All Filtered Stocks"):
            st.dataframe(df)
