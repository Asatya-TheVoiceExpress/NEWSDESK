import { hydrate, cleanHTML, makeBlock, decorateGrid, emptyCell } from './blocks.js';

export class Editor {
  constructor(canvas, { onChange, onCaret } = {}) {
    this.canvas = canvas;
    this.onChange = onChange || (() => {});
    this.onCaret = onCaret || (() => {});
    this.undoStack = []; this.redoStack = []; this.present = '<p><br></p>';
    this._mt = null; this._active = null; this._activeCell = null;
    this._wire();
  }

  load(html) {
    this.canvas.innerHTML = html || '<p><br></p>';
    hydrate(this.canvas);
    this.undoStack = []; this.redoStack = []; this.present = this.serialize();
    this.onChange();
  }
  serialize() { return cleanHTML(this.canvas); }
  focus() { this.canvas.focus(); }

  range() {
    const s = window.getSelection();
    return s && s.rangeCount ? s.getRangeAt(0) : null;
  }
  _topBlock(node) {
    let n = node; while (n && n.parentElement !== this.canvas) n = n.parentElement;
    return (n && this.canvas.contains(n) && n !== this.canvas) ? n : null;
  }
  _track(node) {
    const eln = node && node.nodeType === 1 ? node : node?.parentElement;
    if (!eln) return;
    const b = this._topBlock(eln); if (b) this._active = b;
    const cell = eln.closest?.('.de-grid-cell, .photo-unit figure');
    this._activeCell = (cell && this.canvas.contains(cell)) ? cell : null;
  }
  activeBlock() {
    if (this._active && this.canvas.contains(this._active)) return this._active;
    const r = this.range();
    const sb = r && this.canvas.contains(r.startContainer) ? this._topBlock(r.startContainer) : null;
    return sb || this.canvas.lastElementChild;
  }
  activeCell() { return (this._activeCell && this.canvas.contains(this._activeCell)) ? this._activeCell : null; }
  _caretP() {
    const r = this.range();
    if (!r || !this.canvas.contains(r.startContainer)) return null;
    let n = r.startContainer;
    if (n.nodeType === 3) n = n.parentElement;
    while (n && n !== this.canvas && n.tagName !== 'P') n = n.parentElement;
    return (n && n !== this.canvas && n.tagName === 'P') ? n : null;
  }
  placeCaret(node, atStart = false) {
    const target = node.querySelector?.('p, figcaption, .compare-label, td, h2') || node;
    const r = document.createRange();
    r.selectNodeContents(target);
    r.collapse(atStart);
    const s = window.getSelection();
    s.removeAllRanges(); s.addRange(r);
    this.canvas.focus();
    this._track(target);  
  }

  insertBlock(id) {
    const b = makeBlock(id);
    if (!b) return;
    this.insertElement(b);
    return b;
  }
  insertElement(b) {
    const active = this.activeBlock();
    if (active && active.parentElement === this.canvas) active.after(b);
    else this.canvas.appendChild(b);
    hydrate(this.canvas);
    this.placeCaret(b, true);
    this.changed();
  }
  insertHTMLAtCaret(html) {
    const r = this.range();
    if (!r) { this.canvas.insertAdjacentHTML('beforeend', html); }
    else {
      r.deleteContents();
      const frag = document.createRange().createContextualFragment(html);
      const last = frag.lastChild;
      r.insertNode(frag);
      if (last) { const nr = document.createRange(); nr.setStartAfter(last); nr.collapse(true);
        const s = window.getSelection(); s.removeAllRanges(); s.addRange(nr); }
    }
    hydrate(this.canvas);
    this.changed();
  }

