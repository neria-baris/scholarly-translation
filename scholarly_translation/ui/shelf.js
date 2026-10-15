/* The library as a bookshelf. Built from the list items ui.js renders (#library-list > li), so the
   data flow, actions and their handlers stay exactly as they are; a spine opens the item's own
   detail panel inside a card below the shelf. The list view is the original list. */
(() => {
  'use strict';
  const he = () => document.documentElement.lang !== 'en';
  const L = (h, e) => (he() ? h : e);
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pref = (key, fallback) => { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } };
  const setPref = (key, value) => { try { localStorage.setItem(key, value); } catch { /* memory only */ } };
  const CLOTH = ['#7b3f37', '#3f5f48', '#a3602f', '#5a5470', '#86683b', '#2f5566', '#6d4a6b', '#57674a', '#94473b', '#40626b', '#6b5b45', '#4a5a6e'];
  const hash = s => [...String(s)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
  const state = { view: pref('library-view', 'shelf'), sort: pref('library-sort', 'recent'), search: '', rows: 3, selected: null };
  // While a book is open, its whole list item (entry + detail + handlers) sits in the card, so every
  // item-scoped lookup in ui.js (errors, font select, buttons) keeps working.
  let moved = null; // {li, entry}

  function tools() {
    const host = $('library-tools');
    if (!host) return;
    host.innerHTML = `<label class="library-search"><span class="visually-hidden">${L('חיפוש בספרייה', 'Search the library')}</span>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6" fill="none" stroke="currentColor" stroke-width="2"/><path d="m15 15 5 5" stroke="currentColor" stroke-width="2"/></svg>
        <input id="library-search" type="search" autocomplete="off" placeholder="${L('חיפוש לפי שם קובץ', 'Search by file name')}" value="${esc(state.search)}"></label>
      <label class="library-sort"><span class="visually-hidden">${L('מיון', 'Sort')}</span><select id="library-sort">${[['recent', L('האחרונים קודם', 'Most recent')], ['name', L('לפי שם', 'By name')], ['size', L('הגדולים קודם', 'Largest first')]]
        .map(([v, l]) => `<option value="${v}" ${state.sort === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      <div class="library-view" role="group" aria-label="${L('תצוגת הספרייה', 'Library view')}"><button type="button" data-shelf-view="shelf" aria-pressed="${state.view === 'shelf'}">${L('מדף', 'Shelf')}</button><button type="button" data-shelf-view="list" aria-pressed="${state.view === 'list'}">${L('רשימה', 'List')}</button></div>`;
  }

  function readItem(li) {
    const entry = li.querySelector('.library-entry');
    const title = entry?.querySelector('strong')?.textContent || '';
    const kind = li.querySelector('.library-kind')?.dataset.kind || 'pdf';
    const id = li.dataset.jobId || title;
    const size = Number(li.dataset.size || 0), h = hash(id);
    return { li, entry, id, title, kind, size, date: li.dataset.date || '', progress: li.dataset.progress,
      meta: entry?.querySelector('.library-meta')?.textContent || '', driveOnly: li.classList.contains('drive-only'),
      inDrive: !!li.querySelector('.drive-badge') && !li.classList.contains('drive-only'), blocked: !!li.querySelector('.library-flag'),
      color: CLOTH[h % CLOTH.length], w: Math.round(Math.min(54, Math.max(28, 26 + size / 14))), height: 124 + h % 44, label: h % 3 === 0 };
  }
  function ordered() {
    const list = $('library-list');
    const items = [...list.querySelectorAll(':scope > li.library-item')].map(readItem);
    const q = state.search.trim().toLocaleLowerCase();
    if (state.sort === 'name') items.sort((a, b) => a.title.localeCompare(b.title, he() ? 'he' : 'en'));
    else if (state.sort === 'size') items.sort((a, b) => b.size - a.size);
    else items.sort((a, b) => String(b.date).localeCompare(String(a.date)));
    items.forEach(item => { list.append(item.li); item.li.hidden = !!q && !item.title.toLocaleLowerCase().includes(q); });
    return items.filter(item => !item.li.hidden);
  }
  function spine(b) {
    const status = b.progress != null && b.progress !== '' ? `${b.progress}%` : '';
    const label = [b.title, b.kind.toUpperCase(), b.meta, b.driveOnly ? L('רק ב־Drive', 'Drive only') : '', b.blocked ? L('נדרשת החלטה', 'Decision required') : ''].filter(Boolean).join(' · ');
    const cover = Math.round(Math.min(132, b.height * .74));
    return `<button type="button" class="lib-spine${b.driveOnly ? ' drive-only' : ''}${state.selected === b.id ? ' is-selected' : ''}" data-shelf-book="${esc(b.id)}" aria-expanded="${state.selected === b.id}" aria-controls="library-shelf-detail" aria-label="${esc(label)}" style="--c:${b.color};--w:${b.w}px;--h:${b.height}px;--cw:${cover}px">
      <span class="spine-face" aria-hidden="true"><span class="spine-title${b.label ? ' plate' : ''}" dir="auto">${esc(b.title.replace(/\.[^.]+$/, ''))}</span><span class="spine-kind">${b.kind.toUpperCase()}</span>
        ${b.inDrive ? '<i class="spine-cloud"></i>' : ''}${status ? '<i class="spine-ribbon"></i>' : ''}${b.blocked ? '<i class="spine-flag">!</i>' : ''}</span>
      <span class="cover-face" aria-hidden="true"><span class="cover-kind">${b.kind.toUpperCase()}</span><span class="cover-plate" dir="auto">${esc(b.title.replace(/\.[^.]+$/, ''))}</span>
        <span class="cover-meta" dir="auto">${esc(b.meta)}</span>${status ? `<span class="cover-progress"><i style="width:${esc(status)}"></i></span>` : ''}${b.blocked ? `<span class="cover-flag">${L('נדרשת החלטה', 'Decision needed')}</span>` : ''}${b.driveOnly ? `<span class="cover-flag">${L('רק ב־Drive', 'Drive only')}</span>` : ''}</span></button>`;
  }
  const DECOR = '<span class="shelf-decor" aria-hidden="true"><i class="decor-stack"><b></b><b></b><b></b></i><i class="decor-candle"></i><span class="decor-basket" data-perch="basket"></span><i class="decor-plant"></i></span>';

  function restoreDetail() {
    if (!moved) return;
    const { li, entry } = moved;
    const detail = li.querySelector('.library-detail');
    if (detail) detail.hidden = true;
    entry?.setAttribute('aria-expanded', 'false');
    li.classList.remove('open', 'in-card');
    $('library-list')?.append(li);
    moved = null;
  }
  function showDetail() {
    const card = $('library-shelf-detail');
    if (!card) return;
    restoreDetail();
    const items = ordered();
    const b = items.find(item => item.id === state.selected);
    if (!b) { card.hidden = true; card.innerHTML = ''; return; }
    card.innerHTML = `<div class="shelf-detail-cover" style="--c:${b.color}" aria-hidden="true"><span class="cover-kind">${b.kind.toUpperCase()}</span><span class="cover-plate" dir="auto">${esc(b.title.replace(/\.[^.]+$/, ''))}</span></div>
      <div class="shelf-detail-body"><div class="shelf-detail-head"><span class="eyebrow">${b.kind.toUpperCase()}${b.driveOnly ? ' · ' + L('רק ב־Drive', 'Drive only') : b.inDrive ? ' · ' + L('מגובה ב־Drive', 'Backed up to Drive') : ''}</span>
        <button type="button" class="quiet-button shelf-detail-close" data-shelf-close aria-label="${L('סגירת פרטי הספר', 'Close book details')}">✕</button></div>
        <h3 id="shelf-detail-title" dir="auto">${esc(b.title)}</h3><p class="shelf-detail-meta" dir="auto">${esc(b.meta)}</p><ul class="shelf-detail-item"></ul></div>`;
    card.setAttribute('aria-labelledby', 'shelf-detail-title');
    moved = { li: b.li, entry: b.entry };
    b.li.classList.add('open', 'in-card');
    card.querySelector('.shelf-detail-item').append(b.li);
    const detail = b.li.querySelector('.library-detail');
    if (detail) detail.hidden = false;
    b.entry?.setAttribute('aria-expanded', 'true');
    card.hidden = false;
  }

  function build() {
    const shelf = $('library-shelf'), list = $('library-list'), card = $('library-shelf-detail');
    if (!shelf || !list) return;
    if (moved) {
      // A plain rebuild (resize, sort) returns the open item to the list; after a re-render the
      // list already holds a fresh item for the same book, and the old one is dropped.
      const id = moved.li.dataset.jobId;
      if ([...list.children].some(li => li !== moved.li && li.dataset.jobId === id)) moved = null;
      else restoreDetail();
    }
    if (!$('library-search')) tools();
    const items = ordered();
    const shelfView = state.view === 'shelf';
    list.hidden = shelfView;
    shelf.hidden = !shelfView || !items.length;
    if (card) card.hidden = true;
    if (!shelfView) { window.libraryCat?.refresh(); return; }
    if (!items.some(item => item.id === state.selected)) state.selected = null;
    const width = Math.max(200, shelf.clientWidth - 40), rows = [[]];
    let used = 0;
    for (const item of items) {
      if (used + item.w + 5 > width && rows.at(-1).length) { rows.push([]); used = 0; }
      rows.at(-1).push(item); used += item.w + 5;
    }
    const shown = rows.slice(0, state.rows), count = shown.flat().length;
    shelf.innerHTML = shown.map((row, i) => `<div class="shelf-row"><div class="shelf-books">${row.map(spine).join('')}${i === rows.length - 1 ? DECOR : ''}</div><div class="shelf-plank" data-perch="plank-${i}"></div></div>`).join('')
      + (rows.length > shown.length ? `<div class="shelf-more"><span>${L(`מוצגים ${count} מתוך ${items.length} ספרים`, `Showing ${count} of ${items.length} books`)}</span><button type="button" class="secondary-button" data-shelf-more>${L('עוד מדפים', 'More shelves')}</button></div>` : '');
    showDetail();
    window.libraryCat?.refresh();
  }

  document.addEventListener('click', event => {
    const book = event.target.closest('[data-shelf-book]');
    if (book) {
      state.selected = state.selected === book.dataset.shelfBook ? null : book.dataset.shelfBook;
      document.querySelectorAll('[data-shelf-book]').forEach(s => { const on = s.dataset.shelfBook === state.selected; s.classList.toggle('is-selected', on); s.setAttribute('aria-expanded', String(on)); });
      showDetail();
      if (state.selected) $('library-shelf-detail')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      window.libraryCat?.refresh();
      return;
    }
    if (event.target.closest('[data-shelf-close]')) {
      const id = state.selected; state.selected = null; showDetail();
      const back = document.querySelector(`[data-shelf-book="${CSS.escape(id)}"]`);
      back?.setAttribute('aria-expanded', 'false'); back?.classList.remove('is-selected'); back?.focus();
      return;
    }
    if (event.target.closest('[data-shelf-more]')) {
      const before = document.querySelectorAll('.lib-spine').length;
      state.rows += 3; build();
      document.querySelectorAll('.lib-spine')[before]?.focus({ preventScroll: true });
      return;
    }
    const view = event.target.closest('[data-shelf-view]');
    if (view) { restoreDetail(); state.view = view.dataset.shelfView; setPref('library-view', state.view); state.rows = 3; tools(); build(); document.querySelector(`[data-shelf-view="${state.view}"]`)?.focus(); }
  });
  document.addEventListener('input', event => { if (event.target.id === 'library-search') { restoreDetail(); state.search = event.target.value; state.rows = 3; build(); } });
  document.addEventListener('change', event => { if (event.target.id === 'library-sort') { restoreDetail(); state.sort = event.target.value; setPref('library-sort', state.sort); state.rows = 3; build(); } });
  // Arrow keys move along the shelf, like reading the spines.
  document.addEventListener('keydown', event => {
    const book = event.target.closest?.('.lib-spine');
    if (!book || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const all = [...document.querySelectorAll('.lib-spine')], i = all.indexOf(book);
    const forward = (event.key === 'ArrowLeft') === he();
    const next = event.key === 'Home' ? all[0] : event.key === 'End' ? all.at(-1) : all[i + (forward ? 1 : -1)];
    if (next) { event.preventDefault(); next.focus(); }
  });
  let resizeTimer = 0;
  addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (!$('library-panel')?.hidden && state.view === 'shelf') build(); }, 150); });
  new MutationObserver(() => { if ($('library-tools')) { tools(); if (!$('library-panel')?.hidden) build(); } }).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });

  window.libraryShelf = { build, restoreDetail };
  tools();
})();
