# Playbook → desk: where every rule went

The Playbook (Oct 21 + Oct 23 add-on + Oct 26 sections + Chart's memory) mapped to the new desk. The rules in **code** are in `config/policy.json` (version `2026-10-28.2`) and `engine.py`. **Chart** rules are in `grok/`.

Status labels:
- **code**: enforced by the engine.
- **Chart**: in Chart's prompts.
- **changed**: Nick decided differently later.
- **open**: needs Nick's decision.
- **research**: kept, not automated yet.

## Hard rules
| Playbook | Now | Status |
| --- | --- | --- |
| Only Nick trades real money; Chart never clicks order buttons | `agent_policy.json`, coach prompt rule 1, broker allowlist (paper only) | code + Chart |
| Long calls/puts only, no selling or spreads | The engine only buys to open and sells to close | code |
| Model/paper trades kept separate from Nick's | Separate `real` / `paper` ledgers everywhere | code |

## Session
| Playbook | Now | Status |
| --- | --- | --- |
| No trades 9:30–9:45 (ORB) | ORB FORMING state, no entries | code |
| New setups until 3:30, all out 3:50 | Last entry **3:15**, all out **3:25** (Robinhood may start closing expiring positions at 3:30). Nick approved Oct 27. | changed |
| Holidays / early closes | NYSE 2026–27 calendar hardcoded; early close: last entry 12:30, all out 12:50 | code |
| Focus SPY/QQQ (Oct 26) | Instruments = SPY, QQQ | code |

## Stops, targets, management
| Playbook | Now | Status |
| --- | --- | --- |
| Stop by window: ×0.85 / ×0.88 / ×0.90 (15/12/10%) | **Strict 20% for every window**: trigger = fill × 0.80 + slippage + fees, and the trade is skipped if it can't fit. Earlier windows were tighter. | **open**: see Q1 below |
| Breakeven at ×1.10 / 1.08 / 1.06 | Same | code |
| T1 ×1.20–1.30 / 1.15–1.20 / 1.12–1.15, SELL ALL | T1 at the low end. 2 contracts: sell 1 and trail the rest on the 1m swing (higher low / lower high). 1 contract: lock the stop at the BE level, then trail. Nick asked for trailing (Oct 27). | changed (trail_v2, PROPOSED) |
| If flat: exit 5 / 3 / 3 min after entry | Same, measured from your fill time | code |
| Window change tightens the stop | Stops only tighten (`tighten_only`) | code |
| Runner exception (news / 1.5x volume) | Folded into the trail after T1 | changed |
| "Set your stop in Robinhood" every trade | In every IN reply | code |
| P/L on every sell | OUT reply: P/L, contracts left, day total | code |

## Size and limits
| Playbook | Now | Status |
| --- | --- | --- |
| Max daily loss $50 → STOP FOR TODAY | **No dollar limits** (Nick, Oct 27). Replaced by the streak rule. | changed |
| 4 trades or 2 losses in a row → A only | Max 4 trades/day. 2 losses in a row → A only + 10 min cooldown. **3 in a row → STOP FOR TODAY.** | code (streak numbers PROPOSED) |
| Grade A full / B half / C quarter | A = 2, B = 1. Paper C = watch only; your C = 1 with a "small size / scalp only" note | code |
| Chop day: half size, max 2 trades, no runners | Chop day: max 1 contract, max 2 trades | code |
| Model trades floor($500 / premium) | Replaced by grade sizing (1–2 contracts) | changed |

## Contracts
| Playbook | Now | Status |
| --- | --- | --- |
| Delta 0.30–0.50 (Oct 21) → 0.45–0.70 (master) → "0.40+ normal" (Oct 26) | \|Δ\| 0.30–0.50, ranked closest to 0.40. Delta unknown → nearest ATM, labeled "unknown". | **open**: see Q2 below |
| $0.10–$3.00 premiums (Oct 26) | Same range | code |
| Spread ≤ ~10% | ≤ 10% of mid, else skipped | code |
| "Use a limit at or under $x" | Buy ≤ = ask + $0.02, shown on every plan | code |

## Setups (Nick's 7)
| Setup | Now | Status |
| --- | --- | --- |
| 1 ORB breakout + retest | ORB_BREAK / ORB_RETEST: 5m close beyond ORB. Extended → wait for the retest. | code |
| 2 ORB failed break + reclaim | FAILED_BREAK | code |
| 3 VWAP reclaim / retest | VWAP_RECLAIM (≤ 2 crosses in the last hour) | code |
| 4 King & Queen | Treated as VWAP reclaim | research |
| 5 Level flag | Not automated | research |
| 6 Momentum (first 1–3 candle pause) | Not automated | research |
| 7 Fib pullback | Not automated | research |
| Your named level ("PDH 765.50 puts?") | LEVEL plan: 1m close through it | code |
| Scalp mode (1m) | Not automated | research |

## Read and grade
| Playbook | Now | Status |
| --- | --- | --- |
| Top-down 15m/5m/1m, 200 EMA/SMA bias, VWAP, 9/21 EMA | Grade counts agreement of the 15m trend, the 200s and day type | code |
| EMA 9/13 (Oct 26) vs 9/21 | 9/21/200 (Nick, Oct 27); test others later | changed |
| Entry TF 2m → 5m → 10m by time of day | The engine uses completed 5m bars all day; your level plans use 1m closes | changed |
| Chop rules / "middle of range" / chop vortex | Day type + chop flag lower the grade. Chop days stay tradeable. | code |
| "Don't buy puts on a big red candle / calls on a big green" | Not encoded | research |
| Events within 15 min | ±15 min entry block from `config/events.json` (the 9 AM routine posts it) | code |
| Theta warning after 2pm | Tighter afternoon BE/T1 and flat times | code |

## Chart workflows
| Old | Now | Status |
| --- | --- | --- |
| Chart opens Legend for every ask | The desk computes. Chart opens Legend only for what the desk can't see. | Chart |
| SHORT FORMAT card | The plan card on the page; Chart adds 2–4 lines | code + Chart |
| `bot.py take` on every verdict | **Retired**: the paper engine trades by itself | changed |
| `shadow.py in/out` | Retired: you log IN/OUT on the desk | changed |
| `bot.py lessons` before every verdict | Lessons are in the context Chart receives | code |
| Trade Journal page | Desk journal (auto at 4:05, your notes kept) | code |
| Post-mortem → "PROPOSED RULE", Nick approves | 4:20 review posts PROPOSED lessons, needing ≥ 3 examples | Chart |
| Morning drawing (light-blue BOT lines, max ~10, no ORB) | Kept in the 9 AM prompt, using desk levels | Chart |
| 5-minute proactive watch (paused Oct 23) | Bounded watches (default 15 min) in code, no AI | code |

## Questions for Nick
- **Q1. Stop size by time of day.** The Playbook's stops got tighter later in the day (15% → 12% → 10%). Right now the desk uses a flat strict 20% all day. Keep the flat 20%, or go back to 15/12/10 with 20% as the ceiling?
- **Q2. Delta.** Your notes say 0.30–0.50, 0.45–0.70 and "0.40+" in different places. The desk uses 0.30–0.50, aiming for about 0.40. Keep it?
- **Q3. Trailing plan and streak numbers.** These are marked PROPOSED until you OK them:
  - trail_v2: sell 1 of 2 at T1, then trail.
  - Streak rule: 2 losses in a row means A setups only; 3 in a row means stop for the day.
