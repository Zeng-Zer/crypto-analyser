import psycopg2
import json
from pathlib import Path

ARCHIVE_DIR = Path(__file__).parent
DB_DSN = "host=100.107.186.61 port=5432 dbname=crypto_analyser user=postgres password=postgres"
def find_json_files(base_dir):
    files = []
    for d in base_dir.rglob('*.json'):
        path_str = str(d)
        if "v2" in path_str or "index" in path_str:
            continue
        files.append(d)
    return files

def clean_value(val):
    if val == 'NULL': 
        return None
    else : 
        return val

def extract_article(raw: dict, date: str) -> dict:
    return {
        "date": date,
        "title": clean_value(raw.get("title")),
        "link": clean_value(raw.get("link")),
        "description": clean_value(raw.get("description")),
        "pub_date": clean_value(raw.get("pubDate")),
        "source": clean_value(raw.get("source")),
        "category": clean_value(raw.get("category")),
        "currencies": raw.get("currencies", []),
        "sentiment": clean_value(raw.get("sentiment")),
        "timeago": clean_value(raw.get("timeAgo")),
    }

def parse_file(path: Path) -> tuple[str, list[dict]]:
    with open(path, 'r', encoding='utf-8') as f:
       data = json.load(f)
    date = data["date"]
    articles = [extract_article(a, date) for a in data["articles"]]
    return date, articles

CREATE_TABLE_SQL = """
CREATE EXTENSION IF NOT EXISTS vector; 
CREATE TABLE IF NOT EXISTS crypto_news(
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    link TEXT NOT NULL UNIQUE,
    date_pub TIMESTAMPTZ,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    tickers TEXT[] NOT NULL,
    combo TEXT GENERATED ALWAYS AS (Title || ' ' || COALESCE(Description, '' )) STORED,
    research tsvector GENERATED ALWAYS AS (to_tsvector('english', Title || ' ' || COALESCE(Description, ''))) STORED,
    sentiment VARCHAR(7) NULL,
    timeago TEXT NOT NULL
); 
"""

INSERT_SQL = """ 
INSERT INTO crypto_news (title, description, link, date_pub, source, category, tickers, sentiment, timeago) 
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) 
ON CONFLICT (link) DO NOTHING;
"""

def init_db(conn):
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
        conn.commit()

def insert_articles(conn, articles: list[dict]):
    with conn.cursor() as cur:
        for article in articles:
            valeurs = (
                article["title"],
                article["description"],
                article["link"],
                article["pub_date"],
                article["source"],
                article["category"],
                article["currencies"],
                article["sentiment"],
                article["timeago"],
            )
            cur.execute(INSERT_SQL, valeurs)

def verify_counts(conn, expected: int):
    with conn.cursor() as cur:
       cur.execute("SELECT COUNT(*) FROM crypto_news")
       actual = cur.fetchone()[0]
       print(f"Expected: {expected}, Actual: {actual}")
    assert expected == actual, "MISMATCH!"

def main():
    files = find_json_files(ARCHIVE_DIR)
    print(f"Found {len(files)} JSON files")

    conn = psycopg2.connect(DB_DSN)
    init_db(conn)

    total_articles = 0
    for f in files:
        date, articles = parse_file(f)
        insert_articles(conn, articles)
        total_articles += len(articles)
        print(f"  {date}: {len(articles)} articles insérés/vérifiés")
    conn.commit()  

    verify_counts(conn, total_articles)
    conn.close()
    
if __name__ == "__main__":
    main()