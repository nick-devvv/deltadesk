"""sprint/ - the desk's option backtest engine for the "strategy + exits sprint" (docs/research/SPRINT_PLAN.md).

Research code only. It reads cached Alpaca market data (data/alpaca, pulled by tools/sprint_pull.py on Chart's
computer) and writes results to data/sprint/. It never places, routes or simulates an order on any broker account,
and it never imports broker.py. Every number it prints is a BACKTEST (in-sample on DEV unless a run is labeled
otherwise), with option prices from real Alpaca 1-minute bars (and trades when pulled) and spreads from a model
(MODELED-SPREAD) unless the desk's logged chains are present (MEASURED-SPREAD).

Modules:
  periods   DEV / locked periods L1, L2 and the refusal rule (--locked + --frozen <spec sha256>, checked against git)
  data      cached bar loader, per-symbol series and per-day context (no network)
  spread    half-spread model (logged chains if present, else 5% of premium for SPY/QQQ/IWM, 10% single stocks)
  bs        Black-Scholes helpers (r = 0, 0DTE), implied vol solved from the option price, labeled BS-EST
  levels    the level map known at each minute + the made-up-levels generator
  daytype   day-type features (ADX/DI, efficiency, VWAP crosses, overlap, range/ATR, OR acceptance, trend score)
  entries   entry signals (ORB implemented; other setups pre-registered in docstrings)
  contracts 0DTE contract picker (delta band from BS-EST delta)
  fills     the fill rules (next bar, k x half-spread, stops at the worse of stop and next real price, no-print rule)
  sim       the trade simulator (stops, targets A-E, trails 1-5, time-of-day versions, R:R filter)
  report    metrics and robustness (bootstrap, nudges, random entries, made-up levels, deflated Sharpe)
  engine    passes over the data that run many exit configurations on shared entries
"""
VERSION = "2026-10-31.sprint1"
