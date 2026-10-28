# Design System: Nick's Desk (v2.9)

Source of truth for the desk's look. Any change to `index.html` should follow it. Format from the design-md skill. Rules from taste-skill (app-screen run, "data terminal" style, seed 1121322569) and the Vercel web interface guidelines.

## The screen's one question
"What do I do right now?" The **plan** answers it, so it has the biggest type on the screen: the state word (READY / NEAR / PASS), the side, and three numbers (Max buy, Stop, Target 1). Everything else in the plan sits behind **Details**. The chart is the biggest block because Nick reads price first.

## 1. Visual theme and atmosphere
A night-time trading terminal: near-black, quiet and precise, with one ember-red accent. It looks futuristic because of the squared display face, the slow globe, the light that sweeps the chart frame, and the moving ticker tape. It is not made of glows or boxes. Colour goes on data (P/L, stop, target, state) and on the one primary action. Selections are marked by a 1px ember line exactly as wide as the label.

## 2. Colour palette and roles
| Token | Hex | Role |
|---|---|---|
| `--bg` | #0D090E | Page ground (one ground everywhere) |
| `--glass` | #070508 | Cards: one step darker than the ground (data-terminal move) |
| `--glass-2` | #120C12 | Raised area: the plan hero, the selected watchlist row |
| `--line` | rgba(255,255,255,.065) | The only divider; a whisper |
| `--line-2` | rgba(255,51,85,.24) | The chart frame's ember edge |
| `--ink` | #EEE8F0 | Text and key figures |
| `--ink-2` | #ABA2B1 | Secondary text |
| `--ink-3` | #8E8597 | Labels and meta (passes 4.5:1 on cards) |
| `--brand` | #FF3355 | Ember accent: selection lines, the logo, the session ring |
| button fill | #D81E3D | Filled buttons with white text (Open Legend, Watch, Send) |
| `--up` | #2FE39A | Gains, targets, READY, the frame when a plan is ready |
| `--down` | #FF5A4E | Losses, stops, PASS |
| `--warn` | #FFB547 | NEAR/WAIT, streak warnings, earnings badges, the next step on a position |

Numbers carry their sign in the text (+$6.00, −$38.20), so the meaning never depends on colour alone.

## 3. Typography rules
- **Chakra Petch** 500–700 for the display layer: wordmark, nav, tabs, the state word (36px), the plan numbers (22px), the price on the globe (28px), page titles (26px), tickers.
- **Public Sans** 400–700 for everything else (body 13px, labels 12px, nothing under 11px).
- Tabular numerals everywhere (forced on all elements), so prices and times keep their width as they update.
- Sentence case. Uppercase only for the wordmark and the plan state word, with tracking of .02em at most. No tracked micro-labels.
- Loaded from Google Fonts with `display=swap`.

## 4. Component styles
- **Top bar:** wordmark, SPY/QQQ (plus the selected watchlist ticker) underlined when active, five page links, then the status cluster: session ring (fills 9:30 to close) with "Open, 2h 41m left", Your P/L, Paper, the New York clock, the streak pill (only shown when a streak rule is active), alert and voice icon buttons, and Open Legend.
- **Plan hero:** "Plan" plus the time it was made. Then the state word with the side chip and grade, the contract with Δ, a three-cell number well (Max buy, Stop with its %, Target 1), the trigger line, one amber or red line for the top objection or pass reason, and a **Details** disclosure (setup, invalid if, quote and feed, size, breakeven, if flat, all out, for and against). The disclosure's open state is remembered.
- **Positions:** one row per trade: a You/Paper chip, contract × qty @ fill, P/L on the right, and a grey line with the stop and the next step in amber.
- **Chat:** your messages are ember bubbles on the right; Chart's are dark bubbles on the left; desk output is a thin ember-ruled line that shows its first line, with "Show all" for the rest.
- **Quick actions:** one row: Watch (turns into Unwatch while watching), Check, Fill, Exit, Why?. The composer is a rounded field with a round send button.
- **Left column:** the market-core globe (orbiting SPY/QQQ/Paper/Chart nodes with box-free labels), four small stats, then Watchlist / Feed / News tabs.
- **Chart frame:** 18px radius, ember edge, one 1px light sweeping the top edge every 7 s; it turns green when a plan is READY.
- **Ticker tape (bottom):** SPY/QQQ, the watchlist prices, then the latest headlines, scrolling. It pauses on hover or tap and is static with reduced motion.
- **Pages (Paper, Journal, Review, Rules):** 26px title and a one-line lead, then dark cards (14px radius, 1px whisper border) with sentence-case 15px headings.
- **Voice:** a small mic icon in the top bar (or press J). It opens the full-screen voice view. It is a side feature.

## 5. Layout principles
- Desktop: `300px | 1fr | 400px` columns, 18px gap, 20px side margins (280/380 at 1440 and below). Rows: 60px top bar, deck, 38px tape.
- One divider style. No boxes inside boxes and no corner brackets.
- Below 1100px: one column, with the chart, then the plan and chat, then the lists. The tape sticks to the bottom.
- Phone (≤600px): plan first, then the chart (48vh), then the lists. Open Legend is hidden (Legend is desktop-only), and the header wraps to brand + tickers + icons, then status, then nav.
- Motion: the globe, the frame sweep and the tape only. Everything stops with `prefers-reduced-motion`.

## Deliberate exceptions to taste-skill (and why)
- **The frame sweep and the tape's edge fade use gradients.** Nick asked for "cool animations" like the Algory video. This is the one signature move, marked `taste-skill-ignore` in the CSS.
- **heavy-borders warning:** the inspector reads the 6.5%-white divider as solid white. On screen it is a whisper line.
- **hero-void / panel-void warnings:** they come from the chart area being empty in the offline test (TradingView can't load there). On the real desk the TradingView chart fills it.
