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
const pending = new Map(), errors = [], results = [], dialogs = [];
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
  // Wait for the app and the cat to be ready rather than a fixed time.
  for (let i = 0; i < 60; i++) {
    await sleep(250);
    if (await js(`document.readyState === 'complete' && typeof request === 'function' && !!window.libraryCat`).catch(() => false)) break;
  }
  await sleep(1200);
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
    if (m.method === 'Page.javascriptDialogOpening') { dialogs.push(m.params); send('Page.handleJavaScriptDialog', { accept: false }); return; } // cancel: never delete in checks
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
  if (want('library')) {
    // Fill the sandbox library through the app's own free sample flow (Auto mode, simulated).
    await viewport(1440, 900); await load('he');
    for (let n = await js(`request('/document-library',{}).then(r => (r.documents || []).length)`); n < 7; n++) {
      await js(`sample()`);
      for (let i = 0; i < 60 && (await js(`currentJob?.status`)) !== 'completed'; i++) await sleep(500);
      await js(`show('start-panel')`); await sleep(200);
    }
    await js(`openLibrary()`); await sleep(1500);
    const spines = await js(`document.querySelectorAll('.lib-spine').length`);
    check('the library opens as a shelf of books', spines >= 7 && await js(`!document.getElementById('library-shelf').hidden && document.getElementById('library-list').hidden`), String(spines));
    await shot('library-shelf');
    const r = await js(`(() => { const b = document.querySelectorAll('.lib-spine')[2].getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2 }; })()`);
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: r.x, y: r.y }); await sleep(600);
    check('hover turns the book to its cover (flat 2D turn)', await js(`getComputedStyle(document.querySelectorAll('.lib-spine')[2].querySelector('.cover-face')).transform === 'matrix(1, 0, 0, 1, 0, 0)'`));
    check('books are matte: no perspective or 3D on the shelf', await js(`[...document.querySelectorAll('.library-shelf, .library-shelf *')].every(e => { const s = getComputedStyle(e); return s.perspective === 'none' && s.transformStyle !== 'preserve-3d'; })`));
    await shot('library-hover');
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 5, y: 5 });
    await js(`document.querySelectorAll('.lib-spine')[2].click()`); await sleep(500);
    check('a book opens its real item (download, open, delete) in the card', await js(`(() => { const c = document.getElementById('library-shelf-detail'); return !c.hidden && !!c.querySelector('.library-item .library-download') && !!c.querySelector('.library-open') && !!c.querySelector('.library-delete'); })()`));
    await shot('library-detail', true);
    dialogs.length = 0;
    await js(`document.querySelector('#library-shelf-detail .library-delete').click()`); await sleep(600);
    check('delete still asks for confirmation (cancelled here)', dialogs.some(d => d.type === 'confirm'), dialogs.map(d => d.message.slice(0, 40)).join(' | '));
    check('cancelled delete keeps the book', (await js(`request('/document-library',{}).then(r => (r.documents || []).length)`)) >= 7);
    await js(`document.querySelector('[data-shelf-view=list]').click()`); await sleep(400);
    check('list view shows the original list', await js(`!document.getElementById('library-list').hidden && document.getElementById('library-shelf').hidden && document.querySelectorAll('#library-list > li').length >= 7`));
    await shot('library-list');
    await js(`document.querySelector('[data-shelf-view=shelf]').click()`); await sleep(300);
    await js(`document.getElementById('language-button').click()`); await sleep(1500);
    check('English library keeps the shelf and translated tools', await js(`!document.getElementById('library-shelf').hidden && document.getElementById('library-search').placeholder === 'Search by file name'`));
    await shot('library-shelf-en');
    await js(`document.getElementById('language-button').click()`); await sleep(500);
  }
  if (want('form')) {
    await viewport(1440, 900); await load('he');
    await js(`document.getElementById('translation-options').open = true`); await sleep(300);
    check('short choices are option cards backed by the original selects', await js(`['profile','target-language','model','quality','ocr-review'].every(id => document.getElementById(id).nextElementSibling?.classList.contains('seg-group'))`));
    await js(`document.querySelector('input[name="seg-profile"][value="literary"]').click()`); await sleep(300);
    check('a card writes the select and the summary follows', await js(`document.getElementById('profile').value === 'literary' && document.getElementById('profile-summary').textContent.startsWith('ספרותי')`));
    await js(`document.querySelector('input[name="seg-model"][value="configured"]').click()`); await sleep(500);
    check('own model: review level follows ui.js and model settings open', await js(`document.querySelector('input[name="seg-quality"]:checked')?.value === document.getElementById('quality').value && !document.getElementById('model-settings').hidden`));
    check('own model enables the English target card', await js(`!document.querySelector('input[name="seg-target-language"][value="en"]').disabled`));
    await shot('form-own-model', true);
    await js(`document.querySelector('input[name="seg-model"][value="auto"]').click()`); await sleep(300);
    check('Auto disables the English target card', await js(`document.querySelector('input[name="seg-target-language"][value="en"]').disabled && document.querySelector('input[name="seg-target-language"][value="he"]').checked`));
    await js(`document.querySelector('input[name="seg-model"][value="configured"]').click()`); await sleep(300);
    await js(`document.getElementById('model').value = 'auto'; updateSettings()`); await sleep(200);
    check('programmatic changes reach the cards (as sample() does)', await js(`document.querySelector('input[name="seg-model"][value="auto"]').checked`));
    check('the disabled start button shows what is missing', await js(`(() => { const b = document.getElementById('translate-button'); const n = document.getElementById('send-note'); return !b.disabled || getComputedStyle(n).backgroundColor !== 'rgba(0, 0, 0, 0)'; })()`));
    await js(`document.getElementById('language-button').click()`); await sleep(800);
    check('cards speak English after the switch', await js(`[...document.querySelectorAll('.seg-group b')].some(b => b.textContent.trim() === 'Academic')`), await js(`[...document.querySelectorAll('.seg-group b')].slice(0,4).map(b => b.textContent).join(' | ')`));
    await shot('form-en', true);
    await js(`document.getElementById('language-button').click()`); await sleep(400);
    await viewport(390, 844, true); await sleep(600);
    check('options fit a phone', (await js(`document.documentElement.scrollWidth`)) <= 390);
    await shot('form-390', true);
  }
  if (want('bindery')) {
    await viewport(1440, 900); await load('he');
    check('the processing book is the bindery scene', await js(`(() => { const b = document.getElementById('pixel-book'); return b.classList.contains('bindery') && b.querySelectorAll('.leaf').length === 2 && b.querySelectorAll('.fl').length === 11 && !!b.querySelector('[data-perch=bindery]'); })()`));
    // Freeze the scene in each real job status and capture it (no job needed for the drawing itself).
    await js(`show('processing-panel'); document.getElementById('processing-title').textContent = 'מתרגמים…'`);
    const box = await js(`(() => { window.scrollTo(0, 0); const r = document.getElementById('pixel-book').getBoundingClientRect(); return { x: r.left, y: r.top, width: r.width, height: r.height }; })()`);
    for (const step of ['reading', 'translating', 'reviewing', 'rebuilding']) {
      await js(`(() => { const b = document.getElementById('pixel-book'); b.dataset.phase = 'open'; b.dataset.step = '${step}'; })()`); await sleep(500);
      await js(`document.getElementById('pixel-book').getAnimations({ subtree: true }).forEach(a => { a.pause(); a.currentTime = 0.42 * a.effect.getComputedTiming().duration - (a.effect.getTiming().delay || 0); })`); await sleep(120);
      const r = await send('Page.captureScreenshot', { format: 'png', clip: { ...box, scale: 1 } });
      writeFileSync(join(out, `bindery-${step}.png`), Buffer.from(r.data, 'base64'));
    }
    await js(`document.getElementById('pixel-book').getAnimations({ subtree: true }).forEach(a => a.play())`);
    await js(`document.getElementById('pixel-book').dataset.phase = 'paused'`); await sleep(300);
    check('a paused job freezes the bindery', await js(`getComputedStyle(document.querySelector('#pixel-book .leaf')).animationPlayState === 'paused'`));
    // A real free Auto job: processing, then the finished book on the result page.
    await js(`show('start-panel')`); await js(`sample()`);
    for (let i = 0; i < 60 && (await js(`currentJob?.status`)) !== 'completed'; i++) await sleep(400);
    await sleep(800);
    check('the finished job shows the result with the bound book', await js(`!document.getElementById('result-panel').hidden && document.getElementById('result-book-host').contains(document.getElementById('pixel-book')) && document.getElementById('pixel-book').dataset.phase === 'finished'`));
    await shot('result-he', true);
    await js(`document.getElementById('language-button').click()`); await sleep(800);
    check('the page stamp follows the language', await js(`document.querySelector('#pixel-book .page-stamp').textContent === 'DRAFT'`));
    await shot('result-en', true);
    await js(`document.getElementById('language-button').click()`); await sleep(300);
  }
  if (want('learning')) {
    await viewport(1440, 900);
    await send('Page.navigate', { url: base + 'learning' }); await sleep(2500);
    check('learning window: book typeface and logo', await js(`document.fonts.ready.then(() => document.fonts.check('600 20px "Frank Ruhl Libre"') && !!document.querySelector('.app-header .brand-logo'))`));
    const options = await js(`[...document.getElementById('learning-language').options].map(o => o.value).filter(Boolean)`);
    if (options.length) { await js(`(() => { const s = document.getElementById('learning-language'); s.value = ${JSON.stringify(options[0])}; s.dispatchEvent(new Event('change', { bubbles: true })); })()`); await sleep(1500); }
    const samples = [];
    for (let i = 0; i < 6; i++) { samples.push(await js(catState)); await sleep(800); }
    check('the cat visits the learning window, never on text', samples.some(s => s.shown) && samples.every(s => !s.shown || !s.anchor || ['held', 'jump'].includes(s.pose) || !s.hits.length), JSON.stringify(samples.at(-1)));
    await shot('learning-he');
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
