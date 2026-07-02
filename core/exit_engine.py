"""Level-proximity math and alerting for the Board.

The Board stores hand-drawn chart levels per ticker (target zones T1/T2,
a take-profit, and an invalidation). This module compares the live price
against those levels so the Dashboard can shout when something is in play.

Two public functions:

  proximity(row)      -> dict of signed % distances to each level (+ price)
  board_alerts(rows)  -> list of (severity, ticker, message) tuples

Severity is one of "RED", "GREEN", "YELLOW":
  RED    = at/through invalidation (get out)
  GREEN  = in a take-profit / target zone (trim or sell)
  YELLOW = approaching a level (watch)
"""
from core import schwab_client as sc

# How close (in %) counts as "approaching" a level for a YELLOW alert.
_NEAR_PCT = 1.5


def _pct(price, level):
    """Signed % distance from price to level: (level - price) / price * 100."""
    if not price or not level:
        return None
    return (level - price) / price * 100.0


def proximity(row):
    """Return signed % distances from live price to each level on the row.

    Keys mirror the board levels; 'price' carries the live quote so the UI
    can print it. Returns an empty dict when no price is available so the
    caller can cheaply test 'if prox:'.
    """
    price = sc.get_last(row.get("ticker"))
    if not price:
        return {}
    out = {"price": price}
    for key in ("t1_low", "t1_high", "t2_low", "t2_high", "tp1", "invalidation"):
        level = row.get(key)
        d = _pct(price, level)
        if d is not None and level:
            out[key] = d
    return out


def _within(price, low, high):
    """True if price sits inside an [low, high] zone (order-agnostic)."""
    if not low or not high:
        return False
    lo, hi = sorted((low, high))
    return lo <= price <= hi


def board_alerts(rows):
    """Scan every board row and return the alerts that are currently live."""
    fired = []
    for r in rows:
        t = r.get("ticker")
        price = sc.get_last(t)
        if not price:
            continue

        inval = r.get("invalidation")
        if inval and price <= inval:
            fired.append(("RED", t,
                f"{t}: price {price:.2f} at/below invalidation {inval:.2f} "
                f"— exit per your card."))
            continue  # invalidation dominates; skip softer alerts

        tp1 = r.get("tp1")
        if tp1 and price >= tp1:
            fired.append(("GREEN", t,
                f"{t}: price {price:.2f} tagged TP1 {tp1:.2f} — take profit."))
            continue

        if _within(price, r.get("t1_low"), r.get("t1_high")):
            fired.append(("GREEN", t,
                f"{t}: price {price:.2f} inside T1 zone — trim / trail."))
            continue
        if _within(price, r.get("t2_low"), r.get("t2_high")):
            fired.append(("GREEN", t,
                f"{t}: price {price:.2f} inside T2 zone — trim / trail."))
            continue

        # Softer YELLOW: approaching invalidation or TP1 from the near side.
        near = []
        di = _pct(price, inval)
        if di is not None and -_NEAR_PCT <= di <= 0:
            near.append(f"invalidation {inval:.2f}")
        dt = _pct(price, tp1)
        if dt is not None and 0 <= dt <= _NEAR_PCT:
            near.append(f"TP1 {tp1:.2f}")
        if near:
            fired.append(("YELLOW", t,
                f"{t}: price {price:.2f} approaching " + " & ".join(near) + "."))

    return fired
