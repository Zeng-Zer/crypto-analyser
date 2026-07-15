#!/usr/bin/env python3
"""Formatted semantic-search demo."""

from __future__ import annotations

import argparse
import os
import time

import psycopg2
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.text import Text

from crypto_analyser._paths import repo_root
from crypto_analyser.rag.embeddings import DEFAULT_MODEL, get_embeddings
from crypto_analyser.rag.retrieval import explain_semantic_search, semantic_search


def main(argv: list[str] | None = None) -> int:
    load_dotenv(repo_root() / ".env")
    parser = argparse.ArgumentParser(description="Search historical crypto news by semantic similarity")
    parser.add_argument("--query", required=True, help="Search text, for example 'Terra UST depeg'")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--model", default=os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL))
    parser.add_argument("--api-url", default=os.getenv("LLM_API_URL"))
    args = parser.parse_args(argv)

    api_key = os.getenv("LLM_API_KEY")
    database_url = os.getenv("DATABASE_URL")
    missing = [
        name
        for name, value in (("DATABASE_URL", database_url), ("LLM_API_URL", args.api_url), ("LLM_API_KEY", api_key))
        if not value
    ]
    if missing:
        parser.error(f"required environment variables missing: {', '.join(missing)}")

    console = Console()
    try:
        vector = get_embeddings([args.query], args.api_url, api_key, model=args.model)[0]
        connection = psycopg2.connect(database_url)
        try:
            plan = explain_semantic_search(connection, vector, args.limit)
            started = time.perf_counter()
            rows = semantic_search(connection, vector, args.limit)
            latency_ms = (time.perf_counter() - started) * 1000
        finally:
            connection.close()
    except (psycopg2.Error, RuntimeError, ValueError) as exc:
        console.print(f"[red]Search failed:[/red] {exc}")
        return 1

    table = Table(title=Text(f"Top {len(rows)} results for {args.query!r}"))
    table.add_column("Match", justify="right")
    table.add_column("Article")
    table.add_column("Published / source")
    table.add_column("Tickers")
    for row in rows:
        description = " ".join((row.get("description") or "").split())
        snippet = description[:117] + "..." if len(description) > 120 else description
        article = Text(row["title"])
        if snippet:
            article.append("\n")
            article.append(snippet, style="dim")
        similarity = max(0.0, min(1.0, 1.0 - float(row["distance"])))
        table.add_row(
            f"{similarity:.1%}",
            article,
            Text(f"{row['date_pub']}\n{row['source']}"),
            Text(", ".join(row.get("tickers") or [])),
        )
    console.print(table)
    plan_type = "HNSW" if "idx_crypto_news_embedding" in plan else "sequential scan"
    console.print(f"Latency: {latency_ms:.0f} ms | plan: {plan_type} | rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
