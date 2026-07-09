#!/usr/bin/env python3
"""Run anomaly-window retrieval and verify ticker/time invariants."""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time, timedelta, timezone

import psycopg2
from dotenv import load_dotenv

from crypto_analyser._paths import repo_root
from crypto_analyser.rag.retrieval import retrieve_relevant_news


def main(argv: list[str] | None = None) -> int:
    load_dotenv(repo_root() / ".env")
    parser = argparse.ArgumentParser(description="Test hybrid historical-news retrieval")
    parser.add_argument("--ticker", required=True, help="Crypto ticker, for example LUNA")
    when = parser.add_mutually_exclusive_group(required=True)
    when.add_argument("--date", type=date.fromisoformat, help="UTC date; searches around noon")
    when.add_argument("--timestamp", type=datetime.fromisoformat, help="ISO-8601 anomaly timestamp")
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args(argv)

    timestamp = args.timestamp or datetime.combine(args.date, time(12), timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    required = {name: os.getenv(name) for name in ("DATABASE_URL", "LLM_API_URL", "LLM_API_KEY")}
    missing = [name for name, value in required.items() if not value]
    if missing:
        parser.error(f"required environment variables missing: {', '.join(missing)}")

    try:
        rows = retrieve_relevant_news(
            timestamp,
            args.ticker,
            top_k=args.top_k,
            dsn=required["DATABASE_URL"],
            api_url=required["LLM_API_URL"],
            api_key=required["LLM_API_KEY"],
        )
    except (psycopg2.Error, RuntimeError, ValueError) as exc:
        print(f"Retrieval failed: {exc}")
        return 1

    ticker = args.ticker.strip().upper()
    start_time, end_time = timestamp - timedelta(hours=12), timestamp + timedelta(hours=12)
    valid = bool(rows)
    print(f"Retrieved {len(rows)} {ticker} articles around {timestamp.isoformat()}")
    if not rows:
        print("No matching articles found.")
    for index, row in enumerate(rows, 1):
        ticker_ok = ticker in row["tickers"]
        time_ok = start_time <= row["date_pub"] <= end_time
        valid &= ticker_ok and time_ok
        print(
            f"{index}. ticker={'PASS' if ticker_ok else 'FAIL'} "
            f"time={'PASS' if time_ok else 'FAIL'} "
            f"score={row['rrf_score']:.6f} {row['title']}"
        )

    if ticker == "LUNA" and rows:
        relevant = any(
            term in f"{row['title']} {row.get('description') or ''}".lower()
            for row in rows
            for term in ("luna", "terra", "ust", "depeg")
        )
        valid &= relevant
        print(f"LUNA relevance={'PASS' if relevant else 'FAIL'}")
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
