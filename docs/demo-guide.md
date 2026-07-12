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

Starting demo with query: 'Bitcoin ETF approval' (Limit: 3)

🏆 TOP 3 RESULTS FOR: 'Bitcoin ETF approval'

╭─ 59.4% Match ──────────────────────────────────────────────────────────────────╮
│ RT @btsfav: Earn &amp; Buy #bitcoin and crypto -                               │
│                                                                                │
│ No description available.                                                      │
│                                                                                │
│ 📅 2021-02-01 11:15:38+00:00 | 📰 Historical | 🏷️  [STEEM]                     │
╰────────────────────────────────────────────────────────────────────────────────╯
╭─ 57.7% Match ──────────────────────────────────────────────────────────────────╮
│ [ARK Weekly Discussion Thread] - February 01, 2021                             │
│                                                                                │
│ No description available.                                                      │
│                                                                                │
│ 📅 2021-02-01 09:00:23+00:00 | 📰 Historical | 🏷️  [ARK]                       │
╰────────────────────────────────────────────────────────────────────────────────╯
╭─ 55.2% Match ──────────────────────────────────────────────────────────────────╮
│ Tesla CEO Elon Musk: Bitcoin On ‘The Verge Of Broad Acceptance’                │
│                                                                                │
│ Elon Musk, the billionaire founder of Tesla, has said he thinks the            │
│ cryptocurrency bitcoin is on "the verge" of breaking...                        │
│                                                                                │
│ 📅 2021-02-01 06:55:47+00:00 | 📰 Historical | 🏷️  [BTC, XVG]                  │
╰────────────────────────────────────────────────────────────────────────────────╯

📊 Performance: latency 90ms | HNSW index | 3 rows

## 6. Performance

This tool is built to be super fast. Because we use an HNSW index (Hierarchical Navigable Small World) on the vectors in PostgreSQL, the search response time (latency) should always be under 50ms (<50ms), even with a lot of data.