# LUNAUSDT Data Download

Download historical derivatives data from data.binance.vision for the LUNA crash analysis.

## Usage

```bash
cd poc_binance_api
uv run main.py
```

## Data Downloaded

| Data | Range | Files | Size |
|------|-------|-------|------|
| Klines (1min) | Nov 2021 - May 2022 | 7 monthly | ~26M |
| Funding Rate (8h) | Nov 2021 - May 2022 | 7 monthly | ~28K |
| Open Interest (5min) | Dec 2021 - May 12 2022 | 162 daily | ~4.7M |

Note: Open interest data starts Dec 1, 2021 and ends May 12, 2022 (LUNA delisted after crash).

## Output Structure

```
data/
├── klines/           # 7 CSVs, 1min OHLCV
├── funding_rate/     # 7 CSVs, 8h interval
└── metrics/          # 162 CSVs, 5min open interest
```

## Data Schema

**Klines:**
```
open_time, open, high, low, close, volume, close_time, quote_volume, count, ...
```

**Funding Rate:**
```
calc_time, funding_interval_hours, last_funding_rate
```

**Metrics (Open Interest):**
```
create_time, symbol, sum_open_interest, sum_open_interest_value, count_long_short_ratio, ...
```

## Notes

- Uses Python stdlib only (urllib, zipfile)
- 0.5s rate limit between downloads
- LUNAUSDT = pre-crash symbol
- LUNCUSDT = renamed after crash (no May 2022 data)
