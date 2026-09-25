function TimelinePage({setView,go}){
  const [articles,setArticles]=useState([]);
  const [loading,setLoading]=useState(true);
  const [zoom,setZoom]=useState('month'); 
  const [fCat,setFCat]=useState('');
  const [fAuthor,setFAuthor]=useState('');
  const [fTag,setFTag]=useState('');

  useEffect(()=>{
    API.get('/api/articles?status=published&limit=200')
      .then(d=>{setArticles(safe(d).sort((a,b)=>new Date(b.published_at)-new Date(a.published_at)));setLoading(false);})
      .catch(()=>setLoading(false));
  },[]);

  const cats   =useMemo(()=>[...new Set(articles.map(a=>a.category_name).filter(Boolean))],[articles]);
  const authors=useMemo(()=>[...new Set(articles.map(a=>a.author_name).filter(Boolean))],[articles]);
  const tags   =useMemo(()=>{const t=new Set();articles.forEach(a=>safe(a.tags).forEach(tg=>t.add(tg.name)));return[...t];},[articles]);

  const filtered=useMemo(()=>{
    let r=articles;
    if(fCat)   r=r.filter(a=>a.category_name===fCat);
    if(fAuthor)r=r.filter(a=>a.author_name===fAuthor);
    if(fTag)   r=r.filter(a=>safe(a.tags).some(t=>t.name===fTag));
    return r;
  },[articles,fCat,fAuthor,fTag]);

  const byYear=useMemo(()=>{
    const g={};
    filtered.forEach(a=>{if(!a.published_at)return;const y=new Date(a.published_at).getFullYear();(g[y]=g[y]||[]).push(a);});
    return Object.entries(g).sort(([a],[b])=>b-a);
  },[filtered]);

  const byMonth=useMemo(()=>{
    const g={};
    filtered.forEach(a=>{
      if(!a.published_at)return;
      const dt=new Date(a.published_at);
      const k=`${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}`;
      const label=dt.toLocaleDateString('en-GB',{month:'long',year:'numeric'});
      if(!g[k])g[k]={label,items:[]};
      g[k].items.push(a);
    });
    return Object.entries(g).sort(([a],[b])=>b.localeCompare(a)).map(([,v])=>v);
  },[filtered]);

  const hasFilter=fCat||fAuthor||fTag;
  const fSelect={width:'auto',padding:'.28rem .52rem',fontSize:'.65rem',border:'1px solid var(--g300)',background:'var(--paper)',color:'var(--ink)'};

  if(loading)return <div className="loading">Building Timeline</div>;
  return(
    <div className="tl-page">
      <div className="sec-lbl"><span>Interactive Timeline</span></div>

      <div className="tl-toolbar">
        <div className="tl-zoom-btns">
          <div className={`tl-zoom-btn${zoom==='year'?' on':''}`} onClick={()=>setZoom('year')} title="Group by year">Year</div>
          <div className={`tl-zoom-btn${zoom==='month'?' on':''}`} onClick={()=>setZoom('month')} title="Group by month">Month</div>
        </div>
        <select value={fCat} onChange={e=>setFCat(e.target.value)} style={fSelect}>
          <option value="">All sections</option>
          {cats.map(c=><option key={c} value={c}>{c}</option>)}
        </select>
        <select value={fAuthor} onChange={e=>setFAuthor(e.target.value)} style={fSelect}>
          <option value="">All authors</option>
          {authors.map(a=><option key={a} value={a}>{a}</option>)}
        </select>
        <select value={fTag} onChange={e=>setFTag(e.target.value)} style={fSelect}>
          <option value="">All tags</option>
          {tags.map(t=><option key={t} value={t}>{t}</option>)}
        </select>
        {hasFilter&&<button className="btn-s" style={{fontSize:'.58rem'}} onClick={()=>{setFCat('');setFAuthor('');setFTag('');}}>✕ Clear</button>}
        <span style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g500)',marginLeft:'auto'}}>{filtered.length} stories</span>
      </div>

      {zoom==='year'&&(
        <div className="tl-axis">
          {byYear.length>0
            ?byYear.map(([yr,arts])=>(
              <div key={yr} className="tl-year-row" onClick={()=>setZoom('month')}>
                <div className="tl-year-n">{yr}</div>
                <div className="tl-year-count">{arts.length} {arts.length===1?'story':'stories'}</div>
                <div className="tl-year-hint">Expand →</div>
              </div>
            ))
            :<div className="empty"><div className="empty-title">No stories</div></div>}
        </div>
      )}

      {zoom==='month'&&(
        <div className="tl-axis">
          {byMonth.map(({label,items})=>(
            <div key={label} className="tl-month">
              <div className="tl-month-lbl" style={{cursor:'pointer'}} onClick={()=>setZoom('year')} title="Collapse to year view">
                {label}
              </div>
              {items.map(a=>(
                <div key={a.id} className="tl-entry" onClick={()=>{go(a);setView('article');}}>
                  <div className="tl-date">{fmtShort(a.published_at)}</div>
                  <div>
                    <div className="tl-title">{a.title}</div>
                    <div className="tl-meta">
                      {a.category_name&&<span>{a.category_name} · </span>}
                      {a.author_name}
                      {a.location_name&&<span> · {a.location_name}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ))}
          {!byMonth.length&&<div className="empty"><div className="empty-title">No stories match</div><div className="empty-sub">Try adjusting the filters above</div></div>}
        </div>
      )}
    </div>
  );
}

function MapPage({setView,go,currentUser}){
  const isStaff = currentUser && currentUser.role!=='reader'; 
  const [articles,setArticles]=useState([]);
  const [loading,setLoading]=useState(true);
  const [fCat,setFCat]=useState('');
  const [fAuthor,setFAuthor]=useState('');
  const [fYear,setFYear]=useState('');
  const mapInst=useRef(null);
  const artRef=useRef([]);
  const markersRef=useRef({});
  const roRef=useRef(null);

  useEffect(()=>{
    API.get('/api/articles?status=published&geotagged=true&limit=200')
      .then(d=>{const a=safe(d);setArticles(a);artRef.current=a;setLoading(false);})
      .catch(()=>setLoading(false));
    return()=>{
      if(mapInst.current){try{mapInst.current.remove();}catch{}mapInst.current=null;}
      delete window._mapClick;
    };
  },[]);

  const cats   =useMemo(()=>[...new Set(articles.map(a=>a.category_name).filter(Boolean))],[articles]);
  const authors=useMemo(()=>[...new Set(articles.map(a=>a.author_name).filter(Boolean))],[articles]);
  const years  =useMemo(()=>[...new Set(articles.map(a=>a.published_at?.slice(0,4)).filter(Boolean))].sort((a,b)=>b-a),[articles]);

  const filtered=useMemo(()=>{
    let r=articles;
    if(fCat)   r=r.filter(a=>a.category_name===fCat);
    if(fAuthor)r=r.filter(a=>a.author_name===fAuthor);
    if(fYear)  r=r.filter(a=>a.published_at?.startsWith(fYear));
    return r;
  },[articles,fCat,fAuthor,fYear]);

  useEffect(()=>{
    if(loading)return;
    const t=setTimeout(()=>{
      const el=document.getElementById('leaflet-map');
      if(!el)return;
      if(mapInst.current){try{mapInst.current.remove();}catch{}mapInst.current=null;}
      const defaultView=[28.6139,77.2090]; 
      const map=L.map('leaflet-map',{zoomControl:true}).setView(defaultView,10);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>',maxZoom:18}).addTo(map);
      mapInst.current=map;
      const icon=L.divIcon({className:'',html:'<div style="width:13px;height:13px;background:#0a0a0a;border:2px solid #fafaf8;border-radius:50%;box-shadow:0 0 0 2px #0a0a0a;cursor:pointer;"></div>',iconSize:[13,13],iconAnchor:[6,6],popupAnchor:[0,-12]});
      markersRef.current={};
      const bounds=[];
      artRef.current.forEach(a=>{
        if(!a.latitude||!a.longitude)return;
        const popup=L.popup({closeButton:false,maxWidth:240})
          .setContent(`<div class="map-pop-title" onclick="window._mapClick(${a.id})">${a.title}</div><div class="map-pop-meta">${a.author_name||''} · ${fmtShort(a.published_at)}</div>${a.location_name?`<div class="map-pop-meta" style="margin-top:.2rem">\u{1F4CD} ${a.location_name}</div>`:''}`);
        const marker=L.marker([a.latitude,a.longitude],{icon}).addTo(map).bindPopup(popup);
        markersRef.current[a.id]=marker;
        bounds.push([a.latitude,a.longitude]);
      });
      const fit=()=>{
        map.invalidateSize(false);
        if(bounds.length>1)map.fitBounds(bounds,{padding:[30,30]});
        else if(bounds.length===1)map.setView(bounds[0],13);
      };
      fit();
      requestAnimationFrame(fit);
      if(typeof ResizeObserver!=='undefined'){
        const ro=new ResizeObserver(()=>map.invalidateSize(false));
        ro.observe(el);
        roRef.current=ro;
      }
      window._mapClick=id=>{const f=artRef.current.find(a=>a.id===id);if(f){go(f);setView('article');}};
    },80);
    return()=>{
      clearTimeout(t);
      if(roRef.current){try{roRef.current.disconnect();}catch{}roRef.current=null;}
    };
  },[loading]);

  useEffect(()=>{
    if(!mapInst.current)return;
    const ids=new Set(filtered.map(a=>a.id));
    Object.entries(markersRef.current).forEach(([id,m])=>{
      const aid=parseInt(id);
      if(ids.has(aid)){if(!mapInst.current.hasLayer(m))mapInst.current.addLayer(m);}
      else{if(mapInst.current.hasLayer(m))mapInst.current.removeLayer(m);}
    });
  },[filtered]);

  const flyTo=a=>{
    if(!mapInst.current||!a.latitude||!a.longitude)return;
    mapInst.current.flyTo([a.latitude,a.longitude],12,{duration:1.2});
    setTimeout(()=>markersRef.current[a.id]?.openPopup(),1350);
  };

  const hasFilter=fCat||fAuthor||fYear;
  const fStyle={width:'auto',padding:'.24rem .5rem',fontSize:'.68rem',border:'1px solid var(--g300)',background:'var(--paper)',color:'var(--ink)'};

  const [geoTagging,setGeoTagging]=useState(false);
  const autoGeoTag=async()=>{
    setGeoTagging(true);
    try{
      const r=await fetch('/api/articles/auto-geotag',{method:'POST',headers:{'Content-Type':'application/json'}});
      const d=await r.json();
      if(d.tagged>0){
        const a2=await API.get('/api/articles?status=published&geotagged=true&limit=200').catch(()=>[]);
        const arr=safe(a2);setArticles(arr);artRef.current=arr;
        if(mapInst.current){
          const icon=L.divIcon({className:'',html:'<div style="width:13px;height:13px;background:#0a0a0a;border:2px solid #fafaf8;border-radius:50%;box-shadow:0 0 0 2px #0a0a0a;cursor:pointer;"></div>',iconSize:[13,13],iconAnchor:[6,6],popupAnchor:[0,-12]});
          Object.values(markersRef.current).forEach(m=>m.remove());
          markersRef.current={};
          const bounds=[];
          arr.forEach(a=>{
            if(!a.latitude||!a.longitude)return;
            const popup=L.popup({closeButton:false,maxWidth:240}).setContent(`<div class="map-pop-title" onclick="window._mapClick(${a.id})">${a.title}</div><div class="map-pop-meta">${a.author_name||''} · ${fmtShort(a.published_at)}</div>${a.location_name?`<div class="map-pop-meta" style="margin-top:.2rem">\u{1F4CD} ${a.location_name}</div>`:''}`);
            const marker=L.marker([a.latitude,a.longitude],{icon}).addTo(mapInst.current).bindPopup(popup);
            markersRef.current[a.id]=marker;bounds.push([a.latitude,a.longitude]);
          });
          if(bounds.length>1)mapInst.current.fitBounds(bounds,{padding:[30,30]});
          else if(bounds.length===1)mapInst.current.setView(bounds[0],12);
        }
        alert(`Auto-tagged ${d.tagged} articles with location data.`);
      }else{alert('No new articles to tag (all already have coordinates).');}
    }catch(e){alert('Auto-tag failed: '+e.message);}
    finally{setGeoTagging(false);}
  };

  return(
    <div className="map-page">
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:'.5rem',marginBottom:'.5rem'}}>
        <div className="sec-lbl" style={{margin:0}}><span>Map</span> — Geotagged Reporting</div>
        {isStaff&&hasCap('server_render')&&<button className="btn-s" onClick={autoGeoTag} disabled={geoTagging} title="Infer Delhi-area locations from article content" style={{fontSize:'.58rem',opacity:geoTagging?.6:1}}>
          {geoTagging?'Tagging…':'⊕ Auto-tag locations'}
        </button>}
      </div>

      {!loading&&articles.length>0&&(
        <div className="map-filters">
          <span className="map-filter-lbl">Filter:</span>
          <select value={fCat} onChange={e=>setFCat(e.target.value)} style={fStyle}>
            <option value="">All sections</option>
            {cats.map(c=><option key={c} value={c}>{c}</option>)}
          </select>
          <select value={fAuthor} onChange={e=>setFAuthor(e.target.value)} style={fStyle}>
            <option value="">All authors</option>
            {authors.map(a=><option key={a} value={a}>{a}</option>)}
          </select>
          <select value={fYear} onChange={e=>setFYear(e.target.value)} style={fStyle}>
            <option value="">All years</option>
            {years.map(y=><option key={y} value={y}>{y}</option>)}
          </select>
          {hasFilter&&<button className="btn-s" style={{fontSize:'.58rem'}} onClick={()=>{setFCat('');setFAuthor('');setFYear('');}}>✕ Clear</button>}
          <span style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g500)',marginLeft:'auto'}}>
            {filtered.length}/{articles.length} stories · Click ✈ to fly to location
          </span>
        </div>
      )}

      {loading?<div className="loading">Loading map</div>:(
        <>
          <div className="map-cont"><div id="leaflet-map"/></div>
          {filtered.length>0
            ?<div className="news-grid" style={{gridTemplateColumns:'repeat(auto-fill,minmax(275px,1fr))',marginTop:'1rem'}}>
                {filtered.map(a=>(
                  <div key={a.id} style={{position:'relative'}}>
                    <ACard a={a} setView={setView} go={go}/>
                    <button className="map-fly-btn" onClick={e=>{e.stopPropagation();flyTo(a);}} title={`Fly to ${a.location_name||'location'}`}>
                      ✈ Fly
                    </button>
                  </div>
                ))}
              </div>
            :<div className="empty"><div className="empty-title">{articles.length?'No stories match this filter':'No geotagged stories'}</div><div className="empty-sub">{articles.length?'Try adjusting the filters above':'Add latitude & longitude to articles to see them here'}</div></div>}
        </>
      )}
    </div>
  );
}

