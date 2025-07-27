# scalping_ai_assistant.py
# Streamlit app: Fast Screener Like SQL - Score & Rank Top 10 Stocks

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

# ---------- Setup ----------
st.set_page_config(page_title="Trading AI Assistant", layout="wide")
st.title("🤖 Smart Trading Screener & Journal")

# ---------- Scoring + Quick Filter ----------
def get_top_10_fast():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?apiKey={POLYGON_API_KEY}"
    try:
        res = requests.get(url).json()
        all_tickers = res.get("tickers", [])
        filtered = []

        for stock in all_tickers:
            try:
                price = stock['lastTrade']['p']
                volume = stock['day']['v']
                pct_change = stock['day']['c']

                if 40 <= price <= 75 and volume > 2_000_000 and pct_change >= 2:
                    score = (
                        pct_change +
                        (volume / 1_000_000) +
                        (10 if 50 <= price <= 65 else 0)
                    )
                    filtered.append({
                        "ticker": stock['ticker'],
                        "price": round(price, 2),
                        "volume": volume,
                        "percent_change": round(pct_change, 2),
                        "score": round(score, 2)
                    })
            except:
                continue

        top10 = sorted(filtered, key=lambda x: x['score'], reverse=True)[:10]
        return top10
    except Exception as e:
        st.error(f"❌ Error fetching fast-ranked tickers: {e}")
        return []

# ---------- Full Indicator + GPT ----------
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
st.subheader("🔎 Fast Screener Based on Your Strategy")
if st.button("⚡ Run SQL-Like Fast Screener"):
    with st.spinner("Scoring and ranking top 10 tickers..."):
        top_fast = get_top_10_fast()
        st.write("📈 Top 10 Fast-Filtered Tickers:")
        st.dataframe(pd.DataFrame(top_fast))

        full_data = []
        for t in top_fast:
            st.write(f"📊 Pulling indicators for {t['ticker']}...")
            data = get_all_indicators(t['ticker'])
            if data:
                full_data.append(data)

        if full_data:
            st.subheader("🏆 GPT-Ranked Top Trades")
            st.markdown(rank_with_gpt(full_data))
        else:
            st.warning("No valid candidates after full indicator checks.")
