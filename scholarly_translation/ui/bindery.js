/* The bindery: the processing book becomes a desk scene with a real page turn. ui.js keeps driving
   #pixel-book (data-phase: start/open/paused/error/finished, data-step: the job status); this only
   draws the scene once. Decorative and aria-hidden: progress and status stay in text. */
(() => {
  'use strict';
  const book = document.getElementById('pixel-book');
  if (!book) return;
  const he = () => document.documentElement.lang !== 'en';
  const lines = (n, cls) => `<div class="lines ${cls}">${Array.from({ length: n }, (_, i) => `<i style="--w:${[92, 84, 96, 70, 88, 94, 62, 90, 80][i % 9]}%"></i>`).join('')}</div>`;
  const stamp = () => `<span class="page-stamp">${he() ? 'טיוטה' : 'DRAFT'}</span>`;
  const leaf = delay => `<div class="leaf" style="--delay:${delay}"><div class="face front">${lines(8, 'src')}</div><div class="face back">${lines(8, 'tgt')}${stamp()}</div></div>`;
  // Letters rise out of the pages and change script mid-flight: mostly English into Hebrew, some back.
  const pairs = [['A', 'א'], ['B', 'ב'], ['G', 'ג'], ['D', 'ד'], ['H', 'ה'], ['L', 'ל'], ['M', 'מ'], ['N', 'נ'], ['S', 'ס'], ['T', 'ת'], ['R', 'ר'], ['K', 'כ']];
  const letters = Array.from({ length: 11 }, (_, i) => {
    const [en, heb] = pairs[(i * 5) % pairs.length], toHe = i % 3 !== 2;
    const x = toHe ? 36 + (i * 37) % 130 : -(36 + (i * 53) % 130), dx = toHe ? -(24 + (i * 17) % 80) : 24 + (i * 23) % 80;
    return `<span class="fl" style="--x:${x}px;--y:${(i * 29) % 60}px;--dx:${dx}px;--rise:${120 + (i * 13) % 70}px;--d:${-(i * .53).toFixed(2)}s;--dur:${(3.8 + (i % 4) * .45).toFixed(2)}s"><b class="from">${toHe ? en : heb}</b><b class="to">${toHe ? heb : en}</b></span>`;
  }).join('');
  const quill = '<svg viewBox="0 0 34 84"><path d="M30 2C14 14 6 36 9 62l3 8c2-22 9-44 18-68z" fill="#fffaf0" stroke="#cdbb92" stroke-width="1"/><path d="M30 2C20 22 14 44 11 70" fill="none" stroke="#9c7c4a" stroke-width="1.4"/><path d="M14 30l-5 2M16 22l-6 3M13 40l-5 1M12 50l-4 1" stroke="#e4d6b8" stroke-width="1"/><path d="M10 68l1 14 3-13z" fill="#2b1c10"/></svg>';

  function draw() {
    book.classList.add('bindery');
    book.innerHTML = `<div class="bd-glow"></div><div class="bd-window"><i class="bd-moon"></i><i class="bd-star"></i><i class="bd-star two"></i><i class="bd-star three"></i></div>
      <div class="bd-lamp"><i class="bd-cord"></i><i class="bd-shade"></i><i class="bd-bulb"></i></div>
      <div class="bd-desk"></div><i class="bd-perch" data-perch="bindery"></i>
      <div class="bd-stage"><div class="tome"><div class="tome-cover"></div>
        <div class="tome-page left">${lines(8, 'tgt')}${stamp()}</div><div class="tome-page right">${lines(8, 'src')}</div>
        ${leaf('0s')}${leaf('calc(var(--turn) / -2)')}<div class="tome-gutter"></div></div></div>
      <div class="bd-letters">${letters}</div>
      <div class="bd-props"><div class="bd-glass"></div><div class="bd-stamper"><i></i></div><div class="bd-ink"></div><div class="bd-quill">${quill}</div><div class="bd-candle"><i></i></div></div>`;
  }
  draw();
  new MutationObserver(() => book.querySelectorAll('.page-stamp').forEach(node => { node.textContent = he() ? 'טיוטה' : 'DRAFT'; }))
    .observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
})();
