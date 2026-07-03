"""MAESTRO Terminal v0.1 — run with:  streamlit run app.py"""
import json
from datetime import date
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from core import db, schwab_client as sc, exit_engine, vehicle_selector as vs

st.set_page_config(page_title="MAESTRO Terminal", layout="wide")
db.init()

st.title("MAESTRO Terminal")
mode = "LIVE (Schwab)" if sc.is_live() else "MOCK DATA — July 2, 2026 snapshot. Set MAESTRO_MODE=live in .env after adding Schwab keys."
st.caption(mode)

tab_dash, tab_board, tab_new, tab_journal = st.tabs(
    ["Dashboard", "Board", "New trade (gate)", "Journal"])

# ---------------------------------------------------------------- DASHBOARD
with tab_dash:
    closed = [t for t in db.trades() if t["closed"]]
    effs = [t["exit_efficiency"] for t in closed if t["exit_efficiency"] is not None]
    c1, c2, c3 = st.columns(3)
    c1.metric("Exit efficiency (all closed trades)",
              f"{sum(effs)/len(effs):.0f}%" if effs else "no closed trades yet",
              help="% of peak unrealized gain you actually captured. The headline number.")
    c2.metric("Open trades", len(db.trades(open_only=True)))
    c3.metric("Closed trades logged", len(closed))

    st.subheader("Alerts")
    fired = exit_engine.board_alerts(db.board_rows())
    if not fired:
        st.write("No levels triggered.")
    for sev, t, msg in fired:
        (st.error if sev == "RED" else st.success if sev == "GREEN" else st.warning)(msg)

    st.subheader("Positions (from broker)")
    st.dataframe(pd.DataFrame(sc.get_positions()), width="stretch")

# -------------------------------------------------------------------- BOARD
with tab_board:
    st.caption("The whiteboard, digitized. Edit a row and save. Every level must "
               "match something on the daily chart — no round-number levels.")
    rows = db.board_rows()
    for r in rows:
        prox = exit_engine.proximity(r)
        with st.expander(f"{r['ticker']}  ·  {r['slot']}  ·  {r['status']}"
                         + (f"  ·  {prox.get('price'):.2f}" if prox.get("price") else "")):
            cols = st.columns(6)
            r["t1_low"] = cols[0].number_input("T1 low", value=r["t1_low"], key=f"t1l{r['ticker']}")
            r["t1_high"] = cols[1].number_input("T1 high", value=r["t1_high"], key=f"t1h{r['ticker']}")
            r["t2_low"] = cols[2].number_input("T2 low", value=r["t2_low"], key=f"t2l{r['ticker']}")
            r["t2_high"] = cols[3].number_input("T2 high", value=r["t2_high"], key=f"t2h{r['ticker']}")
            r["tp1"] = cols[4].number_input("TP1", value=r["tp1"], key=f"tp1{r['ticker']}")
            r["invalidation"] = cols[5].number_input("Invalidation", value=r["invalidation"], key=f"inv{r['ticker']}")
            r["notes"] = st.text_input("Notes", value=r["notes"] or "", key=f"n{r['ticker']}")
            r["resting_order"] = int(st.checkbox("Resting order actually placed at broker",
                                                 value=bool(r["resting_order"]), key=f"ro{r['ticker']}"))
            if prox:
                st.caption(" · ".join(f"{k}: {v:+.1f}%" for k, v in prox.items() if k != "price"))
            if st.button("Save", key=f"s{r['ticker']}"):
                db.upsert_board(r); st.success("Saved.")

