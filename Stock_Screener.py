# scalping_ai_assistant.py
# Streamlit app: Scalping Strategy Screener + Journal + AI Insights
# Password-protected access.

import sys
import requests
import pandas as pd
from datetime import datetime
import streamlit as st
import os
import pandas_ta as ta
import openai
import json

# --- API KEYS ---
POLYGON_API_KEY = st.secrets['Polygon_Key']
BENZINGA_API_KEY = st.secrets['Benzinga_Key']
APP_PASSWORD = st.secrets['APP_PASSWORD']

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

# ---------- Setup ----------
if check_password():
st.set_page_config(page_title="Scalping AI Assistant", layout="wide")
st.title("📈 Trading AI Assistant — Top Trades & Journal")

# ---------- Persistent Storage ----------
STRATEGY_FILE = "scalping_strategy.json"
JOURNAL_FILE = "scalping_journal.json"

if not os.path.exists(STRATEGY_FILE):
    json.dump({"min_price": 40, "max_price": 75, "min_rvol": 1.5, "min_pct_change": 2, "max_atr": 5}, open(STRATEGY_FILE, "w"))

if not os.path.exists(JOURNAL_FILE):
    json.dump([], open(JOURNAL_FILE, "w"))

strategy = json.load(open(STRATEGY_FILE))
journal = json.load(open(JOURNAL_FILE))

# ---------- Strategy UI ----------
st.sidebar.header("🔧 Strategy Settings")
strategy['min_price'] = st.sidebar.number_input("Min Price", value=strategy['min_price'])
strategy['max_price'] = st.sidebar.number_input("Max Price", value=strategy['max_price'])
strategy['min_rvol'] = st.sidebar.number_input("Min RVOL", value=strategy['min_rvol'])
strategy['min_pct_change'] = st.sidebar.number_input("Min % Change", value=strategy['min_pct_change'])
strategy['max_atr'] = st.sidebar.number_input("Max ATR", value=strategy['max_atr'])

with open(STRATEGY_FILE, "w") as f:
    json.dump(strategy, f, indent=2)

# ---------- Screener Logic ----------
def get_top_gainers():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={POLYGON_API_KEY}"
    try:
        res = requests.get(url).json()
        return [x['ticker'] for x in res.get('tickers', [])]
    except:
        return []

def get_trade_data(ticker):
    try:
        trade = requests.get(f"https://api.polygon.io/v2/last/trade/{ticker}?apiKey={POLYGON_API_KEY}").json()
        prev = requests.get(f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_API_KEY}").json()
        price = trade['last']['price']
        prev_close = prev['results'][0]['c']
        pct_change = ((price - prev_close) / prev_close) * 100 if prev_close else 0
        return round(price, 2), round(pct_change, 2)
    except:
        return 0, 0

def get_rvol(ticker):
    try:
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/30/2023-01-01/2023-12-31?adjusted=true&sort=desc&limit=30&apiKey={POLYGON_API_KEY}"
        data = requests.get(url).json().get('results', [])
        if len(data) < 21: return 0
        current = data[0]['v']
        avg = sum([d['v'] for d in data[1:21]]) / 20
        return round(current / avg, 2)
    except:
        return 0

def get_atr(ticker):
    try:
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/14/2023-01-01/2023-12-31?adjusted=true&sort=desc&limit=14&apiKey={POLYGON_API_KEY}"
        data = requests.get(url).json().get('results', [])
        if not data: return 0
        df = pd.DataFrame({'h': [d['h'] for d in data], 'l': [d['l'] for d in data], 'c': [d['c'] for d in data]})
        df['tr'] = df[['h', 'l', 'c']].max(axis=1) - df[['h', 'l', 'c']].min(axis=1)
        return round(df['tr'].mean(), 2)
    except:
        return 0

def fetch_and_rank():
    tickers = get_top_gainers()
    candidates = []
    for t in tickers:
        price, change = get_trade_data(t)
        rvol = get_rvol(t)
        atr = get_atr(t)
        if (strategy['min_price'] <= price <= strategy['max_price'] and
            change >= strategy['min_pct_change'] and
            rvol >= strategy['min_rvol'] and
            atr <= strategy['max_atr']):
            candidates.append({"ticker": t, "price": price, "pct_change": change, "rvol": rvol, "atr": atr})
    return rank_with_gpt(candidates)

def rank_with_gpt(candidates):
    if not candidates: return []
    prompt = f"""
You're Mayo's personal trading assistant. Rank these stocks for scalping (1 = best) based on RVOL, price action (% change), and ATR-based volatility control:
{json.dumps(candidates, indent=2)}
Give a sorted list of top 10 in this format:
1. TICKER - Reason
2. ...
"""
    res = OPENAI_CLIENT.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )
    return res.choices[0].message.content

# ---------- UI Section: Top Trades ----------
if st.button("🔍 Get Today's Top 10 Trades"):
    with st.spinner("Analyzing market..."):
        results = fetch_and_rank()
        st.subheader("📊 GPT-Ranked Top 10 Scalping Candidates")
        st.markdown(results)

# ---------- UI Section: Journal ----------
st.markdown("---")
st.subheader("📝 Trade Journal")
journal_entry = st.text_area("Log a trade or insight from today:")

if st.button("Save to Journal"):
    entry = {"timestamp": datetime.now().isoformat(), "entry": journal_entry}
    journal.append(entry)
    with open(JOURNAL_FILE, "w") as f:
        json.dump(journal, f, indent=2)
    st.success("Saved to journal!")

if st.checkbox("Show past journal entries"):
    for j in reversed(journal[-10:]):
        st.markdown(f"**{j['timestamp']}**\n
{j['entry']}")
