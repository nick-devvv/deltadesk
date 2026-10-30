# Ideas borrowed from other projects

Nothing here is copied code. The desk reimplements the ideas in its own code.

| Project | License | What the desk took |
| --- | --- | --- |
| QuantRails/OptionsTradingJournal | CC BY-NC 4.0 | Journal features: P/L calendar, per-trade review (entry/exit reason, went well, improve, next time), time-of-day buckets, strategy breakdowns, intraday timestamped notes, CSV export |
| bandarusrinivas/bandaru-trade-analysis | MIT | Black-Scholes delta fallback when the broker sends IV but no delta (labeled "est."), option-chain levels and TTM squeeze as knowledge/research items |
| manujbh/celo-trader (fork of mmoore723/celo-trader) | no license file (ideas only) | Research catalog entries (BOS/FVG, midday breakout, afternoon reversal); "show real examples, never synthetic charts"; why the desk avoids made-up confidence scores |
| shiyu-coder/Kronos | MIT | Kronos-mini forecast model, run as a shadow test |
| tradesdontlie/tradingview-mcp | see repo | Chart-analysis checklist and performance-review framework (knowledge cards) |
| Leonxlnx/taste-skill, vercel-labs/web-interface-guidelines | see repos | UI design rules |

## v2.9 design tools
- taste-skill (Leonxlnx/taste-skill): app-screen rules, the "data terminal" style, inspector and lint checks.
- Vercel web interface guidelines (vercel-labs/web-interface-guidelines): accessibility and interaction checklist.
- design-md (google-labs-code/stitch-skills): the format of DESIGN.md.
- Fonts: Chakra Petch and Public Sans (SIL Open Font License), loaded from Google Fonts.

## v3.3 repository review (ideas only, no code copied)
The research prompt named six pinned repositories. The desk took **no code** from any of them. Licenses are as reported in that audit and were not re-checked from this build. The decisions:

| Repository (pinned commit) | Decision |
| --- | --- |
| alpacahq/Momentum-Trading-Example @ be43528 | Idea only: stock ORB/MACD as a research hypothesis. Nothing imported (its execution loop has pre-open, forming-bar and reconnect issues). |
| ashish2704/Scalping-Day-Trading-Strategy- @ 44ec052 | ATR expansion stays a hypothesis. Its tuned stops failed later testing, so the desk doesn't adopt them. |
| rithsila/MT5-EA-Sniper-Strategy @ 9f89e8d | Not used: Forex/MQL5 with unverified performance. |
| StockSharp/StockSharp @ 4557175 | Reference only for keeping execution apart from risk. Custom license: nothing reused. |
| PyPatel/Options-Trading-Strategies-in-Python @ c7b8a0d | Not used: syntax, data and P&L defects. |
| Jakeschincariol/day-trader-skill @ 3d0f4ef (MIT) | Ideas reimplemented independently: deterministic ids for each setup (the gate's `G2-...` keys and the router's `R-...` ids), news deduplication and deterministic test fixtures. Not used: its broker execution, quote tolerances, flat times, gap simulator and "win probability". |
