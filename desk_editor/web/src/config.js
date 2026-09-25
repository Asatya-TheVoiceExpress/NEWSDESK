import { api } from './api.js';

const get = (obj, path, dflt = '') => path.split('.').reduce((o, k) => (o && o[k] != null) ? o[k] : undefined, obj) ?? dflt;
const set = (obj, path, val) => {
  const parts = path.split('.'); let o = obj;
  for (const p of parts.slice(0, -1)) o = (o[p] = o[p] || {});
  o[parts[parts.length - 1]] = val;
};

const SECTIONS = [
  ['Publication', [
    ['publication.name', 'Publication name', 'text'],
    ['publication.tagline', 'Tagline', 'text'],
    ['publication.est', 'Year established', 'text'],
    ['publication.location', 'Location', 'text'],
    ['publication.website', 'Website', 'text'],
    ['publication.volume', 'Current volume', 'number'],
    ['publication.description', 'Short description', 'area'],
    ['publication.founding_statement', 'Founding statement', 'area'],
  ]],
  ['Team', [
    ['team.editor_in_chief', 'Editor-in-Chief', 'text'],
    ['team.web_developer', 'Web Developer', 'text'],
    ['team.head_of_marketing', 'Head of Marketing', 'text'],
    ['team.head_of_design', 'Head of Design', 'text'],
    ['team.note', 'Team note', 'area'],
  ]],
  ['Contact', [
    ['contact.email', 'Main contact email', 'text'],
    ['contact.submissions', 'Submissions email', 'text'],
    ['contact.instagram_handle', 'Instagram handle', 'text'],
    ['contact.instagram', 'Instagram URL', 'text'],
    ['contact.website', 'Contact website', 'text'],
    ['contact.emag', 'Magazine URL (emag)', 'text'],
    ['contact.newsstand', 'Newsstand URL', 'text'],
    ['contact.submissions_note', 'Submissions note', 'area'],
  ]],
  ['Support', [
    ['support.kofi.url', 'Ko-fi URL', 'text'],
    ['support.kofi.label', 'Ko-fi label', 'text'],
    ['support.kofi.note', 'Ko-fi note', 'area'],
    ['support.razorpay.url', 'Razorpay URL', 'text'],
    ['support.razorpay.label', 'Razorpay label', 'text'],
    ['support.razorpay.note', 'Razorpay note', 'area'],
    ['support.paypal.url', 'PayPal URL', 'text'],
    ['support.paypal.label', 'PayPal label', 'text'],
    ['support.general_note', 'General support note', 'area'],
  ]],
  ['Print', [
    ['broadsheet.paper_size', 'Broadsheet paper size', 'text'],
    ['broadsheet.columns', 'Broadsheet columns', 'number'],
    ['broadsheet.articles_on_front', 'Articles on front page', 'number'],
    ['broadsheet.include_sudoku', 'Include sudoku', 'bool'],
    ['broadsheet.include_crossword_clues', 'Include crossword clues', 'bool'],
    ['magazine.paper_size', 'Magazine paper size', 'text'],
    ['magazine.issue_number', 'Current issue number', 'number'],
    ['magazine.articles_per_ebook', 'Articles per eBook', 'number'],
    ['magazine.include_support_page', 'Include support page', 'bool'],
    ['magazine.include_masthead_page', 'Include masthead page', 'bool'],
    ['magazine.include_visual_toc', 'Include visual table of contents', 'bool'],
    ['magazine.grayscale_images', 'Grayscale images', 'bool'],
  ]],
];

