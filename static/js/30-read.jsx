
var ROLE_BYLINE_LABEL={photographer:'Photos by',illustrator:'Art by',translator:'Translation by',
  editor:'Edited by','as-told-to':'As told to',reporting:'Additional reporting by',
  typesetter:'Typeset by','post-editor':'Post-edited by'};
function joinNames(names){
  names=(names||[]).filter(Boolean);
  if(!names.length)return '';
  if(names.length===1)return names[0];
  return names.slice(0,-1).join(', ')+' & '+names[names.length-1];
}
function bylineCredits(authors){
  const groups={};
  (authors||[]).forEach(a=>{
    const r=a.role||'author';
    if(r==='author'||r==='co-author')return;
    (groups[r]=groups[r]||[]).push(a.name);
  });
  return Object.keys(groups).map(r=>`${ROLE_BYLINE_LABEL[r]||r[0].toUpperCase()+r.slice(1)+' by'} ${joinNames(groups[r])}`);
}

var ANN_LS_KEY='ve-local-annotations';
function lsAllAnns(){ try{return JSON.parse(localStorage.getItem(ANN_LS_KEY)||'{}');}catch(e){return {};} }
function lsAnnsFor(articleId){ return lsAllAnns()[articleId]||[]; }
function lsSaveAnn(articleId,ann){
  const all=lsAllAnns();
  all[articleId]=[...(all[articleId]||[]),ann];
  try{localStorage.setItem(ANN_LS_KEY,JSON.stringify(all));}catch(e){}
}
function lsDeleteAnn(articleId,id){
  const all=lsAllAnns();
  all[articleId]=(all[articleId]||[]).filter(a=>a.id!==id);
  try{localStorage.setItem(ANN_LS_KEY,JSON.stringify(all));}catch(e){}
}
function HomePage({setView,go,toast,sections}){
  const PAGE=20;
  const [articles,setArticles]=useState([]);
  const [cats,setCats]=useState([]);
  const [tags,setTags]=useState([]);
  const [activeTag,setActiveTag]=useState(null);
  const [activeCat,setActiveCat]=useState('');
  const [loading,setLoading]=useState(true);
  const [loadingMore,setLoadingMore]=useState(false);
  const [hasMore,setHasMore]=useState(true);
  const [filterResults,setFilterResults]=useState(null); 
  const [filterLoading,setFilterLoading]=useState(false);
  const [searchQ,setSearchQ]=useState('');
  const [fpTab,setFpTab]=useState('search');
  const offsetRef=useRef(0);
  const loadingMoreRef=useRef(false);
  const hasMoreRef=useRef(true);
  const sentinelRef=useRef(null);

  const fetchPage=useCallback(async(offset)=>{
    return safe(await API.get(`/api/articles?status=published&limit=${PAGE}&offset=${offset}`));
  },[]);

  const load=useCallback(async()=>{
    setLoading(true);
    offsetRef.current=0;
    hasMoreRef.current=true;
    try{
      const [arts,cs,ts]=await Promise.all([
        fetchPage(0),
        API.get('/api/categories'),
        API.get('/api/tags'),
      ]);
      setArticles(arts);setCats(safe(cs));setTags(safe(ts));
      offsetRef.current=arts.length;
      hasMoreRef.current=arts.length===PAGE;
      setHasMore(arts.length===PAGE);
    }catch{toast('Failed to load','err');}
    setLoading(false);
  },[]);

  const loadMore=useCallback(async()=>{
    if(loadingMoreRef.current||!hasMoreRef.current)return;
    loadingMoreRef.current=true;
    setLoadingMore(true);
    try{
      const arts=await fetchPage(offsetRef.current);
      setArticles(prev=>[...prev,...arts]);
      offsetRef.current+=arts.length;
      hasMoreRef.current=arts.length===PAGE;
      setHasMore(arts.length===PAGE);
    }catch{}
    loadingMoreRef.current=false;
    setLoadingMore(false);
  },[]);

  useEffect(()=>{load();},[]);

  useEffect(()=>{
    if(loading||activeTag||activeCat||searchQ)return;
    const el=sentinelRef.current;
    if(!el)return;
    const obs=new IntersectionObserver(entries=>{
      if(entries[0].isIntersecting)loadMore();
    },{rootMargin:'300px'});
    obs.observe(el);
    return()=>obs.disconnect();
  },[loading,activeTag,activeCat,searchQ]);

  useEffect(()=>{
    if(!activeTag&&!activeCat&&!searchQ){setFilterResults(null);return;}
    setFilterLoading(true);
    const t=setTimeout(()=>{
      let url='/api/articles?status=published&limit=200';
      if(activeTag){const tagObj=safe(tags).find(t=>t.id===activeTag);if(tagObj)url+=`&tag=${encodeURIComponent(tagObj.slug||tagObj.name)}`;}
      if(activeCat)url+=`&category=${encodeURIComponent(activeCat)}`;
      if(searchQ)url+=`&search=${encodeURIComponent(searchQ)}`;
      API.get(url)
        .then(arts=>setFilterResults(safe(arts)))
        .catch(()=>setFilterResults([]))
        .finally(()=>setFilterLoading(false));
    },searchQ?360:0);
    return()=>clearTimeout(t);
  },[activeTag,activeCat,searchQ,tags]);

  const filterActive=activeTag||activeCat||!!searchQ;
  const activeTagName=safe(tags).find(t=>t.id===activeTag)?.name;
  const activeCatName=safe(cats).find(c=>c.slug===activeCat)?.name;
  const featured=useMemo(()=>articles.filter(a=>a.is_featured),[articles]);
  const feat=featured[0];
  const rest=useMemo(()=>articles.filter(a=>!feat||a.id!==feat.id),[articles,feat]);

  if(loading)return <div className="loading">Loading Voice Express</div>;

  if(!articles.length){
    return(
      <div className="page">
        <div className="empty">
          <div className="empty-icon">¶</div>
          <div className="empty-title">The press is silent.</div>
          <div className="empty-sub">Write your first story from the Admin panel.</div>
        </div>
      </div>
    );
  }

  const leadArt=feat||rest[0];
  const sideStart=feat?0:1;
  const gridArticles=filterActive?(filterResults||[]):rest.slice(sideStart+2); 

  return(
    <div className="bs-page">
      <div className="bs-dateline">
        <span>New Delhi, India</span>
        <span>{new Date().toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long',year:'numeric'})}</span>
        <span>Vol. IV · Free · Reader Supported</span>
      </div>
      <div className="bs-hero-split">
        <div className="bs-hero-left">
          <div className="bs-front">
            <div className="bs-lead-col">
              {leadArt&&(
                <>
                  <span className="bs-lead-kicker">{leadArt.section_name||leadArt.category_name||'Top Story'}</span>
                  <div className="bs-lead-headline" onClick={()=>{go(leadArt);setView('article');}}>{leadArt.title}</div>
                  <div className="bs-lead-byline">By {leadArt.author_name||'The Voice Express'} · {fmtDate(leadArt.published_at)}</div>
                  {leadArt.featured_image&&<div className="bs-lead-img"><img src={leadArt.featured_image} alt={leadArt.title}/></div>}
                  <div className="bs-lead-standfirst">{leadArt.excerpt||strip(leadArt.content||'').slice(0,160)}</div>
                </>
              )}
            </div>
            <div className="bs-col bs-col-right">
              {rest.slice(sideStart,sideStart+2).map(a=>(
                <div key={a.id} className="bs-brief" onClick={()=>{go(a);setView('article');}}>
                  <div className="bs-brief-kicker">{a.section_name||a.category_name||'News'}</div>
                  <div className="bs-brief-title">{a.title}</div>
                  <div className="bs-brief-exc">{a.excerpt||strip(a.content||'').slice(0,80)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="bs-hero-right">
          <div className="bs-filter-pane">
            <div className="bs-fp-head">Browse</div>
            <div className="bs-fp-tabs">
              <span className={`bs-fp-tab${fpTab==='search'?' on':''}`} onClick={()=>setFpTab('search')}>Search</span>
              <span className={`bs-fp-tab${fpTab==='topics'?' on':''}`} onClick={()=>setFpTab('topics')}>Topics</span>
              {safe(sections).filter(s=>s.article_count>0).length>0&&(
                <span className={`bs-fp-tab${fpTab==='sections'?' on':''}`} onClick={()=>setFpTab('sections')}>Sections</span>
              )}
            </div>
            <div className="bs-fp-body">
              {fpTab==='search'&&(
                <>
                  <div className="bs-fp-search">
                    <span className="bs-fp-search-icon">⌕</span>
                    <input type="text" placeholder="Search stories, authors…" autoFocus
                      value={searchQ} onChange={e=>setSearchQ(e.target.value)}/>
                  </div>
                  {searchQ&&filterLoading&&<div style={{fontFamily:'var(--fm)',fontSize:'.55rem',color:'var(--g500)',letterSpacing:'.1em',textTransform:'uppercase'}}>Searching…</div>}
                  {searchQ&&!filterLoading&&filterResults!=null&&<div style={{fontFamily:'var(--fm)',fontSize:'.55rem',color:'var(--g500)',letterSpacing:'.08em',textTransform:'uppercase'}}>{filterResults.length} result{filterResults.length!==1?'s':''}</div>}
                </>
              )}
              {fpTab==='topics'&&(
                <>
                  {safe(cats).filter(c=>c.article_count>0).length>0&&(
                    <div>
                      <div className="bs-fp-lbl">Format</div>
                      <div className="bs-fp-cats">
                        <span className={`bs-fp-tag${!activeCat?' on':''}`} onClick={()=>setActiveCat('')}>All</span>
                        {safe(cats).filter(c=>c.article_count>0).map(c=>(
                          <span key={c.id} className={`bs-fp-tag${activeCat===c.slug?' on':''}`}
                            onClick={()=>setActiveCat(activeCat===c.slug?'':c.slug)}>
                            {c.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {safe(tags).length>0&&(
                    <div>
                      <div className="bs-fp-lbl">Tags</div>
                      <div className="bs-fp-tags">
                        {safe(tags).slice(0,60).map(t=>(
                          <span key={t.id} className={`bs-fp-tag${activeTag===t.id?' on':''}`}
                            onClick={()=>setActiveTag(activeTag===t.id?null:t.id)}>
                            {t.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
              {fpTab==='sections'&&safe(sections).filter(s=>s.article_count>0).length>0&&(
                <div className="bs-fp-sects">
                  {safe(sections).filter(s=>s.article_count>0).map(s=>(
                    <div key={s.id} className="bs-fp-sect-chip" onClick={()=>setView(s.slug)}>
                      <span className="bs-fp-sect-name">{s.name}</span>
                      <span className="bs-fp-sect-ct">{s.article_count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      {!filterActive&&<ColumnsRail setView={setView}/>}
      <div className="bs-divider">
        <span className="bs-divider-label">All Stories</span>
        <div className="bs-divider-rule"/>
        <button className="bs-divider-act" onClick={()=>setView('library')}>Newsstand ↗</button>
        <button className="bs-divider-act" onClick={()=>setView('map')}>Map ↗</button>
        <button className="bs-divider-act" onClick={()=>setView('newsletter')}>Newsletter ↗</button>
        <button className="bs-divider-act" onClick={()=>setView('authors')}>Contributors ↗</button>
        {hasCap('admin')&&<button className="bs-divider-act" onClick={()=>setView('admin')}>Admin ✦</button>}
      </div>
      <div className="bs-fold-outer">
        {filterActive&&(
          <div className="bs-active-filters">
            {searchQ&&<span className="filter-active-chip">"{searchQ}" <span style={{cursor:'pointer',opacity:.7}} onClick={()=>setSearchQ('')}>✕</span></span>}
            {activeTagName&&<span className="filter-active-chip">{activeTagName} <span style={{cursor:'pointer',opacity:.7}} onClick={()=>setActiveTag(null)}>✕</span></span>}
            {activeCatName&&<span className="filter-active-chip">{activeCatName} <span style={{cursor:'pointer',opacity:.7}} onClick={()=>setActiveCat('')}>✕</span></span>}
            <button className="btn-s" style={{marginLeft:'auto'}} onClick={()=>{setSearchQ('');setActiveTag(null);setActiveCat('');}}>Clear all</button>
          </div>
        )}
        <div className="bs-fold-inner">
          {filterActive&&filterLoading
            ?<div className="loading" style={{padding:'2rem 0'}}>Filtering…</div>
            :gridArticles.length>0
              ?<div className="bs-fold">
                {gridArticles.map((a,i)=><ACard key={a.id} a={a} size={i<3?'lg':'md'} setView={setView} go={go}/>)}
              </div>
              :filterActive
                ?<div className="empty" style={{padding:'2rem 0'}}><div className="empty-title" style={{fontSize:'1.1rem'}}>No stories match this filter</div></div>
                :null
          }
          {!filterActive&&<div ref={sentinelRef} style={{height:'1px'}}/>}
          {!filterActive&&loadingMore&&<div style={{textAlign:'center',padding:'1.5rem 0',fontFamily:'var(--fm)',fontSize:'.6rem',letterSpacing:'.12em',textTransform:'uppercase',color:'var(--g400)'}}>Loading more…</div>}
          {!filterActive&&!hasMore&&articles.length>PAGE&&<div style={{textAlign:'center',padding:'1.5rem 0',fontFamily:'var(--fm)',fontSize:'.6rem',letterSpacing:'.12em',textTransform:'uppercase',color:'var(--g400)'}}>— end of archive —</div>}
        </div>
      </div>
    </div>
  );
}

function CatPage({cat,setView,go}){
  const [articles,setArticles]=useState([]);
  const [loading,setLoading]=useState(true);
  const label=cat.charAt(0).toUpperCase()+cat.slice(1);
  useEffect(()=>{
    setLoading(true);
    API.get(`/api/articles?status=published&category=${encodeURIComponent(cat)}&limit=30`)
      .then(d=>{setArticles(safe(d));setLoading(false);})
      .catch(()=>setLoading(false));
  },[cat]);
  if(loading)return <div className="loading">Loading {label}</div>;
  return(
    <div className="page">
      <div className="sec-lbl"><span>{label}</span></div>
      {articles.length>0
        ?<div className="news-grid">{articles.map((a,i)=><ACard key={a.id} a={a} size={i===0?'lg':'md'} setView={setView} go={go}/>)}</div>
        :<div className="empty"><div className="empty-icon">¶</div><div className="empty-title">No {label} stories yet</div><div className="empty-sub">Check back soon</div></div>}
    </div>
  );
}

function SectionPage({section,sections,setView,go,toast}){
  const [articles,setArticles]=useState([]);
  const [loading,setLoading]=useState(true);
  const sec=useMemo(()=>safe(sections).find(s=>s.slug===section)||{name:section,description:''},[sections,section]);
  useEffect(()=>{
    setLoading(true);
    API.get(`/api/articles?status=published&section=${encodeURIComponent(section)}&limit=30`)
      .then(d=>{setArticles(safe(d));setLoading(false);})
      .catch(()=>{toast&&toast('Failed to load','err');setLoading(false);});
  },[section]);
  if(loading)return <div className="loading">Loading {sec.name}</div>;
  return(
    <div className="page">
      <div className="sec-lbl">
        <span>{sec.name}</span>
        {sec.description&&<span style={{fontFamily:'var(--fb)',fontSize:'.68rem',color:'var(--g500)',marginLeft:'1rem',fontWeight:400,fontStyle:'italic'}}>{sec.description}</span>}
      </div>
      {articles.length>0
        ?<div className="news-grid">{articles.map((a,i)=><ACard key={a.id} a={a} size={i===0?'lg':'md'} setView={setView} go={go}/>)}</div>
        :<div className="empty"><div className="empty-icon">¶</div><div className="empty-title">No stories in {sec.name} yet.</div><div className="empty-sub">Check back soon.</div></div>}
    </div>
  );
}

function ArticleHistory({history,translators}){
  const [open,setOpen]=useState(false);
  const actionLabel={created:'Written',edited:'Edited',translated:'Translated'};
  return(
    <div className="art-history">
      <div className="art-history-hdr" onClick={()=>setOpen(v=>!v)}>
        Article History <span style={{opacity:.5}}>{open?'▴':'▾'}</span>
        <span style={{fontFamily:'var(--fm)',fontSize:'.54rem',color:'var(--g400)',marginLeft:'.2rem'}}>({history.length} record{history.length!==1?'s':''})</span>
      </div>
      {open&&(
        <div>
          {history.map((h,i)=>(
            <div key={i} className="art-history-row">
              <span className={`art-history-action ${h.action}`}>{actionLabel[h.action]||h.action}</span>
              <span className="art-history-name">{h.display_name||'Unknown'}</span>
              {h.action==='translated'&&h.language&&(
                <span className="art-history-lang">→ {LANGS[h.language]||h.language}</span>
              )}
              <span className="art-history-date">{fmtDate(h.edited_at)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SeriesGrid({art,go,setView}){
  const articles=safe(art.series_articles);
  if(!art.series_title||articles.length<2)return null;
  return(
    <div className="series-strip">
      <div className="series-strip-hdr">Series: <strong>{art.series_title}</strong> · {articles.length} parts</div>
      <div className="series-parts">
        {articles.map((a,i)=>(
          <div key={a.id}
            className={`series-part${a.id===art.id?' cur':''}`}
            onClick={()=>{if(a.id!==art.id){go(a);setView('article');window.scrollTo(0,0);}}}>
            <div className="series-part-n">Part {a.series_order||i+1}</div>
            <div className="series-part-t">{a.title}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MediaLightbox({items,index:i0,onClose}){
  const [i,setI]=useState(i0||0);
  const n=items.length;
  const go=useCallback(d=>setI(p=>(p+d+n)%n),[n]);
  useEffect(()=>{
    const h=e=>{if(e.key==='Escape')onClose();else if(e.key==='ArrowRight')go(1);else if(e.key==='ArrowLeft')go(-1);};
    window.addEventListener('keydown',h);
    const prev=document.body.style.overflow;document.body.style.overflow='hidden';
    return()=>{window.removeEventListener('keydown',h);document.body.style.overflow=prev;};
  },[go,onClose]);
  const it=items[i]||{};
  return (
    <div className="lightbox" onClick={onClose}>
      <button className="lb-close" onClick={onClose} aria-label="Close">✕</button>
      {n>1&&<button className="lb-nav lb-prev" onClick={e=>{e.stopPropagation();go(-1);}} aria-label="Previous">‹</button>}
      <figure className="lb-stage" onClick={e=>e.stopPropagation()}>
        <img src={it.src} alt={it.cap||''}/>
        {(it.cap||n>1)&&<figcaption>{n>1&&<span className="lb-count">{i+1} / {n}</span>}{it.cap&&<span className="lb-cap">{it.cap}</span>}</figcaption>}
      </figure>
      {n>1&&<button className="lb-nav lb-next" onClick={e=>{e.stopPropagation();go(1);}} aria-label="Next">›</button>}
    </div>
  );
}

function ArticleView({article:init,setView,go,goBack,readMode,setReadMode,toast,currentUser,goToAuthor}){
  const [art,setArt]=useState(init);
  const [anns,setAnns]=useState([]);
  const [showAnns,setShowAnns]=useState(false);
  const [popup,setPopup]=useState(null);
  const [popNote,setPopNote]=useState('');
  const [lang,setLang]=useState(init?.language||'en'); 
  const [translated,setTranslated]=useState(null);
  const [translating,setTranslating]=useState(false);
  const contentRef=useRef(null);
  const linkCache=useRef({});
  const lpHide=useRef(null);
  const [linkPrev,setLinkPrev]=useState(null);
  const [lightbox,setLightbox]=useState(null);
  useReadingProgress();

  useEffect(()=>{
    if(!init?.id)return;
    setLang(init.language||'en');
    setTranslated(null);
    setShowAnns(false);
    setPopup(null);
    API.get(`/api/articles/${init.id}`)
      .then(d=>{
        setArt(d);
        setAnns(currentUser?safe(d.annotations):lsAnnsFor(init.id)); 
      })
      .catch(()=>{});
    if(currentUser)API.post('/api/reader/track',{article_id:init.id}).catch(()=>{});
  },[init?.id,currentUser]);

  const translate=async target=>{
    const native=art?.language||'en';
    if(target===native){setLang(native);setTranslated(null);return;} 
    if(target===lang&&translated)return; 
    setTranslating(true);
    try{
      const d=await API.post('/api/translate',{article_id:art.id,target_language:target});
      if(d.error){toast(d.error,'err');}
      else{setTranslated(d);setLang(target);}
    }catch{toast('Translation failed','err');}
    setTranslating(false);
  };

  const handleSelect=useCallback(()=>{
    const sel=window.getSelection();
    if(!sel||sel.isCollapsed||sel.toString().trim().length<4)return;
    const root=contentRef.current; if(!root)return;
    const range=sel.getRangeAt(0);
    if(!root.contains(range.commonAncestorContainer))return; 
    const rect=range.getBoundingClientRect();
    setPopNote('');
    const x=Math.max(8,Math.min(rect.left,window.innerWidth-270));
    const y=Math.min(rect.bottom+window.scrollY+6,window.scrollY+window.innerHeight-170);
    setPopup({x,y,text:sel.toString().trim()});
  },[]);

  useEffect(()=>{
    let t=null;
    const onChange=()=>{
      clearTimeout(t);
      t=setTimeout(handleSelect,150);
    };
    document.addEventListener('selectionchange',onChange);
    return()=>{clearTimeout(t);document.removeEventListener('selectionchange',onChange);};
  },[handleSelect]);

  const saveAnn=async()=>{
    if(!popup||!popNote.trim())return;
    if(currentUser){
      const d=await API.post('/api/annotations',{article_id:art.id,selected_text:popup.text,note:popNote}).catch(()=>({error:'Failed'}));
      if(d.error){toast(d.error,'err');return;}
      setAnns(prev=>[...prev,d]);
    }else{
      const d={id:'local-'+Date.now(),article_id:art.id,selected_text:popup.text,note:popNote,created_at:new Date().toISOString()};
      lsSaveAnn(art.id,d);
      setAnns(prev=>[...prev,d]);
      if(!hasCap('server_render')){
        API.post('/api/annotations',{article_id:art.id,selected_text:popup.text,note:popNote}).catch(()=>{});
      }
    }
    setShowAnns(true);
    setPopup(null);setPopNote('');
    toast('Annotation saved.');
  };

  const delAnn=async id=>{
    if(typeof id==='string'&&id.indexOf('local-')===0){
      lsDeleteAnn(art.id,id);
    }else{
      await API.del(`/api/annotations/${id}`).catch(()=>{});
    }
    setAnns(prev=>prev.filter(a=>a.id!==id));
  };

  const title   = translated?.title   || art?.title   || '';
  const content = translated?.content || art?.content || '';
  const excerpt = translated?.excerpt || art?.excerpt || '';
  const subtitle = art?.subtitle || '';

  useEffect(()=>{
    const root=contentRef.current; if(!root)return;
    root.querySelectorAll('.ve-dropcap').forEach(p=>p.classList.remove('ve-dropcap'));
    const first=root.querySelector('p');
    if(first && first.textContent.trim().length>1) first.classList.add('ve-dropcap');
  },[content]);

  useEffect(()=>{
    if(!readMode)return;
    const h=e=>{if(e.key==='Escape')setReadMode(false);};
    window.addEventListener('keydown',h);
    return()=>window.removeEventListener('keydown',h);
  },[readMode]);

  useEffect(()=>{
    const root=contentRef.current; if(!root)return;
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode(n){
      if(!n.nodeValue||!/https?:\/\//.test(n.nodeValue))return NodeFilter.FILTER_REJECT;
      if(n.parentElement&&n.parentElement.closest('a,script,style,code,pre'))return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }});
    const textNodes=[]; let tn; while(tn=walker.nextNode())textNodes.push(tn);
    const urlre=/https?:\/\/[^\s<>()\[\]"']+/g;
    textNodes.forEach(node=>{
      const s=node.nodeValue; const frag=document.createDocumentFragment(); let last=0,m;
      urlre.lastIndex=0;
      while(m=urlre.exec(s)){
        if(m.index>last)frag.appendChild(document.createTextNode(s.slice(last,m.index)));
        const a=document.createElement('a'); a.href=m[0]; a.textContent=m[0].replace(/^https?:\/\/(www\.)?/,'').replace(/\/$/,''); frag.appendChild(a);
        last=m.index+m[0].length;
      }
      if(last<s.length)frag.appendChild(document.createTextNode(s.slice(last)));
      if(frag.childNodes.length>1||frag.firstChild!==node)node.parentNode.replaceChild(frag,node);
    });
    const show=a=>{
      clearTimeout(lpHide.current);
      const r=a.getBoundingClientRect(), url=a.href;
      setLinkPrev({x:Math.max(8,Math.min(r.left,window.innerWidth-336)),y:r.bottom+8,url,data:linkCache.current[url]||null});
      if(!linkCache.current[url]){
        fetch('/api/link-preview?url='+encodeURIComponent(url)).then(res=>res.json())
          .then(d=>{linkCache.current[url]=d;setLinkPrev(p=>p&&p.url===url?{...p,data:d}:p);}).catch(()=>{});
      }
    };
    const hide=()=>{lpHide.current=setTimeout(()=>setLinkPrev(null),220);};
    root.querySelectorAll('a[href^="http"]').forEach(a=>{
      a.target='_blank'; a.rel='noopener noreferrer'; a.classList.add('ext-link');
      a.addEventListener('mouseenter',()=>show(a));
      a.addEventListener('mouseleave',hide);
    });
    root.querySelectorAll('figure img').forEach(img=>{
      img.addEventListener('click',()=>{
        const grp=img.closest('.photo-group');
        const imgs=grp?[...grp.querySelectorAll('img')]:[img];
        const items=imgs.map(im=>{
          const fig=im.closest('figure');
          const cap=fig&&fig.querySelector('figcaption,.panel-caption');
          return {src:im.currentSrc||im.src,cap:(cap&&cap.textContent.trim())||im.alt||''};
        });
        setLightbox({items,index:Math.max(0,imgs.indexOf(img))});
      });
    });
  },[content]);

  if(!art)return <div className="loading">Loading article</div>;

  return(
    <div className={readMode?'read-mode':''}>
      <div className="art-wrap">
        <div className="print-hdr">
          Voice Express — Truth Takes Time<br/>
          <span style={{fontSize:'.7rem',fontWeight:400}}>{fmtDate(art.published_at)}</span>
        </div>
        <div className="art-nav-row">
          <button className="art-back" onClick={()=>goBack?goBack():setView(art.section_slug||art.category_slug||'home')}>‹ Back</button>
          <div className="breadcrumb">
            <a onClick={()=>setView('home')}>Home</a>
            <span>›</span>
            {art.category_name&&<><a onClick={()=>setView(art.category_slug)}>{art.category_name}</a><span>›</span></>}
            <span>{(art.title||'').slice(0,55)}{(art.title||'').length>55?'…':''}</span>
          </div>
        </div>

        {art.series_title&&(
          <div style={{background:'var(--g100)',border:'var(--rt)',padding:'.52rem 1rem',marginBottom:'.85rem',display:'flex',alignItems:'center',gap:'.62rem',flexWrap:'wrap'}}>
            <span style={{fontFamily:'var(--fm)',fontSize:'.57rem',letterSpacing:'.12em',textTransform:'uppercase',color:'var(--g500)'}}>Part of series</span>
            <span style={{fontFamily:'var(--fh)',fontSize:'.92rem',fontWeight:700}}>{art.series_title}</span>
            {art.series_order>0&&<span style={{fontFamily:'var(--fm)',fontSize:'.57rem',color:'var(--g500)',letterSpacing:'.06em',textTransform:'uppercase'}}>· Part {art.series_order}</span>}
          </div>
        )}
        {art.category_name&&<div className="art-cat-lbl" onClick={()=>setView(art.category_slug)}>{art.category_name}</div>}
        <h1 className="art-title">{title}</h1>
        {subtitle&&<div className="art-subtitle">{subtitle}</div>}
        {excerpt&&<div className="art-deck">{excerpt}</div>}
        <div className="art-byline">
          {(() => {
            const writers=(art.authors||[]).filter(au=>!au.role||au.role==='author'||au.role==='co-author');
            const credits=bylineCredits(art.authors);
            const writerNode = art.byline
              ? <strong
                  style={{cursor:art.author_id&&goToAuthor?'pointer':'default'}}
                  onClick={()=>art.author_id&&goToAuthor&&goToAuthor(art.author_id)}>{art.byline}</strong>
              : (writers.length
                  ? <span>By {writers.map((au,i)=>(
                      <React.Fragment key={au.id}>
                        {i>0&&(i===writers.length-1?' & ':', ')}
                        <strong style={{cursor:goToAuthor?'pointer':'default'}}
                          onClick={()=>goToAuthor&&goToAuthor(au.id)}
                          title={`All stories by ${au.name} →`}>{au.name}</strong>
                      </React.Fragment>))}</span>
                  : (art.author_name?<strong>By {art.author_name}</strong>:null));
            return <>
              {writerNode}
              {credits.map((c,i)=><em key={i} className="art-byline-credit"> — {c}</em>)}
            </>;
          })()}
          {art.location_name&&<> — <em>{art.location_name}</em></>}
        </div>

        {safe(art.corrections).length>0&&(
          <div className="corrections-box">
            {art.corrections.map(c=>(
              <div key={c.id} className={`correction-item correction-${c.severity}`}>
                <div className="correction-hdr">
                  {c.severity==='retraction'?'Retraction':c.severity==='major'?'Correction':'Note'}
                  {' · '}{fmtDate(c.published_at)}
                </div>
                <div className="correction-title">{c.title}</div>
                <div className="correction-body">{c.body}</div>
              </div>
            ))}
          </div>
        )}

        <div className="art-metabar">
          <div className="art-metaleft">
            <span>{fmtDate(art.published_at)}</span>
            {art.reading_time&&<span>{art.reading_time} min read</span>}
            <span>{LANGS[art.language]||art.language||'English'}</span>
          </div>
          <div className="art-metaright">
            <button className={`btn-s${readMode?' on':''}`} onClick={()=>setReadMode(v=>!v)} title="Toggle distraction-free reading">{readMode?'Exit Read Mode':'Read Mode'}</button>
            <button className="btn-s" onClick={()=>window.open(hasCap('server_render')?'/api/articles/'+art.id+'/print':'static/media/gazette_'+art.id+'.html','_blank')} title="Download this article as a designed Gazette (logo cover, typeset, QR colophon)">Gazette ↓</button>
            <button className={`btn-s${showAnns?' on':''}`} onClick={()=>setShowAnns(v=>!v)} title="View/add annotations">
              {showAnns?'Hide Notes':'Annotate'}{anns.length>0?` (${anns.length})`:''}
            </button>
          </div>
        </div>

        <div className="lang-bar">
          <span className="lang-lbl">Read in:</span>
          <select className="lang-select" value={lang} disabled={translating}
            onChange={e=>translate(e.target.value)}>
            {Object.entries(LANGS).filter(([code])=>code===art.language||TRANSLATABLE_LANGS[code]).map(([code,name])=>(
              <option key={code} value={code}>{name}{code===art.language?' (original)':''}</option>
            ))}
          </select>
          {translating&&<span style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g500)',marginLeft:'.32rem'}}>Translating…</span>}
        </div>

        {art.featured_image&&(
          <div className="art-fimg">
            <img src={art.featured_image} alt={title} onError={e=>e.target.closest('.art-fimg').style.display='none'}/>
          </div>
        )}

        <div className="art-content dropcap" ref={contentRef} onMouseUp={handleSelect} onTouchEnd={handleSelect}
          dangerouslySetInnerHTML={{__html:content}}/>

        {linkPrev&&(
          <div className="link-preview" style={{left:linkPrev.x,top:linkPrev.y}}
            onMouseEnter={()=>clearTimeout(lpHide.current)} onMouseLeave={()=>setLinkPrev(null)}>
            {!linkPrev.data
              ? <div className="lp-load">Loading preview…</div>
              : <a className="lp-link" href={linkPrev.url} target="_blank" rel="noopener noreferrer">
                  {linkPrev.data.image&&<div className="lp-img" style={{backgroundImage:`url("${linkPrev.data.image}")`}}/>}
                  <div className="lp-site">{linkPrev.data.site}</div>
                  <div className="lp-title">{linkPrev.data.title||linkPrev.url}</div>
                  {linkPrev.data.description&&<div className="lp-desc">{linkPrev.data.description}</div>}
                </a>}
          </div>
        )}

        {lightbox&&<MediaLightbox items={lightbox.items} index={lightbox.index} onClose={()=>setLightbox(null)}/>}

        <div className="art-divider">— ✦ —</div>

        {safe(art.tags).length>0&&(
          <div className="tags-sect tags" style={{paddingTop:'.8rem',borderTop:'var(--rt)'}}>
            {art.tags.map(t=><span key={t.id} className="tag">{t.name}</span>)}
          </div>
        )}

        {art.author_name&&(
          <div className="author-card"
            style={{cursor:art.author_id&&goToAuthor?'pointer':'default',transition:'background .15s'}}
            onClick={()=>art.author_id&&goToAuthor&&goToAuthor(art.author_id)}
            onMouseOver={e=>{if(art.author_id&&goToAuthor)e.currentTarget.style.background='var(--g100)';}}
            onMouseOut={e=>{e.currentTarget.style.background='';}}>
            <Avatar author={art} size={76}/>
            <div>
              <div className="au-role">{art.author_role||'Correspondent'}</div>
              <div className="au-name">{art.author_name}</div>
              {art.author_bio&&<div className="au-bio">{art.author_bio}</div>}
              {(art.social_twitter||art.social_instagram)&&(
                <div className="au-social">
                  {art.social_twitter&&<span>{art.social_twitter}</span>}
                  {art.social_instagram&&<span style={{marginLeft:'.75rem'}}>{art.social_instagram}</span>}
                </div>
              )}
              {art.author_id&&goToAuthor&&(
                <div style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',marginTop:'.32rem',letterSpacing:'.06em',textTransform:'uppercase'}}>
                  View all stories →
                </div>
              )}
            </div>
          </div>
        )}

        {safe(art.history).length>0&&<ArticleHistory history={art.history} translators={art.translators||{}}/>}

        <SeriesGrid art={art} go={go} setView={setView}/>

        {safe(art.citations).length>0&&(
          <div className="cit-sect">
            <h3>References &amp; Sources</h3>
            {art.citations.map(c=>(
              <div key={c.id} className="cit-item">
                <span className="cit-n">[{c.citation_number}]</span>
                <span>{c.reference_text}
                  {c.author&&<> — <em>{c.author}</em></>}
                  {c.published_date&&<> ({c.published_date})</>}
                  {c.url&&<> · <a href={c.url} target="_blank" rel="noopener noreferrer">Source ↗</a></>}
                </span>
              </div>
            ))}
          </div>
        )}

        {safe(art.related).length>0&&(
          <div className="related-sect">
            <h3>Related Stories</h3>
            <div className="related-grid">
              {art.related.map(r=>(
                <div key={r.id} className="rel-item" onClick={()=>{go(r);setView('article');window.scrollTo(0,0);}}>
                  <div className="rel-title">{r.title}</div>
                  <div className="rel-meta">{r.author_name}{r.author_name&&' · '}{fmtShort(r.published_at)}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {popup&&(
        <div className="ann-popup" style={{left:popup.x,top:popup.y}}>
          <div style={{fontFamily:'var(--fm)',fontSize:'.56rem',letterSpacing:'.1em',textTransform:'uppercase',marginBottom:'.38rem',color:'var(--g600)'}}>Add Note</div>
          <div style={{fontStyle:'italic',fontSize:'.74rem',color:'var(--g500)',marginBottom:'.42rem',borderLeft:'3px solid var(--ink)',paddingLeft:'.45rem',lineHeight:1.45}}>
            "{popup.text.slice(0,95)}{popup.text.length>95?'…':''}"
          </div>
          <textarea autoFocus placeholder="Your annotation… (Ctrl+Enter to save)" value={popNote}
            onChange={e=>setPopNote(e.target.value)}
            onKeyDown={e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))saveAnn();}}
            style={{minHeight:52,marginBottom:'.38rem'}}/>
          <div className="ann-popup-btns">
            <button className="btn-p" style={{padding:'.27rem .62rem',fontSize:'.56rem'}} onClick={saveAnn}>Save</button>
            <button className="btn-o" style={{padding:'.27rem .62rem',fontSize:'.56rem'}} onClick={()=>setPopup(null)}>Cancel</button>
          </div>
        </div>
      )}

      {showAnns&&(
        <div className="ann-panel" role="complementary" aria-label="Annotations">
          <div className="ann-hdr">
            <span>Annotations ({anns.length})</span>
            <span className="ann-close" onClick={()=>setShowAnns(false)} role="button" aria-label="Close">✕</span>
          </div>
          {!anns.length
            ?<div style={{padding:'1rem',fontSize:'.8rem',color:'var(--g500)',fontStyle:'italic',lineHeight:1.5}}>Select any text in the article and a note popup will appear.</div>
            :anns.map(a=>(
              <div key={a.id} className="ann-item">
                <div className="ann-quote">"{a.selected_text}"</div>
                <div className="ann-note">{a.note}</div>
                <span className="ann-del" onClick={()=>delAnn(a.id)} role="button">× Delete</span>
              </div>
            ))}
        </div>
      )}
      {art?.id&&(
        <div className="art-wrap">
          {!hasCap('server_render')&&<LikeButton articleId={art.id}/>}
          <CommentsSection articleId={art.id} toast={toast}/>
        </div>
      )}
      <BackToTop/>
    </div>
  );
}

