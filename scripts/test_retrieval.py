#!/usr/bin/env python3
import argparse, sys, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Set up paths and load environment variables
script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(script_dir.parent))
from src.retrieval import retrieve_relevant_news

load_dotenv(dotenv_path=script_dir.parent / '.env')

def get_args():
    parser = argparse.ArgumentParser(description="CLI test for hybrid search.")
    parser.add_argument('--ticker', type=str, required=True, help="Crypto ticker (e.g., LUNA)")
    parser.add_argument('--date', type=str, help="Date format YYYY-MM-DD")
    parser.add_argument('--timestamp', type=str, help="Exact timestamp ISO 8601")
    parser.add_argument('--top-k', type=int, default=10, help="Max results")
    args = parser.parse_args()

    if not args.date and not args.timestamp:
        parser.error("You must provide --date or --timestamp.")

    # Parse date or timestamp to UTC
    if args.timestamp:
        target_time = datetime.fromisoformat(args.timestamp)
    else:
        target_time = datetime.strptime(args.date, "%Y-%m-%d")

    if target_time.tzinfo is None:
        target_time = target_time.replace(tzinfo=timezone.utc)

    return args.ticker, target_time, args.top_k

def main():
    ticker, target_time, top_k = get_args()
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        print("Error: DATABASE_URL not found in .env file.")
        sys.exit(1)

    print(f"--- Searching for {ticker} at {target_time.isoformat()} ---")
    start_time = target_time - timedelta(hours=12)
    end_time = target_time + timedelta(hours=12)

    # Fetch data
    try:
        results = retrieve_relevant_news(
            anomaly_timestamp=target_time,
            ticker=ticker,
            top_k=top_k,
            window_hours=12,
            dsn=db_url
        )
    except Exception as e:
        print(f"Critical error with SQL or API: {e}")
        sys.exit(1)

    # Handle empty results
    if not results:
        print(f"\nInfo: No articles found for {ticker} on this date.")
        sys.exit(0)

    # QA Verification for Sisyphus
    print("\n=== QA VERIFICATION ===")

    keywords = [ticker.lower(), 'crash', 'collapse', 'surge', 'drop']
    
    for i, art in enumerate(results, 1):
        tickers = art.get('tickers', [])
        pub_date = art.get('date_pub')
        
        if pub_date and pub_date.tzinfo is None:
             pub_date = pub_date.replace(tzinfo=timezone.utc)

        title = art.get('title') or ""
        desc = art.get('description') or ""
        content = f"{title} {desc}".lower()

        # Check conditions
        t_pass = "PASS" if ticker in tickers else "FAIL"
        d_pass = "PASS" if start_time <= pub_date <= end_time else "FAIL"
        k_pass = "PASS" if any(kw in content for kw in keywords) else "FAIL"
        k_text = "contains 'Terra'" if k_pass == "PASS" else "missing target keywords"

        # Print results
        print(f"[Ticker check] article {i}: tickers=[{', '.join(tickers)}] {t_pass} {ticker} present")
        print(f"[Time check]   article {i}: pub_date={pub_date.isoformat()} {d_pass} within 12h")
        print(f"[Keyword check] article {i}: {k_text} {k_pass}")

if __name__ == "__main__":
    main()