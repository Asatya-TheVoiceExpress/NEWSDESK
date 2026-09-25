
var SS_ID = '';   

var SHEET_SECRET = 'wchVZSsOPG2NxZGAPzvPyImQL-W9Tzyt';  

function _authorized(p) { return !SHEET_SECRET || p.secret === SHEET_SECRET; }

var ACTIVITY_HEADERS   = ['time', 'kind', 'title', 'file', 'type', 'amount',
                          'currency', 'via', 'user', 'ref'];
var MESSAGE_HEADERS    = ['time', 'from', 'message', 'about', 'ip'];
var USER_HEADERS       = ['username', 'created', 'library', 'hearts'];
var LIKE_HEADERS       = ['article_id', 'count'];
var ANNOTATION_HEADERS = ['time', 'article_id', 'selected_text', 'note',
                          'username', 'target_kind', 'target_ref'];
var SUBSCRIBER_HEADERS = ['time', 'email', 'ip'];

function _ss() { return SS_ID ? SpreadsheetApp.openById(SS_ID) : SpreadsheetApp.getActiveSpreadsheet(); }

function _sheet(name, headers) {
  var ss = _ss(), sh = ss.getSheetByName(name);
  if (!sh) { sh = ss.insertSheet(name); sh.appendRow(headers); }
  return sh;
}

var ALL_SHEETS = function () {
  return [
    ['Comments',      COMMENT_HEADERS],
    ['Letters',       LETTERS_HEADERS],
    ['EbookRequests', EBOOK_REQUEST_HEADERS],
    ['Likes',         LIKE_HEADERS],
    ['Subscribers',   SUBSCRIBER_HEADERS],
    ['Messages',      MESSAGE_HEADERS],
    ['Activity',      ACTIVITY_HEADERS],
    ['Users',         USER_HEADERS],
    ['Annotations',   ANNOTATION_HEADERS]
  ];
};

function _setup(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var made = [], updated = [], kept = [];
  ALL_SHEETS().forEach(function (pair) {
    var name = pair[0], headers = pair[1];
    var existed = !!_ss().getSheetByName(name);
    var sh = _sheet(name, headers);
    if (!existed) { made.push(name); return; }
    var before = sh.getLastColumn();
    _ensureCols(sh, headers);
    (sh.getLastColumn() > before ? updated : kept).push(name);
  });
  var junk = _ss().getSheetByName('Sheet1');  
  var removed = false;
  if (junk && _ss().getSheets().length > 1 && junk.getLastRow() === 0) {
    _ss().deleteSheet(junk);
    removed = true;
  }
  return _out({ ok: true, created: made, columns_added: updated,
                unchanged: kept, removed_default_sheet: removed }, cb);
}

function setupSheets() {
  var r = _setup({ secret: SHEET_SECRET }, null);
  Logger.log(r.getContent());
  return r.getContent();
}

function _out(obj, cb) {
  var body = cb ? cb + '(' + JSON.stringify(obj) + ')' : JSON.stringify(obj);
  return ContentService.createTextOutput(body)
    .setMimeType(cb ? ContentService.MimeType.JAVASCRIPT : ContentService.MimeType.JSON);
}

function _findUser(sh, username) {
  var data = sh.getDataRange().getValues(), u = (username || '').toLowerCase();
  for (var i = 1; i < data.length; i++) {
    if (('' + data[i][0]).toLowerCase() === u) return i + 1;
  }
  return 0;
}