  applyRole(role) {
    let b = this.activeBlock();
    const r = this.range();
    if (b && b.classList?.contains('article-section') && r) {
      let p = r.startContainer;
      while (p && p.parentElement && !(p.tagName === 'P')) p = p.parentElement;
      if (p && b.contains(p)) b = p;
    }
    if (!b) return;
    if (b.tagName !== 'P') return;  
    if (role) b.setAttribute('data-text-role', role);
    else b.removeAttribute('data-text-role');
    this.changed();
  }
  exec(cmd) { document.execCommand(cmd, false, null); this.changed(); }
  makeLink() {
    const url = prompt('Link URL', 'https://');
    if (url) document.execCommand('createLink', false, url);
    this.changed();
  }
  insertFootnote() {
    const n = this.canvas.querySelectorAll('p.fn[id^="fn"]').length + 1;
    this.insertHTMLAtCaret(`<sup data-fn="${n}">${n}</sup>`);
    if (!this.canvas.querySelector(`#fn${n}`))
      this.canvas.appendChild(
        document.createRange().createContextualFragment(`<p class="fn" id="fn${n}">${n}. Note…</p>`));
    this.changed();
  }
  insertCitationRef(n) { this.insertHTMLAtCaret(`<sup data-cite="${n}">[${n}]</sup>`); }
  // After citation `removed` (1-based) is deleted: drop its markers, shift later ones down.
  renumberCitations(removed) {
    this.canvas.querySelectorAll('sup[data-cite]').forEach(s => {
      const n = parseInt(s.dataset.cite, 10);
      if (n === removed) s.remove();
      else if (n > removed) { s.dataset.cite = String(n - 1); s.textContent = `[${n - 1}]`; }
    });
    this.changed();
  }

  selectionText() { const r = this.range(); return r ? r.toString() : ''; }
  convertSelectionTo(kind, attribution) {
    const text = this.selectionText().trim();
    if (!text) return;
    let html;
    if (kind === 'pull-quote') html = `<blockquote class="pull-quote">${text}</blockquote>`;
    else if (kind === 'field-quote') html = `<blockquote class="field-quote">${text}<cite>— ${attribution || 'Source'}</cite></blockquote>`;
    else if (kind === 'spoken-quote') html = `<blockquote class="spoken-quote">${text}<cite>— ${attribution || 'Speaker'}</cite></blockquote>`;
    else if (kind === 'section') html = `<div class="article-section"><h2 class="section-heading">${text}</h2><p><br></p></div>`;
    else return;
    const r = this.range();
    r.deleteContents();
    const frag = document.createRange().createContextualFragment(html);
    const node = frag.firstElementChild;
    const active = this.activeBlock();
    if (active && active.parentElement === this.canvas) active.after(node); else this.canvas.appendChild(node);
    hydrate(this.canvas);
    this.placeCaret(node, false);
    this.changed();
  }

  addCell(grid) { const comic = grid.dataset.type === 'comic'; grid.appendChild(emptyCell(comic)); decorateGrid(grid); this.changed(); }
  removeCell(cell) { const g = cell.parentElement; cell.remove(); if (g) decorateGrid(g); this.changed(); }
  setImage(cell, url, alt) {
    cell.querySelector('.de-cell-empty')?.remove();
    let img = cell.querySelector('img');
    if (!img) { img = document.createElement('img'); cell.insertBefore(img, cell.firstChild); }
    img.src = url; img.alt = alt || '';
    this.changed();
  }

  stats() {
    const text = this.canvas.textContent || '';
    const words = (text.trim().match(/\S+/g) || []).length;
    return { words, reading: Math.max(1, Math.round(words / 200)) };
  }

  changed() { this.onChange(); clearTimeout(this._mt); this._mt = setTimeout(() => this.mark(), 450); }

