"""Load historical crypto-news JSON into PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import load_dotenv

from crypto_analyser._paths import repo_root

INSERT_SQL = """
INSERT INTO crypto_news
    (title, description, link, date_pub, source, category, tickers, sentiment)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (link, date_pub) DO NOTHING
"""


def find_json_files(base_dir: Path) -> list[Path]:
    """Return archive JSON files in deterministic order."""
    return sorted(path for path in base_dir.rglob("*.json") if "v2" not in path.parts and path.name != "index.json")


def clean_value(value: Any) -> Any:
    """Normalize archive NULL sentinels and CDATA wrappers."""
    if value is None or value == "NULL":
        return None
    if isinstance(value, str):
        return value.replace("<![CDATA[", "").replace("]]>", "").strip()
    return value


def extract_article(raw: dict[str, Any]) -> dict[str, Any]:
    currencies = raw.get("currencies")
    return {
        "title": clean_value(raw.get("title")),
        "description": clean_value(raw.get("description")),
        "link": clean_value(raw.get("link")),
        "pub_date": clean_value(raw.get("pubDate")),
        "source": clean_value(raw.get("source")) or "unknown",
        "category": clean_value(raw.get("category")) or "general",
        "tickers": [str(item) for item in currencies] if isinstance(currencies, list) else [],
        "sentiment": clean_value(raw.get("sentiment")),
    }


def parse_file(path: Path) -> list[dict[str, Any]]:
    """Parse one daily archive file; malformed files contribute no rows."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
        return []
    return [extract_article(article) for article in data["articles"] if isinstance(article, dict)]


def insert_articles(connection: Any, articles: list[dict[str, Any]]) -> int:
    """Insert valid articles, returning rows added after conflict handling."""
    inserted = 0
    with connection.cursor() as cursor:
        for article in articles:
            if not article["title"] or not article["link"]:
                continue
            cursor.execute(
                INSERT_SQL,
                (
                    article["title"],
                    article["description"],
                    article["link"],
                    article["pub_date"],
                    article["source"],
                    article["category"],
                    article["tickers"],
                    article["sentiment"],
                ),
            )
            inserted += cursor.rowcount
    return inserted


def load_archive(archive_dir: Path, database_url: str) -> tuple[int, int]:
    """Load every daily JSON file, returning ``(articles_read, rows_inserted)``."""
    files = find_json_files(archive_dir)
    attempted = 0
    inserted = 0
    connection = psycopg2.connect(database_url)
    try:
        for path in files:
            articles = parse_file(path)
            attempted += len(articles)
            with connection:
                inserted += insert_articles(connection, articles)
    finally:
        connection.close()
    return attempted, inserted


def main(argv: list[str] | None = None) -> int:
    load_dotenv(repo_root() / ".env")
    parser = argparse.ArgumentParser(description="Load historical crypto-news JSON into PostgreSQL")
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=os.getenv("NEWS_ARCHIVE_DIR"),
        help="Archive root or month directory (default: NEWS_ARCHIVE_DIR)",
    )
    args = parser.parse_args(argv)

    if args.archive_dir is None:
        parser.error("--archive-dir or NEWS_ARCHIVE_DIR is required")
    archive_dir = args.archive_dir.expanduser().resolve()
    if not archive_dir.is_dir():
        parser.error(f"archive directory not found: {archive_dir}")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required")

    attempted, inserted = load_archive(archive_dir, database_url)
    print(f"Read {attempted} articles; inserted {inserted} new rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
