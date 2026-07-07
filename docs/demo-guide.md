# User Guide: Vector Search Demo

## 1. Overview

This command-line tool (demo_retrieval.py) lets you do smart, semantic searches inside our crypto news database. It turns your text search into a math vector using an AI API. Then, it looks through the database to find the articles that have the closest meaning to your search.

## 2. Prerequisites

Before running the script, please make sure you have:

A running PostgreSQL database with the pgvector extension installed and turned on.

The data (embeddings) already loaded into the crypto_news table.

A valid API key (API_KEY) and database URL (DATABASE_URL) set up in a .env or settings.yaml file in the main project folder.

## 3. Usage

The basic command to run a search is:

python scripts/demo_retrieval.py --query "your query here"


If you want to limit the number of results you get (the default is 10), you can add the --limit argument:

python scripts/demo_retrieval.py --query "..." --limit 5


# 4. Example Queries to Try

Here are some great examples to test how well the semantic search works:

"Terra UST depeg"

"LUNA price crash"

"Bitcoin ETF approval"

"Ethereum merge"

## 5. Sample Output

Here is what your terminal should look like when a search is successful:

Starting demo with the following parameters:
- Request : Bitcoin ETF approval
- Limit   : 3 articles
- Model   : qwen3-embedding

[1/3] Connecting to PostgreSQL database...
✅ Connected and pgvector enabled.

[2/3] Generating search vector...
✅ Success! Vector retrieved (Dimension: 4096)

[3/3] Searching and displaying similar articles...
✅ SQL search latency: 34.12 ms (using HNSW index)

================================================================================
🏆 TOP 3 RESULTS FOR: 'Bitcoin ETF approval'
================================================================================
[88.4% Match] 📄 SEC Officially Approves Spot Bitcoin ETFs
📝 The Securities and Exchange Commission has officially approved the first spot Bitcoin exchange-traded...
📅 2024-01-10 15:45:00+00:00 | 📰 CryptoDaily | 🏷️  [BTC]
--------------------------------------------------------------------------------
[82.1% Match] 📄 What the Bitcoin ETF Means for Crypto Markets
📝 With the landmark approval of several Bitcoin ETFs, institutional investors are finally stepping into...
📅 2024-01-11 09:30:00+00:00 | 📰 MarketWatch | 🏷️  [BTC, ETH]
--------------------------------------------------------------------------------
[79.5% Match] 📄 Fake SEC Tweet Causes Bitcoin Price Rollercoaster
📝 A compromised social media account led to a premature announcement of the Bitcoin ETF approval, causi...
📅 2024-01-09 21:15:00+00:00 | 📰 CoinDesk | 🏷️  [BTC]
--------------------------------------------------------------------------------

🔒 Cleanup: Database connection closed properly.


## 6. Performance

This tool is built to be super fast. Because we use an HNSW index (Hierarchical Navigable Small World) on the vectors in PostgreSQL, the search response time (latency) should always be under 50ms (<50ms), even with a lot of data.