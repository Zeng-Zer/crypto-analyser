import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from dotenv import load_dotenv, find_dotenv
from pgvector.psycopg2 import register_vector

# Load environment variables
load_dotenv(find_dotenv(), override=True)

def get_embedding(text: str) -> list[float]:
    """Get the embedding vector from the API."""
    # Simplified config loading: trusting the .env values directly
    api_url = os.getenv("api_url")
    api_key = os.getenv("api_key") 
    
    full_url = f"{api_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": text,
        "model": "qwen3-embedding"
    }
    
    try:
        response = requests.post(full_url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        embedding = response.json()["data"][0]["embedding"]
        
        # Keep the 2000 cut for Postgres HNSW limits
        return embedding[:2000]
        
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API error: {e}")

def retrieve_relevant_news(
    anomaly_timestamp: datetime,
    ticker: str,
    top_k: int = 10,
    window_hours: int = 12,
    conn=None,
    dsn: str = None,
    rrf_k: int = 60,
) -> list[dict]:
    """Fetch relevant articles using vector and text search (RRF)."""
    
    start_time = anomaly_timestamp - timedelta(hours=window_hours)
    end_time = anomaly_timestamp + timedelta(hours=window_hours)
    
    # 1. Vector query (Long sentence for the AI model)
    vector_query = f"{ticker} crash price anomaly crypto news"
    raw_vector = get_embedding(vector_query)
    
    # 2. Text query (Specific keywords for Postgres text search)
    text_query = f"{ticker} crash collapse depeg"
    
    sql = """
        WITH ranked AS (
            SELECT 
                id, title, description, date_pub, source, tickers,
                -- Vector rank
                ROW_NUMBER() OVER (
                    ORDER BY ((((ai_emb)::real[])[1:2000])::vector(2000)) <=> %(query_vector)s::vector ASC
                ) AS rank_v,
                -- Text rank using websearch_to_tsquery for better matching
                ROW_NUMBER() OVER (
                    ORDER BY ts_rank(research, websearch_to_tsquery('english', %(text_query)s)) DESC
                ) AS rank_t
            FROM crypto_news
            WHERE 
                tickers @> ARRAY[%(ticker)s]::text[]
                AND date_pub BETWEEN %(start_time)s AND %(end_time)s
                AND ai_emb IS NOT NULL
        )
        SELECT 
            id, title, description, date_pub, source, tickers,
            (1.0 / (%(rrf_k)s + rank_v) + 1.0 / (%(rrf_k)s + rank_t)) AS rrf_score
        FROM ranked
        ORDER BY rrf_score DESC
        LIMIT %(top_k)s;
    """
    
    # Pass the raw_vector list directly, no more string formatting
    params = {
        "query_vector": raw_vector,
        "text_query": text_query,
        "ticker": ticker,
        "start_time": start_time,
        "end_time": end_time,
        "rrf_k": rrf_k,
        "top_k": top_k
    }

    own_conn = False
    if conn is None:
        if dsn is None:
            raise ValueError("You must provide either 'conn' or 'dsn'.")
        conn = psycopg2.connect(dsn)
        own_conn = True

    try:
        # Tell psycopg2 how to handle vector types
        register_vector(conn)
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        if own_conn and conn is not None and not conn.closed:
            conn.close()