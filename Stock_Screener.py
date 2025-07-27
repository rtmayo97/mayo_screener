# streamlit_sql_screener.py
# Streamlit UI for querying Polygon.io snapshot data with SQL

import streamlit as st
import requests
import pandas as pd
import sqlite3

# --- API CONFIG ---
POLYGON_API_KEY = st.secrets["Polygon_Key"]
url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?apiKey={POLYGON_API_KEY}"
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

# --- PAGE SETUP ---
st.set_page_config(page_title="Polygon SQL Screener", layout="wide")
st.title("🔍 Polygon.io API SQL Screener")

# --- FETCH DATA ---
@st.cache_data(ttl=300)
def fetch_data():
    response = requests.get(url)
    data = response.json()
    tickers = pd.json_normalize(data['tickers'])
    tickers.columns = [col.replace('.', '_') for col in tickers.columns]
    tickers = tickers[[col for col in tickers.columns if tickers[col].apply(lambda x: isinstance(x, (list, dict))).sum() == 0]]
    tickers = tickers.loc[:, ~tickers.columns.str.lower().duplicated()]
    return tickers

# --- LOAD DATA ---
tickers_df = fetch_data()

# --- SQL INPUT ---
st.subheader("🧠 SQL Query Editor")
def get_sql_result(query):
    conn = sqlite3.connect(":memory:")
    tickers_df.to_sql("stocks", conn, index=False, if_exists="replace")
    try:
        result_df = pd.read_sql_query(query, conn)
        return result_df
    except Exception as e:
        st.error(f"SQL Error: {e}")
        return None

sql_query = st.text_area("Write your SQL query below:",
                         """
SELECT ticker, lastTrade_p AS price, todaysChangePerc AS pct_change, day_v AS volume
FROM stocks
WHERE lastTrade_p BETWEEN 40 AND 75
AND todaysChangePerc >= 1.5
AND day_v > 2000000
ORDER BY todaysChangePerc DESC
LIMIT 10
""",
                         height=200)

if st.button("Run Query"):
    result = get_sql_result(sql_query)
    if result is not None:
        st.success(f"✅ Returned {len(result)} rows")
        st.dataframe(result, use_container_width=True)
    else:
        st.warning("No results found or query error.")
