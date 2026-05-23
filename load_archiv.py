import psycopg2
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ARCHIVE_DIR = Path(__file__).parent
DB_DSN = os.environ.get("DATABASE_URL")

def find_json_files(base_dir):
    files = []
    for d in base_dir.rglob('*.json'):
        if "v2" in d.parts or d.name == "index.json":
            continue
        files.append(d)
    return files

def clean_value(val):
    if val == 'NULL': 
        return None
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
    }

def parse_file(path: Path) -> tuple[str, list[dict]]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
           data = json.load(f)
    except json.JSONDecodeError:
        return None, []
    
    if type(data) is not dict or "date" not in data or "articles" not in data:
        return None, []
        
    date = data["date"]
    articles = [extract_article(a, date) for a in data["articles"]]
    return date, articles

INSERT_SQL = """ 
INSERT INTO crypto_news (title, description, link, date_pub, source, category, tickers, sentiment) 
VALUES (%s,%s,%s,%s,%s,%s,%s,%s) 
ON CONFLICT (link) DO NOTHING;
"""

def insert_articles(conn, articles: list[dict]) -> int:
    inserted_count = 0
    with conn.cursor() as cur:
        for article in articles:

            if not article["title"] or not article["link"]:
                continue

            valeurs = (
                article["title"],
                article["description"],
                article["link"],
                article["pub_date"],
                article["source"],
                article["category"],
                article["currencies"],
                article["sentiment"],
            )
            cur.execute(INSERT_SQL, valeurs)
            inserted_count += cur.rowcount 
            
    return inserted_count


def main():
    files = find_json_files(ARCHIVE_DIR)
    print(f"Found {len(files)} JSON files to process.")

    conn = psycopg2.connect(DB_DSN)

    total_attempted = 0
    total_inserted = 0

    for f in files:
        date, articles = parse_file(f)
        if date is None:
            continue
           
        inserted_this_file = insert_articles(conn, articles)
       
        conn.commit()  

        total_attempted += len(articles)
        total_inserted += inserted_this_file
        
        
    print(f"\nFinal result : {total_inserted} artciles actually added to the database based on {total_attempted} readed.")
    conn.close()

if __name__ == "__main__":
    main()
