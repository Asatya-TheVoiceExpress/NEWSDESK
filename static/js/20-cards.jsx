function CImg({a,minH}){
  return(
    <div className="c-img" style={minH?{minHeight:minH}:{}}>
      {a.featured_image
        ?<img src={a.featured_image} alt={a.title} loading="lazy" onError={e=>{e.target.style.display='none';e.target.nextSibling&&(e.target.nextSibling.style.display='flex');}}/>
        :<div className="c-ph"><span className="c-ph-icon">¶</span></div>}
    </div>
  );
}

function ACard({a,size='md',setView,go,featured}){
  const nav=()=>{go(a);setView('article');};
  const goSect=e=>{e.stopPropagation();if(a.section_slug)setView(a.section_slug);};
  const goCat =e=>{e.stopPropagation();if(a.category_slug)setView(a.category_slug);};
  const labels=(
    <div className="c-labels">
      {a.section_name&&<span className="c-sect" onClick={goSect}>{a.section_name}</span>}
      {a.category_name&&<span className="c-cat-badge" onClick={goCat}>{a.category_name}</span>}
      {!a.section_name&&!a.category_name&&<span className="c-cat-badge">Uncategorised</span>}
    </div>
  );
  if(featured){
    return(
      <div className="card-feat">
        <CImg a={a} minH={300}/>
        <div className="c-body">
          {labels}
          <div className="c-title xl" onClick={nav}>{a.title}</div>
          <div className="c-exc">{a.excerpt||strip(a.content||'').slice(0,225)}</div>
          <div className="tags">{safe(a.tags).slice(0,3).map(t=><span key={t.id} className="tag">{t.name}</span>)}</div>
          <div className="c-meta">
            <span>{a.author_name}</span><span className="dot">·</span>
            <span>{fmtDate(a.published_at)}</span><span className="dot">·</span>
            <span>{a.reading_time||1} min read</span>
          </div>
        </div>
      </div>
    );
  }
  return(
    <div className="card">
      <CImg a={a}/>
      <div className="c-body">
        {labels}
        <div className={`c-title ${size}`} onClick={nav}>{a.title}</div>
        <div className="c-exc">{a.excerpt||strip(a.content||'').slice(0,165)}</div>
        <div className="c-meta">
          <span>{a.author_name}</span><span className="dot">·</span>
          <span>{fmtShort(a.published_at)}</span>
          {a.reading_time&&<><span className="dot">·</span><span>{a.reading_time} min</span></>}
        </div>
      </div>
    </div>
  );
}

function FilterPanel({tags,cats,activeTag,setActiveTag,activeCat,setActiveCat,label,hideCategories}){
  const [open,setOpen]=useState(false);
  const [tagQ,setTagQ]=useState('');
  const hasActive=activeTag!=null||!!activeCat;
  const activeTagName=safe(tags).find(t=>t.id===activeTag)?.name;
  const activeCatName=safe(cats).find(c=>c.slug===activeCat)?.name;
  const tagInputRef=useRef(null);

  const matchedTags=useMemo(()=>{
    if(!tagQ.trim()) return safe(tags).slice(0,60);
    const q=tagQ.toLowerCase();
    return safe(tags).filter(t=>t.name.toLowerCase().includes(q)).slice(0,30);
  },[tags,tagQ]);

  const pickTag=t=>{
    setActiveTag(activeTag===t.id?null:t.id);
    setTagQ('');
  };

  return(
    <div className="filter-bar">
      <div className="filter-bar-row">
        <button className={`filter-toggle${open?' on':''}`} onClick={()=>setOpen(v=>!v)}>
          {label||(hideCategories?'Tags':'Filters')} <span className="arrow">▾</span>
        </button>
        {activeTagName&&(
          <span className="filter-active-chip">{activeTagName} <span style={{cursor:'pointer',opacity:.7}} onClick={()=>setActiveTag(null)}>✕</span></span>
        )}
        {!hideCategories&&activeCatName&&(
          <span className="filter-active-chip">{activeCatName} <span style={{cursor:'pointer',opacity:.7}} onClick={()=>setActiveCat('')}>✕</span></span>
        )}
        {hasActive&&(
          <button className="btn-s" style={{fontSize:'.57rem'}} onClick={()=>{setActiveTag(null);setActiveCat&&setActiveCat('');setTagQ('');}}>Clear all</button>
        )}
      </div>

      <div className={`filter-panel-wrap${open?' open':''}`}>
        <div className="filter-panel-inner">
          <div className="filter-panel">

            {!hideCategories&&safe(cats).length>0&&(
              <>
                <div className="filter-section-lbl">Categories</div>
                <div style={{display:'flex',flexWrap:'wrap',gap:'.25rem',marginBottom:'.52rem'}}>
                  <span className={`tag${!activeCat?' on':''}`} onClick={()=>setActiveCat&&setActiveCat('')}>All</span>
                  {cats.map(c=>(
                    <span key={c.id} className={`tag${activeCat===c.slug?' on':''}`}
                      onClick={()=>setActiveCat&&setActiveCat(activeCat===c.slug?'':c.slug)}>
                      {c.name}{c.article_count>0&&<span style={{opacity:.55,fontSize:'.85em',marginLeft:2}}>{c.article_count}</span>}
                    </span>
                  ))}
                </div>
              </>
            )}

            {safe(tags).length>0&&(
              <>
                <div className="filter-section-lbl" style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
                  <span>Tags</span>
                  <input
                    ref={tagInputRef}
                    type="text"
                    value={tagQ}
                    onChange={e=>setTagQ(e.target.value)}
                    placeholder="Search tags…"
                    style={{
                      fontFamily:'var(--fm)',fontSize:'.6rem',
                      border:'var(--rt)',padding:'.2rem .45rem',
                      background:'var(--paper)',color:'var(--ink)',
                      width:'10rem',outline:'none',
                    }}
                  />
                </div>
                <div className="filter-tag-grid">
                  {matchedTags.map(t=>(
                    <div key={t.id} className={`filter-tag${activeTag===t.id?' on':''}`}
                      onClick={()=>pickTag(t)}>
                      <span style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{t.name}</span>
                      {t.article_count>0&&<span className="filter-tag-n">{t.article_count}</span>}
                    </div>
                  ))}
                  {matchedTags.length===0&&tagQ&&(
                    <div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g400)',padding:'.25rem .5rem',fontStyle:'italic'}}>No tags match "{tagQ}"</div>
                  )}
                </div>
              </>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}

