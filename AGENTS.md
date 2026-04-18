# Agent Instructions for crypto-analyser

## Git Write Actions - MUST CONSULT USER

Before performing ANY git write actions, ask the user for confirmation:

- Creating issues
- Commenting on issues
- Closing issues
- Creating commits
- Pushing to remote
- Creating pull requests
- Any action that modifies the git repository or GitHub

**Ask first. Do not assume permission.**

## Project Context

See `.sisyphus/PROJECT.md` for full project overview.

Key constraints:
- Milestone 1 is entirely batch/historical (no real-time)
- Symbol: LUNAUSDT (not LUNCUSDT)
- Data source: data.binance.vision (API limited to 30 days)
- Two derivatives signals: funding rate + open interest