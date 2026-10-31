// v3.5 browser check for the Markets chart sizing fix (C2). Run against a desk you can open locally (a demo, or the
// real desk through an SSH tunnel - never paste the token link into a script): DESK=http://127.0.0.1:8765/ node chart_size_check.js
// It prints the frame / chart box / chart root / canvas sizes on load, every 3 s, after a tab switch, at 4 widths and
// after timeframe changes. Before the fix the Markets root grew ~320 px every 3 s; after it, root == box at every step.
const { chromium } = require('playwright');
const out = process.env.OUT || "./chart_check_out";
require('fs').mkdirSync(out, {recursive: true});
const dims = () => {
  const r = s => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return [Math.round(b.width), Math.round(b.height)]; };
  const cv = [...document.querySelectorAll('#mkDesk canvas')].map(c => [c.width, c.height]);
  const cv2 = [...document.querySelectorAll('#desk canvas')].map(c => [c.width, c.height]);
  return {frame: r('.mkframe'), box: r('#v-markets .chartbox'), root: r('#mkDesk'), table: r('#mkDesk table'), canvases: cv.length, canvas0: cv[0],
          tradeRoot: r('#desk'), tradeCanvas0: cv2[0], page: [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
          mkScroll: document.querySelector('#v-markets') ? document.querySelector('#v-markets').scrollHeight : null};
};
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({viewport: {width: 1440, height: 900}});
  const log = [];
  const snap = async (tag) => { const d = await p.evaluate(dims); log.push([tag, d]); console.log(tag, JSON.stringify(d)); };
  await p.goto((process.env.DESK || "http://127.0.0.1:8799/") + "#markets"); await p.waitForTimeout(2500); await snap('load');
  for (let i = 1; i <= 4; i++) { await p.waitForTimeout(3000); await snap('t+' + 3 * i + 's'); }
  await p.evaluate(() => location.hash = 'trade'); await p.waitForTimeout(1500); await snap('trade tab');
  await p.evaluate(() => location.hash = 'markets'); await p.waitForTimeout(1500); await snap('back to markets');
  for (const w of [1000, 760, 390, 1440]) { await p.setViewportSize({width: w, height: w < 500 ? 844 : 900}); await p.waitForTimeout(1500); await snap('width ' + w); }
  for (const tf of ['1', '5', '15', '2']) { await p.click(`#mkTf button[data-tf="${tf}"]`); await p.waitForTimeout(1500); await snap('tf ' + tf); }
  await p.screenshot({path: out + '/markets_after.png'});
  require('fs').writeFileSync(out + '/size_log.json', JSON.stringify(log, null, 1));
  await b.close();
})();
