"""Greeks \"lights\" and vehicle selection for the New-trade gate.

Every light returns a tuple:  (icon, why)  where icon is one of the
module-level RED / YELLOW / GREEN emoji. The gate counts RED lights to
decide whether a typed override reason is required.

select_vehicle() is the opinionated recommender: given the vol regime and
timing, it nudges you toward shares, buying a call, or selling a put — and
always explains its reasoning so the call is auditable in the weekly review.
"""

# Light icons — compared by identity in app.py (reds += icon == vs.RED).
RED = "U0001F534"     # stop / demands an override reason
YELLOW = "U0001F7E1"  # caution / size down
GREEN = "U0001F7E2"   # clear


# ------------------------------------------------------------- LIGHTS
def light_iv_rank(iv_rank):
    """High IV punishes long premium and rewards selling it."""
    if iv_rank is None:
        return YELLOW, "IV rank unknown — pull it before sizing."
    if iv_rank >= 70:
        return RED, f"IV rank {iv_rank:.0f}: rich — long calls overpay, favor selling premium."
    if iv_rank >= 45:
        return YELLOW, f"IV rank {iv_rank:.0f}: elevated — mind theta and the vol crush."
    return GREEN, f"IV rank {iv_rank:.0f}: reasonable for long premium."


def light_tape(tape):
    """Don't initiate into a flush or chase a gap."""
    if tape == "flush day":
        return RED, "Flush day — don't catch it falling; wait for the base."
    if tape == "gap day":
        return YELLOW, "Gap day — let the open settle before entering."
    if tape == "drift day":
        return GREEN, "Drift day — orderly tape, fine to work an entry."
    return GREEN, "Normal tape."


def light_delta(delta):
    """Too low = lottery ticket; too high = expensive stock proxy."""
    if delta is None:
        return YELLOW, "No delta set."
    if delta < 0.45:
        return RED, f"Delta {delta:.2f}: too low — that's a lottery ticket, not a position."
    if delta > 0.80:
        return YELLOW, f"Delta {delta:.2f}: deep ITM — you're paying up to rent the stock."
    return GREEN, f"Delta {delta:.2f}: in the productive 0.45–0.80 band."


def light_breakeven(breakeven, tp1):
    """Your own take-profit must clear the option breakeven, with room."""
    if not breakeven or not tp1:
        return YELLOW, "Set breakeven and TP1 to check the math."
    if tp1 <= breakeven:
        return RED, (f"TP1 {tp1:.2f} is below breakeven {breakeven:.2f} — "
                     f"the trade can't win at your own target.")
    cushion = (tp1 - breakeven) / breakeven * 100.0
    if cushion < 3.0:
        return YELLOW, f"Only {cushion:.1f}% between breakeven and TP1 — thin cushion."
    return GREEN, f"TP1 clears breakeven by {cushion:.1f}%."


def light_spread(spread_pct):
    """Wide option spreads quietly eat the edge."""
    if spread_pct is None:
        return YELLOW, "Spread unknown."
    if spread_pct > 8.0:
        return RED, f"Spread {spread_pct:.1f}% of mid — illiquid, the fill will bleed you."
    if spread_pct > 4.0:
        return YELLOW, f"Spread {spread_pct:.1f}% of mid — use limits, expect slippage."
    return GREEN, f"Spread {spread_pct:.1f}% of mid — tight enough."


# --------------------------------------------------- VEHICLE SELECTOR
def select_vehicle(iv_rank, days_to_catalyst, dte, is_earnings_binary,
                   already_open, wants_leverage):
    """Recommend shares / buy call / sell put with reasons.

    Args:
        iv_rank            IV rank 0–100 (None if unknown).
        days_to_catalyst   days until the catalyst, or None.
        dte                days to expiry of the contemplated option, or None.
        is_earnings_binary True if the catalyst is a binary earnings print.
        already_open       True if there's already an open options position
                           in the same name (avoid stacking premium).
        wants_leverage     True if the user is explicitly seeking leverage.

    Returns:
        (recommendation, [reasons])
    """
    reasons = []
    iv = iv_rank if iv_rank is not None else 50

    if already_open:
        reasons.append("You already hold options in this name — add shares, "
                       "don't stack more premium and theta.")
        return "shares", reasons

    if not wants_leverage:
        reasons.append("No leverage requested — shares keep it simple and "
                       "carry no time decay.")
        return "shares", reasons

    # Timing sanity: the option must comfortably outlast the catalyst.
    if days_to_catalyst is not None and dte is not None and dte < days_to_catalyst:
        reasons.append(f"DTE {dte} < {days_to_catalyst} days to catalyst — "
                       f"the option can expire before the thesis plays out.")
        return "shares", reasons

    if is_earnings_binary:
        reasons.append("Binary earnings event — defined-risk long call caps the "
                       "downside if it gaps against you.")
        return "buy call", reasons

    if iv >= 60:
        reasons.append(f"IV rank {iv:.0f} is rich — sell the put to collect that "
                       f"premium and get paid to wait for your entry.")
        return "sell put", reasons

    if iv <= 40:
        reasons.append(f"IV rank {iv:.0f} is cheap — buying a call is an efficient "
                       f"way to rent upside without overpaying for vol.")
        if days_to_catalyst is not None:
            reasons.append(f"Size expiry past the {days_to_catalyst}-day catalyst "
                           f"with buffer for slippage.")
        return "buy call", reasons

    reasons.append(f"IV rank {iv:.0f} is middling — no vol edge either way; "
                   f"shares avoid paying for a coin-flip on vol.")
    return "shares", reasons