  mark() {
    const cur = this.serialize();
    if (cur === this.present) return;
    this.undoStack.push(this.present);
    if (this.undoStack.length > 120) this.undoStack.shift();
    this.present = cur; this.redoStack = [];
  }
  undo() {
    clearTimeout(this._mt); this.mark();
    if (!this.undoStack.length) return;
    this.redoStack.push(this.present);
    this.present = this.undoStack.pop();
    this._restore(this.present);
  }
  redo() {
    if (!this.redoStack.length) return;
    this.undoStack.push(this.present);
    this.present = this.redoStack.pop();
    this._restore(this.present);
  }
  _restore(html) {
    // keep the caret near where it was instead of jumping to the end
    const blocks = [...this.canvas.children];
    const at = Math.max(0, blocks.indexOf(this.activeBlock()));
    this.canvas.innerHTML = html; hydrate(this.canvas);
    const target = this.canvas.children[Math.min(at, this.canvas.children.length - 1)] || this.canvas;
    this.placeCaret(target, false);
    this.onChange();
  }

  mdShortcut() {
    const b = this.activeBlock();
    if (!b || b.tagName !== 'P') return false;
    const t = b.textContent.split(String.fromCharCode(160)).join(' ');
    let made = null;
    if (t === '# ' || t === '## ' || t === '### ') made = mk('<div class="article-section"><h2 class="section-heading"></h2></div>');
    else if (t === '> ') made = mk('<blockquote class="spoken-quote"></blockquote>');
    else if (t === '- ' || t === '* ') made = mk('<ul><li></li></ul>');
    else if (t === '1. ') made = mk('<ol><li></li></ol>');
    else if (t === '"" ') made = mk('<blockquote class="pull-quote"></blockquote>');
    if (made) { this.mark(); b.replaceWith(made); hydrate(this.canvas); this.placeCaret(made, true); this.changed(); return true; }
    if (t === '---') { this.mark(); const hr = mk('<hr class="section-divider">'); const p = mk('<p><br></p>'); b.replaceWith(hr); hr.after(p); hydrate(this.canvas); this.placeCaret(p, true); this.changed(); return true; }
    return false;
  }

  pasteHTML(frag) {
    const blockLevel = [...frag.childNodes].some(n => n.nodeType === 1 &&
      /^(P|DIV|BLOCKQUOTE|H1|H2|H3|H4|H5|H6|UL|OL|FIGURE|TABLE|HR)$/.test(n.tagName));
    if (!blockLevel) {
      const r = this.range();
      if (r) { r.deleteContents(); r.insertNode(frag); r.collapse(false); }
      else this.canvas.appendChild(frag);
    } else {
      const active = this.activeBlock();
      const nodes = [...frag.childNodes];
      if (active && active.parentElement === this.canvas) {
        let ref = active;
        nodes.forEach(n => { ref.after(n); ref = n; });
        if (active.textContent.trim() === '') active.remove();
      } else nodes.forEach(n => this.canvas.appendChild(n));
    }
    hydrate(this.canvas);
    this.changed();
  }

