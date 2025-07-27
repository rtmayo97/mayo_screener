import requests
import pandas as pd

# --- CONFIG ---
POLYGON_API_KEY = st.secrets['Polygon_Key']

# --- API CALL ---
def get_polygon_snapshot():
    url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?apiKey={POLYGON_API_KEY}"
    response = requests.get(url)
    data = response.json()
    return data['tickers']

# --- SCORING FUNCTION ---
def score_ticker(ticker):
    try:
        price = ticker['lastTrade']['p']
        percent_change = ticker['todaysChangePerc']
        volume = ticker['day']['v']
        rvol = volume / (ticker['prevDay']['v'] if ticker['prevDay']['v'] > 0 else 1)

        if not (40 <= price <= 75 and percent_change >= 1.5 and volume > 2_000_000):
            return None

        score = 0
        score += min((percent_change / 10), 1.5)  # Max 1.5
        score += min((volume / 5_000_000), 2.5)    # Max 2.5
        score += min((rvol / 2), 2)               # Max 2
        score += 4                                 # Base for meeting criteria

        return {
            "ticker": ticker['ticker'],
            "price": price,
            "percent_change": percent_change,
            "volume": volume,
            "rvol": round(rvol, 2),
            "score": round(min(score, 10.0), 2)
        }

    except Exception:
        return None

# --- MAIN FUNCTION ---
def get_top_trades():
    tickers = get_polygon_snapshot()
    scored = [score_ticker(t) for t in tickers]
    scored = [s for s in scored if s is not None]
    top_trades = sorted(scored, key=lambda x: x['score'], reverse=True)[:10]
    return pd.DataFrame(top_trades)

# --- RUN ---
if __name__ == "__main__":
    df = get_top_trades()
    print(df)