function doGet(e) {
  var p = e.parameter || {}, cb = p.callback, action = ('' + (p.action || '')).toLowerCase();
  try {
    if (action === 'log')     return _log(p, cb);
    if (action === 'message') return _message(p, cb);
    if (action === 'signup')  return _signup(p, cb);
    if (action === 'login')   return _login(p, cb);
    if (action === 'getlib')  return _getlib(p, cb);
    if (action === 'savelib') return _savelib(p, cb);
    if (action === 'comments_get') return _commentsGet(p, cb);
    if (action === 'comments_add') return _commentsAdd(p, cb);
    if (action === 'like_add')     return _likeAdd(p, cb);
    if (action === 'like_count')   return _likeCount(p, cb);
    if (action === 'likes_all')    return _likesAll(p, cb);
    if (action === 'letters_add')          return _lettersAdd(p, cb);
    if (action === 'letters_export')       return _lettersExport(p, cb);
    if (action === 'letters_mark_imported') return _lettersMarkImported(p, cb);
    if (action === 'subscribe')    return _subscribe(p, cb);
    if (action === 'comments_export') return _commentsExport(p, cb);
    if (action === 'likes_export')    return _likesExport(p, cb);
    if (action === 'annotation_add')  return _annotationAdd(p, cb);
    if (action === 'messages_export')     return _messagesExport(p, cb);
    if (action === 'subscribers_export')  return _subscribersExport(p, cb);
    if (action === 'activity_export')     return _activityExport(p, cb);
    if (action === 'users_export')        return _usersExport(p, cb);
    if (action === 'annotations_export')  return _annotationsExport(p, cb);
    if (action === 'ebook_request_add')        return _ebookRequestAdd(p, cb);
    if (action === 'ebook_requests_export')    return _ebookRequestsExport(p, cb);
    if (action === 'ebook_requests_mark_built') return _ebookRequestsMarkBuilt(p, cb);
    if (action === 'ebook_email')              return _ebookEmail(p, cb);
    if (action === 'comments_set_status')      return _commentsSetStatus(p, cb);
    if (action === 'letters_set_replied')      return _lettersSetReplied(p, cb);
    if (action === 'ebook_requests_set_result') return _ebookRequestsSetResult(p, cb);
    if (action === 'ebook_requests_set_failed') return _ebookRequestsSetFailed(p, cb);
    if (action === 'comments_push')            return _commentsPush(p, cb);
    if (action === 'setup')                    return _setup(p, cb);
    if (action === 'ping')                     return _out({ ok: true, pong: true }, cb);
    return _out({ ok: false, error: 'unknown action: ' + action }, cb);
  } catch (err) { return _out({ ok: false, error: String(err) }, cb); }
}

function _log(p, cb) {
  var sh = _sheet('Activity', ACTIVITY_HEADERS);
  var headerRow = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  var values = {
    time: p.t || new Date().toISOString(), kind: p.kind || 'download', title: p.title || '',
    file: p.file || '', type: p.type || '', amount: p.amount || 0, currency: p.currency || '',
    via: p.via || '', user: p.user || '', ref: p.ref || ''
  };
  var row = headerRow.map(function (h) { return values.hasOwnProperty(h) ? values[h] : ''; });
  sh.appendRow(row);
  return _out({ ok: true }, cb);
}

function _message(p, cb) {
  var body = ('' + (p.body || '')).trim();
  if (!body) return _out({ ok: false, error: 'empty' }, cb);
  var sh = _sheet('Messages', MESSAGE_HEADERS);
  sh.appendRow([new Date().toISOString(), p.from || 'anon', body, p.ref || '', p.ip || '']);
  return _out({ ok: true }, cb);
}

function _signup(p, cb) {
  var u = ('' + (p.username || '')).trim();
  if (!u) return _out({ ok: false, error: 'empty' }, cb);
  var sh = _sheet('Users', USER_HEADERS);
  if (_findUser(sh, u)) return _out({ ok: false, error: 'taken' }, cb);
  sh.appendRow([u, new Date().toISOString(), '[]', 0]);
  return _out({ ok: true, username: u, library: [] }, cb);
}

function _login(p, cb) {
  var u = ('' + (p.username || '')).trim();
  if (!u) return _out({ ok: false, error: 'empty' }, cb);
  var sh = _sheet('Users', USER_HEADERS);
  var row = _findUser(sh, u);
  if (!row) return _out({ ok: false, error: 'nouser' }, cb);
  return _out({ ok: true, username: sh.getRange(row, 1).getValue(), library: _readLib(sh, row) }, cb);
}

