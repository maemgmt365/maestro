# MAESTRO Terminal

A single-operator trading terminal that treats **the exit as the product**.
Every position must carry a written exit card before it can be logged, and
the headline metric is *exit efficiency* — how much of each trade's peak
unrealized gain you actually captured.

Built with Streamlit on top of a small SQLite store and a broker shim that
runs in mock mode out of the box (no credentials required).

## What it does

- **Dashboard** — exit-efficiency headline, open/closed counts, live level
  alerts, and current broker positions.
- **Board** — the whiteboard, digitized: per-ticker chart levels (target
  zones, take-profit, invalidation) with live proximity readouts.
- **New trade (gate)** — a hard gate. Greeks "lights" flag bad setups, red
  lights demand a typed override reason, and the save button stays locked
  until a complete exit card exists. A vehicle selector recommends
  shares / buy call / sell put and explains why.
- **Journal** — close trades with peak-gain and drawdown inputs so exit
  efficiency is computed automatically; review closed trades in a table.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens in **mock mode** using a July 2, 2026 data snapshot, so it is
fully usable with no keys. A local `maestro.db` is created on first run.

## Going live (Schwab)

Create a `.env` (or export the vars) with your Charles Schwab Trader API
credentials, then set the mode:

```bash
MAESTRO_MODE=live
SCHWAB_APP_KEY=your_app_key
SCHWAB_APP_SECRET=your_app_secret
```

Then implement the `_fetch_live_*` helpers in `core/schwab_client.py`
(marked with TODOs) to map Schwab responses into the shapes the app expects.
Until those are wired up, live mode fails loudly rather than returning
empty data.

## Layout

```
app.py                     Streamlit UI (Dashboard / Board / Gate / Journal)
core/
  __init__.py
  db.py                    SQLite persistence + exit-efficiency math
  schwab_client.py         Broker shim (mock snapshot / live stubs)
  exit_engine.py           Level proximity + board alerts
  vehicle_selector.py      Greeks lights + vehicle recommender
requirements.txt
```

## Notes

- Every board level should match something on the daily chart — no
  round-number levels.
- Override reasons are logged permanently and are meant to be replayed in
  the weekly review; the first ten closed trades teach more than any
  backtest.

*v0.1 — mock data. Not financial advice.*
