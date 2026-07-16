"""Command-line interface for the crypto analyser."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import load_dotenv

from crypto_analyser._paths import repo_root
from crypto_analyser.constants import (
    FUNDING_RATE_THRESHOLD,
    LLM_MODEL,
    MIN_CONSECUTIVE,
    OI_CHANGE_THRESHOLD,
    WINDOW_HOURS,
    ZSCORE_THRESHOLD,
)
from crypto_analyser.pipeline import VALID_MODES, run_pipeline
from crypto_analyser.rag.archive_loader import load_archive
from crypto_analyser.rag.database import initialize_database
from crypto_analyser.rag.embeddings import DEFAULT_MODEL, generate_pending_embeddings
from crypto_analyser.rag.retrieval import search_news


def _env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _run(args: argparse.Namespace) -> None:
    path = run_pipeline(
        args.symbol,
        args.start,
        args.end,
        args.mode,
        data_dir=args.data_dir,
        skip_download=args.skip_download,
        force_download=args.force_download,
        window_hours=args.window_hours,
        threshold=args.threshold,
        min_consecutive=args.min_consecutive,
        funding_rate_threshold=args.funding_rate_threshold,
        oi_change_threshold=args.oi_change_threshold,
        llm_model=args.model,
    )
    print(path)


def _init_news(_args: argparse.Namespace) -> None:
    initialize_database(_env("DATABASE_URL"))
    print("Database initialized.")


def _load_news(args: argparse.Namespace) -> None:
    archive_dir = args.archive_dir or (Path(os.environ["NEWS_ARCHIVE_DIR"]) if os.getenv("NEWS_ARCHIVE_DIR") else None)
    if archive_dir is None:
        raise RuntimeError("--archive-dir or NEWS_ARCHIVE_DIR is required")
    archive_dir = archive_dir.expanduser().resolve()
    if not archive_dir.is_dir():
        raise RuntimeError(f"archive directory not found: {archive_dir}")
    attempted, inserted = load_archive(archive_dir, _env("DATABASE_URL"))
    print(f"Read {attempted} articles; inserted {inserted} new rows.")


def _search_news(args: argparse.Namespace) -> None:
    rows = search_news(
        args.query,
        _env("DATABASE_URL"),
        _env("LLM_API_URL"),
        _env("LLM_API_KEY"),
        limit=args.limit,
        model=args.model,
    )
    for index, row in enumerate(rows, 1):
        similarity = max(0.0, min(1.0, 1.0 - float(row["distance"])))
        print(f"{index}. [{similarity:.1%}] {row['title']} — {row['date_pub']} ({row['source']})")


def _embed_news(args: argparse.Namespace) -> None:
    if args.batch_size < 1 or args.max_attempts < 1:
        raise ValueError("--batch-size and --max-attempts must be positive")
    count = generate_pending_embeddings(
        _env("DATABASE_URL"),
        _env("LLM_API_URL"),
        _env("LLM_API_KEY"),
        args.model,
        args.batch_size,
        args.max_attempts,
        args.start,
        args.end,
        args.query,
    )
    print(f"Embedded {count} articles.")


def _evaluate(args: argparse.Namespace) -> None:
    from crypto_analyser.evaluation import write_evaluation

    try:
        path = write_evaluation(
            args.symbol,
            args.start,
            args.end,
            _env("DATABASE_URL"),
            args.judge_model,
            _env("LLM_API_URL"),
            _env("LLM_API_KEY"),
            args.embedding_model,
            args.data_dir,
        )
    except ImportError as exc:
        raise RuntimeError("evaluation dependencies missing; install crypto-analyser[evaluation]") from exc
    except Exception as exc:
        raise RuntimeError(f"evaluation failed: {exc}") from exc
    print(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crypto-analyser", description="Historical crypto anomaly analysis")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Run historical anomaly analysis")
    run.add_argument("--symbol", default="LUNAUSDT")
    run.add_argument("--start", required=True)
    run.add_argument("--end", required=True)
    run.add_argument("--mode", choices=sorted(VALID_MODES), default="derivatives_only")
    run.add_argument("--data-dir", type=Path, default=Path("data"))
    run.add_argument("--window-hours", type=float, default=WINDOW_HOURS)
    run.add_argument("--threshold", type=float, default=ZSCORE_THRESHOLD)
    run.add_argument("--min-consecutive", type=int, default=MIN_CONSECUTIVE)
    run.add_argument("--funding-rate-threshold", type=float, default=FUNDING_RATE_THRESHOLD)
    run.add_argument("--oi-change-threshold", type=float, default=OI_CHANGE_THRESHOLD)
    run.add_argument("--model", default=os.getenv("LLM_MODEL", LLM_MODEL))
    run.add_argument("--skip-download", action="store_true")
    run.add_argument("--force-download", action="store_true")
    run.set_defaults(handler=_run)

    news = commands.add_parser("news", help="Manage historical news data")
    news_commands = news.add_subparsers(dest="news_command", required=True)

    init = news_commands.add_parser("init", help="Initialize PostgreSQL schema")
    init.set_defaults(handler=_init_news)

    load = news_commands.add_parser("load", help="Load JSON news archive into PostgreSQL")
    load.add_argument("--archive-dir", type=Path)
    load.set_defaults(handler=_load_news)

    embed = news_commands.add_parser("embed", help="Generate embeddings for pending news")
    embed.add_argument("--batch-size", type=int, default=20)
    embed.add_argument("--max-attempts", type=int, default=3)
    embed.add_argument("--model", default=os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL))
    embed.add_argument("--start")
    embed.add_argument("--end")
    embed.add_argument("--query")
    embed.set_defaults(handler=_embed_news)

    search = news_commands.add_parser("search", help="Search embedded historical news")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--model", default=os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL))
    search.set_defaults(handler=_search_news)

    evaluate = commands.add_parser("evaluate", help="Evaluate completed evidence modes")
    evaluate.add_argument("--symbol", default="LUNAUSDT")
    evaluate.add_argument("--start", default="2022-05-07")
    evaluate.add_argument("--end", default="2022-05-11")
    evaluate.add_argument("--judge-model", default=os.getenv("RAGAS_JUDGE_MODEL", "glm-5.2-short"))
    evaluate.add_argument("--embedding-model", default=os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL))
    evaluate.add_argument("--data-dir", type=Path, default=Path("data"))
    evaluate.set_defaults(handler=_evaluate)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(repo_root() / ".env")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    try:
        args = build_parser().parse_args(argv)
        handler: Any = args.handler
        handler(args)
    except (OSError, psycopg2.Error, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
