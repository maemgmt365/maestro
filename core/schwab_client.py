"""Broker interface for MAESTRO Terminal.

Two modes, chosen by the MAESTRO_MODE env var:

  * mock  (default) — returns a fixed July 2, 2026 snapshot so the whole
    app is usable with zero credentials.
  * live            — talks to the Charles Schwab Trader API. Wire your
    real calls into the marked TODO sections once keys are in .env.

Keeping every broker call behind this thin shim means the Streamlit layer
never knows or cares whether the data is real.
"""
import os

# ---------------------------------------------------------------- MODE
def is_live():
    """True when configured for live Schwab data AND keys are present."""
    if os.environ.get("MAESTRO_MODE", "mock").lower() != "live":
        return False
    return bool(os.environ.get("SCHWAB_APP_KEY") and
                os.environ.get("SCHWAB_APP_SECRET"))


# ------------------------------------------------------------ MOCK DATA
# A believable book for a themed swing/options screener. Prices are the
# July 2, 2026 snapshot referenced in the app caption.
_MOCK_POSITIONS = [
    {"ticker": "NVDA", "qty": 200,  "avg_price": 1042.10, "last": 1121.44,
     "mkt_value": 224288.0, "unreal_pl": 15868.0, "account": "taxable"},
    {"ticker": "MU",   "qty": 400,  "avg_price": 138.55,  "last": 151.02,
     "mkt_value": 60408.0,  "unreal_pl": 4988.0,  "account": "taxable"},
    {"ticker": "VST",  "qty": 150,  "avg_price": 172.30,  "last": 168.11,
     "mkt_value": 25216.5,  "unreal_pl": -628.5,  "account": "IRA"},
    {"ticker": "RKLB", "qty": 1000, "avg_price": 24.80,   "last": 29.66,
     "mkt_value": 29660.0,  "unreal_pl": 4860.0,  "account": "taxable"},
    {"ticker": "GLD",  "qty": 120,  "avg_price": 241.90,  "last": 255.73,
     "mkt_value": 30687.6,  "unreal_pl": 1659.6,  "account": "IRA"},
]

# IV rank (0–100) snapshot used to pre-fill the greeks lights.
_MOCK_IV_RANK = {
    "NVDA": 58, "MU": 71, "VST": 44, "RKLB": 82,
    "GLD": 22, "SMCI": 77, "SPY": 18,
}


# --------------------------------------------------------------- QUERIES
def get_positions():
    """List of position dicts for the Dashboard table."""
    if is_live():
        # TODO(live): call Schwab /accounts/{hash}/positions and map fields
        # into the same shape as _MOCK_POSITIONS below.
        return _fetch_live_positions()
    return _MOCK_POSITIONS


def get_iv_rank(ticker):
    """IV rank (0–100) for a ticker, or None if unknown.

    Used only to pre-fill the gate form — the user can always override.
    """
    if not ticker:
        return None
    ticker = ticker.upper().strip()
    if is_live():
        # TODO(live): derive IV rank from Schwab option chain / vol history.
        return _fetch_live_iv_rank(ticker)
    return _MOCK_IV_RANK.get(ticker)


def get_last(ticker):
    """Last price for a ticker, or None. Consumed by exit_engine.proximity."""
    if not ticker:
        return None
    ticker = ticker.upper().strip()
    if is_live():
        # TODO(live): call Schwab /marketdata/{symbol}/quotes.
        return _fetch_live_quote(ticker)
    for p in _MOCK_POSITIONS:
        if p["ticker"] == ticker:
            return p["last"]
    return None


# --------------------------------------------------- LIVE STUBS (Schwab)
# These raise until real integration is wired up, so a half-configured
# live mode fails loudly instead of silently returning empty data.
def _client():
    raise NotImplementedError(
        "Live Schwab client not wired yet. Add SCHWAB_APP_KEY / "
        "SCHWAB_APP_SECRET to .env and implement the _fetch_live_* helpers.")


def _fetch_live_positions():
    _client()


def _fetch_live_iv_rank(ticker):
    _client()


def _fetch_live_quote(ticker):
    _client()