function _getlib(p, cb) {
  var u = ('' + (p.username || '')).trim();
  var sh = _sheet('Users', USER_HEADERS);
  var row = _findUser(sh, u);
  if (!row) return _out({ ok: false, error: 'nouser' }, cb);
  return _out({ ok: true, library: _readLib(sh, row) }, cb);
}

function _savelib(p, cb) {
  var u = ('' + (p.username || '')).trim();
  if (!u) return _out({ ok: false, error: 'empty' }, cb);
  var sh = _sheet('Users', USER_HEADERS);
  var row = _findUser(sh, u);
  if (!row) { sh.appendRow([u, new Date().toISOString(), '[]', 0]); row = _findUser(sh, u); }
  var lib = p.library || '[]';
  if (typeof lib !== 'string') lib = JSON.stringify(lib);
  sh.getRange(row, 3).setValue(lib);
  return _out({ ok: true }, cb);
}

function _readLib(sh, row) {
  try { return JSON.parse(sh.getRange(row, 3).getValue() || '[]'); } catch (_) { return []; }
}


var COMMENT_HEADERS = ['time', 'article_id', 'display_name', 'content', 'status', 'username',
                       'target_kind', 'target_ref', 'selected_text'];

function _ensureCols(sh, headers) {
  var have = sh.getLastColumn();
  if (have >= headers.length) return sh;
  for (var c = have; c < headers.length; c++) {
    sh.getRange(1, c + 1).setValue(headers[c]);
  }
  return sh;
}

function _target(p) {
  var kind = ('' + (p.target_kind || '')).trim().toLowerCase();
  var ref  = ('' + (p.target_ref || '')).trim();
  if (!ref) { ref = '' + (p.article_id || ''); kind = kind || 'article'; }
  return { kind: kind === 'publication' ? 'publication' : 'article', ref: ref };
}

function _rowTarget(row) {
  var kind = ('' + (row[6] || '')).trim().toLowerCase() || 'article';
  var ref  = ('' + (row[7] || '')).trim() || ('' + (row[1] || ''));
  return { kind: kind === 'publication' ? 'publication' : 'article', ref: ref };
}

function _commentsGet(p, cb) {
  var want = _target(p);
  if (!want.ref) return _out([], cb);
  var sh = _sheet('Comments', COMMENT_HEADERS);
  var data = sh.getDataRange().getValues(), out = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i], got = _rowTarget(row);
    if (got.kind !== want.kind || got.ref !== want.ref) continue;
    if (row[4] && row[4] !== 'approved') continue;   
    out.push({ id: i + 1, created_at: row[0], article_id: row[1], display_name: row[2],
      content: row[3], username: row[5] || '',
      target_kind: got.kind, target_ref: got.ref, selected_text: row[8] || '' });
  }
  return _out(out, cb);
}

function _commentsAdd(p, cb) {
  var name = ('' + (p.display_name || '')).trim();
  var content = ('' + (p.content || '')).trim();
  if (!name || !content) return _out({ ok: false, error: 'Name and comment required' }, cb);
  var sh = _ensureCols(_sheet('Comments', COMMENT_HEADERS), COMMENT_HEADERS);
  var t = _target(p);
  if (!t.ref) return _out({ ok: false, error: 'Nothing to comment on' }, cb);
  sh.appendRow([new Date().toISOString(), t.kind === 'article' ? t.ref : '', name, content,
    'pending', ('' + (p.username || '')).trim(), t.kind, t.ref,
    ('' + (p.selected_text || '')).trim().slice(0, 500)]);
  return _out({ ok: true, moderated: true }, cb);
}