# ---------------------------------------------------------- NEW TRADE (GATE)
with tab_new:
    st.caption("This form is a GATE. Red lights demand a typed override reason. "
               "No exit card, no trade — the save button stays locked until the card is complete.")
    g1, g2, g3 = st.columns(3)
    ticker = g1.text_input("Ticker").upper().strip()
    vehicle = g2.selectbox("Vehicle", ["shares", "buy call", "sell put"])
    account = g3.selectbox("Account", ["taxable", "IRA"])
    qty = g1.number_input("Qty / contracts", min_value=0.0, value=0.0)
    entry_price = g2.number_input("Entry price (underlying or premium)", min_value=0.0, value=0.0)
    slot = g3.selectbox("Slot", ["power/cooling", "memory", "energy", "space",
                                 "decorrelator", "materials", "satellite", "bench"])

    thesis = st.text_area("Thesis (3 sentences max)")
    mechanism = st.selectbox("Mispricing mechanism (or admit it's momentum)",
        ["thin coverage", "wrong sector classification", "lumpy earnings vs backlog",
         "foreign/OTC listing", "market pricing old business", "laggard gap in theme",
         "momentum/catalyst trade (no mechanism)"])
    catalyst = st.text_input("Catalyst")
    catalyst_date = st.date_input("Catalyst date", value=None)
    tape = st.selectbox("Today's tape for this name", ["drift day", "flush day", "gap day", "normal"])
    emotions = st.multiselect("Emotion tags (be honest — this builds your psych profile)",
        ["conviction", "plan-fill", "FOMO", "revenge", "boredom", "sympathy-dip", "familiarity"])

    st.markdown("**Greeks lights** (contracts)")
    iv_default = sc.get_iv_rank(ticker) if ticker else None
    l1, l2, l3 = st.columns(3)
    iv_rank = l1.number_input("IV rank (0-100)", 0, 100, int(iv_default) if iv_default else 50)
    delta = l2.number_input("Delta", 0.0, 1.0, 0.6) if vehicle == "buy call" else None
    dte = l3.number_input("Days to expiry", 0, 720, 120) if vehicle != "shares" else None
    breakeven = l1.number_input("Breakeven", 0.0) if vehicle == "buy call" else None
    tp1_in = l2.number_input("Your TP1 on underlying", 0.0)
    spread = l3.number_input("Option spread % of mid", 0.0, 25.0, 2.0) if vehicle != "shares" else None

    lights, reds = [], 0
    lights.append(vs.light_iv_rank(iv_rank))
    lights.append(vs.light_tape(tape))
    if vehicle == "buy call":
        lights.append(vs.light_delta(delta))
        lights.append(vs.light_breakeven(breakeven, tp1_in))
    if spread is not None:
        lights.append(vs.light_spread(spread))
    for icon, why in lights:
        st.write(f"{icon} {why}")
        reds += icon == vs.RED

    if ticker and vehicle != "shares":
        dtc = (catalyst_date - date.today()).days if catalyst_date else None
        open_same = [t for t in db.trades(open_only=True)
                     if t["ticker"] == ticker and t["vehicle"] != "shares"]
        rec, reasons = vs.select_vehicle(iv_rank, dtc, dte, False, bool(open_same), True)
        st.info(f"**Vehicle selector: {rec}**\n\n" + "\n".join(f"- {r}" for r in reasons))

    st.markdown("**Exit card — mandatory**")
    e1, e2, e3 = st.columns(3)
    velocity_take = e1.text_input("Velocity take (level + speed)",
                                  placeholder="Tags 1130-1150 within 21 days → sell")
    time_stop = e2.text_input("Time stop (date + condition)",
                              placeholder="Aug 15: below 1080 → exit regardless")
    invalidation = e3.text_input("Invalidation (chart level)",
                                 placeholder="Daily close < 950 → exit same day")
    max_loss = st.number_input("Max loss on ticket % (contracts)", 0, 100, 50)

    override = ""
    if reds:
        override = st.text_input(f"{reds} RED light(s). Typed override reason required — "
                                 "it is logged forever and replayed in the weekly review.")

    card_ok = all([velocity_take.strip(), time_stop.strip(), invalidation.strip()])
    gate_ok = card_ok and ticker and thesis.strip() and (not reds or override.strip())
    if not card_ok:
        st.warning("Exit card incomplete. No exit card, no trade.")
    if st.button("Log trade", disabled=not gate_ok, type="primary"):
        db.open_trade(dict(opened=date.today().isoformat(), ticker=ticker, vehicle=vehicle,
            qty=qty, entry_price=entry_price, account=account, slot=slot, thesis=thesis,
            mechanism=mechanism, catalyst=catalyst,
            catalyst_date=str(catalyst_date) if catalyst_date else None,
            iv_rank_entry=iv_rank, tape_context=tape, emotions=json.dumps(emotions),
            velocity_take=velocity_take, time_stop=time_stop, invalidation=invalidation,
            max_loss_pct=max_loss, override_reason=override or None))
        st.success(f"{ticker} logged with exit card. Now go place the resting orders.")

# ------------------------------------------------------------------ JOURNAL
with tab_journal:
    open_t = db.trades(open_only=True)
    st.subheader("Open — exit cards in force")
    for t in open_t:
        with st.expander(f"#{t['id']} {t['ticker']} {t['vehicle']} · opened {t['opened']}"):
            st.write(f"**Velocity take:** {t['velocity_take']}  \n**Time stop:** {t['time_stop']}  \n"
                     f"**Invalidation:** {t['invalidation']}  \n**Thesis:** {t['thesis']}")
            x1, x2, x3 = st.columns(3)
            exit_price = x1.number_input("Exit price", 0.0, key=f"xp{t['id']}")
            peak = x2.number_input("Peak unrealized gain % during hold", 0.0, key=f"pk{t['id']}")
            mae = x3.number_input("Worst drawdown % during hold", 0.0, key=f"mae{t['id']}")
            reason = st.selectbox("Exit reason", ["velocity take", "time stop", "invalidation",
                                  "override", "panic", "forgot"], key=f"rs{t['id']}")
            note = st.text_input("One-sentence post-note", key=f"pn{t['id']}")
            if st.button("Close trade", key=f"cl{t['id']}"):
                db.close_trade(t["id"], exit_price, reason, peak, mae, note)
                st.success("Closed — exit efficiency computed.")
                st.rerun()

    st.subheader("Closed")
    closed = [t for t in db.trades() if t["closed"]]
    if closed:
        df = pd.DataFrame(closed)[["id", "ticker", "vehicle", "opened", "closed",
                                   "exit_reason", "exit_efficiency", "emotions", "mechanism"]]
        st.dataframe(df, width="stretch")
        st.caption("Weekly review (v1.0) correlates emotion tags and override outcomes with P&L.")
    else:
        st.write("Nothing closed yet. The first ten closed trades teach you more than any backtest.")
