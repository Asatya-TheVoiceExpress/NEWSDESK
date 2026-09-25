async function j(method, url, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(url, opt);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `${method} ${url} -> ${r.status}`);
  return r.status === 204 ? null : r.json();
}

export const api = {
  lookups: () => j('GET', '/api/lookups'),
  drafts: () => j('GET', '/api/drafts'),
  article: (id) => j('GET', `/api/articles/${id}`),
  create: (data) => j('POST', '/api/articles', data),
  update: (id, data) => j('PUT', `/api/articles/${id}`, data),
  preview: (id) => j('POST', `/api/articles/${id}/preview`),
  versions: (id) => j('GET', `/api/articles/${id}/versions`),
  restore: (id, vid) => j('POST', `/api/articles/${id}/versions/${vid}/restore`),

  translations: (id) => j('GET', `/api/articles/${id}/translations`),
  translationSave: (id, data) => j('POST', `/api/articles/${id}/translations`, data),
  translationDelete: (id, lang) => j('DELETE', `/api/articles/${id}/translation/${lang}`),
  translationAuto: (id, lang) => j('POST', `/api/articles/${id}/translate`, { target_language: lang }),

  mediaList: (article) => j('GET', '/api/media' + (article ? `?article=${article}` : '')),
  injectPath: (path, article) => j('POST', '/api/media/inject', { path, article_id: article }),
  async injectFile(file, article) {
    const fd = new FormData();
    fd.append('file', file);
    if (article) fd.append('article_id', article);
    const r = await fetch('/api/media/inject', { method: 'POST', body: fd });
    if (!r.ok) throw new Error('upload failed');
    return r.json();
  },

  async ingest(file, article) {
    const fd = new FormData();
    fd.append('file', file);
    if (article) fd.append('article_id', article);
    const r = await fetch('/api/ingest', { method: 'POST', body: fd });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || 'import failed');
    return data;
  },

  scanFolder: (path) => j('GET', `/api/palette/scan?path=${encodeURIComponent(path)}`),
  paletteGet: (id) => j('GET', `/api/articles/${id}/palette`),
  palettePost: (id, data) => j('POST', `/api/articles/${id}/palette`, data),

  sourcesGet: (id) => j('GET', `/api/articles/${id}/sources`),
  sourceAdd: (id, data) => j('POST', `/api/articles/${id}/sources`, data),
  sourceSave: (sid, data) => j('PUT', `/api/sources/${sid}`, data),
  sourceDel: (sid) => j('DELETE', `/api/sources/${sid}`),

  library: () => j('GET', '/api/library'),
  deleteArticle: (id) => j('DELETE', `/api/articles/${id}`),
  batch: (data) => j('POST', '/api/articles/batch', data),

  createTag: (name) => j('POST', '/api/tags', { name }),
  authorsFull: () => j('GET', '/api/authors'),
  authorCreate: (data) => j('POST', '/api/authors', data),
  authorUpdate: (id, data) => j('PUT', `/api/authors/${id}`, data),

  categories: () => j('GET', '/api/categories'),
  categoryCreate: (data) => j('POST', '/api/categories', data),
  categoryUpdate: (id, data) => j('PUT', `/api/categories/${id}`, data),
  categoryDelete: (id) => j('DELETE', `/api/categories/${id}`),
  categoryMerge: (id, into) => j('POST', `/api/categories/${id}/merge`, { into }),

  sections: () => j('GET', '/api/sections'),
  sectionUpdate: (id, data) => j('PUT', `/api/sections/${id}`, data),

  tagsFull: () => j('GET', '/api/tags'),
  tagUpdate: (id, data) => j('PUT', `/api/tags/${id}`, data),
  tagDelete: (id) => j('DELETE', `/api/tags/${id}`),
  tagMerge: (id, into) => j('POST', `/api/tags/${id}/merge`, { into }),

  seriesList: () => j('GET', '/api/series'),
  seriesCreate: (data) => j('POST', '/api/series', data),
  seriesUpdate: (id, data) => j('PUT', `/api/series/${id}`, data),
  seriesDelete: (id) => j('DELETE', `/api/series/${id}`),

  pagesList: () => j('GET', '/api/pages'),
  pageGet: (slug) => j('GET', `/api/pages/${slug}`),
  pageSave: (slug, data) => j('PUT', `/api/pages/${slug}`, data),

  configGet: () => j('GET', '/api/config'),
  configSave: (data) => j('PUT', '/api/config', data),

  rebuild: (targets) => j('POST', '/api/rebuild', { targets }),

  columns: () => j('GET', '/api/columns'),
  columnGet: (slugOrId) => j('GET', `/api/columns/${slugOrId}`),
  columnCreate: (data) => j('POST', '/api/columns', data),
  columnUpdate: (id, data) => j('PUT', `/api/columns/${id}`, data),
  columnDelete: (id) => j('DELETE', `/api/columns/${id}`),

  publications: () => j('GET', '/api/publications'),
  publicationGet: (id) => j('GET', `/api/publications/${id}`),
  publicationUpdate: (id, data) => j('PUT', `/api/publications/${id}`, data),
  publicationDelete: (id) => j('DELETE', `/api/publications/${id}`),
  publicationIcon: (id) => j('POST', `/api/publications/${id}/icon`),
  async publicationUpload(file, fields) {
    const fd = new FormData();
    fd.append('file', file);
    Object.entries(fields || {}).forEach(([k, v]) => { if (v != null && k !== 'cover') fd.append(k, v); });
    if (fields && fields.cover instanceof File) fd.append('cover', fields.cover);
    const r = await fetch('/api/publications/upload', { method: 'POST', body: fd });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || 'upload failed');
    return data;
  },
  async publicationReplace(id, file) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(`/api/publications/${id}/replace`, { method: 'POST', body: fd });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || 'replace failed');
    return data;
  },

  pdfEnhancementGet: (type, key) => j('GET', `/api/pdf-enhancements/${type}/${encodeURIComponent(key)}`),
  pdfEnhancementSave: (type, key, data) => j('PUT', `/api/pdf-enhancements/${type}/${encodeURIComponent(key)}`, data),
  broadsheetMonths: () => j('GET', '/api/broadsheet-months'),
};