function _commentsSetStatus(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _ensureCols(_sheet('Comments', COMMENT_HEADERS), COMMENT_HEADERS);
  var last = sh.getLastRow(), n = 0;
  ('' + (p.pairs || '')).split(',').forEach(function (chunk) {
    var bits = chunk.split(':');
    var r = parseInt(bits[0], 10), st = ('' + (bits[1] || '')).trim();
    if (!(r > 1) || r > last) return;  
    if (['approved', 'pending', 'rejected', 'deleted'].indexOf(st) < 0) return;
    sh.getRange(r, 5).setValue(st);
    n++;
  });
  return _out({ ok: true, updated: n }, cb);
}


function _likeAdd(p, cb) {
  var articleId = _target(p).ref;
  if (!articleId) return _out({ ok: false, error: 'empty' }, cb);
  var sh = _sheet('Likes', LIKE_HEADERS);
  var data = sh.getDataRange().getValues(), row = 0;
  for (var i = 1; i < data.length; i++) { if (('' + data[i][0]) === articleId) { row = i + 1; break; } }
  var count;
  if (row) { count = (Number(sh.getRange(row, 2).getValue()) || 0) + 1; sh.getRange(row, 2).setValue(count); }
  else { count = 1; sh.appendRow([articleId, count]); }
  return _out({ ok: true, count: count }, cb);
}

function _likeCount(p, cb) {
  var articleId = _target(p).ref;
  var sh = _sheet('Likes', LIKE_HEADERS);
  var data = sh.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (('' + data[i][0]) === articleId) return _out({ ok: true, count: Number(data[i][1]) || 0 }, cb);
  }
  return _out({ ok: true, count: 0 }, cb);
}

function _likesAll(p, cb) {
  var sh = _sheet('Likes', LIKE_HEADERS);
  var data = sh.getDataRange().getValues(), out = {};
  for (var i = 1; i < data.length; i++) {
    var k = '' + data[i][0];
    if (k) out[k] = Number(data[i][1]) || 0;
  }
  return _out({ ok: true, counts: out }, cb);
}


function _commentsExport(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _sheet('Comments', COMMENT_HEADERS);
  var data = sh.getDataRange().getValues(), out = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    if (row[4] === 'rejected' || row[4] === 'deleted') continue;
    var t = _rowTarget(row);
    out.push({ row: i + 1, created_at: row[0], article_id: row[1], display_name: row[2],
      content: row[3], username: row[5] || '',
      target_kind: t.kind, target_ref: t.ref, selected_text: row[8] || '' });
  }
  return _out(out, cb);
}

function _likesExport(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _sheet('Likes', LIKE_HEADERS);
  var data = sh.getDataRange().getValues(), out = [];
  for (var i = 1; i < data.length; i++) out.push({ article_id: '' + data[i][0], count: Number(data[i][1]) || 0 });
  return _out(out, cb);
}


var LETTERS_HEADERS = ['time', 'name', 'subject', 'content', 'status', 'imported', 'username', 'replied'];

function _lettersAdd(p, cb) {
  var name    = ('' + (p.name || 'Anonymous')).trim() || 'Anonymous';
  var subject = ('' + (p.subject || '')).trim();
  var content = ('' + (p.content || '')).trim();
  if (!subject || !content) return _out({ ok: false, error: 'Subject and message required' }, cb);
  var sh = _ensureCols(_sheet('Letters', LETTERS_HEADERS), LETTERS_HEADERS);
  sh.appendRow([new Date().toISOString(), name, subject, content, 'approved', '',
    ('' + (p.username || '')).trim(), '']);
  return _out({ ok: true }, cb);
}

function _lettersSetReplied(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _ensureCols(_sheet('Letters', LETTERS_HEADERS), LETTERS_HEADERS);
  var last = sh.getLastRow();
  var col = LETTERS_HEADERS.indexOf('replied') + 1;
  var rows = ('' + (p.rows || '')).split(',').map(function (s) { return parseInt(s, 10); })
    .filter(function (n) { return n > 1 && n <= last; });
  if (!rows.length) return _out({ ok: false, error: 'no rows' }, cb);
  var stamp = new Date().toISOString();
  rows.forEach(function (r) { sh.getRange(r, col).setValue(stamp); });
  return _out({ ok: true, marked: rows.length }, cb);
}

