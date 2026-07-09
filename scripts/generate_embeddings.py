import os
import time
import requests
import psycopg2
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv
from crypto_analyser.config import load_config


def get_unprocessed_articles(cur, limit):
    sql_query = """
        SELECT id, title_description 
        FROM crypto_news 
        WHERE text_embedding IS NULL 
          AND title_description IS NOT NULL 
          AND TRIM(title_description) != '' 
        LIMIT %s;
    """
    
    cur.execute(sql_query, (limit,))
    rows = cur.fetchall()
    
    return [{"id": row[0], "text": row[1]} for row in rows]


def get_embeddings(texts, api_url, api_key, max_attempts=3): 
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen3-embedding", 
        "input": texts
    }
    
    print(f"[API] Requesting vectors for {len(texts)} articles...")
    
    for attempt in range(max_attempts):
        try:
            response = requests.post(
                f"{api_url}/embeddings",
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status() 
            
            data = response.json()
            vecteurs = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
            return vecteurs
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                wait = int(e.response.headers.get("Retry-After", 10))
                print(f"Rate limit reached (429). Waiting for {wait} seconds... (Attempt {attempt + 1}/{max_attempts})")
                time.sleep(wait)
            else:
                print(f"Unexpected API error: {e}")
                break 
        except Exception as e:
            print(f"Network error: {e}")
            break
            
    return None


def update_articles_with_vectors(cur, ids, vectors):
    data_to_update = list(zip(vectors, ids))
    cur.executemany("UPDATE crypto_news SET text_embedding = %s WHERE id = %s;", data_to_update)


def main():
    print("Connecting to PostgreSQL...")
    
    load_dotenv()
    config = load_config()
    
    api_url = config["api_keys"]["llm_api_url"]
    api_key = config["api_keys"]["llm_api_key"]
    db_connection_string = os.getenv("DATABASE_URL")
    
    conn = psycopg2.connect(db_connection_string)
    register_vector(conn)
    cur = conn.cursor()

    batch_size = 20
    total_processed = 0

    try:
        while True:
            articles = get_unprocessed_articles(cur, limit=batch_size)
            
            if not articles:
                print("Processing complete. No pending articles found.")
                break
            
            texts = [a["text"] for a in articles]
            ids = [a["id"] for a in articles]
            vectors = get_embeddings(texts, api_url, api_key)

            if not vectors:
                print("Failed to fetch embeddings from API. Stopping the script.")
                break 
                
            update_articles_with_vectors(cur, ids, vectors)
            conn.commit()
            
            total_processed += len(articles)
            print(f"Progress: {total_processed} articles updated.")
            
    except KeyboardInterrupt:
        print("\nScript stopped manually.")
    finally:
        cur.close()
        conn.close()
        print("Disconnected from the database.")


if __name__ == "__main__":
    main()