function FormField({label,children}){
  return <div className="form-g"><label className="form-lbl">{label}</label>{children}</div>;
}

(function(){

var STORE = {ready:null, articles:[], categories:[], sections:[], tags:[],
  authors:[], series:[], newsletters:{months:[],issues:[]}, columns:[],
  pages:{}, publications:[], crosswords:{}, config:{api:''}, letters:[], readerState:{}};

function fetchJSON(path){
  var build=(typeof window!=='undefined'&&window.VE&&window.VE.build)||'';
  var url=build?path+(path.indexOf('?')<0?'?':'&')+'v='+encodeURIComponent(build):path;
  return fetch(url).then(function(r){ if(!r.ok) throw new Error(r.status); return r.json(); })
    .catch(function(){ return null; });
}

STORE.ready = Promise.all([
  fetchJSON('./data/articles.json').then(function(d){ STORE.articles = d||[]; }),
  fetchJSON('./data/categories.json').then(function(d){ STORE.categories = d||[]; }),
  fetchJSON('./data/sections.json').then(function(d){ STORE.sections = d||[]; }),
  fetchJSON('./data/tags.json').then(function(d){ STORE.tags = d||[]; }),
  fetchJSON('./data/authors.json').then(function(d){ STORE.authors = d||[]; }),
  fetchJSON('./data/series.json').then(function(d){ STORE.series = d||[]; }),
  fetchJSON('./data/newsletters.json').then(function(d){ STORE.newsletters = d||{months:[],issues:[]}; }),
  fetchJSON('./data/columns.json').then(function(d){ STORE.columns = d||[]; }),
  fetchJSON('./data/pages.json').then(function(d){ STORE.pages = d||{}; }),
  fetchJSON('./data/publications.json').then(function(d){ STORE.publications = d||[]; }),
  fetchJSON('./data/link-previews.json').then(function(d){ STORE.linkPreviews = d||{}; }),
  fetchJSON('./data/puzzles/crossword-words.json').then(function(d){ STORE.crosswords = d||{}; }),
  fetchJSON('./data/config.json').then(function(d){ STORE.config = d||{api:''}; }),
  fetchJSON('./data/letters.json').then(function(d){ STORE.letters = d||[]; }),  
  fetchJSON('./data/reader_state.json').then(function(d){ STORE.readerState = d||{}; }),  
]);

function jsonp(params){
  return new Promise(function(res,rej){
    var api = STORE.config.api;
    if(!api){ rej('noapi'); return; }
    var cb = 've_cb_'+Math.random().toString(36).slice(2);
    var s = document.createElement('script');
    var to = setTimeout(function(){ cleanup(); rej('timeout'); }, 12000);
    function cleanup(){ clearTimeout(to); try{ delete window[cb]; }catch(e){} s.remove(); }
    window[cb] = function(d){ cleanup(); res(d); };
    params.callback = cb;
    s.src = api + (api.indexOf('?')>-1?'&':'?') + new URLSearchParams(params).toString();
    s.onerror = function(){ cleanup(); rej('neterr'); };
    document.head.appendChild(s);
  });
}

var VE_USER_KEY = 've_user';
function veUser(){ try{ return localStorage.getItem(VE_USER_KEY)||''; }catch(e){ return ''; } }
function veSetUser(u){
  try{ u ? localStorage.setItem(VE_USER_KEY,u) : localStorage.removeItem(VE_USER_KEY); }catch(e){}
  window.dispatchEvent(new CustomEvent('ve-user-changed',{detail:u||''}));
}
function veAccount(mode, username){
  return jsonp({action: mode==='up'?'signup':'login', username:username});
}
function veReaderState(username){
  var u = (username||veUser()||'').trim().toLowerCase();
  var s = u && STORE.readerState ? STORE.readerState[u] : null;
  return s || {comments:[], letters:[], ebooks:[]};
}
window.veUser = veUser; window.veSetUser = veSetUser;
window.veAccount = veAccount; window.veReaderState = veReaderState;

var LS_KEY = 've-puzzle-sessions';
function lsSessions(){ try{ return JSON.parse(localStorage.getItem(LS_KEY)||'{}'); }catch(e){ return {}; } }
function lsSaveSessions(s){ try{ localStorage.setItem(LS_KEY, JSON.stringify(s)); }catch(e){} }
function sessionKey(type,date,difficulty){ return type+'|'+date+'|'+(difficulty||''); }

function dayOfYear(ds){ var d=new Date(ds+'T12:00:00'); return Math.floor((d-new Date(d.getFullYear(),0,0))/864e5); }

function qs(url){ var i=url.indexOf('?'); var p={}; if(i<0) return p;
  new URLSearchParams(url.slice(i+1)).forEach(function(v,k){ p[k]=v; }); return p; }
function path(url){ var i=url.indexOf('?'); return i<0?url:url.slice(0,i); }

function articleMatches(a,p,idx){
  if(p.status && p.status!=='all' && a.status!==p.status) return false;
  if(p.category && a.category_slug!==p.category && a.category_name!==p.category) return false;
  if(p.section && a.section_slug!==p.section && a.section_name!==p.section) return false;
  if(p.author_id && String(a.author_id)!==String(p.author_id)) return false;
  if(p.language && a.language!==p.language) return false;
  if(p.geotagged==='true' && !(a.latitude && a.latitude!==0)) return false;
  if(p.featured==='true' && !a.is_featured) return false;
  if(p.tag){
    var tags=a.tags||[];
    if(!tags.some(function(t){ return t.slug===p.tag || t.name===p.tag; })) return false;
  }
  if(p.title_search){
    var q=p.title_search.toLowerCase();
    if((a.title||'').toLowerCase().indexOf(q)<0) return false;
  } else if(p.search){
    var q2=p.search.toLowerCase();
    var body = (idx && idx[String(a.id)]) || '';
    var hay=[a.title,a.excerpt,a.author_name,body].join(' ').toLowerCase();
    if(hay.indexOf(q2)<0) return false;
  }
  return true;
}

function listArticles(p){
  var offset = parseInt(p.offset||'0',10)||0;
  var limit  = Math.min(parseInt(p.limit||'50',10)||50, 200);
  var page = function(idx){
    var out = STORE.articles.filter(function(a){ return articleMatches(a,p,idx); });
    return out.slice(offset, offset+limit);
  };
  if(p.search && !p.title_search) return ensureSearchIndex().then(page);  
  return page(null);
}

var _detail = {};   

function findArticleLite(id){
  return STORE.articles.find(function(a){ return String(a.id)===String(id); }) || null;
}

var _logged = {};
function logRead(id){
  if(_logged[id]) return; _logged[id] = 1;
  try{
    var a = findArticleLite(id) || {};
    jsonp({action:'log', kind:'read', t:new Date().toISOString(),
      title:(a.title||''), file:'', type:'article', amount:0,
      currency:(STORE.config&&STORE.config.currency)||'', via:'emag',
      user:veUser(), ip:'', ref:location.href}).catch(function(){});
  }catch(e){}
}

function getArticle(id){
  var lite = findArticleLite(id);
  if(lite && typeof lite.content === 'string') return Promise.resolve(lite);  
  if(!_detail[id]){
    _detail[id] = fetchJSON('./data/articles/' + encodeURIComponent(id) + '.json')
      .then(function(full){
        if(!full) return lite;
        var i = STORE.articles.findIndex(function(a){ return String(a.id)===String(id); });
        if(i >= 0) STORE.articles[i] = Object.assign({}, STORE.articles[i], full);
        else STORE.articles.push(full);
        return STORE.articles[i >= 0 ? i : STORE.articles.length - 1];
      });
  }
  return _detail[id];
}

var _searchIdx = null;
function ensureSearchIndex(){
  if(_searchIdx) return _searchIdx;
  _searchIdx = fetchJSON('./data/search-index.json').then(function(d){ return d || {}; });
  return _searchIdx;
}

function routeGet(url){
  return STORE.ready.then(function(){
    var p2 = path(url), params = qs(url), m;

    if(p2==='/api/articles') return listArticles(params);

    if((m=p2.match(/^\/api\/articles\/(\d+)$/))){ logRead(m[1]); return getArticle(m[1]); }

    if((m=p2.match(/^\/api\/articles\/(\d+)\/comments$/))){
      return jsonp({action:'comments_get', article_id:m[1]}).catch(function(){ return []; });
    }
    if((m=p2.match(/^\/api\/articles\/(\d+)\/likes$/))){
      return jsonp({action:'like_count', article_id:m[1]}).catch(function(){ return {count:0}; });
    }
    if((m=p2.match(/^\/api\/articles\/(\d+)\/translations$/))){
      return getArticle(m[1]).then(function(a){ return (a&&a.translations)||[]; });
    }
    if((m=p2.match(/^\/api\/articles\/(\d+)\/translation\/([a-z-]+)$/))){
      return getArticle(m[1]).then(function(a2){
        var t=((a2&&a2.translations)||[]).find(function(x){return x.language===m[2];});
        return t||{error:'not found'};
      });
    }
    if((m=p2.match(/^\/api\/articles\/(\d+)\/corrections$/))){
      return getArticle(m[1]).then(function(a3){ return (a3&&a3.corrections)||[]; });
    }

    if(p2==='/api/categories') return STORE.categories;
    if(p2==='/api/sections')   return STORE.sections;
    if(p2==='/api/tags')       return STORE.tags;
    if(p2==='/api/authors')    return STORE.authors;
    if((m=p2.match(/^\/api\/authors\/(\d+)\/links$/))){
      var au=STORE.authors.find(function(x){return String(x.id)===m[1];}); return (au&&au.links)||[];
    }
    if((m=p2.match(/^\/api\/authors\/(\d+)\/contributions$/))){
      var au2=STORE.authors.find(function(x){return String(x.id)===m[1];}); return (au2&&au2.contributions)||[];
    }
    if(p2==='/api/series') return STORE.series;
    if((m=p2.match(/^\/api\/series\/(\d+)$/))){
      return STORE.series.find(function(s){return String(s.id)===m[1];})||{error:'not found'};
    }

    if(p2==='/api/newsletters/months') return STORE.newsletters.months;
    if(p2==='/api/newsletters/current'){
      var now=new Date();
      return STORE.newsletters.issues.find(function(i){return i.year===now.getFullYear()&&i.month===now.getMonth()+1;})
        || STORE.newsletters.issues[0] || null;
    }
    if(p2==='/api/newsletters/range'){
      var yms = STORE.newsletters.months.map(function(x){return x.year+'-'+String(x.month).padStart(2,'0');});
      return {min: yms.length?yms[yms.length-1]:'', max: yms.length?yms[0]:''};
    }
    if((m=p2.match(/^\/api\/newsletters\/(\d+)\/(\d+)$/))){
      var y=+m[1], mo=+m[2];
      return STORE.newsletters.issues.find(function(i){return i.year===y&&i.month===mo;}) || {error:'not found'};
    }

    if(p2==='/api/columns') return STORE.columns;
    if((m=p2.match(/^\/api\/columns\/([^/]+)$/))){
      return STORE.columns.find(function(c){return c.slug===m[1]||String(c.id)===m[1];}) || {error:'not found'};
    }
    if((m=p2.match(/^\/api\/column-entries\/(\d+)$/))){
      for(var i=0;i<STORE.columns.length;i++){
        var e=(STORE.columns[i].entries||[]).find(function(x){return String(x.id)===m[1];});
        if(e) return e;
      }
      return {error:'not found'};
    }

    if((m=p2.match(/^\/api\/pages\/([^/]+)$/))) return STORE.pages[m[1]] || {error:'not found'};
    if(p2==='/api/pages') return Object.values(STORE.pages);

    if(p2==='/api/publications') return {publications: STORE.publications};
    if((m=p2.match(/^\/api\/publications\/(\d+)$/))){
      return STORE.publications.find(function(x){return String(x.id)===m[1];}) || {error:'not found'};
    }

    if(p2==='/api/puzzles/wordcache'){
      var doy = params.date ? dayOfYear(params.date) : 0;
      var topics = Object.keys(STORE.crosswords);
      var key = topics.length ? String(doy % topics.length) : null;
      return key!==null ? STORE.crosswords[key] : null;
    }
    if(p2==='/api/puzzles/session'){
      var sess = lsSessions();
      var s = sess[sessionKey(params.type,params.date,params.difficulty)];
      return s || null;
    }
    if(p2==='/api/puzzles/archive'){
      var sess2 = lsSessions(), out=[];
      Object.keys(sess2).forEach(function(k){
        var parts=k.split('|');
        if(parts[0]===params.type && (params.difficulty||'')===parts[2]){
          out.push({puzzle_date:parts[1], difficulty:parts[2], elapsed:sess2[k].elapsed||0, completed:!!sess2[k].completed});
        }
      });
      out.sort(function(a,b){ return a.puzzle_date<b.puzzle_date?1:-1; });
      return out.slice(0,60);
    }

    if(p2==='/api/link-preview'){
      return STORE.linkPreviews[params.url] || {url:params.url, site:'', title:'', description:'', image:''};
    }

    if(p2==='/api/letters') return STORE.letters;  

    if(p2==='/api/auth/me') return null;   

    return {error:'not available in the static build'};
  });
}

var LANG_MM_CODE = {en:'en',hi:'hi',fr:'fr',es:'es',ar:'ar',zh:'zh-CN',de:'de'};
function mmChunks(text){
  var LIMIT=450;
  if(encodeURIComponent(text).length<LIMIT) return [text];
  var parts=text.match(/[^.!?\n]+[.!?\n]*\s*/g)||[text];
  var chunks=[], cur='';
  parts.forEach(function(p){
    if(encodeURIComponent(cur+p).length>LIMIT){ if(cur)chunks.push(cur); cur=p; }
    else cur+=p;
  });
  if(cur) chunks.push(cur);
  return chunks;
}
function mmCall(text, source, target){
  if(!text||!text.trim()) return Promise.resolve(text);
  var url='https://api.mymemory.translated.net/get?q='+encodeURIComponent(text)+'&langpair='+source+'|'+target;
  return fetch(url).then(function(r){return r.json();}).then(function(d){
    if(d && d.responseData && d.responseData.translatedText) return d.responseData.translatedText;
    throw new Error((d&&d.responseDetails)||'translate failed');
  });
}
function mmTranslateText(text, source, target){
  if(!text||!text.trim()) return Promise.resolve(text);
  var chunks=mmChunks(text);
  return Promise.all(chunks.map(function(c){return mmCall(c,source,target);})).then(function(res){return res.join('');});
}
function mmTranslateHTML(html, source, target){
  if(!html) return Promise.resolve(html);
  var wrap=document.createElement('div'); wrap.innerHTML=html;
  var walker=document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT);
  var nodes=[], n;
  while((n=walker.nextNode())) if(n.nodeValue && n.nodeValue.trim()) nodes.push(n);
  return nodes.reduce(function(p,node){
    return p.then(function(){
      return mmTranslateText(node.nodeValue, source, target).then(function(t){ node.nodeValue=t; });
    });
  }, Promise.resolve()).then(function(){ return wrap.innerHTML; });
}

function routePost(url, data){
  var p2 = path(url), m;
  if((m=p2.match(/^\/api\/articles\/(\d+)\/comments$/))){
    return jsonp({action:'comments_add', article_id:m[1], username:veUser(),
      display_name:(data&&data.display_name)||'', content:(data&&data.content)||''}).catch(function(){
        return {error:'Could not reach the comment service. Try again.'};
      });
  }
  if((m=p2.match(/^\/api\/articles\/(\d+)\/like$/))){
    return jsonp({action:'like_add', article_id:m[1]}).catch(function(){
      return {error:'Could not reach the like service. Try again.'};
    });
  }
  if(p2==='/api/letters'){
    return jsonp({action:'letters_add', username:veUser(),
      name:(data&&(data.guest_name||data.name))||'', subject:(data&&data.subject)||'', content:(data&&data.content)||''}).then(function(r){
        if(r&&r.error) return r;
        return {success:true};
      }).catch(function(){
        return {error:'Could not reach the letters service. Try again.'};
      });
  }
  if(p2==='/api/subscribe'){
    return jsonp({action:'subscribe', email:(data&&data.email)||''}).catch(function(){
      return {error:'Could not reach the subscribe service. Try again.'};
    });
  }
  if(p2==='/api/ebook-requests'){
    return jsonp({action:'ebook_request_add', username:veUser(),
      name:(data&&data.name)||'', email:(data&&data.email)||'',
      title:(data&&data.title)||'', creator:(data&&data.creator)||'',
      description:(data&&data.description)||'', article_ids:(data&&data.article_ids)||''}).then(function(r){
        if(r&&r.error) return r;
        return {success:true};
      }).catch(function(){
        return {error:'Could not reach the ebook request service. Try again.'};
      });
  }
  if(p2==='/api/annotations'){
    return jsonp({action:'annotation_add', article_id:(data&&data.article_id)||'',
      selected_text:(data&&data.selected_text)||'', note:(data&&data.note)||''}).catch(function(){ return {ok:false}; });
  }
  if(p2==='/api/puzzles/session'){
    var sess = lsSessions();
    sess[sessionKey(data.type,data.date,data.difficulty)] = {state:data.state, elapsed:data.elapsed, completed:data.completed};
    lsSaveSessions(sess);
    return Promise.resolve({ok:true});
  }
  if(p2==='/api/reader/puzzle-complete'){
    var sess2 = lsSessions();
    var k = sessionKey(data.type,data.date,data.difficulty);
    sess2[k] = Object.assign({}, sess2[k], {completed:true, elapsed:data.elapsed});
    lsSaveSessions(sess2);
    return Promise.resolve({ok:true});
  }
  if(p2==='/api/puzzles/wordcache'){
    return Promise.resolve({ok:true});   
  }
  if(p2==='/api/translate'){
    return getArticle(data.article_id).then(function(art){  
      if(!art) return {error:'Article not found'};
      var native = art.language||'en';
      var target = data.target_language;
      if(!target||target===native) return {error:'Invalid target language'};
      var existing = ((art.translations)||[]).find(function(x){return x.language===target;});
      if(existing) return existing;
      var srcMM = LANG_MM_CODE[native]||native, tgtMM = LANG_MM_CODE[target]||target;
      return Promise.all([
        mmTranslateText(art.title||'', srcMM, tgtMM),
        mmTranslateText(art.excerpt||'', srcMM, tgtMM),
        mmTranslateHTML(art.content||'', srcMM, tgtMM)
      ]).then(function(r){
        return {title:r[0], excerpt:r[1], content:r[2], language:target};
      }).catch(function(){
        return {error:'Translation service unavailable. Please try again.'};
      });
    });
  }
  return Promise.resolve({error:'not available in the static build'});
}

API.get  = function(u){ return routeGet(u); };
API.post = function(u,d){ return routePost(u,d); };
API.put  = function(u,d){ return Promise.resolve({error:'not available in the static build'}); };
API.del  = function(u){ return Promise.resolve({error:'not available in the static build'}); };
API.upload = function(u,fd){ return Promise.resolve({error:'not available in the static build'}); };

(function readerDesk(){
  function el(tag, cls, txt){
    var n = document.createElement(tag);
    if(cls) n.className = cls;
    if(txt != null) n.textContent = txt;   
    return n;
  }
  function fmt(d){
    if(!d) return '';
    var t = new Date(d);
    return isNaN(t) ? '' : t.toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'});
  }
  function htmlToText(html){
    var s = String(html||'');
    if(!s) return '';
    try{
      var doc = new DOMParser().parseFromString(s,'text/html');
      s = (doc.body && doc.body.textContent) || '';
    }catch(e){
      s = s.replace(/<[^>]+>/g,' ');
    }
    return s.replace(/\s+/g,' ').trim().slice(0,400);
  }

  var host = el('div','ve-desk');
  var pill = el('button','ve-desk-pill');
  var panel = el('div','ve-desk-panel');
  panel.hidden = true;
  host.appendChild(pill); host.appendChild(panel);

  function countNews(st){
    return st.letters.filter(function(l){ return l.replied; }).length
         + st.ebooks.filter(function(b){ return b.status==='built'; }).length
         + st.comments.filter(function(c){ return c.status && c.status!=='approved'; }).length;
  }

  function renderPill(){
    var u = veUser();
    if(!u){ pill.textContent = 'Sign in'; pill.title = 'Use your Voice Express handle'; return; }
    var n = countNews(veReaderState(u));
    pill.textContent = n ? (u + ' · ' + n) : u;
    pill.title = n ? (n + ' update(s) on your submissions') : 'Your submissions';
  }

  function renderSignedOut(){
    panel.textContent = '';
    panel.appendChild(el('h3','ve-desk-h','Your Voice Express handle'));
    panel.appendChild(el('p','ve-desk-note',
      'The same handle works on the Newsstand. No password — it just lets us '
      + 'show you what happened to your comments, letters and ebook requests.'));
    var input = el('input','ve-desk-input');
    input.placeholder = 'handle'; input.setAttribute('aria-label','Your handle');
    var msg = el('p','ve-desk-msg');
    var rowb = el('div','ve-desk-row');

    function go(mode){
      var u = (input.value||'').trim();
      if(!u){ msg.textContent = 'Enter a handle.'; return; }
      msg.textContent = 'Checking…';
      veAccount(mode, u).then(function(d){
        if(d && d.ok){ veSetUser(d.username || u); return; }
        var e = d && d.error;
        msg.textContent = e==='taken' ? 'That handle is taken — try signing in.'
                        : e==='nouser' ? "No such handle — try creating it."
                        : 'Could not reach the service. Try again.';
      }).catch(function(){ msg.textContent = 'Could not reach the service. Try again.'; });
    }
    var bIn = el('button','ve-desk-btn','Sign in');
    var bUp = el('button','ve-desk-btn','Create');
    bIn.onclick = function(){ go('in'); };
    bUp.onclick = function(){ go('up'); };
    rowb.appendChild(bIn); rowb.appendChild(bUp);
    panel.appendChild(input); panel.appendChild(rowb); panel.appendChild(msg);
  }

  function section(title, items, render){
    var wrap = el('div','ve-desk-sec');
    wrap.appendChild(el('h4','ve-desk-h4', title));
    if(!items.length){ wrap.appendChild(el('p','ve-desk-empty','Nothing yet.')); return wrap; }
    items.forEach(function(it){ wrap.appendChild(render(it)); });
    return wrap;
  }

  function renderSignedIn(){
    var u = veUser(), st = veReaderState(u);
    panel.textContent = '';
    var head = el('div','ve-desk-row');
    head.appendChild(el('h3','ve-desk-h', u));
    var out = el('button','ve-desk-btn','Sign out');
    out.onclick = function(){ veSetUser(''); };
    head.appendChild(out);
    panel.appendChild(head);

    panel.appendChild(section('Letters', st.letters, function(l){
      var d = el('div','ve-desk-item');
      d.appendChild(el('strong', null, l.subject || '(no subject)'));
      if(l.replied){
        d.appendChild(el('span','ve-desk-badge','Answered'));
        (l.replies||[]).forEach(function(r){
          var q = el('div','ve-desk-reply');
          q.textContent = htmlToText(r.content);
          d.appendChild(q);
        });
      } else {
        d.appendChild(el('span','ve-desk-badge ve-desk-badge-wait','Awaiting a reply'));
      }
      d.appendChild(el('div','ve-desk-when', fmt(l.created_at)));
      return d;
    }));

    panel.appendChild(section('Ebook requests', st.ebooks, function(b){
      var d = el('div','ve-desk-item');
      d.appendChild(el('strong', null, b.title || 'Untitled'));
      if(b.status==='built' && b.download_url){
        d.appendChild(el('span','ve-desk-badge','Ready'));
        var a = el('a','ve-desk-link','Download your ebook');
        a.href = b.download_url;   
        d.appendChild(a);
      } else {
        d.appendChild(el('span','ve-desk-badge ve-desk-badge-wait','Being built'));
      }
      d.appendChild(el('div','ve-desk-when', fmt(b.built_at)));
      return d;
    }));

    panel.appendChild(section('Comments', st.comments, function(c){
      var d = el('div','ve-desk-item');
      d.appendChild(el('div', null, c.excerpt || ''));
      var ok = !c.status || c.status==='approved';
      var b = el('span','ve-desk-badge'+(ok?'':' ve-desk-badge-no'),
        ok ? 'Published' : (c.status==='pending' ? 'Awaiting review' : 'Not published'));
      d.appendChild(b);
      d.appendChild(el('div','ve-desk-when', fmt(c.created_at)));
      return d;
    }));

    panel.appendChild(el('p','ve-desk-note',
      'Updated when the site was last published — a very recent reply may not show yet.'));
  }

  function draw(){
    renderPill();
    if(!panel.hidden){ veUser() ? renderSignedIn() : renderSignedOut(); }
  }
  pill.onclick = function(){
    panel.hidden = !panel.hidden;
    if(!panel.hidden){ veUser() ? renderSignedIn() : renderSignedOut(); }
  };
  window.addEventListener('ve-user-changed', draw);
  document.addEventListener('click', function(e){
    if(!panel.hidden && !host.contains(e.target)){ panel.hidden = true; }
  });

  STORE.ready.then(function(){  
    document.body.appendChild(host);
    draw();
  });
})();

})();