function _lettersExport(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _sheet('Letters', LETTERS_HEADERS);
  var data = sh.getDataRange().getValues(), out = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    if (row[4] !== 'approved') continue;
    if (row[5]) continue;   
    out.push({ row: i + 1, time: row[0], name: row[1], subject: row[2], content: row[3],
      username: row[6] || '' });
  }
  return _out(out, cb);
}

function _lettersMarkImported(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var rows = ('' + (p.rows || '')).split(',').map(function(s) { return parseInt(s, 10); }).filter(function(n) { return n > 1; });
  if (!rows.length) return _out({ ok: false, error: 'no rows' }, cb);
  var sh = _sheet('Letters', LETTERS_HEADERS);
  rows.forEach(function(r) { sh.getRange(r, 6).setValue(new Date().toISOString()); });
  return _out({ ok: true, marked: rows.length }, cb);
}


function _annotationAdd(p, cb) {
  var text = ('' + (p.selected_text || '')).trim();
  var note = ('' + (p.note || '')).trim();
  var t = _target(p);
  if (!t.ref || !note) return _out({ ok: false, error: 'missing fields' }, cb);
  var sh = _ensureCols(_sheet('Annotations', ANNOTATION_HEADERS), ANNOTATION_HEADERS);
  sh.appendRow([new Date().toISOString(), t.kind === 'article' ? t.ref : '',
    text.slice(0, 500), note, ('' + (p.username || '')).trim(), t.kind, t.ref]);
  return _out({ ok: true }, cb);
}

function _rowTarget2(row) {
  var kind = ('' + (row[5] || '')).trim().toLowerCase() || 'article';
  var ref  = ('' + (row[6] || '')).trim() || ('' + (row[1] || ''));
  return { kind: kind === 'publication' ? 'publication' : 'article', ref: ref };
}

function _subscribe(p, cb) {
  var email = ('' + (p.email || '')).trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return _out({ ok: false, error: 'Enter a valid email' }, cb);
  var sh = _sheet('Subscribers', SUBSCRIBER_HEADERS);
  var data = sh.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (('' + data[i][1]).toLowerCase() === email) return _out({ ok: true, already: true }, cb);
  }
  sh.appendRow([new Date().toISOString(), email, p.ip || '']);
  return _out({ ok: true }, cb);
}


function _subscribersExport(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _sheet('Subscribers', SUBSCRIBER_HEADERS);
  var data = sh.getDataRange().getValues(), out = [];
  for (var i = 1; i < data.length; i++) {
    out.push({ time: data[i][0], email: data[i][1], ip: data[i][2] });
  }
  return _out(out, cb);
}

function _messagesExport(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _sheet('Messages', MESSAGE_HEADERS);
  var data = sh.getDataRange().getValues(), out = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    out.push({ time: row[0], from: row[1], message: row[2], about: row[3], ip: row[4] });
  }
  return _out(out, cb);
}

function _activityExport(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _sheet('Activity', ACTIVITY_HEADERS);
  var data = sh.getDataRange().getValues(), out = [];
  var headerRow = data[0], idx = {};
  for (var h = 0; h < headerRow.length; h++) idx[headerRow[h]] = h;
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    out.push({
      time: row[idx.time], kind: row[idx.kind], title: row[idx.title], file: row[idx.file],
      type: row[idx.type], amount: row[idx.amount], currency: row[idx.currency], via: row[idx.via],
      user: row[idx.user], ref: row[idx.ref]
    });
  }
  return _out(out, cb);
}

function _usersExport(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _sheet('Users', USER_HEADERS);
  var data = sh.getDataRange().getValues(), out = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    out.push({ username: row[0], created: row[1], library: row[2], hearts: row[3] });
  }
  return _out(out, cb);
}

