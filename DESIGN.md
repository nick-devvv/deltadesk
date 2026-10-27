# Nick's Desk — design system

Direction: Algory "command deck" (from Nick's screenshots, Oct 27): red-black HUD, red-framed panels with
corner brackets, wide-tracked red mono labels, pill tabs, a glowing hero panel, a bottom status strip. Written from the Taste app-screen rules and the Vercel interface guidelines.

## The screen's one question
"What do I do right now?" The answer is the **plan card** (state + trigger + contract + stop/BE/T1),
so it is the biggest, highest block in the right column. The chart is the biggest block overall
because Nick reads price first; RSI/MACD are off by default so price has the height.

## Tokens (v2 command deck)
--bg #070405 (faint red grid + top glow) · --panel rgba(18,8,10,.86) · --line #3A1219 · --line-2 #5A1C26
--ink #F3ECEC · --ink-2 #B9A9AB · --ink-3 #86737A · --brand #E8314A (hover #FF4D63)
--up #39D08A · --down #FF6A55 (coral, distinct from brand) · --warn #F2B84B
Numbers always carry +/− or a word (STOP, T1), so meaning never rides on red alone.

## Type
IBM Plex Mono for labels, data and tabs (labels 9.5–10.5px, tracking .24–.32em, uppercase, brand red).
IBM Plex Sans for prose. Plan state 24px mono with soft glow. Big price 30px.

## Layout (deck)
Top bar: logo // COMMAND DECK, SPY/QQQ pills, view tabs (Deck/Paper/Journal/Review/Rules), streak pill, Open Legend.
Three columns: Market + Positions + Engine feed (330px) | Chart hero panel with plan strip (Plan, Trigger,
Buy ≤, Stop, Breakeven, T1) | Plan + Conversation + composer (410px).
Bottom status strip: Session · Active watch · Your P/L · Paper engine · System clock.
<1100px: chart, then plan/chat, then left column; status strip 2-up.

## Panels
.box = HUD panel (1px red-dark border, 12px brand corner brackets top-left/bottom-right).
.box.hero = rounded 10px glowing frame (chart only). Buttons and tabs = pills, mono uppercase.

## Motion
120ms hover color/glow; 1s red fade on a new feed row. Honors prefers-reduced-motion.