  _wire() {
    this.canvas.addEventListener('paste', (e) => {
      const dt = e.clipboardData; if (!dt) return;
      const html = dt.getData('text/html');
      const text = dt.getData('text/plain');
      if (!html && !text) return;
      e.preventDefault();
      const clean = html ? sanitizePaste(html)
        : text.split(/\n{2,}/).map(t => `<p>${escAttr(t).replace(/\n/g, '<br>')}</p>`).join('');
      this.pasteHTML(document.createRange().createContextualFragment(clean));
    });
    this.canvas.addEventListener('input', () => { if (!this.mdShortcut()) this.changed(); });
    const caret = () => { const r = this.range(); if (r && this.canvas.contains(r.startContainer)) this._track(r.startContainer); this.onCaret(); };
    this.canvas.addEventListener('keyup', caret);
    this.canvas.addEventListener('mouseup', caret);
    this.canvas.addEventListener('click', (e) => { this._track(e.target); this.onCaret(); });
    this.canvas.addEventListener('focus', () => this.onCaret());

    this.canvas.addEventListener('mousedown', (e) => {
      const grip = e.target.closest?.('[data-cell="move"]'); if (!grip) return;
      e.preventDefault();
      const cell = grip.closest('.de-grid-cell'); const group = cell?.parentElement; if (!group) return;
      this.mark();
      const move = (ev) => {
        const over = document.elementFromPoint(ev.clientX, ev.clientY)?.closest?.('.de-grid-cell');
        if (over && over !== cell && over.parentElement === group) {
          const r = over.getBoundingClientRect();
          group.insertBefore(cell, (ev.clientX > r.left + r.width / 2) ? over.nextSibling : over);
        }
      };
      const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); decorateGrid(group); this.changed(); };
      document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
    });
    this.canvas.addEventListener('keydown', (e) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === 'z' && !e.shiftKey) { e.preventDefault(); this.undo(); return; }
      if (mod && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))) { e.preventDefault(); this.redo(); return; }
      if (e.key === 'Enter' && e.target.classList?.contains('de-cell-empty')) e.preventDefault();
      if (mod && e.key.toLowerCase() === 'a') {
        e.preventDefault();
        const b = this.activeBlock();
        if (b) {
          const r = document.createRange();
          r.selectNodeContents(b);
          const s = window.getSelection();
          s.removeAllRanges(); s.addRange(r);
        }
        return;
      }
      if (e.key === 'Enter' && !mod) {
        const before = this._caretP();
        setTimeout(() => {
          const after = this._caretP();
          if (after && after !== before && after.hasAttribute('data-text-role')) {
            after.removeAttribute('data-text-role');
            this.changed();
          }
        }, 0);
      }
    });
  }

  moveBlock(block, beforeEl) {
    if (!block || (beforeEl === block)) return;
    this.mark();
    if (beforeEl) this.canvas.insertBefore(block, beforeEl); else this.canvas.appendChild(block);
    this.changed();
  }
}

function mk(html) { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; }

const KEEP_INLINE = new Set(['B', 'STRONG', 'I', 'EM', 'A', 'BR', 'SUP', 'CITE', 'SPAN']);
const KEEP_BLOCK = new Set(['P', 'BLOCKQUOTE', 'UL', 'OL', 'LI', 'FIGURE', 'IMG', 'FIGCAPTION', 'HR']);

export function sanitizePaste(html) {
  const root = document.createElement('div');
  root.innerHTML = html;
  root.querySelectorAll('script,style,meta,link,head,noscript,o\\:p').forEach(n => n.remove());

  const walk = (node) => {
    [...node.childNodes].forEach(child => {
      if (child.nodeType === 3) return;  
      if (child.nodeType !== 1) { child.remove(); return; }
      const tag = child.tagName;
      walk(child);  
      if (/^H[1-6]$/.test(tag)) {
        const sec = document.createElement('div'); sec.className = 'article-section';
        const h = document.createElement('h2'); h.className = 'section-heading'; h.textContent = child.textContent;
        sec.appendChild(h); child.replaceWith(sec); return;
      }
      if (tag === 'BLOCKQUOTE') {
        child.className = 'spoken-quote'; stripAttrs(child, ['class']); return;
      }
      if (tag === 'A') { const href = child.getAttribute('href') || ''; stripAttrs(child, []); if (href) child.setAttribute('href', href); return; }
      if (tag === 'IMG') { const src = child.getAttribute('src') || ''; const alt = child.getAttribute('alt') || ''; stripAttrs(child, []); child.setAttribute('src', src); child.setAttribute('alt', alt); return; }
      if (KEEP_INLINE.has(tag) || KEEP_BLOCK.has(tag)) { stripAttrs(child, []); return; }
      child.replaceWith(...child.childNodes);  
    });
  };
  walk(root);
  root.querySelectorAll('p,span,div').forEach(n => { if (!n.textContent.trim() && !n.querySelector('img,br')) n.remove(); });
  return root.innerHTML;
}

function stripAttrs(el, keep) {
  [...el.attributes].forEach(a => { if (!keep.includes(a.name)) el.removeAttribute(a.name); });
}
const escAttr = (s) => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
