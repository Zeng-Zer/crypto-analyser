#!/usr/bin/env python3
import argparse
import sys
import os
import requests
import time
import psycopg2
from pgvector.psycopg2 import register_vector
from pathlib import Path
from dotenv import load_dotenv

from rich.console import Console
from rich.panel import Panel

console = Console()

script_dir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=script_dir.parent / '.env')

def load_config(yaml_path: Path) -> dict:

    if not yaml_path.exists():
        return {}
    try:
        import yaml
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        def expand_vars(item):
            if isinstance(item, dict):
                return {k: expand_vars(v) for k, v in item.items()}
            elif isinstance(item, list):
                return [expand_vars(v) for v in item]
            elif isinstance(item, str):
                expanded = os.path.expandvars(item)
                if expanded == item:
                    if item.upper() in os.environ:
                        return os.environ[item.upper()]
                    elif item.lower() in os.environ:
                        return os.environ[item.lower()]
                return expanded
            return item

        return expand_vars(config)

    except ImportError:
        console.print("[yellow]⚠️ Warning: 'pyyaml' library is not installed. Ignoring settings.yaml.[/yellow]")
        return {}
    except Exception as e:
        console.print(f"[yellow]⚠️ Error reading settings.yaml: {e}[/yellow]")
        return {}

def parse_args(config: dict):

    parser = argparse.ArgumentParser(description="CLI Demo for crypto vector search")
    
    parser.add_argument("--query", required=True, type=str, help="The search query (e.g., 'Terra UST depeg')")
    
    default_limit = config.get("limit", 10)
    parser.add_argument("--limit", type=int, default=default_limit, help=f"Number of results (default: {default_limit})")
    
    api_keys_section = config.get("api_keys", {})
    
    default_url = api_keys_section.get("llm_api_url") or os.getenv("API_URL") or os.getenv("api_url", "http://localhost:8000/v1")
    parser.add_argument("--api-url", "--api_url", dest="api_url", type=str, default=default_url, help="AI model base URL")
    
    default_model = config.get("model") or os.getenv("EMBEDDING_MODEL") or os.getenv("embedding_model", "qwen3-embedding")
    parser.add_argument("--model", type=str, default=default_model, help="Embedding model name")
    
    return parser.parse_args()

def embed_query(query_text: str, api_url: str, api_key: str, model_name: str) -> list:

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": query_text,
        "model": model_name
    }

    full_url = f"{api_url.rstrip('/')}/embeddings"

    try:
        response = requests.post(full_url, json=payload, headers=headers, timeout=10)
        response.raise_for_status() 
        data = response.json()
        return data["data"][0]["embedding"]

    except requests.exceptions.ConnectionError:
        raise RuntimeError("Failed to reach the embedding API. Check the URL or your connection.")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "Unknown"
        raise RuntimeError(f"HTTP Error (Code {status}). Details: {e}")
    except requests.exceptions.Timeout:
        raise RuntimeError("The API took too long to respond (Timeout).")
    except Exception as e:
        raise RuntimeError(f"Unexpected API error: {e}")

def search_similar(conn, query_vector: list, limit: int):

    sql = """
        SELECT id, title, date_pub, source, tickers, title_description,
               ai_emb <=> %s::vector AS distance
        FROM crypto_news
        WHERE ai_emb IS NOT NULL
        ORDER BY ai_emb <=> %s::vector
        LIMIT %s;
    """
    params = (query_vector, query_vector, limit)
    
    with conn.cursor() as cur:
        cur.execute("SET enable_seqscan = off;")
        
        start = time.perf_counter()
        cur.execute(sql, params)
        rows = cur.fetchall()
        latency_ms = (time.perf_counter() - start) * 1000
        
        cur.execute("SET enable_seqscan = on;")
        
    return rows, latency_ms

def render_results(rows: list, latency: float, query: str):

    console.print(f"[bold cyan]🏆 TOP {len(rows)} RESULTS FOR: '{query}'[/bold cyan]\n")
    
    for row in rows:
        article_id, title, date_pub, source, tickers, title_desc, distance = row
        
        similarity = max(0.0, min(1.0, 1 - distance))
        
        if title_desc:
            desc_only = title_desc[len(title):].strip() if title and title_desc.startswith(title) else title_desc
            
            if desc_only:
                desc_clean = desc_only.replace("\n", " ").strip()
                snippet = desc_clean[:120] + "..." if len(desc_clean) > 120 else desc_clean
            else:
                snippet = "No description available."
        else:
            snippet = "No description available."
            
        tickers_str = f"[{', '.join(tickers)}]" if tickers else "[]"
        
        card_content = (
            f"[bold white]{title}[/bold white]\n\n"
            f"[grey74]{snippet}[/grey74]\n\n"
            f"📅 [cyan]{date_pub}[/cyan] | 📰 [yellow]{source}[/yellow] | 🏷️  [green]{tickers_str}[/green]"
        )
        
        panel = Panel(
            card_content, 
            title=f"[bold green]{similarity:.1%} Match[/bold green]", 
            title_align="left",
            border_style="blue"
        )
        console.print(panel)

    console.print(f"\n📊 [bold green]Performance: latency {latency:.0f}ms | HNSW index | {len(rows)} rows[/bold green]")

def main():
    config_path = script_dir.parent / 'config' / 'settings.yaml'
    config = load_config(config_path)
    args = parse_args(config)
    
    api_keys_section = config.get("api_keys", {})
    api_key = api_keys_section.get("llm_api_key") or os.getenv("API_KEY") or os.getenv("api_key", "dummy_key")
    
    db_url = config.get("database_url") or config.get("db_url") or os.getenv("DATABASE_URL") or os.getenv("database_url")
    
    if not db_url:
        console.print("[bold red]❌ Error: DATABASE_URL not found in .env or settings.yaml[/bold red]")
        sys.exit(1)

    console.print(f"Starting demo with query: [bold]'{args.query}'[/bold] (Limit: {args.limit})")

    conn = None 

    try:
        conn = psycopg2.connect(db_url)
        register_vector(conn)
        
        try:
            vec = embed_query(args.query, args.api_url, api_key, args.model)
            rows, latency = search_similar(conn, vec, args.limit)
            render_results(rows, latency, args.query)
            
        except RuntimeError as e:
            console.print(f"\n[bold red]❌ API Error:[/bold red] {e}")
            sys.exit(1) 
        except Exception as e:
            console.print(f"\n[bold red]❌ Unexpected error during search:[/bold red] {e}")
            sys.exit(1)
            
    except psycopg2.Error as e:
        console.print(f"\n[bold red]❌ Database connection error:[/bold red] {e}")
        sys.exit(1)
        
    finally:
        if conn is not None and not conn.closed:
            conn.close()

if __name__ == "__main__":
    main()