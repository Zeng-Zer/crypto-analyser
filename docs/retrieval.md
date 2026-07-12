# Hybrid News Retrieval

## 1. Overview
This function finds relevant crypto news articles during a market crash. It gives us context about why a price anomaly happened. It returns a simple list of article dictionaries.

## 2. Inputs 
*   `anomaly_timestamp` (datetime): The exact time of the crash.
*   `ticker` (str): The crypto coin (e.g., "BTC", "LUNA").
*   `top_k` (int): Max articles to return (default: 10).
*   `window_hours` (int): Time window before/after the crash (default: 12).
*   `conn` or `dsn`: Use `conn` if you already have a database connection, or pass a `dsn` string to let the function handle it.

## 3. Pipeline
The SQL query does 3 things:
1. **Ticker filter:** Keeps articles matching the coin (`tickers @> ARRAY[...]`).
2. **Time filter:** Keeps articles within the 12-hour window (`date_pub BETWEEN ... AND ...`).
3. **Ranking:** Ranks them using Reciprocal Rank Fusion (RRF).

## 4. Scoring Formula
We combine the text rank and vector rank using the RRF formula:
`score = 1 / (60 + rank_v) + 1 / (60 + rank_t)`

We use `k=60` because it is the standard value for RRF. This rank-based method safely balances vector and text scores.

## 5. Vector vs Text Similarity
*   **Vector (Semantic):** Uses the `<=>` (cosine distance) operator. 
*   **Text (Keyword):** Uses `websearch_to_tsquery` to find words like "crash" or "depeg".
We use both because they are complementary (Vector gets the context, Text gets the exact words).

## 6. Dimensionality Note
The AI model (`qwen3-embedding`) gives 4096 dimensions. However, the database HNSW index is limited to 2000. We truncate the vector to 2000 (`[:2000]`) before sending it to PostgreSQL to prevent database errors.

## 7. Usage Example

```bash
python3 scripts/test_retrieval.py --ticker BTC --timestamp 2021-02-01T14:00:00
```
Here's the uoutput : 

--- Searching for BTC at 2021-02-01T14:00:00+00:00 ---

=== QA VERIFICATION ===
[Ticker check] article 1: tickers=[BTC, XVG] PASS BTC present
[Time check]   article 1: pub_date=2021-02-01T11:45:06+00:00 PASS within 12h
[Keyword check] article 1: contains target keywords PASS
[Ticker check] article 2: tickers=[BTC, ETH] PASS BTC present
[Time check]   article 2: pub_date=2021-02-01T13:10:00+00:00 PASS within 12h
[Keyword check] article 2: missing target keywords FAIL
[Ticker check] article 3: tickers=[BTC, DOGE, XVG] PASS BTC present
[Time check]   article 3: pub_date=2021-02-01T09:21:40+00:00 PASS within 12h
[Keyword check] article 3: missing target keywords FAIL