export async function openConfigBoard() {
  const cfg = await api.configGet();
  let dirty = false;

  const back = document.createElement('div'); back.className = 'de-modal-back';
  back.innerHTML = `<div class="de-modal" style="width:min(760px,94vw)">
    <div class="de-modal-head"><h3>Site config</h3><span style="flex:1"></span>
      <button class="de-mini" id="cf-close">close</button></div>
    <div class="de-modal-body" id="cf-body"></div></div>`;
  document.body.appendChild(back);
  const body = back.querySelector('#cf-body');

  SECTIONS.forEach(([title, fields]) => {
    const h = document.createElement('div'); h.className = 'de-section-title'; h.textContent = title;
    body.appendChild(h);
    fields.forEach(([path, label, kind]) => {
      const w = document.createElement('div'); w.className = 'de-field';
      w.innerHTML = `<label>${label}</label>`;
      if (kind === 'bool') {
        const row = document.createElement('div'); row.style.display = 'flex'; row.style.alignItems = 'center'; row.style.gap = '.5rem';
        const cb = document.createElement('input'); cb.type = 'checkbox'; cb.style.width = 'auto';
        cb.checked = !!get(cfg, path, false);
        cb.onchange = () => { set(cfg, path, cb.checked); dirty = true; };
        row.appendChild(cb); w.appendChild(row);
      } else if (kind === 'area') {
        const t = document.createElement('textarea'); t.value = get(cfg, path, '');
        t.rows = 4;
        t.oninput = () => { set(cfg, path, t.value); dirty = true; };
        w.appendChild(t);
      } else {
        const i = document.createElement('input'); i.type = kind === 'number' ? 'number' : 'text';
        i.value = get(cfg, path, '');
        i.oninput = () => { set(cfg, path, kind === 'number' ? Number(i.value) : i.value); dirty = true; };
        w.appendChild(i);
      }
      body.appendChild(w);
    });
  });

  const banner = document.createElement('div'); banner.hidden = true; body.appendChild(banner);
  const save = document.createElement('button'); save.className = 'de-mini de-primary'; save.textContent = 'Save config';
  save.style.marginTop = '1rem';
  save.onclick = async () => {
    save.textContent = 'Saving…';
    try {
      await api.configSave(cfg);
      dirty = false;
      banner.className = 'de-banner ok'; banner.hidden = false;
      banner.textContent = 'Saved -- next PDF / newsletter / magazine build will use these values.';
    } catch (e) {
      banner.className = 'de-banner err'; banner.hidden = false; banner.textContent = 'Save failed: ' + e.message;
    }
    save.textContent = 'Save config';
  };
  body.appendChild(save);

  back.querySelector('#cf-close').onclick = () => { if (dirty && !confirm('Discard unsaved changes?')) return; back.remove(); };
  back.onclick = (e) => { if (e.target === back && (!dirty || confirm('Discard unsaved changes?'))) back.remove(); };
}

export async function openPublishBoard() {
  const back = document.createElement('div'); back.className = 'de-modal-back';
  back.innerHTML = `<div class="de-modal" style="width:min(640px,94vw)">
    <div class="de-modal-head"><h3>Push live</h3><span style="flex:1"></span>
      <button class="de-mini" id="pb-close">close</button></div>
    <div class="de-modal-body">
      <p class="de-hint" style="margin-bottom:1rem">
        Articles, authors, pages and the config you edit here are saved straight into the shared
        database and files. The public <b>emag</b> and <b>Stand</b> sites are frozen snapshots though --
        click below to rebuild them from the latest edits.
      </p>
      <label style="display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem;font-size:.86rem">
        <input type="checkbox" id="pb-vepush" checked style="width:auto"> Rebuild <b>emag/</b> (articles, authors, pages, newsletters)
      </label>
      <label style="display:flex;align-items:center;gap:.5rem;margin-bottom:1rem;font-size:.86rem">
        <input type="checkbox" id="pb-librarize" checked style="width:auto"> Rebuild <b>voiceexpressstand/</b> (publication catalogue)
      </label>
      <button class="de-mini de-good" id="pb-run">Push live now</button>
      <div id="pb-log" class="de-log" style="margin-top:1rem" hidden></div>
    </div></div>`;
  document.body.appendChild(back);
  const log = back.querySelector('#pb-log');
  back.querySelector('#pb-run').onclick = async (e) => {
    const btn = e.currentTarget;
    const targets = [];
    if (back.querySelector('#pb-vepush').checked) targets.push('ve-push');
    if (back.querySelector('#pb-librarize').checked) targets.push('librarize');
    if (!targets.length) return;
    btn.disabled = true; btn.textContent = 'Pushing… this can take a minute';
    log.hidden = false; log.textContent = 'Running…';
    try {
      const r = await api.rebuild(targets);
      log.textContent = r.log || '(no output)';
      btn.textContent = r.success ? 'Done -- push live now' : 'Finished with errors -- push live now';
    } catch (e2) {
      log.textContent = 'Failed: ' + e2.message;
      btn.textContent = 'Push live now';
    }
    btn.disabled = false;
  };
  back.querySelector('#pb-close').onclick = () => back.remove();
  back.onclick = (e) => { if (e.target === back) back.remove(); };
}