function NewsletterPage({setView,go,toast,currentUser}){
  const [nl,setNl]=useState(null);
  const [all,setAll]=useState([]);
  const [range,setRange]=useState(null);
  const [loading,setLoading]=useState(true);
  const [navving,setNavving]=useState(false);
  const [tab,setTab]=useState('current');
  const [regen,setRegen]=useState(false);
  const [editingEd,setEditingEd]=useState(false);
  const [edDraft,setEdDraft]=useState('');
  const [pay,setPay]=useState(null);
  const [payAmt,setPayAmt]=useState(0);

  const load=async()=>{
    setLoading(true);
    try{
      const tgt=window.__nlGoto; window.__nlGoto=null;
      const [curr,months,rng]=await Promise.all([
        (tgt?API.get(`/api/newsletters/${tgt.year}/${tgt.month}`):API.get('/api/newsletters/current')).catch(()=>null),
        API.get('/api/newsletters/months').catch(()=>[]),
        API.get('/api/newsletters/range').catch(()=>null),
      ]);
      setNl(curr);setAll(safe(months));setRange(rng);
    }catch{}
    setLoading(false);
  };
  useEffect(()=>{load();},[]);

  const goMonth=async(y,m)=>{
    if(m<1){y--;m=12;} if(m>12){y++;m=1;}
    setNavving(true);
    try{const ed=await API.get(`/api/newsletters/${y}/${m}`);setNl(ed);setTab('current');window.scrollTo(0,0);}
    catch{toast('Could not load that edition','err');}
    setNavving(false);
  };
  const ymKey=(y,m)=>`${y}-${String(m).padStart(2,'0')}`;
  const canPrev=nl&&(!range||ymKey(nl.month===1?nl.year-1:nl.year,nl.month===1?12:nl.month-1)>=(range.min||'0'));
  const canNext=nl&&(!range||ymKey(nl.month===12?nl.year+1:nl.year,nl.month===12?1:nl.month+1)<=(range.max||'9999'));

  const regenerate=async()=>{
    if(!nl)return;
    setRegen(true);
    try{const ed=await API.post('/api/newsletters/regenerate',{year:nl.year,month:nl.month});setNl(ed);}
    catch{}
    try{setAll(safe(await API.get('/api/newsletters/months')));}catch{}
    setRegen(false);toast('Edition regenerated!');
  };

  const saveEditorial=async()=>{
    if(!nl?.id)return;
    try{
      await API.put(`/api/newsletters/${nl.id}`,{editorial:edDraft});
      setNl(n=>({...n,content:{...getC(n),editorial:edDraft}}));
      setEditingEd(false);
      toast('Editorial note saved!');
    }catch{toast('Save failed','err');}
  };

  const getC=n=>{
    if(!n)return{articles:[],editorial:''};
    if(n.content&&typeof n.content==='object')return n.content;
    try{return JSON.parse(n.content||'{}')}catch{return{};}
  };

  if(loading)return <div className="loading">Preparing Newsletter</div>;
  const c=getC(nl);
  const monthStr=nl?new Date(2000,(nl.month||1)-1).toLocaleString('default',{month:'long'}):'';

  return(
    <div className="nl-page">
      <div style={{display:'flex',gap:'.45rem',marginBottom:'1.3rem',alignItems:'center',flexWrap:'wrap'}}>
        <button className={`btn-s${tab==='current'?' on':''}`} onClick={()=>setTab('current')}>Current Edition</button>
        <button className={`btn-s${tab==='archive'?' on':''}`} onClick={()=>setTab('archive')}>Archive</button>
        {nl&&safe(getC(nl).articles).length>0&&(
          <button className="btn-s" style={{marginLeft:'auto'}}
            onClick={()=>{setPayAmt(0);setPay({
              title:`${monthStr} ${nl.year} — Broadsheet`,
              pub_type:'broadsheet',
              description:'This edition as a vintage newspaper broadsheet — full grid, puzzles, plotter-ready. Download the PDF, or read the edition online.',
              ...broadsheetLinks(nl.year,nl.month),
              _nl:{year:nl.year,month:nl.month}});}}
            title="Download this edition as a vintage broadsheet PDF, or read online">Get this edition ↓</button>
        )}
        {currentUser&&currentUser.role!=='reader'&&hasCap('server_render')&&
          <button className="btn-s" style={nl&&safe(getC(nl).articles).length>0?{}:{marginLeft:'auto'}} onClick={regenerate} disabled={regen}
            title="Rebuild this edition from current articles">{regen?'Regenerating…':'↻ Regenerate'}</button>}
      </div>

      {!hasCap('server_render')&&<SubscribeBox toast={toast}/>}

      {tab==='current'&&nl&&(
        <>
          <div className="nl-monthnav">
            <button className="nl-navbtn" disabled={!canPrev||navving}
              onClick={()=>goMonth(nl.month===1?nl.year-1:nl.year,nl.month===1?12:nl.month-1)}
              title="Previous month">‹ Prev</button>
            <span className="nl-navlbl">{navving?'Loading…':`${monthStr} ${nl.year}`}</span>
            <button className="nl-navbtn" disabled={!canNext||navving}
              onClick={()=>goMonth(nl.month===12?nl.year+1:nl.year,nl.month===12?1:nl.month+1)}
              title="Next month">Next ›</button>
          </div>
          <div className="nl-hdr">
            <div className="nl-issue">{monthStr} {nl.year}</div>
            <div className="nl-title">{nl.title}</div>
            <div className="nl-ed">
              {editingEd?(
                <div style={{textAlign:'left',marginTop:'.3rem'}}>
                  <textarea
                    style={{width:'100%',minHeight:'70px',fontFamily:'var(--fb)',fontStyle:'italic',
                      fontSize:'.9rem',lineHeight:1.6,border:'var(--rule)',padding:'.5rem',
                      background:'var(--paper)',color:'var(--ink)',resize:'vertical',boxSizing:'border-box'}}
                    value={edDraft}
                    onChange={e=>setEdDraft(e.target.value)}/>
                  <div style={{display:'flex',gap:'.35rem',marginTop:'.42rem',justifyContent:'center'}}>
                    <button className="btn-s" onClick={saveEditorial}>Save</button>
                    <button className="btn-s" onClick={()=>setEditingEd(false)}>Cancel</button>
                  </div>
                </div>
              ):(
                <>
                  {c.editorial||'The essential stories of the month, curated by our editors.'}
                  {currentUser&&(
                    <span title="Edit editorial note"
                      style={{cursor:'pointer',marginLeft:'.45rem',opacity:.3,fontSize:'.78em',userSelect:'none'}}
                      onClick={()=>{setEdDraft(c.editorial||'');setEditingEd(true);}}>✎</span>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="nl-grid">
            {safe(c.articles).map((a,i)=>(
              <div key={a.id} className={`nl-art${i===0?' nl-feat':''}`}
                onClick={()=>{go(a);setView('article');}}>
                {a.featured_image&&(
                  <img className="nl-art-thumb"
                    src={a.featured_image.startsWith('/')?a.featured_image:'/static/uploads/'+a.featured_image}
                    alt={a.title}
                    onError={e=>e.target.style.display='none'}/>
                )}
                <div className="nl-art-body">
                  <div className="nl-art-cat">{a.category_name||'Report'}</div>
                  <div className="nl-art-title">{a.title}</div>
                  <div className="nl-art-exc">{a.excerpt||strip(a.content||'').slice(0,185)}</div>
                  <div className="nl-art-meta">By {a.author_name||a.byline||'—'} · {fmtShort(a.published_at)}</div>
                </div>
              </div>
            ))}
            {!safe(c.articles).length&&(
              <div style={{padding:'2rem',color:'var(--g500)',gridColumn:'1/-1',textAlign:'center',fontStyle:'italic',fontSize:'1rem'}}>
                No dispatches filed for {monthStr} {nl.year}.
              </div>
            )}
          </div>

          {safe(c.columns).length>0&&(
            <div style={{marginTop:'2rem'}}>
              <div className="sec-lbl"><span>From the Columns</span></div>
              <div className="nl-cols">
                {safe(c.columns).map(e=>(
                  <div key={e.id} className="nl-col-entry"
                    onClick={()=>{setView('columns');}}
                    title={`${e.column_title} — open columns`}>
                    {e.cover_image&&<img className="nl-col-thumb"
                      src={e.cover_image.startsWith('/')?e.cover_image:'/static/uploads/'+e.cover_image}
                      alt={e.title} onError={ev=>ev.target.style.display='none'}/>}
                    <div className="nl-col-body">
                      <div className="nl-art-cat">{e.column_title}</div>
                      <div className="nl-col-title">{e.title}</div>
                      {e.subtitle&&<div className="nl-art-exc">{e.subtitle}</div>}
                      <div className="nl-art-meta">{fmtShort(e.entry_date)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
      {tab==='current'&&!nl&&<div className="empty"><div className="empty-title">No newsletter yet</div><div className="empty-sub">Publish articles first</div></div>}

      {tab==='archive'&&(
        <div>
          <div className="sec-lbl"><span>Archive — Browse by Month</span></div>
          {!all.length&&<div className="empty" style={{padding:'2rem 0'}}><div className="empty-title">No past editions yet</div><div className="empty-sub">Newsletters appear here after each month</div></div>}
          {(()=>{
            const byYear={};
            all.forEach(n=>{if(!byYear[n.year])byYear[n.year]={};byYear[n.year][n.month]=n;});
            const years=Object.keys(byYear).map(Number).sort((a,b)=>b-a);
            const MN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
            return years.map(yr=>(
              <div key={yr} style={{marginBottom:'2.2rem'}}>
                <div style={{fontFamily:'var(--fh)',fontSize:'1.28rem',fontWeight:700,marginBottom:'.72rem',borderBottom:'var(--rule)',paddingBottom:'.38rem'}}>{yr}</div>
                <div style={{display:'grid',gridTemplateColumns:'repeat(6,1fr)',gap:'2px',background:'var(--ink)',border:'var(--rule)'}}>
                  {MN.map((m,i)=>{
                    const nlEntry=byYear[yr][i+1];
                    return(
                      <div key={m}
                        onClick={()=>{if(nlEntry){goMonth(yr,i+1);}}}
                        style={{
                          background:nlEntry?'var(--paper)':'var(--g100)',
                          padding:'1.1rem .5rem .9rem',
                          textAlign:'center',
                          cursor:nlEntry?'pointer':'default',
                          transition:'background .15s',
                        }}
                        onMouseOver={e=>{if(nlEntry)e.currentTarget.style.background='var(--g200)';}}
                        onMouseOut={e=>{if(nlEntry)e.currentTarget.style.background='var(--paper)';}}>
                        <div style={{fontFamily:'var(--fm)',fontSize:'.6rem',letterSpacing:'.1em',textTransform:'uppercase',color:nlEntry?'var(--ink)':'var(--g400)',fontWeight:nlEntry?700:400}}>{m}</div>
                        {nlEntry&&<div style={{marginTop:'.32rem',width:7,height:7,background:'var(--ink)',borderRadius:'50%',margin:'.32rem auto 0'}}/>}
                      </div>
                    );
                  })}
                </div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.06em',marginTop:'.45rem'}}>
                  {Object.keys(byYear[yr]).length} edition{Object.keys(byYear[yr]).length!==1?'s':''} · Click a highlighted month to read
                </div>
              </div>
            ));
          })()}
        </div>
      )}
      {pay&&<PaymentModal pub={pay} amount={payAmt} setAmount={setPayAmt} onClose={()=>setPay(null)} toast={toast} setView={setView}/>}
    </div>
  );
}

function AuthorProfilePage({author,onBack,setView,go}){
  const [links,setLinks]=useState([]);
  const [articles,setArticles]=useState([]);
  const [contrib,setContrib]=useState({translated:[],edited:[]});
  const [tab,setTab]=useState('written');
  useEffect(()=>{
    if(!author?.id)return;
    API.get(`/api/authors/${author.id}/links`).then(d=>setLinks(safe(d))).catch(()=>{});
    API.get(`/api/articles?status=published&author_id=${author.id}&limit=12`).then(d=>setArticles(safe(d))).catch(()=>{});
    API.get(`/api/authors/${author.id}/contributions`).then(d=>setContrib(d||{translated:[],edited:[]})).catch(()=>{});
  },[author?.id]);
  const typeLabel=AUTHOR_TYPES.find(t=>t.value===author?.author_type)?.label||(author?.author_type||'');
  return(
    <div className="ap-wrap">
      {onBack&&<div style={{textAlign:'left',marginBottom:'1.2rem'}}>
        <button className="btn-o" onClick={onBack}>← All Contributors</button>
      </div>}
      <div className="ap-av">
        {author.avatar_url
          ?<img src={author.avatar_url} alt={author.name} onError={e=>e.target.style.display='none'}/>
          :initials(author.name)}
      </div>
      <div className="ap-name">{author.name}</div>
      {typeLabel&&<div className="ap-type-tag">{typeLabel}</div>}
      {author.role&&<div className="ap-role-lbl">{author.role}</div>}
      {author.bio&&<div className="ap-bio">{author.bio}</div>}
      {(author.social_twitter||author.social_instagram||author.email)&&(
        <div className="ap-socials">
          {author.social_twitter&&<a href={`https://x.com/${author.social_twitter.replace('@','')}`} target="_blank" rel="noopener noreferrer" className="ap-soc-btn">{author.social_twitter}</a>}
          {author.social_instagram&&<a href={`https://instagram.com/${author.social_instagram.replace('@','')}`} target="_blank" rel="noopener noreferrer" className="ap-soc-btn">{author.social_instagram}</a>}
          {author.email&&<a href={`mailto:${author.email}`} className="ap-soc-btn">{author.email}</a>}
        </div>
      )}
      {links.length>0&&(
        <div className="ap-links">
          {links.map(l=>{
            const lt=LINK_TYPES[l.link_type]||LINK_TYPES.other;
            return(
              <a key={l.id} href={l.url} target="_blank" rel="noopener noreferrer" className="ap-link-card">
                <div className="ap-link-icon">{lt.icon}</div>
                <div className="ap-link-title">{l.title}</div>
                <div className="ap-link-arr">↗</div>
              </a>
            );
          })}
        </div>
      )}
      {(articles.length>0||contrib.translated?.length>0||contrib.edited?.length>0)&&(
        <div style={{display:'flex',borderBottom:'var(--rule)',marginBottom:'1.35rem',textAlign:'left',width:'100%'}}>
          {[
            ['written',`Written (${articles.length})`],
            ...(contrib.translated?.length>0?[['translated',`Translated (${contrib.translated.length})`]]:[]),
            ...(contrib.edited?.length>0?[['edited',`Edited (${contrib.edited.length})`]]:[]),
          ].map(([id,lbl])=>(
            <div key={id} className={`a-tab${tab===id?' on':''}`} onClick={()=>setTab(id)}>{lbl}</div>
          ))}
        </div>
      )}

      {tab==='written'&&articles.length>0&&(
        <div className="news-grid" style={{textAlign:'left'}}>
          {articles.map(a=><ACard key={a.id} a={a} setView={setView} go={go}/>)}
        </div>
      )}
      {tab==='written'&&!articles.length&&(
        <div style={{fontFamily:'var(--fb)',fontStyle:'italic',color:'var(--g500)',fontSize:'1rem'}}>No published articles yet.</div>
      )}

      {tab==='translated'&&(
        <div style={{textAlign:'left'}}>
          {safe(contrib.translated).map(a=>(
            <div key={`${a.id}-${a.language}`} className="sr-item" style={{cursor:'pointer'}} onClick={()=>{go(a);setView('article');}}>
              <div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.55rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.08em',marginBottom:'.15rem'}}>
                  {LANGS[a.language]||a.language} translation · original by {a.original_author}
                </div>
                <div style={{fontFamily:'var(--fh)',fontSize:'1rem',fontWeight:700,lineHeight:1.3}}>{a.title}</div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g400)',marginTop:'.15rem'}}>{fmtDate(a.published_at)}</div>
              </div>
              {a.featured_image&&<img className="sr-thumb" src={a.featured_image} alt="" onError={e=>e.target.style.display='none'}/>}
            </div>
          ))}
        </div>
      )}

      {tab==='edited'&&(
        <div style={{textAlign:'left'}}>
          {safe(contrib.edited).map(a=>(
            <div key={`${a.id}-${a.edited_at}`} className="sr-item" style={{cursor:'pointer'}} onClick={()=>{go(a);setView('article');}}>
              <div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.55rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.08em',marginBottom:'.15rem'}}>
                  Edited · original by {a.author_name}
                </div>
                <div style={{fontFamily:'var(--fh)',fontSize:'1rem',fontWeight:700,lineHeight:1.3}}>{a.title}</div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g400)',marginTop:'.15rem'}}>{fmtDate(a.edited_at)}</div>
              </div>
              {a.featured_image&&<img className="sr-thumb" src={a.featured_image} alt="" onError={e=>e.target.style.display='none'}/>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AuthorsPage({setView,go,initAuthorId,onAuthorShown}){
  const [authors,setAuthors]=useState([]);
  const [selected,setSelected]=useState(null);
  const [loading,setLoading]=useState(true);
  useEffect(()=>{
    API.get('/api/authors').then(d=>{
      const list=safe(d);
      setAuthors(list);
      setLoading(false);
      if(initAuthorId){
        const found=list.find(a=>a.id===initAuthorId||a.id===parseInt(initAuthorId));
        if(found){setSelected(found);window.scrollTo(0,0);onAuthorShown&&onAuthorShown();}
      }
    }).catch(()=>setLoading(false));
  },[]);
  if(loading)return <div className="loading">Loading Authors</div>;
  if(selected)return(
    <div className="page">
      <AuthorProfilePage author={selected} onBack={()=>{setSelected(null);window.scrollTo(0,0);}} setView={setView} go={go}/>
    </div>
  );
  return(
    <div className="page">
      <div className="sec-lbl"><span>Contributors</span></div>
      <div className="authors-grid">
        {authors.map(a=>{
          const typeLabel=AUTHOR_TYPES.find(t=>t.value===a.author_type)?.label||'';
          return(
            <div key={a.id} className="au-card" onClick={()=>{setSelected(a);window.scrollTo(0,0);}}>
              <Avatar author={a} size={62}/>
              <div className="au-name" style={{marginTop:'.62rem',fontSize:'1.06rem'}}>{a.name}</div>
              {typeLabel&&<div style={{fontFamily:'var(--fm)',fontSize:'.54rem',letterSpacing:'.1em',textTransform:'uppercase',color:'var(--g500)',marginBottom:'.1rem'}}>{typeLabel}</div>}
              <div className="au-role">{a.role}</div>
              <div className="au-bio" style={{marginTop:'.32rem',fontSize:'.85rem'}}>{(a.bio||'').slice(0,115)}{(a.bio||'').length>115?'…':''}</div>
              <div style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g500)',marginTop:'.52rem'}}>{a.article_count} published {a.article_count===1?'story':'stories'}</div>
            </div>
          );
        })}
        {!authors.length&&<div style={{padding:'2rem',fontStyle:'italic',color:'var(--g500)',gridColumn:'1/-1'}}>No authors yet. Add them in Admin → Authors.</div>}
      </div>
    </div>
  );
}

function SearchPage({query:initQ,setView,go}){
  const [q,setQ]=useState(initQ||'');
  const [sugg,setSugg]=useState([]);
  const [titleOnly,setTitleOnly]=useState(false);
  const [selAuthor,setSelAuthor]=useState('');
  const [selTags,setSelTags]=useState([]);
  const [selCat,setSelCat]=useState('');
  const [locQ,setLocQ]=useState('');
  const [locResults,setLocResults]=useState([]);
  const [locPick,setLocPick]=useState(null); 
  const [radius,setRadius]=useState(50);
  const [results,setResults]=useState([]);
  const [loading,setLoading]=useState(false);
  const [authors,setAuthors]=useState([]);
  const [tags,setTags]=useState([]);
  const [cats,setCats]=useState([]);
  const mapRef=useRef(null);
  const mapInst=useRef(null);
  const circleRef=useRef(null);
  const sugRef=useRef(null);
  const acTimer=useRef(null);
  const acDismissed=useRef(false);

  useEffect(()=>{
    Promise.all([API.get('/api/authors'),API.get('/api/tags'),API.get('/api/categories')])
      .then(([a,t,c])=>{setAuthors(safe(a));setTags(safe(t));setCats(safe(c));}).catch(()=>{});
  },[]);

  useEffect(()=>{
    clearTimeout(acTimer.current);
    acDismissed.current=false; 
    if(!q.trim()||q.length<2){setSugg([]);return;}
    acTimer.current=setTimeout(async()=>{
      const r=await fetch(`https://api.datamuse.com/sug?s=${encodeURIComponent(q)}&max=7`).then(r=>r.json()).catch(()=>[]);
      if(acDismissed.current)return; 
      setSugg(r.map(x=>x.word));
    },260);
  },[q]);

  const dismissSugg=()=>{acDismissed.current=true;clearTimeout(acTimer.current);setSugg([]);};

  useEffect(()=>{
    if(!q.trim()&&!selAuthor&&!selTags.length&&!selCat&&!locPick)return;
    setLoading(true);
    const params=new URLSearchParams({status:'published',limit:'60'});
    if(q.trim())params.set(titleOnly?'title_search':'search',q.trim());
    if(selAuthor)params.set('author_id',selAuthor);
    if(selCat)params.set('category',selCat);
    if(selTags.length)params.set('tag',selTags[0]);
    API.get(`/api/articles?${params}`)
      .then(d=>{
        let res=safe(d);
        if(selTags.length>1)res=res.filter(a=>selTags.every(tid=>safe(a.tags).some(t=>t.id===tid)));
        if(locPick){
          res=res.filter(a=>{
            if(!a.latitude||!a.longitude)return false;
            const R=6371,dL=(a.latitude-locPick.lat)*Math.PI/180,dO=(a.longitude-locPick.lon)*Math.PI/180;
            const x=Math.sin(dL/2)**2+Math.cos(locPick.lat*Math.PI/180)*Math.cos(a.latitude*Math.PI/180)*Math.sin(dO/2)**2;
            return R*2*Math.atan2(Math.sqrt(x),Math.sqrt(1-x))<=radius;
          });
        }
        setResults(res);setLoading(false);
      }).catch(()=>setLoading(false));
  },[q,titleOnly,selAuthor,selTags,selCat,locPick,radius]);

  useEffect(()=>{
    if(!locPick||!mapRef.current)return;
    setTimeout(()=>{
      if(!mapInst.current){
        mapInst.current=L.map(mapRef.current).setView([locPick.lat,locPick.lon],8);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(mapInst.current);
      } else {
        mapInst.current.setView([locPick.lat,locPick.lon],8);
      }
      if(circleRef.current)circleRef.current.remove();
      circleRef.current=L.circle([locPick.lat,locPick.lon],{radius:radius*1000,color:'var(--ink)',fillOpacity:.1}).addTo(mapInst.current);
    },60);
  },[locPick,radius]);

  useEffect(()=>()=>{if(mapInst.current){try{mapInst.current.remove();}catch{}mapInst.current=null;}},[]);

  const searchLoc=async()=>{
    if(!locQ.trim())return;
    const res=await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(locQ)}&format=json&limit=4`,{headers:{'Accept-Language':'en'}}).then(r=>r.json()).catch(()=>[]);
    setLocResults(res);
  };

  const toggleTag=id=>setSelTags(p=>p.includes(id)?p.filter(x=>x!==id):[...p,id]);
  const clearLoc=()=>{setLocPick(null);setLocResults([]);setLocQ('');if(mapInst.current){try{mapInst.current.remove();}catch{}mapInst.current=null;}};

  const hasFilters=q.trim()||selAuthor||selTags.length||selCat||locPick;

  return(
    <div className="adv-search">
      <div className="sec-lbl"><span>Search</span></div>

      <div className="ac-wrap">
        <div style={{display:'flex',gap:'.38rem'}}>
          <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search articles, topics, keywords…"
            onKeyDown={e=>{if(e.key==='Escape'||e.key==='Enter')dismissSugg();}}
            style={{flex:1}} autoFocus/>
          <div style={{display:'flex',alignItems:'center',gap:'.28rem',flexShrink:0}}>
            <label style={{fontFamily:'var(--fm)',fontSize:'.58rem',letterSpacing:'.06em',textTransform:'uppercase',cursor:'pointer',display:'flex',alignItems:'center',gap:'.28rem',whiteSpace:'nowrap',color:'var(--g500)'}}>
              <input type="checkbox" checked={titleOnly} onChange={e=>setTitleOnly(e.target.checked)} style={{width:'auto',border:'none'}}/>Title only
            </label>
          </div>
        </div>
        {sugg.length>0&&(
          <div className="ac-drop" ref={sugRef}>
            {sugg.map((s,i)=>(
              <div key={i} className="ac-item" onClick={()=>{setQ(s);dismissSugg();}}>
                {s}<span className="ac-tag">suggestion</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="adv-search-grid">
        <div className="adv-filters">
          <div className="adv-filter-sec">
            <div className="adv-filter-lbl">Author</div>
            <select value={selAuthor} onChange={e=>setSelAuthor(e.target.value)} style={{width:'100%'}}>
              <option value="">All authors</option>
              {authors.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          <div className="adv-filter-sec">
            <div className="adv-filter-lbl">Section</div>
            <select value={selCat} onChange={e=>setSelCat(e.target.value)} style={{width:'100%'}}>
              <option value="">All sections</option>
              {cats.map(c=><option key={c.id} value={c.slug}>{c.name}</option>)}
            </select>
          </div>
          <div className="adv-filter-sec">
            <div className="adv-filter-lbl">Tags</div>
            <div className="adv-tags">
              {tags.map(t=>(
                <span key={t.id} className={`tag${selTags.includes(t.id)?' on':''}`} onClick={()=>toggleTag(t.id)}>{t.name}</span>
              ))}
            </div>
          </div>
          <div className="adv-filter-sec">
            <div className="adv-filter-lbl">Location Radius</div>
            <div style={{display:'flex',gap:'.32rem',marginBottom:'.38rem'}}>
              <input value={locQ} onChange={e=>setLocQ(e.target.value)} placeholder="Place name…"
                onKeyDown={e=>e.key==='Enter'&&searchLoc()} style={{flex:1}}/>
              <button className="btn-s" onClick={searchLoc}>Find</button>
            </div>
            {locResults.length>0&&(
              <div style={{marginBottom:'.38rem'}}>
                {locResults.map((r,i)=>(
                  <div key={i} className="ac-item" style={{border:'var(--rt)',padding:'.32rem .52rem',cursor:'pointer',fontSize:'.8rem'}}
                    onClick={()=>{setLocPick({lat:parseFloat(r.lat),lon:parseFloat(r.lon),name:r.display_name});setLocResults([]);}}>
                    {r.display_name.slice(0,60)}{r.display_name.length>60?'…':''}
                  </div>
                ))}
              </div>
            )}
            {locPick&&(
              <>
                <div style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g600)',marginBottom:'.28rem',display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                  <span>{locPick.name.slice(0,40)}{locPick.name.length>40?'…':''}</span>
                  <span style={{cursor:'pointer',color:'var(--g400)'}} onClick={clearLoc}>✕</span>
                </div>
                <div style={{display:'flex',alignItems:'center',gap:'.38rem',marginBottom:'.32rem'}}>
                  <input type="range" min="5" max="500" value={radius} onChange={e=>setRadius(Number(e.target.value))} style={{flex:1,width:'auto',border:'none',padding:0}}/>
                  <span style={{fontFamily:'var(--fm)',fontSize:'.62rem',whiteSpace:'nowrap'}}>{radius} km</span>
                </div>
                <div id="adv-search-map" ref={mapRef} className="adv-map"/>
              </>
            )}
            {(selAuthor||selTags.length||selCat||locPick)&&(
              <button className="btn-s" style={{marginTop:'.52rem',width:'100%'}} onClick={()=>{setSelAuthor('');setSelTags([]);setSelCat('');clearLoc();}}>Clear All Filters</button>
            )}
          </div>
        </div>

        <div>
          {hasFilters&&<div className="adv-results-hdr">{loading?'Searching…':`${results.length} result${results.length!==1?'s':''}`}</div>}
          {!hasFilters&&<div style={{fontFamily:'var(--fb)',fontStyle:'italic',color:'var(--g500)',padding:'2rem 0',fontSize:'1rem'}}>Type a search term, pick an author, select tags, or drop a location pin.</div>}
          {results.map(a=>(
            <div key={a.id} className="sr-item" onClick={()=>{go(a);setView('article');}}>
              <div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.55rem',letterSpacing:'.1em',textTransform:'uppercase',color:'var(--g500)',marginBottom:'.17rem'}}>{a.category_name}</div>
                <div style={{fontFamily:'var(--fh)',fontSize:'1.02rem',fontWeight:700,lineHeight:1.3,marginBottom:'.28rem'}}>{a.title}</div>
                <div style={{fontSize:'.87rem',color:'var(--g600)',lineHeight:1.5}}>{a.excerpt||strip(a.content||'').slice(0,200)}</div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.04em',marginTop:'.38rem'}}>{a.author_name} · {fmtDate(a.published_at)}</div>
              </div>
              {a.featured_image&&<img className="sr-thumb" src={a.featured_image} alt="" onError={e=>e.target.style.display='none'}/>}
            </div>
          ))}
          {hasFilters&&!loading&&!results.length&&<div className="empty"><div className="empty-icon">⌕</div><div className="empty-title">Nothing found</div><div className="empty-sub">Adjust your filters or try different keywords</div></div>}
        </div>
      </div>
    </div>
  );
}

function MyProfilePage({currentUser,toast,setView}){
  const [profile,setProfile]=useState(null);
  const [history,setHistory]=useState([]);
  const [pStats,setPStats]=useState([]);
  const [pwForm,setPwForm]=useState({password:'',confirm:''});
  const [email,setEmail]=useState('');
  const [saving,setSaving]=useState(false);
  const [tab,setTab]=useState('history');

  useEffect(()=>{
    if(!currentUser)return;
    API.get('/api/reader/profile').then(d=>{ setProfile(d); setEmail(d.email||''); }).catch(()=>{});
    API.get('/api/reader/history').then(d=>setHistory(safe(d))).catch(()=>{});
    API.get('/api/reader/puzzle-stats').then(d=>setPStats(safe(d))).catch(()=>{});
  },[currentUser]);

  if(!currentUser)return(
    <div className="reader-page">
      <div className="empty"><div className="empty-icon">⊕</div><div className="empty-title">Not signed in</div><div className="empty-sub">Sign in or create a reader account to track your history</div></div>
    </div>
  );

  const sdkCount=pStats.filter(p=>p.puzzle_type==='sudoku').length;
  const cwCount=pStats.filter(p=>p.puzzle_type==='crossword').length;

  return(
    <div className="reader-page">
      <div className="rp-hero">
        <div className="rp-av">{initials(profile?.username||currentUser.username)}</div>
        <div>
          <div className="rp-role">{currentUser.role}</div>
          <div style={{fontFamily:'var(--fh)',fontSize:'1.55rem',fontWeight:900}}>{profile?.username||currentUser.username}</div>
          {profile?.email&&<div style={{fontFamily:'var(--fm)',fontSize:'.65rem',color:'var(--g500)',marginTop:'.15rem'}}>{profile.email}</div>}
          {profile?.created_at&&<div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g400)',marginTop:'.1rem'}}>Member since {fmtDate(profile.created_at)}</div>}
        </div>
      </div>

      <div className="rp-stats">
        {[['Articles Read',profile?.article_count||0],['Sudoku Solved',sdkCount],['Crosswords Solved',cwCount]].map(([l,n])=>(
          <div key={l} className="rp-stat"><div className="rp-stat-n">{n}</div><div className="rp-stat-l">{l}</div></div>
        ))}
      </div>

      <div style={{display:'flex',borderBottom:'var(--rule)',marginBottom:'1.35rem'}}>
        {[['history','Reading History'],['puzzles','Puzzle History'],['settings','Settings']].map(([id,lbl])=>(
          <div key={id} className={`a-tab${tab===id?' on':''}`} onClick={()=>setTab(id)}>{lbl}</div>
        ))}
      </div>

      {tab==='history'&&(
        <div>
          {!history.length&&<div className="empty"><div className="empty-title">No reading history yet</div><div className="empty-sub">Articles you open will appear here</div></div>}
          {history.map(a=>(
            <div key={a.id} className="sr-item" style={{cursor:'pointer'}}>
              <div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.54rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:'.15rem'}}>
                  {a.category_name} · Read {fmtDate(a.read_at)}{a.read_count>1?` · ${a.read_count}×`:''}
                </div>
                <div style={{fontFamily:'var(--fh)',fontSize:'1rem',fontWeight:700,lineHeight:1.3}}>{a.title}</div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g500)',marginTop:'.15rem'}}>{a.author_name} · {a.reading_time} min read</div>
              </div>
              {a.featured_image&&<img className="sr-thumb" src={a.featured_image} alt="" onError={e=>e.target.style.display='none'}/>}
            </div>
          ))}
        </div>
      )}

      {tab==='puzzles'&&(
        <div>
          {!pStats.length&&<div className="empty"><div className="empty-title">No puzzle completions yet</div><div className="empty-sub">Solve a sudoku or crossword to see your stats here</div></div>}
          {pStats.length>0&&(
            <table className="art-tbl">
              <thead><tr><th>Puzzle</th><th>Date</th><th>Difficulty</th><th>Time</th><th>Completed</th></tr></thead>
              <tbody>
                {pStats.map((p,i)=>(
                  <tr key={i}>
                    <td style={{fontFamily:'var(--fh)',fontWeight:600,textTransform:'capitalize'}}>{p.puzzle_type}</td>
                    <td style={{fontFamily:'var(--fm)',fontSize:'.68rem'}}>{p.puzzle_date}</td>
                    <td style={{fontFamily:'var(--fm)',fontSize:'.65rem',textTransform:'capitalize'}}>{p.difficulty||'—'}</td>
                    <td style={{fontFamily:'var(--fm)',fontSize:'.65rem'}}>{fmtMin(p.elapsed)}</td>
                    <td style={{fontFamily:'var(--fm)',fontSize:'.65rem'}}>{fmtShort(p.completed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab==='settings'&&(
        <div>
          <div style={{padding:'1.35rem',border:'var(--rt)',background:'var(--g100)',marginBottom:'1.35rem'}}>
            <div className="form-lbl" style={{marginBottom:'.72rem',fontSize:'.65rem'}}>Update Email</div>
            <FormField label="Email Address"><input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="your@email.com"/></FormField>
            <button className="btn-p" disabled={saving} onClick={async()=>{
              setSaving(true);
              const r=await API.put('/api/reader/profile',{email}).catch(()=>({error:'Failed'}));
              setSaving(false);
              if(r.error)toast(r.error,'err');else toast('Email updated.');
            }}>Save Email</button>
          </div>
          <div style={{padding:'1.35rem',border:'var(--rt)',background:'var(--g100)'}}>
            <div className="form-lbl" style={{marginBottom:'.72rem',fontSize:'.65rem'}}>Change Password</div>
            <FormField label="New Password"><input type="password" value={pwForm.password} onChange={e=>setPwForm(p=>({...p,password:e.target.value}))}/></FormField>
            <FormField label="Confirm Password"><input type="password" value={pwForm.confirm} onChange={e=>setPwForm(p=>({...p,confirm:e.target.value}))}/></FormField>
            <button className="btn-p" disabled={saving} onClick={async()=>{
              if(pwForm.password!==pwForm.confirm){toast('Passwords do not match','err');return;}
              if(pwForm.password.length<6){toast('Min 6 characters','err');return;}
              setSaving(true);
              const r=await API.put('/api/reader/profile',{password:pwForm.password}).catch(()=>({error:'Failed'}));
              setSaving(false);
              if(r.error)toast(r.error,'err');else{toast('Password updated.');setPwForm({password:'',confirm:''});}
            }}>Change Password</button>
          </div>
        </div>
      )}
    </div>
  );
}

