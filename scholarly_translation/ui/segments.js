/* Short choices as option cards. Each hidden <select> stays the single source of truth for ui.js:
   a card writes select.value and fires "change"; the cards follow every select change (options,
   labels, disabled state, programmatic values) via a MutationObserver and libraryForm.sync(). */
(() => {
  'use strict';
  const FIELDS = ['profile', 'target-language', 'model', 'quality', 'ocr-review'];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  // "Scholarly (precise, notes kept)" or "Fast — no extra review" -> title and caption.
  function split(text) {
    const paren = text.match(/^(.*?)\s*\((.*)\)\s*$/);
    if (paren) return [paren[1], paren[2]];
    const dash = text.match(/^(.*?)\s+[—–-]\s+(.*)$/);
    return dash ? [dash[1], dash[2]] : [text, ''];
  }
  const signature = select => [select.disabled, ...[...select.options].map(o => `${o.value}|${o.disabled}|${o.textContent.trim()}`)].join('§');

  function build(select) {
    let group = select.nextElementSibling?.classList.contains('seg-group') ? select.nextElementSibling : null;
    if (!group) {
      group = document.createElement('div');
      group.className = 'seg-group';
      group.setAttribute('role', 'radiogroup');
      const label = document.querySelector(`label[for="${select.id}"]`);
      if (label) { label.id ||= `${select.id}-label`; group.setAttribute('aria-labelledby', label.id); }
      select.classList.add('seg-source');
      select.tabIndex = -1;
      select.setAttribute('aria-hidden', 'true');
      select.after(group);
    }
    group.dataset.signature = signature(select);
    group.innerHTML = [...select.options].map(option => {
      const [title, caption] = split(option.textContent.trim());
      const off = option.disabled || select.disabled;
      return `<label class="seg-choice${off ? ' is-disabled' : ''}"><input type="radio" name="seg-${select.id}" value="${esc(option.value)}" ${option.value === select.value ? 'checked' : ''} ${off ? 'disabled' : ''}><span><b>${esc(title)}</b>${caption ? `<small>${esc(caption)}</small>` : ''}</span></label>`;
    }).join('');
  }
  function sync() {
    for (const id of FIELDS) {
      const select = document.getElementById(id);
      if (!select) continue;
      const group = select.nextElementSibling?.classList.contains('seg-group') ? select.nextElementSibling : null;
      if (!group || group.dataset.signature !== signature(select)) { build(select); continue; }
      group.querySelectorAll('input').forEach(input => { input.checked = input.value === select.value; });
    }
  }
  document.addEventListener('change', event => {
    const input = event.target;
    if (!input.name?.startsWith('seg-')) return;
    const select = document.getElementById(input.name.slice(4));
    if (!select || select.value === input.value) return;
    select.value = input.value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    sync();
  });
  document.addEventListener('change', event => { if (FIELDS.includes(event.target.id)) sync(); });
  const watch = new MutationObserver(sync);
  for (const id of FIELDS) {
    const select = document.getElementById(id);
    if (select) watch.observe(select, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['disabled'] });
  }
  window.libraryForm = { sync };
  sync();
})();
