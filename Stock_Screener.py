import requests
import pandas as pd
import sqlite3

# 1. Pull snapshot data
POLYGON_API_KEY = "your_polygon_api_key"
url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?apiKey={POLYGON_API_KEY}"
response = requests.get(url)
data = response.json()

# 2. Flatten + clean columns
tickers = pd.json_normalize(data['tickers'])
tickers.columns = [col.replace('.', '_') for col in tickers.columns]
tickers = tickers.loc[:, ~tickers.columns.str.lower().duplicated()]  # Case-insensitive deduplication

# 3. Load into SQLite
conn = sqlite3.connect(":memory:")
tickers.to_sql("stocks", conn, index=False, if_exists="replace")

# 4. Run SQL
query = """
SELECT ticker, lastTrade_p AS price, todaysChangePerc AS pct_change, day_v AS volume
FROM stocks
WHERE lastTrade_p BETWEEN 40 AND 75
AND todaysChangePerc >= 1.5
AND day_v > 2000000
ORDER BY todaysChangePerc DESC
LIMIT 10
"""

df = pd.read_sql_query(query, conn)
print(df)