function _annotationsExport(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _sheet('Annotations', ANNOTATION_HEADERS);
  var data = sh.getDataRange().getValues(), out = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    var t = _rowTarget2(row);
    out.push({ time: row[0], article_id: row[1], selected_text: row[2], note: row[3],
      username: row[4] || '', target_kind: t.kind, target_ref: t.ref });
  }
  return _out(out, cb);
}


var EBOOK_REQUEST_HEADERS = ['time', 'name', 'email', 'title', 'creator', 'description',
  'article_ids', 'built', 'username', 'publication_id', 'download_url', 'error'];

function _ebookRequestAdd(p, cb) {
  var title = ('' + (p.title || '')).trim();
  var articleIds = ('' + (p.article_ids || '')).trim();
  if (!title || !articleIds) return _out({ ok: false, error: 'Title and at least one article required' }, cb);
  var sh = _ensureCols(_sheet('EbookRequests', EBOOK_REQUEST_HEADERS), EBOOK_REQUEST_HEADERS);
  sh.appendRow([
    new Date().toISOString(),
    ('' + (p.name || 'Anonymous')).trim() || 'Anonymous',
    ('' + (p.email || '')).trim(),
    title.slice(0, 200),
    ('' + (p.creator || '')).trim().slice(0, 200),
    ('' + (p.description || '')).trim().slice(0, 1000),
    articleIds,
    '',
    ('' + (p.username || '')).trim(),
    '',
    '',
    ''
  ]);
  var _r = sh.getLastRow(), _c = EBOOK_REQUEST_HEADERS.indexOf('article_ids') + 1;
  if (_c > 0) sh.getRange(_r, _c).setNumberFormat('@').setValue(articleIds);
  return _out({ ok: true }, cb);
}

function _ebookRequestsExport(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _sheet('EbookRequests', EBOOK_REQUEST_HEADERS);
  var data = sh.getDataRange().getValues(), out = [];
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    if (row[7]) continue;   
    out.push({ row: i + 1, time: row[0], name: row[1], email: row[2], title: row[3],
      creator: row[4], description: row[5], article_ids: row[6], username: row[8] || '' });
  }
  return _out(out, cb);
}

function _ebookRequestsMarkBuilt(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var rows = ('' + (p.rows || '')).split(',').map(function(s) { return parseInt(s, 10); }).filter(function(n) { return n > 1; });
  if (!rows.length) return _out({ ok: false, error: 'no rows' }, cb);
  var sh = _sheet('EbookRequests', EBOOK_REQUEST_HEADERS);
  rows.forEach(function(r) { sh.getRange(r, 8).setValue(new Date().toISOString()); });
  return _out({ ok: true, marked: rows.length }, cb);
}

function _ebookRequestsSetFailed(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _ensureCols(_sheet('EbookRequests', EBOOK_REQUEST_HEADERS), EBOOK_REQUEST_HEADERS);
  var last = sh.getLastRow(), stamp = new Date().toISOString(), n = 0;
  var cBuilt = EBOOK_REQUEST_HEADERS.indexOf('built') + 1;
  var cErr   = EBOOK_REQUEST_HEADERS.indexOf('error') + 1;
  var msg = ('' + (p.message || 'could not be built')).slice(0, 500);
  ('' + (p.rows || '')).split(',').forEach(function (s) {
    var r = parseInt(s, 10);
    if (!(r > 1) || r > last) return;
    sh.getRange(r, cBuilt).setValue('failed ' + stamp);
    sh.getRange(r, cErr).setNumberFormat('@').setValue(msg);
    n++;
  });
  return _out({ ok: true, failed: n }, cb);
}

