"""SQLite persistence for MAESTRO Terminal.

Single-file DB kept next to the app. No migrations — v0.1 creates the
schema on init() and everything else reads/writes plain dicts so the
Streamlit layer never touches SQL.
"""
import os
import sqlite3
from datetime import date

DB_PATH = os.environ.get("MAESTRO_DB", "maestro.db")

# Slots seeded on first run so the Board has rows to edit out of the box.
_SEED_BOARD = [
    ("NVDA", "power/cooling"),
    ("SMCI", "power/cooling"),
    ("MU",   "memory"),
    ("VST",  "energy"),
    ("RKLB", "space"),
    ("GLD",  "decorrelator"),
]


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    """Create tables if missing and seed the board once."""
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                opened          TEXT,
                closed          TEXT,
                ticker          TEXT,
                vehicle         TEXT,
                qty             REAL,
                entry_price     REAL,
                exit_price      REAL,
                account         TEXT,
                slot            TEXT,
                thesis          TEXT,
                mechanism       TEXT,
                catalyst        TEXT,
                catalyst_date   TEXT,
                iv_rank_entry   REAL,
                tape_context    TEXT,
                emotions        TEXT,
                velocity_take   TEXT,
                time_stop       TEXT,
                invalidation    TEXT,
                max_loss_pct    REAL,
                override_reason TEXT,
                exit_reason     TEXT,
                peak_gain_pct   REAL,
                mae_pct         REAL,
                post_note       TEXT,
                exit_efficiency REAL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS board (
                ticker        TEXT PRIMARY KEY,
                slot          TEXT,
                status        TEXT DEFAULT 'watch',
                t1_low        REAL DEFAULT 0.0,
                t1_high       REAL DEFAULT 0.0,
                t2_low        REAL DEFAULT 0.0,
                t2_high       REAL DEFAULT 0.0,
                tp1           REAL DEFAULT 0.0,
                invalidation  REAL DEFAULT 0.0,
                notes         TEXT DEFAULT '',
                resting_order INTEGER DEFAULT 0
            )
        """)
        existing = c.execute("SELECT COUNT(*) AS n FROM board").fetchone()["n"]
        if not existing:
            c.executemany(
                "INSERT INTO board (ticker, slot) VALUES (?, ?)", _SEED_BOARD)


# ------------------------------------------------------------------ TRADES
def trades(open_only=False):
    """Return trades as a list of dicts. Adds a boolean 'closed' flag."""
    q = "SELECT * FROM trades"
    if open_only:
        q += " WHERE closed IS NULL"
    q += " ORDER BY id DESC"
    with _conn() as c:
        rows = [dict(r) for r in c.execute(q).fetchall()]
    for r in rows:
        r["closed"] = bool(r.get("closed"))
    return rows


def open_trade(data):
    """Insert a new open trade. 'data' is the dict built in the gate form."""
    cols = ", ".join(data.keys())
    marks = ", ".join("?" for _ in data)
    with _conn() as c:
        cur = c.execute(
            f"INSERT INTO trades ({cols}) VALUES ({marks})", list(data.values()))
        return cur.lastrowid


def close_trade(trade_id, exit_price, reason, peak_gain_pct, mae_pct, note):
    """Close a trade and compute exit efficiency."""
    eff = _exit_efficiency(exit_price, peak_gain_pct, trade_id)
    with _conn() as c:
        c.execute("""
            UPDATE trades SET
                closed          = ?,
                exit_price      = ?,
                exit_reason     = ?,
                peak_gain_pct   = ?,
                mae_pct         = ?,
                post_note       = ?,
                exit_efficiency = ?
            WHERE id = ?
        """, (date.today().isoformat(), exit_price, reason,
              peak_gain_pct, mae_pct, note, eff, trade_id))
    return eff


def _exit_efficiency(exit_price, peak_gain_pct, trade_id):
    """% of the peak unrealized gain that was actually captured at exit.

    realized_gain% / peak_gain% * 100, clamped to [0, 100].
    Returns None when there was no positive peak to measure against.
    """
    if not peak_gain_pct or peak_gain_pct <= 0:
        return None
    with _conn() as c:
        row = c.execute(
            "SELECT entry_price FROM trades WHERE id = ?", (trade_id,)).fetchone()
    entry = row["entry_price"] if row else None
    if not entry:
        return None
    realized_pct = (exit_price - entry) / entry * 100.0
    eff = realized_pct / peak_gain_pct * 100.0
    return max(0.0, min(100.0, round(eff, 1)))


# ------------------------------------------------------------------- BOARD
def board_rows():
    with _conn() as c:
        return [dict(r) for r in
                c.execute("SELECT * FROM board ORDER BY slot, ticker").fetchall()]


def upsert_board(r):
    """Insert or update a single board row (keyed by ticker)."""
    with _conn() as c:
        c.execute("""
            INSERT INTO board
                (ticker, slot, status, t1_low, t1_high, t2_low, t2_high,
                 tp1, invalidation, notes, resting_order)
            VALUES
                (:ticker, :slot, :status, :t1_low, :t1_high, :t2_low, :t2_high,
                 :tp1, :invalidation, :notes, :resting_order)
            ON CONFLICT(ticker) DO UPDATE SET
                slot          = excluded.slot,
                status        = excluded.status,
                t1_low        = excluded.t1_low,
                t1_high       = excluded.t1_high,
                t2_low        = excluded.t2_low,
                t2_high       = excluded.t2_high,
                tp1           = excluded.tp1,
                invalidation  = excluded.invalidation,
                notes         = excluded.notes,
                resting_order = excluded.resting_order
        """, {
            "ticker": r["ticker"],
            "slot": r.get("slot", "bench"),
            "status": r.get("status", "watch"),
            "t1_low": r.get("t1_low", 0.0),
            "t1_high": r.get("t1_high", 0.0),
            "t2_low": r.get("t2_low", 0.0),
            "t2_high": r.get("t2_high", 0.0),
            "tp1": r.get("tp1", 0.0),
            "invalidation": r.get("invalidation", 0.0),
            "notes": r.get("notes", ""),
            "resting_order": int(r.get("resting_order", 0)),
        })
