export const PROSE_ROLES = ['lede', 'analysis', 'context', 'scene', 'testimony',
  'resolution', 'note', 'dateline'];

function el(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

export function emptyCell(comic = false) {
  const fig = el(comic ? '<div class="panel"></div>' : '<figure></figure>');
  fig.appendChild(el('<div class="de-ui de-cell-empty" contenteditable="false">drop image</div>'));
  fig.appendChild(el(comic
    ? '<div class="panel-caption" data-text-role="caption"></div>'
    : '<figcaption data-text-role="caption"></figcaption>'));
  return fig;
}

export const BLOCKS = [
  { id: 'section', label: 'Section', icon: 'H', keywords: 'heading chapter part',
    make: () => el('<div class="article-section" data-section-index="1"><h2 class="section-heading">Section title</h2><p>Text…</p></div>') },
  { id: 'pull-quote', label: 'Pull quote', icon: '"', keywords: 'quote display enlarge',
    make: () => el('<blockquote class="pull-quote">A line worth enlarging.</blockquote>') },
  { id: 'field-quote', label: 'Field quote', icon: '"', keywords: 'quote source attributed',
    make: () => el('<blockquote class="field-quote">A quote gathered in reporting.<cite>— Source</cite></blockquote>') },
  { id: 'spoken-quote', label: 'Spoken quote', icon: '"', keywords: 'quote speech interview verbatim',
    make: () => el('<blockquote class="spoken-quote">Verbatim speech.<cite>— Speaker</cite></blockquote>') },
  { id: 'qa-line', label: 'Q&A line', icon: 'Q', keywords: 'interview question answer dialogue',
    make: () => el('<p class="qa-line"><span class="qa-speaker">Name:</span> answer…</p>') },
  { id: 'photo', label: 'Photo', icon: '[]', keywords: 'image picture figure single',
    make: () => el('<div class="photo-unit" data-type="captioned"><figure><div class="de-ui de-cell-empty" contenteditable="false">drop image</div><figcaption data-text-role="caption">Caption</figcaption></figure></div>') },
  { id: 'grid', label: 'Photo grid', icon: ':::', keywords: 'gallery images collage group mosaic',
    make: () => {
      const g = el('<div class="photo-group" data-type="grid"></div>');
      for (let i = 0; i < 3; i++) g.appendChild(emptyCell(false));
      return g;
    } },
  { id: 'sequence', label: 'Sequence', icon: '1-2', keywords: 'event order chronological band',
    make: () => {
      const g = el('<div class="photo-group" data-type="sequence"></div>');
      for (let i = 0; i < 3; i++) g.appendChild(emptyCell(false));
      return g;
    } },
  { id: 'comic', label: 'Comic', icon: '#', keywords: 'panels gutter strip sequential',
    make: () => {
      const g = el('<div class="photo-group" data-type="comic"></div>');
      for (let i = 0; i < 4; i++) g.appendChild(emptyCell(true));
      return g;
    } },
  { id: 'comparison', label: 'Comparison', icon: '||', keywords: 'parallel side then now versus',
    make: () => el('<div class="comparison" data-count="2"><div class="compare-item"><div class="compare-label">Now</div><p>…</p></div><div class="compare-item"><div class="compare-label">Then</div><p>…</p></div></div>') },
  { id: 'table', label: 'Table', icon: '#', keywords: 'data rows columns grid tabular',
    make: () => el('<table class="article-table"><thead><tr><th>Column A</th><th>Column B</th></tr></thead><tbody><tr><td>…</td><td>…</td></tr><tr><td>…</td><td>…</td></tr></tbody></table>') },
  { id: 'intro-note', label: "Editor's note", icon: '*', keywords: 'note aside editorial intro',
    make: () => el('<p class="intro-note">Editor’s note…</p>') },
  { id: 'divider', label: 'Divider', icon: '--', keywords: 'rule break separator hr',
    make: () => el('<hr class="section-divider">') },
];

const BY_ID = Object.fromEntries(BLOCKS.map(b => [b.id, b]));
export const makeBlock = (id) => BY_ID[id] ? BY_ID[id].make() : null;

const WIDGET_SEL = '.photo-unit, .photo-group, .comparison, table.article-table';
const EDITABLE_SUBFIELDS = 'figcaption, .panel-caption, .compare-label, .compare-item p, td, th';

export function hydrate(canvas) {
  canvas.querySelectorAll(WIDGET_SEL).forEach(w => {
    w.setAttribute('contenteditable', 'false');
    w.querySelectorAll(EDITABLE_SUBFIELDS).forEach(f => f.setAttribute('contenteditable', 'true'));
  });
  canvas.querySelectorAll('hr').forEach(h => h.setAttribute('contenteditable', 'false'));
  canvas.querySelectorAll('.photo-group').forEach(g => decorateGrid(g));
  if (!canvas.lastElementChild || !isText(canvas.lastElementChild)) {
    canvas.appendChild(el('<p><br></p>'));
  }
}

const isText = (n) => n && (n.tagName === 'P' || n.tagName === 'BLOCKQUOTE' || n.classList?.contains('article-section'));

export function decorateGrid(g) {
  const comic = g.dataset.type === 'comic';
  g.querySelectorAll(':scope > figure, :scope > .panel').forEach(cell => {
    cell.classList.add('de-grid-cell');
    cell.setAttribute('contenteditable', 'false');
    cell.querySelectorAll('figcaption, .panel-caption').forEach(c => c.setAttribute('contenteditable', 'true'));
    if (!cell.querySelector('.de-cell-tools')) {
      const tools = el('<div class="de-ui de-cell-tools" contenteditable="false">'
        + '<button data-cell="move" title="Drag to reorder">⠿</button>'
        + '<button data-cell="add" title="Add cell">+</button>'
        + '<button data-cell="del" title="Remove cell">&times;</button></div>');
      cell.appendChild(tools);
    }
    if (!cell.querySelector('img') && !cell.querySelector('.de-cell-empty')) {
      const ph = el('<div class="de-ui de-cell-empty" contenteditable="false">drop image</div>');
      cell.insertBefore(ph, cell.firstChild);
    }
    if (!cell.querySelector('figcaption, .panel-caption')) {
      cell.appendChild(el(comic
        ? '<div class="panel-caption" data-text-role="caption"></div>'
        : '<figcaption data-text-role="caption"></figcaption>'));
    }
    cell.querySelectorAll('figcaption, .panel-caption').forEach(c => c.setAttribute('contenteditable', 'true'));
  });
}

export function cleanHTML(canvas) {
  const c = canvas.cloneNode(true);
  c.querySelectorAll('.de-ui').forEach(n => n.remove());
  c.querySelectorAll('[contenteditable]').forEach(n => n.removeAttribute('contenteditable'));
  c.querySelectorAll('.de-grid-cell').forEach(n => n.classList.remove('de-grid-cell'));
  c.querySelectorAll('.de-active-block').forEach(n => n.classList.remove('de-active-block'));
  c.querySelectorAll('[class=""]').forEach(n => n.removeAttribute('class'));
  c.querySelectorAll('.photo-credit').forEach(cite => { if (!cite.textContent.trim()) cite.remove(); });  
  c.querySelectorAll('figcaption, .panel-caption').forEach(cap => { if (!cap.textContent.trim()) cap.remove(); });
  c.querySelectorAll('.photo-group > figure, .photo-group > .panel').forEach(f => {
    if (!f.querySelector('img')) f.remove();
  });
  c.querySelectorAll('.photo-group, .photo-unit').forEach(g => {
    if (!g.querySelector('img')) g.remove();
  });
  let i = 0;
  c.querySelectorAll('.article-section').forEach(s => { s.setAttribute('data-section-index', String(++i)); });
  return c.innerHTML.trim();
}