function _ebookEmail(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var to    = ('' + (p.to || '')).trim();
  var url   = ('' + (p.url || '')).trim();
  var title = ('' + (p.title || 'Your Voice Express ebook')).trim().slice(0, 200);
  var name  = ('' + (p.name || 'reader')).trim().slice(0, 100) || 'reader';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) return _out({ ok: false, error: 'bad address' }, cb);
  if (!/^https:\/\/[a-z0-9.-]*thevoiceexpress\.in\//i.test(url)) {
    return _out({ ok: false, error: 'link is not a Voice Express URL' }, cb);
  }
  var esc = function (s) {
    return ('' + s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  };
  var body =
    'Hello ' + name + ',\n\n' +
    'The ebook you asked us to put together — "' + title + '" — is ready, ' +
    'and it is on the Newsstand now:\n\n' + url + '\n\n' +
    'It is an ePub: open it in Apple Books, Calibre, KOReader, or any e-reader.\n\n' +
    'Thank you for reading.\n\nThe Voice Express\n' +
    'https://emag.thevoiceexpress.in\n';
  var html =
    '<p>Hello ' + esc(name) + ',</p>' +
    '<p>The ebook you asked us to put together — <b>' + esc(title) + '</b> — is ready, ' +
    'and it is on the Newsstand now.</p>' +
    '<p><a href="' + esc(url) + '">Download your ebook</a></p>' +
    '<p>It is an ePub: open it in Apple Books, Calibre, KOReader, or any e-reader.</p>' +
    '<p>Thank you for reading.<br><b>The Voice Express</b><br>' +
    '<a href="https://emag.thevoiceexpress.in">emag.thevoiceexpress.in</a></p>';
  try {
    MailApp.sendEmail({
      to: to,
      subject: 'Your ebook is ready — ' + title,
      body: body,
      htmlBody: html,
      name: 'The Voice Express'
    });
  } catch (err) {
    return _out({ ok: false, error: String(err) }, cb);
  }
  return _out({ ok: true, sent: 1 }, cb);
}

function _commentsPush(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var name = ('' + (p.display_name || '')).trim();
  var content = ('' + (p.content || '')).trim();
  if (!name || !content) return _out({ ok: false, error: 'Name and comment required' }, cb);
  var status = ('' + (p.status || 'approved')).trim();
  if (['approved', 'pending', 'rejected', 'deleted'].indexOf(status) < 0) status = 'approved';
  var sh = _ensureCols(_sheet('Comments', COMMENT_HEADERS), COMMENT_HEADERS);
  var t = _target(p);
  sh.appendRow([
    ('' + (p.created_at || '')).trim() || new Date().toISOString(),
    t.kind === 'article' ? t.ref : '', name, content, status,
    ('' + (p.username || '')).trim(), t.kind, t.ref,
    ('' + (p.selected_text || '')).trim().slice(0, 500)
  ]);
  return _out({ ok: true, row: sh.getLastRow() }, cb);
}

function _ebookRequestsSetResult(p, cb) {
  if (!_authorized(p)) return _out({ ok: false, error: 'unauthorized' }, cb);
  var sh = _ensureCols(_sheet('EbookRequests', EBOOK_REQUEST_HEADERS), EBOOK_REQUEST_HEADERS);
  var last = sh.getLastRow(), stamp = new Date().toISOString(), n = 0;
  var cBuilt = EBOOK_REQUEST_HEADERS.indexOf('built') + 1;
  var cPub   = EBOOK_REQUEST_HEADERS.indexOf('publication_id') + 1;
  var cUrl   = EBOOK_REQUEST_HEADERS.indexOf('download_url') + 1;
  ('' + (p.results || '')).split('|').forEach(function (rec) {
    if (!rec) return;
    var first = rec.indexOf(':'); if (first < 0) return;
    var second = rec.indexOf(':', first + 1);
    var r = parseInt(rec.slice(0, first), 10);
    var pub = second < 0 ? rec.slice(first + 1) : rec.slice(first + 1, second);
    var url = second < 0 ? '' : rec.slice(second + 1);
    if (!(r > 1) || r > last) return;
    sh.getRange(r, cBuilt).setValue(stamp);
    sh.getRange(r, cPub).setValue(pub);
    sh.getRange(r, cUrl).setNumberFormat('@').setValue(url);
    n++;
  });
  return _out({ ok: true, updated: n }, cb);
}
