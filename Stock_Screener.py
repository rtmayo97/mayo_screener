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
def get_top_gainers():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/gainers?apiKey={POLYGON_API_KEY}"
    try:
        res = requests.get(url).json()
        return [x['ticker'] for x in res.get('tickers', [])]
    except:
        return []

def get_all_indicators(ticker):
    try:
        trade = requests.get(f"https://api.polygon.io/v2/last/trade/{ticker}?apiKey={POLYGON_API_KEY}").json()
        prev = requests.get(f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?adjusted=true&apiKey={POLYGON_API_KEY}").json()
        stats = requests.get(f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/30/2023-01-01/2023-12-31?adjusted=true&sort=desc&limit=30&apiKey={POLYGON_API_KEY}").json()
        news = requests.get(f"https://api.benzinga.com/api/v2/news?token={BENZINGA_API_KEY}&symbols={ticker}&channels=stock").json()

        last_price = trade.get('last', {}).get('price', 0)
        prev_close = prev.get('results', [{}])[0].get('c', 0)
        pct_change = ((last_price - prev_close) / prev_close) * 100 if prev_close else 0

        vols = [x['v'] for x in stats.get('results', [])]
        rvol = round(vols[0] / (sum(vols[1:21]) / 20), 2) if len(vols) > 20 else 0

        highs = [x['h'] for x in stats.get('results', [])]
        lows = [x['l'] for x in stats.get('results', [])]
        closes = [x['c'] for x in stats.get('results', [])]
        atr = round(pd.Series([h - l for h, l in zip(highs, lows)]).mean(), 2) if highs and lows else 0

        headline = news.get('news', [{}])[0].get('title', 'No recent news.') if news.get('news') else 'No recent news.'
        sentiment = news.get('news', [{}])[0].get('sentiment', 0)

        return {
            "ticker": ticker,
            "price": round(last_price, 2),
            "percent_change": round(pct_change, 2),
            "vol": vol,
            "rvol": rvol,
            "atr": atr,
            "headline": headline,
            "sentiment": sentiment
        }
    except:
        return {}

def fetch_and_rank():
    tickers = get_top_gainers()
    candidates = []
    for t in tickers:
        data = get_all_indicators(t)
        if data: candidates.append(data)
    return rank_with_gpt(candidates)

def rank_with_gpt(candidates):
    if not candidates: return []
    prompt = f"""
You're Mayo's trusted AI scalping assistant. Analyze these stocks based on:
- % price change
- RVOL
- Volume
- ATR (volatility)
- Headline relevance & sentiment
- Risk-reward potential
- Any other indicator from the data that helps assess scalping quality

{json.dumps(candidates, indent=2)}

Rank the **top 5–10 stocks** for scalping today, with scores (1 = best), and briefly explain why for each.
"""
    res = OPENAI_CLIENT.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )
    return res.choices[0].message.content

# ---------- Strategy Suggestions ----------
def suggest_strategy_adjustment():
    if len(journal) < 3:
        return "Not enough journal data to suggest changes yet."

    prompt = f"""
You're Mayo's personal trading assistant. Based on these recent journal entries, suggest 1–2 specific tweaks to the scalping strategy that could improve trade outcomes.
Be specific with filters (like RVOL, ATR, sentiment, etc.):

{json.dumps(journal[-10:], indent=2)}
"""
    response = OPENAI_CLIENT.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return response.choices[0].message.content

# ---------- UI: Top Trades ----------
if st.button("🔍 Get Today's Top 10 Scalping Picks"):
    with st.spinner("Scanning market and consulting GPT..."):
        results = fetch_and_rank()
        st.subheader("🏆 GPT-Ranked Top Trades")
        st.markdown(results)

# ---------- UI: Journal ----------
st.markdown("---")
st.subheader("📝 Journal")
entry = st.text_area("Log your thoughts, wins, or strategy updates:")

if st.button("💾 Save to Journal"):
    log = {"timestamp": datetime.now().isoformat(), "entry": entry}
    journal.append(log)
    with open(JOURNAL_FILE, "w") as f:
        json.dump(journal, f, indent=2)
    st.success("Saved!")

if st.checkbox("📚 Show Past Entries"):
    for j in reversed(journal[-10:]):
        st.markdown(f"**{j['timestamp']}**\n
{j['entry']}")

# ---------- UI: Strategy Suggestion ----------
st.markdown("---")
st.subheader("🧠 Strategy Suggestions from GPT")

if st.button("🔧 Suggest Adjustments Based on Journal"):
    with st.spinner("Analyzing your journal..."):
        suggestion = suggest_strategy_adjustment()
        st.info(suggestion)
        st.markdown("If you like the changes, apply them manually to your filters in your strategy settings.")