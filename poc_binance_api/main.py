#!/usr/bin/env python
"""Download LUNAUSDT derivatives data from data.binance.vision.

6 months pre-crash (Nov 2021 - Apr 2022) + crash month (May 2022).
Uses only urllib - no external dependencies.
"""
import urllib.request
import urllib.error
import zipfile
import io
import time
from pathlib import Path
from datetime import date, timedelta

BASE_URL = "https://data.binance.vision/"
DESTINATION = Path(__file__).parent / "data"

# Configuration
SYMBOL = "LUNAUSDT"
START_MONTH = "2021-11"  # Nov 2021
END_MONTH = "2022-05"    # May 2022 (crash)
START_DATE = date(2021, 11, 1)
END_DATE = date(2022, 5, 31)


def download_and_extract(url: str, save_path: Path) -> bool:
    """Download zip file and extract CSV."""
    if save_path.exists():
        print(f"  [exists] {save_path.name}")
        return True

    save_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        print(f"  [download] {url}")
        response = urllib.request.urlopen(url)
        zip_data = response.read()
        
        # Extract CSV from zip
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            csv_name = zf.namelist()[0]  # Only one file in zip
            csv_data = zf.read(csv_name)
            with open(save_path, "wb") as f:
                f.write(csv_data)
        
        print(f"  [saved] {save_path.name}")
        time.sleep(0.5)
        return True
    
    except urllib.error.HTTPError as e:
        print(f"  [error] HTTP {e.code}: {url}")
        return False


def months_range(start: str, end: str) -> list[str]:
    """Generate months between start and end (YYYY-MM format)."""
    start_year, start_month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    
    months = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        months.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def dates_range(start: date, end: date) -> list[str]:
    """Generate dates between start and end (YYYY-MM-DD format)."""
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def download_klines():
    """Download klines (1m interval, monthly archives)."""
    print("\n[1] Klines (1m, monthly)")
    months = months_range(START_MONTH, END_MONTH)
    
    for month in months:
        url = f"{BASE_URL}data/futures/um/monthly/klines/{SYMBOL}/1m/{SYMBOL}-1m-{month}.zip"
        save_path = DESTINATION / "klines" / f"{SYMBOL}-1m-{month}.csv"
        download_and_extract(url, save_path)


def download_funding_rate():
    """Download funding rate (8h interval, monthly archives)."""
    print("\n[2] Funding Rate (8h, monthly)")
    months = months_range(START_MONTH, END_MONTH)
    
    for month in months:
        url = f"{BASE_URL}data/futures/um/monthly/fundingRate/{SYMBOL}/{SYMBOL}-fundingRate-{month}.zip"
        save_path = DESTINATION / "funding_rate" / f"{SYMBOL}-fundingRate-{month}.csv"
        download_and_extract(url, save_path)


def download_metrics():
    """Download metrics (open interest, 5min interval, daily archives)."""
    print("\n[3] Metrics (5min, daily)")
    dates = dates_range(START_DATE, END_DATE)
    
    for d in dates:
        url = f"{BASE_URL}data/futures/um/daily/metrics/{SYMBOL}/{SYMBOL}-metrics-{d}.zip"
        save_path = DESTINATION / "metrics" / f"{SYMBOL}-metrics-{d}.csv"
        download_and_extract(url, save_path)


def main():
    print("=" * 50)
    print(f"LUNAUSDT Data Download")
    print(f"Range: {START_MONTH} to {END_MONTH}")
    print("=" * 50)
    
    download_klines()
    download_funding_rate()
    download_metrics()
    
    print("\n" + "=" * 50)
    print("Done. Check data/ directory.")
    print("=" * 50)


if __name__ == "__main__":
    main()
