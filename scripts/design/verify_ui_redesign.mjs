// Headless-Chrome checks for the redesigned real UI, served by scripts/design/serve_ui_sandbox.py.
// node --experimental-websocket scripts/design/verify_ui_redesign.mjs [baseUrl] [outDir] [step...]
// Auto mode only: nothing here sends a paid request.
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const base = process.argv[2] || 'http://127.0.0.1:8840/';
const out = resolve(process.argv[3] || 'outputs/ux/ui-redesign');
const only = process.argv.slice(4);
mkdirSync(out, { recursive: true });
const chrome = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const port = 9500 + Math.floor(Math.random() * 300);
const proc = spawn(chrome, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), 'uir-'))}`, '--no-first-run', '--hide-scrollbars', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0;
const pending = new Map(), errors = [], results = [];
const send = (method, params = {}) => new Promise((res, rej) => { const n = ++id; pending.set(n, { res, rej }); ws.send(JSON.stringify({ id: n, method, params })); });
async function js(expression) {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true, userGesture: true });
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 500));
  return r.result.value;
}
async function shot(name, full = false) { const r = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: full }); writeFileSync(join(out, name + '.png'), Buffer.from(r.data, 'base64')); }
const viewport = (width, height, mobile = false) => send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile });
async function load(lang = 'he', hash = '') {
  await send('Page.navigate', { url: base });
  await sleep(600);
  await js(`localStorage.setItem('ui-language', '${lang}'); localStorage.removeItem('cat-mode')`);
  await send('Page.reload', { ignoreCache: true }); // the server serves exactly "/", so no query string
  await sleep(2200);
  if (hash) { await js(`location.hash = '${hash}'`); await sleep(300); }
}
function check(name, ok, detail = '') { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ' — ' + detail : ''}`); }
const catState = `(() => { const d = libraryCat.debug(); const c = document.querySelector('.roam-cat'); const r = c.querySelector('.roam-body').getBoundingClientRect();
  const hits = [...document.querySelectorAll('button,a[href],input,select,textarea,summary,label,[tabindex]:not([tabindex="-1"]),h1,p,li,[data-cat-avoid]')].filter(e => !c.contains(e) && e.getClientRects().length && !e.closest('dialog:not([open])'))
    .map(e => [e, e.getBoundingClientRect()]).filter(([, b]) => b.left < r.right - 8 && b.right > r.left + 8 && b.top < r.bottom - 6 && b.bottom > r.top + 6).map(([e]) => e.tagName + '#' + e.id);
  return { x: Math.round(d.x), y: Math.round(d.y), anchor: d.anchor, pose: d.pose, shown: !c.hidden && getComputedStyle(c).opacity !== '0', hits }; })()`;

try {
  for (let i = 0; i < 60; i++) { try { const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); const p = list.find(x => x.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch {} await sleep(250); }
  await new Promise(r => ws.addEventListener('open', r));
  ws.addEventListener('message', ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); return; }
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') errors.push(m.params.args.map(a => a.value || a.description).join(' '));
  });
  await send('Page.enable'); await send('Runtime.enable');
  const want = s => !only.length || only.includes(s);

  if (want('foundation')) {
    for (const [lang, w, h] of [['he', 1440, 900], ['en', 1440, 900], ['he', 390, 844]]) {
      await viewport(w, h, w < 600); await load(lang); await sleep(2500);
      const tag = `${lang}-${w}`;
      check(`[${tag}] page language and direction`, await js(`document.documentElement.lang === '${lang}' && document.documentElement.dir === '${lang === 'en' ? 'ltr' : 'rtl'}'`));
      check(`[${tag}] book typeface loaded`, await js(`document.fonts.ready.then(() => document.fonts.check('600 20px "Frank Ruhl Libre"'))`));
      check(`[${tag}] new logo in the header`, await js(`!!document.querySelector('.app-header .brand-logo')`));
      check(`[${tag}] no horizontal overflow`, (await js(`document.documentElement.scrollWidth`)) <= w);
      const samples = [];
      for (let i = 0; i < 6; i++) { samples.push(await js(catState)); await sleep(900); }
      check(`[${tag}] the cat is on the page`, samples.some(s => s.shown), JSON.stringify(samples.at(-1)));
      const blocked = samples.filter(s => s.shown && s.anchor && !['held', 'jump'].includes(s.pose) && s.hits.length);
      check(`[${tag}] the cat never sits on controls or text`, blocked.length === 0, blocked.map(s => s.hits.join(',')).slice(0, 2).join(' | '));
      await shot(`foundation-${tag}`);
    }
    await viewport(1440, 900); await load('he');
    await js(`document.getElementById('cat-button').click()`); await sleep(300);
    check('cat settings dialog opens from the footer', await js(`document.querySelector('.cat-dialog')?.open === true`));
    await shot('cat-settings');
    await js(`(() => { const r = document.querySelector('input[name=cat-mode][value=away]'); r.checked = true; r.dispatchEvent(new Event('change', {bubbles:true})); document.querySelector('[data-cat-close]').click(); })()`); await sleep(400);
    check('“on holiday” hides the cat and is remembered', await js(`document.querySelector('.roam-cat').hidden && localStorage.getItem('cat-mode') === 'away'`));
    await js(`localStorage.removeItem('cat-mode')`);
    await js(`document.getElementById('language-button').click()`); await sleep(600);
    check('language switch updates the cat button', await js(`document.getElementById('cat-button').textContent.includes('Cat')`));
  }
  check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '));
} catch (e) {
  console.error(e); check('script completed', false, String(e.message).slice(0, 300));
} finally {
  writeFileSync(join(out, 'verification.json'), JSON.stringify({ date: new Date().toISOString(), base, results, errors }, null, 2));
  try { ws?.close(); } catch {}
  proc.kill();
  const failed = results.filter(r => !r.ok).length;
  console.log(`${results.length - failed}/${results.length} passed`);
  process.exit(failed ? 1 : 0);
}
