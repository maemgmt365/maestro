"""Broker interface for MAESTRO Terminal.

Two modes, chosen by the MAESTRO_MODE env var:

* mock (default) - returns a fixed July 2, 2026 snapshot so the whole
  app is usable with zero credentials.
* live - talks to the Charles Schwab Trader API via the schwab-py
  library. Add SCHWAB_APP_KEY / SCHWAB_APP_SECRET / SCHWAB_CALLBACK_URL
  to .env and set MAESTRO_MODE=live to enable. The first live call opens
  a browser window for the Schwab OAuth consent screen; after that the
  token is cached to data/schwab_token.json and refreshed automatically.

Keeping every broker call behind this thin shim means the Streamlit layer
never knows or cares whether the data is real.
"""
import os
import warnings
from pathlib import Path

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
    {"ticker": "NVDA", "qty": 200, "avg_price": 1042.10, "last": 1121.44,
     "mkt_value": 224288.0, "unreal_pl": 15868.0, "account": "taxable"},
    {"ticker": "MU", "qty": 400, "avg_price": 138.55, "last": 151.02,
     "mkt_value": 60408.0, "unreal_pl": 4988.0, "account": "taxable"},
    {"ticker": "VST", "qty": 150, "avg_price": 172.30, "last": 168.11,
     "mkt_value": 25216.5, "unreal_pl": -628.5, "account": "IRA"},
    {"ticker": "RKLB", "qty": 1000, "avg_price": 24.80, "last": 29.66,
     "mkt_value": 29660.0, "unreal_pl": 4860.0, "account": "taxable"},
    {"ticker": "GLD", "qty": 120, "avg_price": 241.90, "last": 255.73,
     "mkt_value": 30687.6, "unreal_pl": 1659.6, "account": "IRA"},
]

# IV rank (0-100) snapshot used to pre-fill the greeks lights.
_MOCK_IV_RANK = {
    "NVDA": 58, "MU": 71, "VST": 44, "RKLB": 82,
    "GLD": 22, "SMCI": 77, "SPY": 18,
}

# --------------------------------------------------------------- QUERIES
def get_positions():
    """List of position dicts for the Dashboard table."""
    if is_live():
        return _fetch_live_positions()
    return _MOCK_POSITIONS

def get_iv_rank(ticker):
    """IV rank (0-100) for a ticker, or None if unknown.

    Used only to pre-fill the gate form - the user can always override.
    Live mode pulls the option chain; if that call fails for any reason
    we fall back to the mock value and raise a VISIBLE warning banner
    (never a silent fallback).
    """
    if not ticker:
        return None
    ticker = ticker.upper().strip()
    if is_live():
        try:
            return _fetch_live_iv_rank(ticker)
        except Exception as exc:
            _warn_banner(
                f"Live option-chain fetch for {ticker} failed ({exc}). "
                f"Showing MOCK IV rank instead - treat this number as a placeholder."
            )
            return _MOCK_IV_RANK.get(ticker)
    return _MOCK_IV_RANK.get(ticker)

def get_last(ticker):
    """Last price for a ticker, or None. Consumed by exit_engine.proximity."""
    if not ticker:
        return None
    ticker = ticker.upper().strip()
    if is_live():
        return _fetch_live_quote(ticker)
    for p in _MOCK_POSITIONS:
        if p["ticker"] == ticker:
            return p["last"]
    return None

# ---------------------------------------------------------------- WARN
def _warn_banner(msg):
    """Surface a visible warning in the Streamlit UI (and the console),
    so a degraded live call is never mistaken for good data."""
    warnings.warn(msg)
    try:
        import streamlit as st
        st.warning(f"Schwab live data warning: {msg}")
    except Exception:
        # Not running inside Streamlit (e.g. a script/test) - console only.
        print(f"WARNING: {msg}")

# --------------------------------------------------- LIVE CLIENT (Schwab)
_TOKEN_PATH = Path(__file__).resolve().parent.parent / "data" / "schwab_token.json"
_client_singleton = None

def _client():
    """Lazily build (or reuse) an authenticated schwab-py client.

    Uses the easy_client OAuth helper: the first call opens a browser to
    the Schwab login/consent screen, then caches the resulting token to
    data/schwab_token.json. Subsequent calls silently refresh from that
    cached token - no browser prompt needed until the refresh token
    itself expires (Schwab refresh tokens are valid for 7 days).
    """
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton

    from schwab.auth import easy_client

    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _client_singleton = easy_client(
        api_key=os.environ["SCHWAB_APP_KEY"],
        app_secret=os.environ["SCHWAB_APP_SECRET"],
        callback_url=os.environ.get("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182"),
        token_path=str(_TOKEN_PATH),
    )
    return _client_singleton

def _fetch_live_positions():
    """Map Schwab /accounts positions into the _MOCK_POSITIONS shape.

    NOTE: this endpoint returns YOUR account holdings, not general market
    data. It only runs if you complete the OAuth flow yourself with your
    own keys - this repo never calls it on your behalf.
    """
    client = _client()
    resp = client.get_accounts(fields=[client.Account.Fields.POSITIONS])
    resp.raise_for_status()
    accounts = resp.json()

    out = []
    for wrapper in accounts:
        acct = wrapper.get("securitiesAccount", {})
        acct_type = (acct.get("type") or "UNKNOWN").lower()
        for pos in acct.get("positions", []):
            instr = pos.get("instrument", {})
            qty = pos.get("longQuantity", 0.0) - pos.get("shortQuantity", 0.0)
            mkt_value = pos.get("marketValue", 0.0)
            out.append({
                "ticker": instr.get("symbol"),
                "qty": qty,
                "avg_price": pos.get("averagePrice", 0.0),
                "last": (mkt_value / qty) if qty else 0.0,
                "mkt_value": mkt_value,
                "unreal_pl": pos.get("currentDayProfitLoss", 0.0),
                "account": acct_type,
            })
    return out

def _fetch_live_quote(ticker):
    """GET /marketdata/v1/{symbol}/quotes - pure market data, last price only."""
    client = _client()
    resp = client.get_quote(ticker)
    resp.raise_for_status()
    data = resp.json()
    quote = data.get(ticker, {}).get("quote", {})
    return quote.get("lastPrice")

def _fetch_live_iv_rank(ticker):
    """GET /marketdata/v1/chains - pure market data.

    Schwab's chain response gives current implied vol per contract but
    not a ready-made 52-week IV rank, so this approximates rank as this
    ticker's current mean IV positioned between the min/max IV seen
    across today's chain. Swap in a proper 52-week IV history if/when
    you have one; until then treat this as directional, not exact.
    """
    client = _client()
    resp = client.get_option_chain(ticker)
    resp.raise_for_status()
    data = resp.json()

    ivs = []
    for exp_map_name in ("callExpDateMap", "putExpDateMap"):
        for strikes in data.get(exp_map_name, {}).values():
            for contracts in strikes.values():
                for c in contracts:
                    iv = c.get("volatility")
                    if iv and iv > 0:
                        ivs.append(iv)

    if not ivs:
        raise ValueError(f"empty/invalid option chain for {ticker}")

    current = sum(ivs) / len(ivs)
    lo, hi = min(ivs), max(ivs)
    if hi == lo:
        return 50
    rank = (current - lo) / (hi - lo) * 100
    return round(max(0.0, min(100.0, rank)))
