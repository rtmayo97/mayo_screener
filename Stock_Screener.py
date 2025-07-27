# scalping_ai_assistant.py
# Streamlit app: Scalping Strategy Screener + Journal + AI Insights
# Password-protected access.

import sys
import requests
import pandas as pd
from datetime import date, timedelta, datetime
import streamlit as st
import os
import pandas_ta as ta
import openai
import json

# --- API KEYS ---
POLYGON_API_KEY = st.secrets['Polygon_Key']
BENZINGA_API_KEY = st.secrets['Benzinga_Key']
APP_PASSWORD = st.secrets['APP_PASSWORD']
openai.api_key = st.secrets["Open_AI_Key"]
OPENAI_CLIENT = openai

# --- PASSWORD CHECK ---
def check_password():
    def password_entered():
        if st.session_state["password"] == APP_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # clear for security
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

# ---------- Setup ----------
st.set_page_config(page_title="Trading AI Assistant", layout="wide")
st.title("🤖 Smart Trading Screener & Journal")

STRATEGY_FILE = "scalping_strategy.json"
JOURNAL_FILE = "scalping_journal.json"

if not os.path.exists(STRATEGY_FILE):
    json.dump({}, open(STRATEGY_FILE, "w"))

if not os.path.exists(JOURNAL_FILE):
    json.dump([], open(JOURNAL_FILE, "w"))

strategy = json.load(open(STRATEGY_FILE))
journal = json.load(open(JOURNAL_FILE))

# ---------- Screener Logic ----------
def is_valid_candidate(stock):
    return (
        40 <= stock["price"] <= 75 and
        stock["volume"] > 2_000_000 and
        stock["percent_change"] >= 2 and
        3 <= stock["atr"] <= 6 and
        stock["price"] > stock["vwap"] and
        stock["price"] > stock["ema"] and
        stock["rsi"] < 70
    )

def get_top_gainers():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={POLYGON_API_KEY}"
    try:
        res = requests.get(url).json()
        return [x['ticker'] for x in res.get('tickers', [])]
    except:
        return []

def get_all_indicators(ticker):
    try:
        trade_resp = requests.get(f"https://api.polygon.io/v2/last/trade/{ticker}?apiKey={POLYGON_API_KEY}")
        prev_resp = requests.get(f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_API_KEY}")
        end = date.today()
        start = end - timedelta(days=30)
        stats_resp = requests.get(f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}?adjusted=true&sort=desc&limit=30&apiKey={POLYGON_API_KEY}")
        news_resp = requests.get(f"https://api.polygon.io/v2/reference/news?ticker={ticker}&limit=1&apiKey={POLYGON_API_KEY}")

        trade = trade_resp.json()
        prev = prev_resp.json()
        stats = stats_resp.json()
        news = news_resp.json()

        last_price = trade.get('last', {}).get('price', 0)
        prev_close = prev.get('results', [{}])[0].get('c', 0)
        pct_change = ((last_price - prev_close) / prev_close) * 100 if prev_close else 0

        results = stats.get('results', [])
        df = pd.DataFrame(results)
        df['hl'] = df['h'] - df['l']
        atr = round(df['hl'].mean(), 2)
        rvol = round(df['v'].iloc[0] / df['v'].iloc[1:21].mean(), 2) if len(df) > 20 else 0
        vwap = df.iloc[0]['vwap'] if 'vwap' in df.iloc[0] else 0
        close_prices = df['c'].tolist()
        rsi = ta.rsi(pd.Series(close_prices), length=14).iloc[-1] if len(close_prices) >= 14 else 50
        ema = ta.ema(pd.Series(close_prices), length=9).iloc[-1] if len(close_prices) >= 9 else 0

        headline = news.get('results', [{}])[0].get('title', 'No recent news.') if news.get('results') else 'No recent news.'
        sentiment_prompt = f"What is the market sentiment of this headline? Respond only with 'positive', 'neutral', or 'negative'.\n\nHeadline: {headline}"
        sentiment_res = OPENAI_CLIENT.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": sentiment_prompt}],
            temperature=0
        )
        sentiment = sentiment_res.choices[0].message.content.strip().lower()

        return {
            "ticker": ticker,
            "price": round(last_price, 2),
            "percent_change": round(pct_change, 2),
            "volume": df.iloc[0]['v'],
            "rvol": rvol,
            "atr": atr,
            "vwap": vwap,
            "ema": ema,
            "rsi": round(rsi, 2),
            "headline": headline,
            "sentiment": sentiment
        }
    except Exception as e:
        st.error(f"❌ Error getting indicators for {ticker}: {e}")
        return {}

def fetch_and_rank():
    tickers = get_top_gainers()
    st.write("✅ Top Gainers from Polygon:", tickers)
    candidates = []
    for t in tickers:
        data = get_all_indicators(t)
        if data and is_valid_candidate(data):
            candidates.append(data)
    if not candidates:
        return "⚠️ No valid candidates found to rank."
    return rank_with_gpt(candidates)

def rank_with_gpt(candidates):
    prompt = f"""
You're Mayo's trusted AI scalping assistant. Analyze these stocks based on:
- % price change
- RVOL
- Volume
- ATR (volatility)
- VWAP / EMA confirmation
- RSI momentum
- News sentiment

{json.dumps(candidates, indent=2)}

Rank the top 5–10 stocks for scalping today, with scores and brief reasons.
"""
    res = OPENAI_CLIENT.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )
    return res.choices[0].message.content

# ---------- UI ----------
if st.button("🔍 Get Today's Top 10 Scalping Picks"):
    with st.spinner("Scanning market and consulting GPT..."):
        results = fetch_and_rank()
        st.subheader("🏆 GPT-Ranked Top Trades")
        st.markdown(results)
