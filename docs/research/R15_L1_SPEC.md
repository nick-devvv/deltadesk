# Round 15 L1 confirmation spec (frozen)

Rules (unchanged from round 14 code at commit 1b35f0b and SPRINT_PLAN "Round 15 pre-registration"):
- T6: sprint/r14.py t6_decisions on the round 14 engine.
- A2: sprint/r14.py ma_decisions(kind="A2").
- RSI2: sprint/r14.py candidates()["RSI2"].
- P1: daily mean of T6, A2, RSI2 net returns.
- P2: P1 with sprint/r14.py risk_control.

Data: Yahoo daily bars 2024-08-01..2026-10-30 (one pull), ^IRX cash. Scored window: L1 2026-07-01..2026-10-30.
Costs 10 bps per side. Per rule: OK if L1 excess return over cash > -2% and L1 max drawdown shallower than -8%; else BROKE.
One run only. Results are reported whatever they are; nothing is re-tuned on L1.
