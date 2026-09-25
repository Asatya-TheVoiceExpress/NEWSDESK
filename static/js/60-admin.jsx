function AdminPanel({setView,go,currentUser}){
  const [tab,setTab]=useState('articles');
  const [articles,setArticles]=useState([]);
  const [authors,setAuthors]=useState([]);
  const [categories,setCategories]=useState([]);
  const [allSections,setAllSections]=useState([]);
  const [tags,setTags]=useState([]);
  const [series,setSeries]=useState([]);
  const [users,setUsers]=useState([]);
  const [editing,setEditing]=useState(null);
  const [artSearch,setArtSearch]=useState('');
  const [artStatus,setArtStatus]=useState('all');
  const [needsFilter,setNeedsFilter]=useState('');
  const [selected,setSelected]=useState(()=>new Set());
  const [sortBy,setSortBy]=useState('date');
  const [bulkBusy,setBulkBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [msg,setMsg]=useState(null);
  const [stats,setStats]=useState({});
  const [confirm,setConfirm]=useState(null);
  const [newAu,setNewAu]=useState({name:'',email:'',bio:'',role:'',author_type:'reporter',social_twitter:'',avatar_url:''});
  const [editAu,setEditAu]=useState(null);
  const [linksAuId,setLinksAuId]=useState(null);
  const [auLinksMap,setAuLinksMap]=useState({});
  const [newLink,setNewLink]=useState({title:'',url:'',link_type:'web'});
  const [newCat,setNewCat]=useState({name:'',description:''});
  const [newTag,setNewTag]=useState('');
  const [tagFilter,setTagFilter]=useState('');
  const [mergeSrc,setMergeSrc]=useState(null);
  const [newSeries,setNewSeries]=useState({title:'',description:''});
  const [editingSeries,setEditingSeries]=useState(null);
  const [newUser,setNewUser]=useState({username:'',password:'',role:'author',author_id:''});
  const auAvatarRef=useRef(null);
  const toast=(m,t='ok')=>setMsg({m,t});

  const load=async()=>{
    setLoading(true);
    const [arts,aus,cats,sects,tgs,st,ser,usrs]=await Promise.all([
      API.get('/api/articles?status=all&limit=100').catch(()=>[]),
      API.get('/api/authors').catch(()=>[]),
      API.get('/api/categories').catch(()=>[]),
      API.get('/api/sections').catch(()=>[]),
      API.get('/api/tags').catch(()=>[]),
      API.get('/api/stats').catch(()=>({})),
      API.get('/api/series').catch(()=>[]),
      currentUser?.role==='admin'?API.get('/api/auth/users').catch(()=>[]):Promise.resolve([]),
    ]);
    setArticles(safe(arts));setAuthors(safe(aus));setCategories(safe(cats));
    setAllSections(safe(sects));
    setTags(safe(tgs));setStats(st||{});setSeries(safe(ser));
    if(Array.isArray(usrs)&&usrs.length)setUsers(usrs);
    setLoading(false);
  };
  useEffect(()=>{load();},[]);

  const delArt=async id=>{
    const r=await API.del(`/api/articles/${id}`).catch(()=>({error:'Network error'}));
    if(r.error)toast(r.error,'err');
    else{toast('Article deleted.');load();}
  };

  const toggleSel=id=>setSelected(s=>{const n=new Set(s);n.has(id)?n.delete(id):n.add(id);return n;});
  const selectMany=ids=>setSelected(s=>{const all=ids.every(i=>s.has(i));return new Set(all?[]:ids);});
  const clearSel=()=>setSelected(new Set());
  const setRowStatus=async(id,status)=>{
    const r=await API.put(`/api/articles/${id}`,{status,version_message:status==='published'?'published':'unpublished'}).catch(()=>({error:'Network error'}));
    if(r&&r.error)toast(r.error,'err'); else{toast(status==='published'?'Published.':'Moved to draft.');load();}
  };
  const runBulk=async(fn,label)=>{
    const ids=[...selected]; if(!ids.length)return;
    setBulkBusy(true);
    let ok=0,err=0;
    for(const id of ids){ try{ const r=await fn(id); if(r&&r.error)err++; else ok++; }catch{err++;} }
    setBulkBusy(false); clearSel(); load();
    toast(`${label}: ${ok} done${err?`, ${err} failed`:''}`, err?'err':'ok');
  };
  const bulkStatus=status=>runBulk(id=>API.put(`/api/articles/${id}`,{status,version_message:'bulk '+status}),status==='published'?'Published':'Moved to draft');
  const bulkSection=sid=>runBulk(id=>API.put(`/api/articles/${id}`,{section_id:sid,version_message:'bulk section'}),'Section set');
  const bulkCategory=cid=>runBulk(id=>API.put(`/api/articles/${id}`,{category_id:cid,version_message:'bulk category'}),'Category set');
  const bulkAddTag=tid=>runBulk(id=>{
    const a=articles.find(x=>x.id===id); const cur=safe(a&&a.tags).map(t=>t.id);
    const next=cur.includes(+tid)?cur:[...cur,+tid];
    return API.put(`/api/articles/${id}`,{tag_ids:next,version_message:'bulk tag'});
  },'Tag added');
  const bulkDelete=()=>setConfirm({msg:`Delete ${selected.size} article(s)? This cannot be undone.`,act:()=>runBulk(id=>API.del(`/api/articles/${id}`),'Deleted')});

  const renameTag=async t=>{const nn=(prompt('Rename tag',t.name)||'').trim();if(!nn||nn===t.name)return;const r=await API.put(`/api/tags/${t.id}`,{name:nn}).catch(()=>({error:'Failed'}));if(r.error)toast(r.error,'err');else{toast('Tag renamed.');load();}};
  const mergeTagInto=async target=>{if(!mergeSrc||mergeSrc===target.id)return;const r=await API.post(`/api/tags/${mergeSrc}/merge`,{into:target.id}).catch(()=>({error:'Failed'}));setMergeSrc(null);if(r.error)toast(r.error,'err');else{toast('Tags merged.');load();}};
  const renameCat=async c=>{const nn=(prompt('Rename category',c.name)||'').trim();if(!nn||nn===c.name)return;const r=await API.put(`/api/categories/${c.id}`,{name:nn,description:c.description||''}).catch(()=>({error:'Failed'}));if(r.error)toast(r.error,'err');else{toast('Category renamed.');load();}};
  const mergeCat=async(c,into)=>{const r=await API.post(`/api/categories/${c.id}/merge`,{into}).catch(()=>({error:'Failed'}));if(r.error)toast(r.error,'err');else{toast('Categories merged.');load();}};

  const openEdit=async a=>{
    const full=await API.get(`/api/articles/${a.id}`).catch(()=>null);
    setEditing(full&&!full.error?full:a);
  };

  if(editing!==null){
    return(
      <div className="admin-page">
        <ArticleEditor
          article={editing===true?null:editing}
          authors={authors} categories={categories} allSections={allSections} tags={tags} allSeries={series}
          toast={toast}
          onSave={()=>{setEditing(null);load();}}
          onCancel={()=>setEditing(null)}/>
        {msg&&<Toast msg={msg.m} type={msg.t} onDone={()=>setMsg(null)}/>}
      </div>
    );
  }

  if(!currentUser||currentUser.role==='reader'){
    return(
      <div className="admin-page">
        <div className="empty" style={{paddingTop:'4rem'}}>
          <div className="empty-icon">✦</div>
          <div className="empty-title">Editorial Desk</div>
          <div className="empty-sub">Staff access required. Sign in with an editor or admin account to continue.</div>
        </div>
      </div>
    );
  }

  return(
    <div className="admin-page">
      {msg&&<Toast msg={msg.m} type={msg.t} onDone={()=>setMsg(null)}/>}
      {confirm&&(
        <div className="modal-overlay" onClick={()=>setConfirm(null)}>
          <div className="modal" onClick={e=>e.stopPropagation()}>
            <div className="modal-hdr"><span className="modal-title">Confirm</span><span className="modal-close" onClick={()=>setConfirm(null)}>✕</span></div>
            <div className="modal-body"><p style={{fontSize:'1rem',lineHeight:1.6}}>{confirm.msg}</p></div>
            <div className="modal-foot">
              <button className="btn-o" onClick={()=>setConfirm(null)}>Cancel</button>
              <button className="btn-p" onClick={()=>{confirm.act();setConfirm(null);}}>Confirm</button>
            </div>
          </div>
        </div>
      )}

      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:'1.35rem',flexWrap:'wrap',gap:'1rem'}}>
        <div>
          <div style={{fontFamily:'var(--fh)',fontSize:'2rem',fontWeight:900}}>Editorial Desk</div>
          <div style={{fontFamily:'var(--fm)',fontSize:'.59rem',color:'var(--g500)',letterSpacing:'.1em',textTransform:'uppercase',marginTop:'.14rem'}}>Voice Express — Content Management</div>
        </div>
        <div style={{display:'flex',gap:'.32rem',flexWrap:'wrap'}}>
          <button className="btn-p" onClick={()=>setEditing(true)}>+ New Article</button>
        </div>
      </div>

      <div className="stats-grid">
        {[['Published',stats.articles||0],['Drafts',stats.drafts||0],['Authors',stats.authors||0],['Sections',stats.categories||0],['Tags',stats.tags||0],['Geotagged',stats.geotagged||0],['Annotations',stats.annotations||0]].map(([l,n])=>(
          <div key={l} className="stat-box"><div className="stat-num">{n}</div><div className="stat-lbl">{l}</div></div>
        ))}
      </div>

      {(()=>{
        const Q=[
          ['Drafts to finish',a=>a.status==='draft','draft-status'],
          ['No abstract',a=>!(a.excerpt||'').trim(),'no-abstract'],
          ['No SEO',a=>!(a.seo_description||'').trim(),'no-seo'],
          ['Untagged',a=>!(a.tags||[]).length,'untagged'],
          ['No cover image',a=>!(a.featured_image||'').trim(),'no-image'],
          ['No beat',a=>!a.section_id,'no-section'],
        ];
        const counts=Q.map(([l,fn,key])=>[l,articles.filter(fn).length,key]).filter(c=>c[1]>0);
        if(!counts.length) return null;
        return (
          <div className="needs-panel">
            <div className="needs-lbl">Needs attention</div>
            <div className="needs-chips">
              {counts.map(([l,n,key])=>(
                <button key={key} className="needs-chip" onClick={()=>{
                  if(key==='draft-status'){setArtStatus('draft');setNeedsFilter('');}
                  else{setArtStatus('all');setNeedsFilter(key);}
                  setTab('articles');
                }}><span className="needs-n">{n}</span> {l}</button>
              ))}
            </div>
          </div>
        );
      })()}

      <div className="desk-shell">
        <nav className="desk-rail">
          {[
            ['Newsroom',[['articles','Writing Desk'],['series','Series'],['pages','Pages']]],
            ['Periodicals',[['columns','Column Studio']]],
            ['Distribution',[['newsletter','Newsletter']]],
            ['Audience',[['comments','Comments'],['mailbox','Mailbox'],['sheet-data','Sheet Data']]],
            ['Insights',[['analytics','Analytics']]],
            ['Taxonomy & People',[['authors','Authors'],['categories','Categories'],['tags','Tags'],...(currentUser?.role==='admin'?[['users','Users']]:[])]],
          ].map(([grp,items])=>(
            <div key={grp} className="desk-rail-group">
              <div className="desk-rail-lbl">{grp}</div>
              {items.map(([id,lbl])=>(
                <div key={id} className={`desk-rail-item${tab===id?' on':''}`} onClick={()=>setTab(id)}>{lbl}</div>
              ))}
            </div>
          ))}
        </nav>
        <div className="desk-main">

      {loading?<div className="loading">Loading</div>:<>

        {tab==='analytics'&&<AdminAnalytics/>}

        {tab==='pages'&&<AdminPages toast={showToast}/>}

        {tab==='series'&&(
          <div>
                        <div style={{padding:'1.35rem',border:'var(--rt)',background:'var(--g100)',marginBottom:'1.85rem'}}>
              <div className="form-lbl" style={{marginBottom:'.9rem',fontSize:'.65rem'}}>
                {editingSeries?`Editing: ${editingSeries.title}`:'Add New Series'}
              </div>
              <div className="form-row">
                <FormLabel label="Series Title *">
                  <input value={editingSeries?editingSeries.title:newSeries.title}
                    onChange={e=>editingSeries?setEditingSeries(p=>({...p,title:e.target.value})):setNewSeries(p=>({...p,title:e.target.value}))}
                    placeholder="e.g. The Climate Files"/>
                </FormLabel>
                <FormLabel label="Description">
                  <input value={editingSeries?editingSeries.description||'':newSeries.description}
                    onChange={e=>editingSeries?setEditingSeries(p=>({...p,description:e.target.value})):setNewSeries(p=>({...p,description:e.target.value}))}
                    placeholder="Brief description of the series"/>
                </FormLabel>
              </div>
              <div style={{display:'flex',gap:'.38rem'}}>
                {editingSeries?(
                  <>
                    <button className="btn-p" onClick={async()=>{
                      if(!editingSeries.title.trim()){toast('Title required','err');return;}
                      const r=await API.put(`/api/series/${editingSeries.id}`,editingSeries).catch(()=>({error:'Failed'}));
                      if(r.error)toast(r.error,'err');
                      else{toast('Series updated.');setEditingSeries(null);load();}
                    }}>Save Changes</button>
                    <button className="btn-o" onClick={()=>setEditingSeries(null)}>Cancel</button>
                  </>
                ):(
                  <button className="btn-p" onClick={async()=>{
                    if(!newSeries.title.trim()){toast('Title required','err');return;}
                    const r=await API.post('/api/series',newSeries).catch(()=>({error:'Failed'}));
                    if(r.error)toast(r.error,'err');
                    else{toast('Series created.');setNewSeries({title:'',description:''});load();}
                  }}>Create Series</button>
                )}
              </div>
            </div>

                        {series.length===0&&(
              <div className="empty" style={{padding:'2.5rem 0'}}>
                <div className="empty-icon">¶</div>
                <div className="empty-title">No series yet</div>
                <div className="empty-sub">Create your first series above to group related articles</div>
              </div>
            )}
            {series.map(s=>(
              <div key={s.id} style={{padding:'1rem 1.1rem',border:'var(--rt)',marginBottom:'2px',display:'flex',justifyContent:'space-between',alignItems:'center',gap:'1rem',background:'var(--paper)'}}>
                <div style={{flex:1}}>
                  <div style={{fontFamily:'var(--fh)',fontSize:'1.02rem',fontWeight:700,marginBottom:'.15rem'}}>{s.title}</div>
                  {s.description&&<div style={{fontFamily:'var(--fb)',fontSize:'.85rem',color:'var(--g600)',lineHeight:1.5}}>{s.description}</div>}
                  <div style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.04em',marginTop:'.22rem'}}>{s.article_count||0} {(s.article_count||0)===1?'article':'articles'}</div>
                </div>
                <div style={{display:'flex',gap:'.32rem',flexShrink:0}}>
                  <button className="btn-s" onClick={()=>setEditingSeries({...s})}>Edit</button>
                  <button className="btn-s" onClick={()=>setConfirm({msg:`Delete series "${s.title}"? Articles won't be deleted — they will just be removed from the series.`,act:async()=>{await API.del(`/api/series/${s.id}`);load();}})}>✕</button>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab==='articles'&&(()=>{
          const NEEDS={
            'no-abstract':a=>!(a.excerpt||'').trim(),
            'no-seo':a=>!(a.seo_description||'').trim(),
            'untagged':a=>!(a.tags||[]).length,
            'no-image':a=>!(a.featured_image||'').trim(),
            'no-section':a=>!a.section_id,
          };
          const filteredArts=articles.filter(a=>
            (artStatus==='all'||a.status===artStatus)&&
            (!needsFilter||(NEEDS[needsFilter]&&NEEDS[needsFilter](a)))&&
            (!artSearch||(a.title||'').toLowerCase().includes(artSearch.toLowerCase())||(a.author_name||'').toLowerCase().includes(artSearch.toLowerCase()))
          );
          const sorted=[...filteredArts].sort((a,b)=>{
            if(sortBy==='title')return (a.title||'').localeCompare(b.title||'');
            if(sortBy==='status')return (a.status||'').localeCompare(b.status||'')||((b.published_at||'').localeCompare(a.published_at||''));
            return (b.published_at||'').localeCompare(a.published_at||'');
          });
          const pageIds=sorted.map(a=>a.id);
          const allChecked=pageIds.length>0&&pageIds.every(i=>selected.has(i));
          const selOpt=(label,opts,fn)=>(
            <select defaultValue="" disabled={bulkBusy} onChange={e=>{if(e.target.value){fn(e.target.value);e.target.value='';}}}
              style={{fontFamily:'var(--fm)',fontSize:'.58rem',width:'auto',padding:'.2rem .4rem'}}>
              <option value="">{label}</option>{opts.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          );
          return (
          <div style={{overflowX:'auto'}}>
            <div style={{display:'flex',gap:'.4rem',alignItems:'center',marginBottom:'1rem',flexWrap:'wrap'}}>
              <input value={artSearch} onChange={e=>setArtSearch(e.target.value)} placeholder="Search headlines or authors…" style={{flex:1,minWidth:200}}/>
              {[['all','All'],['published','Published'],['draft','Drafts']].map(([v,l])=>(
                <button key={v} className={`btn-s${artStatus===v?' on':''}`} onClick={()=>{setArtStatus(v);clearSel();}}>{l}</button>
              ))}
              {needsFilter&&<button className="btn-s on" onClick={()=>{setNeedsFilter('');clearSel();}} title="Clear needs-attention filter">needs: {needsFilter.replace('no-','no ')} ✕</button>}
              <select value={sortBy} onChange={e=>setSortBy(e.target.value)} title="Sort" style={{fontFamily:'var(--fm)',fontSize:'.58rem',width:'auto',padding:'.2rem .4rem'}}>
                <option value="date">Newest first</option><option value="title">Title A–Z</option><option value="status">By status</option>
              </select>
              <span style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',letterSpacing:'.06em',whiteSpace:'nowrap'}}>{sorted.length} of {articles.length}</span>
            </div>
            {selected.size>0&&(
              <div className="bulk-bar">
                <span className="bulk-n">{selected.size} selected</span>
                <button className="btn-s" disabled={bulkBusy} onClick={()=>bulkStatus('published')}>Publish</button>
                <button className="btn-s" disabled={bulkBusy} onClick={()=>bulkStatus('draft')}>To draft</button>
                {selOpt('Set beat…',allSections,bulkSection)}
                {selOpt('Set category…',categories,bulkCategory)}
                {selOpt('Add tag…',tags,bulkAddTag)}
                <button className="btn-s" disabled={bulkBusy} onClick={bulkDelete} style={{color:'var(--err,#b00)'}}>Delete</button>
                <button className="btn-s" disabled={bulkBusy} onClick={clearSel} style={{marginLeft:'auto'}}>Clear</button>
              </div>
            )}
            <table className="art-tbl">
              <thead><tr>
                <th style={{width:28}}><input type="checkbox" checked={allChecked} onChange={()=>selectMany(pageIds)} style={{width:'auto',border:'none'}} title="Select all"/></th>
                <th>Headline</th><th>Author</th><th>Section</th><th>Status</th><th>Date</th><th>Actions</th>
              </tr></thead>
              <tbody>
                {sorted.map(a=>(
                  <tr key={a.id} className={selected.has(a.id)?'sel':''}>
                    <td><input type="checkbox" checked={selected.has(a.id)} onChange={()=>toggleSel(a.id)} style={{width:'auto',border:'none'}}/></td>
                    <td style={{fontFamily:'var(--fh)',fontWeight:600,maxWidth:240,wordBreak:'break-word',lineHeight:1.3}}>{a.title}</td>
                    <td style={{fontFamily:'var(--fm)',fontSize:'.68rem',whiteSpace:'nowrap'}}>{a.author_name||'—'}</td>
                    <td style={{fontFamily:'var(--fm)',fontSize:'.65rem'}}>{a.category_name||'—'}</td>
                    <td><span className={`s-badge ${a.status}`}>{a.status}</span></td>
                    <td style={{fontFamily:'var(--fm)',fontSize:'.65rem',whiteSpace:'nowrap'}}>{fmtShort(a.published_at)||'—'}</td>
                    <td>
                      <div style={{display:'flex',gap:'.26rem',flexWrap:'wrap'}}>
                        <button className="btn-s" onClick={()=>{go(a);setView('article');}}>View</button>
                        <button className="btn-s" onClick={()=>openEdit(a)}>Edit</button>
                        {a.status==='published'
                          ?<button className="btn-s" title="Move to draft" onClick={()=>setRowStatus(a.id,'draft')}>Unpublish</button>
                          :<button className="btn-s" title="Publish now" onClick={()=>setRowStatus(a.id,'published')}>Publish</button>}
                        <button className="btn-s" onClick={()=>setConfirm({msg:`Delete "${a.title.slice(0,55)}"? This cannot be undone.`,act:()=>delArt(a.id)})}>✕</button>
                        {window.DesignDashboard&&<button className="btn-s" title="Custom PDF design: preview, custom CSS, screenshot-verify" onClick={()=>window.DesignDashboard.showModal('article',a.id,`Design Editor: ${a.title.slice(0,40)}`)}>🎨 Design</button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!articles.length&&(
              <div className="empty">
                <div className="empty-icon">¶</div>
                <div className="empty-title">No articles yet</div>
                <div style={{display:'flex',gap:'.45rem',justifyContent:'center',marginTop:'1rem',flexWrap:'wrap'}}>
                  <button className="btn-p" onClick={()=>setEditing(true)}>Write first story</button>
                </div>
              </div>
            )}
            {articles.length>0&&!filteredArts.length&&(
              <div className="empty" style={{padding:'2rem 0'}}><div className="empty-title">No articles match</div><div className="empty-sub">Try a different search or status filter</div></div>
            )}
          </div>
          );
        })()}

        {tab==='authors'&&(
          <div>
                        <div style={{padding:'1.35rem',border:'var(--rt)',background:'var(--g100)',marginBottom:'1.85rem'}}>
              <div className="form-lbl" style={{marginBottom:'.9rem',fontSize:'.65rem'}}>Add New Author</div>
              <div className="form-row">
                <FormLabel label="Full Name *"><input value={newAu.name} onChange={e=>setNewAu(p=>({...p,name:e.target.value}))} placeholder="Full name"/></FormLabel>
                <FormLabel label="Email"><input type="email" value={newAu.email} onChange={e=>setNewAu(p=>({...p,email:e.target.value}))} placeholder="email@voiceexpress.com"/></FormLabel>
              </div>
              <div className="form-row">
                <FormLabel label="Role / Title"><input value={newAu.role} onChange={e=>setNewAu(p=>({...p,role:e.target.value}))} placeholder="Senior Correspondent"/></FormLabel>
                <FormLabel label="Author Type">
                  <select value={newAu.author_type} onChange={e=>setNewAu(p=>({...p,author_type:e.target.value}))}>
                    {AUTHOR_TYPES.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </FormLabel>
              </div>
              <div className="form-row">
                <FormLabel label="Twitter / X"><input value={newAu.social_twitter} onChange={e=>setNewAu(p=>({...p,social_twitter:e.target.value}))} placeholder="@handle"/></FormLabel>
                <FormLabel label="Avatar">
                  <div style={{display:'flex',gap:'.32rem'}}>
                    <input value={newAu.avatar_url} onChange={e=>setNewAu(p=>({...p,avatar_url:e.target.value}))} placeholder="URL or →"/>
                    <input type="file" accept="image/*" style={{display:'none'}} ref={auAvatarRef} onChange={async e=>{
                      const f=e.target.files?.[0];if(!f)return;
                      const fd=new FormData();fd.append('file',f);
                      const r=await API.upload('/api/upload',fd).catch(()=>({}));
                      if(r.url)setNewAu(p=>({...p,avatar_url:r.url}));
                      e.target.value='';
                    }}/>
                    <button className="btn-s" style={{flexShrink:0}} onClick={()=>auAvatarRef.current?.click()}>Upload</button>
                  </div>
                  {newAu.avatar_url&&<img src={newAu.avatar_url} alt="" style={{width:44,height:44,borderRadius:'50%',objectFit:'cover',marginTop:'.32rem',border:'var(--rt)'}} onError={e=>e.target.style.display='none'}/>}
                </FormLabel>
              </div>
              <FormLabel label="Biography"><textarea value={newAu.bio} onChange={e=>setNewAu(p=>({...p,bio:e.target.value}))} placeholder="Author biography…" style={{minHeight:65}}/></FormLabel>
              <button className="btn-p" onClick={async()=>{
                if(!newAu.name.trim()){toast('Name is required','err');return;}
                const r=await API.post('/api/authors',newAu).catch(()=>({error:'Failed'}));
                if(r.error)toast(r.error,'err');
                else{toast('Author added.');setNewAu({name:'',email:'',bio:'',role:'',author_type:'reporter',social_twitter:'',avatar_url:''});load();}
              }}>Add Author</button>
            </div>

                        {authors.map(a=>(
              <div key={a.id} style={{border:'var(--rt)',marginBottom:'2px',background:'var(--paper)'}}>
                <div style={{display:'flex',alignItems:'center',gap:'.85rem',padding:'.72rem 1rem'}}>
                  <Avatar author={a} size={44}/>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{fontFamily:'var(--fh)',fontWeight:700,fontSize:'.97rem'}}>{a.name}</div>
                    <div style={{fontFamily:'var(--fm)',fontSize:'.55rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.04em'}}>
                      {AUTHOR_TYPES.find(t=>t.value===a.author_type)?.label||a.author_type||''}{a.role?` · ${a.role}`:''}
                    </div>
                  </div>
                  <div style={{display:'flex',gap:'.25rem',flexShrink:0,flexWrap:'wrap'}}>
                    <button className="btn-s" onClick={()=>{setEditAu(editAu?.id===a.id?null:{...a});setLinksAuId(null);}}>{editAu?.id===a.id?'Cancel':'Edit'}</button>
                    <button className="btn-s" onClick={async()=>{
                      if(linksAuId===a.id){setLinksAuId(null);return;}
                      setLinksAuId(a.id);setEditAu(null);
                      if(!auLinksMap[a.id]){
                        const ls=await API.get(`/api/authors/${a.id}/links`).catch(()=>[]);
                        setAuLinksMap(p=>({...p,[a.id]:safe(ls)}));
                      }
                    }}>Links{auLinksMap[a.id]?.length>0?` (${auLinksMap[a.id].length})`:''}</button>
                    <button className="btn-s" onClick={()=>setConfirm({msg:`Delete "${a.name}"?`,act:async()=>{await API.del(`/api/authors/${a.id}`);load();}})}>✕</button>
                  </div>
                </div>

                                {editAu?.id===a.id&&(
                  <div style={{padding:'1rem 1.1rem',background:'var(--g100)',borderTop:'1px solid var(--g300)'}}>
                    <div className="form-row">
                      <div className="form-g"><label className="form-lbl">Name</label><input value={editAu.name||''} onChange={e=>setEditAu(p=>({...p,name:e.target.value}))}/></div>
                      <div className="form-g"><label className="form-lbl">Email</label><input value={editAu.email||''} onChange={e=>setEditAu(p=>({...p,email:e.target.value}))}/></div>
                    </div>
                    <div className="form-row">
                      <div className="form-g"><label className="form-lbl">Role / Title</label><input value={editAu.role||''} onChange={e=>setEditAu(p=>({...p,role:e.target.value}))}/></div>
                      <div className="form-g"><label className="form-lbl">Author Type</label>
                        <select value={editAu.author_type||'reporter'} onChange={e=>setEditAu(p=>({...p,author_type:e.target.value}))}>
                          {AUTHOR_TYPES.map(t=><option key={t.value} value={t.value}>{t.label}</option>)}
                        </select>
                      </div>
                    </div>
                    <div className="form-row">
                      <div className="form-g"><label className="form-lbl">Twitter / X</label><input value={editAu.social_twitter||''} onChange={e=>setEditAu(p=>({...p,social_twitter:e.target.value}))}/></div>
                      <div className="form-g"><label className="form-lbl">Avatar</label>
                        <div style={{display:'flex',gap:'.32rem'}}>
                          <input value={editAu.avatar_url||''} onChange={e=>setEditAu(p=>({...p,avatar_url:e.target.value}))} placeholder="URL or upload"/>
                          <button className="btn-s" style={{flexShrink:0}} onClick={()=>{
                            const inp=document.createElement('input');inp.type='file';inp.accept='image/*';
                            inp.onchange=async()=>{const f=inp.files?.[0];if(!f)return;const fd=new FormData();fd.append('file',f);const r=await API.upload('/api/upload',fd).catch(()=>({}));if(r.url)setEditAu(p=>({...p,avatar_url:r.url}));};
                            inp.click();
                          }}>Upload</button>
                        </div>
                        {editAu.avatar_url&&<img src={editAu.avatar_url} alt="" style={{width:44,height:44,borderRadius:'50%',objectFit:'cover',marginTop:'.28rem',border:'var(--rt)'}} onError={e=>e.target.style.display='none'}/>}
                      </div>
                    </div>
                    <div className="form-g"><label className="form-lbl">Biography</label><textarea value={editAu.bio||''} onChange={e=>setEditAu(p=>({...p,bio:e.target.value}))} style={{minHeight:60}}/></div>
                    <button className="btn-p" onClick={async()=>{
                      const r=await API.put(`/api/authors/${editAu.id}`,editAu).catch(()=>({error:'Failed'}));
                      if(r.error)toast(r.error,'err');
                      else{toast('Author updated.');setEditAu(null);load();}
                    }}>Save Changes</button>
                  </div>
                )}

                                {linksAuId===a.id&&(
                  <div style={{padding:'1rem 1.1rem',background:'var(--paper)',borderTop:'1px solid var(--g300)'}}>
                    <div className="form-lbl" style={{marginBottom:'.72rem'}}>Link Store — {a.name}</div>
                    {(auLinksMap[a.id]||[]).map(l=>(
                      <div key={l.id} style={{display:'flex',alignItems:'center',gap:'.5rem',padding:'.38rem .68rem',background:'var(--g100)',marginBottom:'2px'}}>
                        <span style={{width:22,textAlign:'center',flexShrink:0}}>{LINK_TYPES[l.link_type]?.icon||'↗'}</span>
                        <span style={{flex:1,fontSize:'.85rem',fontFamily:'var(--fb)'}}>{l.title}</span>
                        <a href={l.url} target="_blank" rel="noopener noreferrer" style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',flex:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{l.url}</a>
                        <button className="btn-s" style={{padding:'.1rem .35rem',flexShrink:0}} onClick={async()=>{
                          await API.del(`/api/authors/links/${l.id}`);
                          setAuLinksMap(p=>({...p,[a.id]:(p[a.id]||[]).filter(x=>x.id!==l.id)}));
                        }}>✕</button>
                      </div>
                    ))}
                    {!(auLinksMap[a.id]||[]).length&&<div style={{fontFamily:'var(--fm)',fontSize:'.62rem',color:'var(--g400)',fontStyle:'italic',marginBottom:'.52rem'}}>No links yet.</div>}
                    <div style={{display:'grid',gridTemplateColumns:'auto 1fr 1fr auto',gap:'.28rem',marginTop:'.62rem',alignItems:'end'}}>
                      <div>
                        <label className="form-lbl">Type</label>
                        <select value={newLink.link_type} onChange={e=>setNewLink(p=>({...p,link_type:e.target.value}))} style={{width:'auto'}}>
                          {Object.entries(LINK_TYPES).map(([k,v])=><option key={k} value={k}>{v.icon} {v.label}</option>)}
                        </select>
                      </div>
                      <div><label className="form-lbl">Title</label><input value={newLink.title} onChange={e=>setNewLink(p=>({...p,title:e.target.value}))} placeholder="My Newsletter"/></div>
                      <div><label className="form-lbl">URL</label><input value={newLink.url} onChange={e=>setNewLink(p=>({...p,url:e.target.value}))} placeholder="https://…"/></div>
                      <button className="btn-p" style={{alignSelf:'flex-end'}} onClick={async()=>{
                        if(!newLink.title.trim()||!newLink.url.trim()){toast('Title and URL required','err');return;}
                        const r=await API.post(`/api/authors/${a.id}/links`,newLink).catch(()=>({error:'Failed'}));
                        if(r.error){toast(r.error,'err');return;}
                        setAuLinksMap(p=>({...p,[a.id]:[...(p[a.id]||[]),r]}));
                        setNewLink({title:'',url:'',link_type:'web'});toast('Link added.');
                      }}>+ Add</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
            {!authors.length&&<div className="empty"><div className="empty-icon">¶</div><div className="empty-title">No authors yet</div></div>}
          </div>
        )}

        {tab==='users'&&(
          <div>
            {currentUser?.role!=='admin'
              ?<div style={{padding:'2rem',fontFamily:'var(--fm)',fontSize:'.7rem',color:'var(--g500)',textAlign:'center',letterSpacing:'.1em',textTransform:'uppercase'}}>Admin access required.</div>
              :(
              <>
                <div style={{padding:'1.35rem',border:'var(--rt)',background:'var(--g100)',marginBottom:'1.85rem'}}>
                  <div className="form-lbl" style={{marginBottom:'.9rem',fontSize:'.65rem'}}>Create New User</div>
                  <div className="form-row">
                    <div className="form-g"><label className="form-lbl">Username *</label><input value={newUser.username} onChange={e=>setNewUser(p=>({...p,username:e.target.value}))} placeholder="jsmith"/></div>
                    <div className="form-g"><label className="form-lbl">Password *</label><input type="password" value={newUser.password} onChange={e=>setNewUser(p=>({...p,password:e.target.value}))} placeholder="min 6 chars"/></div>
                  </div>
                  <div className="form-row">
                    <div className="form-g"><label className="form-lbl">Role</label>
                      <select value={newUser.role} onChange={e=>setNewUser(p=>({...p,role:e.target.value}))}>
                        <option value="author">Author</option>
                        <option value="translator">Translator</option>
                        <option value="typesetter">Typesetter</option>
                        <option value="editor">Editor</option>
                        <option value="admin">Admin</option>
                      </select>
                    </div>
                    <div className="form-g"><label className="form-lbl">Linked Author (optional)</label>
                      <select value={newUser.author_id} onChange={e=>setNewUser(p=>({...p,author_id:e.target.value}))}>
                        <option value="">— None —</option>
                        {authors.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}
                      </select>
                    </div>
                  </div>
                  <button className="btn-p" onClick={async()=>{
                    if(!newUser.username.trim()||!newUser.password.trim()){toast('Username and password required','err');return;}
                    if(newUser.password.length<6){toast('Password min 6 characters','err');return;}
                    const r=await API.post('/api/auth/register',newUser).catch(()=>({error:'Failed'}));
                    if(r.error)toast(r.error,'err');
                    else{toast('User created.');setNewUser({username:'',password:'',role:'author',author_id:''});load();}
                  }}>Create User</button>
                </div>
                <table className="art-tbl">
                  <thead><tr><th>Username</th><th>Role</th><th>Author</th><th>Last Login</th><th>Actions</th></tr></thead>
                  <tbody>
                    {users.map(u=>(
                      <tr key={u.id}>
                        <td style={{fontFamily:'var(--fh)',fontWeight:600}}>{u.username}</td>
                        <td><span className="s-badge">{u.role}</span></td>
                        <td style={{fontFamily:'var(--fm)',fontSize:'.68rem'}}>{u.author_name||'—'}</td>
                        <td style={{fontFamily:'var(--fm)',fontSize:'.65rem'}}>{u.last_login?fmtShort(u.last_login):'Never'}</td>
                        <td>
                          <div style={{display:'flex',gap:'.25rem'}}>
                            <button className="btn-s" onClick={()=>{
                              const pw=window.prompt(`New password for ${u.username} (min 6 chars):`);
                              if(!pw)return;
                              if(pw.length<6){toast('Min 6 characters','err');return;}
                              API.put(`/api/auth/users/${u.id}/password`,{password:pw}).then(()=>toast('Password updated.')).catch(()=>toast('Failed','err'));
                            }}>Reset PW</button>
                            {u.username!=='admin'&&<button className="btn-s" onClick={()=>setConfirm({msg:`Delete user "${u.username}"?`,act:async()=>{await API.del(`/api/auth/users/${u.id}`);load();}})}>✕</button>}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}

        {tab==='categories'&&(
          <div>
            <div style={{padding:'1.35rem',border:'var(--rt)',background:'var(--g100)',marginBottom:'1.85rem'}}>
              <div className="form-lbl" style={{marginBottom:'.9rem',fontSize:'.65rem'}}>Add New Section</div>
              <div className="form-row">
                <FormLabel label="Name *"><input value={newCat.name} onChange={e=>setNewCat(p=>({...p,name:e.target.value}))} placeholder="Category name" onKeyDown={async e=>{if(e.key==='Enter'&&newCat.name.trim()){const r=await API.post('/api/categories',newCat).catch(()=>({error:'Failed'}));if(!r.error){toast('Category added.');setNewCat({name:'',description:''});load();}}}}/></FormLabel>
                <FormLabel label="Description"><input value={newCat.description} onChange={e=>setNewCat(p=>({...p,description:e.target.value}))} placeholder="Brief description"/></FormLabel>
              </div>
              <button className="btn-p" onClick={async()=>{
                if(!newCat.name.trim()){toast('Name is required','err');return;}
                const r=await API.post('/api/categories',newCat).catch(()=>({error:'Failed'}));
                if(r.error)toast(r.error,'err');
                else{toast('Category added.');setNewCat({name:'',description:''});load();}
              }}>Add Category</button>
            </div>
            <table className="art-tbl">
              <thead><tr><th>Name</th><th>Slug</th><th>Description</th><th>Stories</th><th>Actions</th></tr></thead>
              <tbody>
                {categories.map(c=>(
                  <tr key={c.id}>
                    <td style={{fontFamily:'var(--fh)',fontWeight:600}}>{c.name}</td>
                    <td style={{fontFamily:'var(--fm)',fontSize:'.66rem'}}>{c.slug}</td>
                    <td style={{color:'var(--g600)',fontSize:'.85rem'}}>{c.description}</td>
                    <td style={{fontFamily:'var(--fm)',fontSize:'.68rem'}}>{c.article_count}</td>
                    <td>
                      <div style={{display:'flex',gap:'.26rem',flexWrap:'wrap',alignItems:'center'}}>
                        <button className="btn-s" onClick={()=>renameCat(c)}>Rename</button>
                        <select defaultValue="" onChange={e=>{if(e.target.value){const into=+e.target.value;setConfirm({msg:`Merge "${c.name}" into "${(categories.find(x=>x.id===into)||{}).name}"? Its ${c.article_count} stories move over and "${c.name}" is removed.`,act:()=>mergeCat(c,into)});}e.target.value='';}}
                          style={{fontFamily:'var(--fm)',fontSize:'.58rem',width:'auto',padding:'.18rem .35rem'}}>
                          <option value="">Merge into…</option>
                          {categories.filter(x=>x.id!==c.id).map(x=><option key={x.id} value={x.id}>{x.name}</option>)}
                        </select>
                        <button className="btn-s" onClick={()=>setConfirm({msg:`Delete category "${c.name}"? Stories keep their content but lose this category.`,act:async()=>{await API.del(`/api/categories/${c.id}`);load();}})}>✕</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab==='tags'&&(
          <div>
            <div style={{display:'flex',gap:'.52rem',marginBottom:'1.85rem',alignItems:'flex-end'}}>
              <div className="form-g" style={{flex:1,marginBottom:0}}>
                <label className="form-lbl">New Tag</label>
                <input value={newTag} onChange={e=>setNewTag(e.target.value)} placeholder="Tag name…"
                  onKeyDown={async e=>{
                    if(e.key!=='Enter'||!newTag.trim())return;
                    const r=await API.post('/api/tags',{name:newTag}).catch(()=>({error:'Failed'}));
                    if(r.error)toast(r.error,'err');else{toast('Tag added.');setNewTag('');load();}
                  }}/>
              </div>
              <button className="btn-p" onClick={async()=>{
                if(!newTag.trim())return;
                const r=await API.post('/api/tags',{name:newTag}).catch(()=>({error:'Failed'}));
                if(r.error)toast(r.error,'err');else{toast('Tag added.');setNewTag('');load();}
              }}>Add</button>
            </div>
            <div style={{display:'flex',gap:'.5rem',alignItems:'center',marginBottom:'.8rem',flexWrap:'wrap'}}>
              <input value={tagFilter} onChange={e=>setTagFilter(e.target.value)} placeholder="Filter tags…" style={{flex:1,minWidth:180}}/>
              <span style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g500)'}}>{tags.length} tags</span>
              {mergeSrc&&<button className="btn-s on" onClick={()=>setMergeSrc(null)}>Cancel merge — click a tag to merge into ✕</button>}
            </div>
            <div style={{display:'flex',gap:'.38rem',flexWrap:'wrap'}}>
              {tags.filter(t=>!tagFilter||t.name.toLowerCase().includes(tagFilter.toLowerCase())).map(t=>(
                <div key={t.id} className={`tagchip${mergeSrc===t.id?' merging':''}`} title={mergeSrc?(mergeSrc===t.id?'merging…':'click to merge into this tag'):''}
                  onClick={()=>{if(mergeSrc&&mergeSrc!==t.id)mergeTagInto(t);}}
                  style={{border:'var(--rule)',padding:'.35rem .6rem',display:'flex',alignItems:'center',gap:'.4rem',background:mergeSrc===t.id?'var(--ink)':'var(--paper)',color:mergeSrc===t.id?'var(--paper)':'var(--ink)',cursor:mergeSrc&&mergeSrc!==t.id?'pointer':'default'}}>
                  <span style={{fontFamily:'var(--fm)',fontSize:'.64rem'}}>{t.name}</span>
                  <span style={{fontFamily:'var(--fm)',fontSize:'.54rem',color:'var(--g400)'}}>({t.article_count})</span>
                  {!mergeSrc&&<>
                    <span title="Rename" style={{cursor:'pointer',color:'var(--g400)',fontSize:'.6rem'}} onClick={e=>{e.stopPropagation();renameTag(t);}}>✎</span>
                    <span title="Merge into another tag" style={{cursor:'pointer',color:'var(--g400)',fontSize:'.6rem'}} onClick={e=>{e.stopPropagation();setMergeSrc(t.id);toast('Now click the tag to merge this one into.');}}>⤳</span>
                    <span style={{cursor:'pointer',color:'var(--g300)',fontSize:'.7rem',lineHeight:1}}
                      onMouseOver={e=>e.target.style.color='var(--ink)'} onMouseOut={e=>e.target.style.color='var(--g300)'}
                      onClick={e=>{e.stopPropagation();setConfirm({msg:`Delete tag "${t.name}"? It will be removed from all articles.`,act:async()=>{await API.del(`/api/tags/${t.id}`);load();}});}}>✕</span>
                  </>}
                </div>
              ))}
              {!tags.length&&<div style={{fontFamily:'var(--fm)',fontSize:'.62rem',color:'var(--g400)',fontStyle:'italic'}}>No tags yet.</div>}
            </div>
          </div>
        )}


        {tab==='mailbox'&&<AdminMailbox toast={toast} currentUser={currentUser}/>}

        {tab==='comments'&&<AdminComments toast={toast}/>}

        {tab==='sheet-data'&&<AdminSheetMirrors toast={toast}/>}

        {tab==='newsletter'&&<AdminNewsletterTab toast={toast} setView={setView}/>}
        {tab==='columns'&&<AdminColumns toast={toast}/>}
      </>}
        </div>
      </div>
    </div>
  );
}

function Footer({setView}){
  return(
    <footer>
      <div className="footer-brand">Voice Express</div>
      <div className="footer-tagline">Truth Takes Time</div>
      <div className="footer-links">
        {[['home','Home'],['puzzles','Puzzles'],['timeline','Timeline'],['map','Map'],['newsletter','Newsletter'],['authors','Contributors'],...(hasCap('admin')?[['admin','Editorial Desk']]:[])].map(([id,l])=>(
          <span key={id} className="footer-link" onClick={()=>setView(id)}>{l}</span>
        ))}
      </div>
      <div className="footer-copy">© {new Date().getFullYear()} Voice Express. Independent journalism.</div>
    </footer>
  );
}

const ROUTE_VIEWS={
  home:'/', puzzles:'/puzzles', timeline:'/timeline', map:'/map',
  library:'/newsstand', newsletter:'/newsletter', authors:'/authors',
  admin:'/admin', search:'/search', profile:'/profile', about:'/about',
  submissions:'/submissions', ebook:'/ebook', letters:'/letters',
  columns:'/columns',
};
const VIEW_BY_ROUTE=Object.fromEntries(Object.entries(ROUTE_VIEWS).map(([v,p])=>[p,v]));

function routeFor(view,current,authorId,search,colEntryId){
  if(view==='article'&&current)return '#/article/'+encodeURIComponent(current.slug||current.id);
  if(view==='authors'&&authorId)return '#/author/'+encodeURIComponent(authorId);
  if(view==='search'&&search)return '#/search?q='+encodeURIComponent(search);
  if(Object.prototype.hasOwnProperty.call(ROUTE_VIEWS,view))return '#'+ROUTE_VIEWS[view];
  if(view.indexOf('col:')===0){
    const base='#/column/'+encodeURIComponent(view.slice(4));
    return colEntryId?base+'/'+encodeURIComponent(colEntryId):base;
  }
  return '#/'+encodeURIComponent(view);          
}

function parseRoute(hash){
  const raw=String(hash||'').replace(/^#/,'')||'/';
  const [path,qs]=raw.split('?');
  const seg=path.split('/').filter(Boolean).map(decodeURIComponent);
  const q=(()=>{try{return new URLSearchParams(qs||'').get('q')||'';}catch{return'';}})();
  if(!seg.length)return {view:'home'};
  if(seg[0]==='article')return {view:'article',articleSlug:seg[1]||''};
  if(seg[0]==='author') return {view:'authors',authorId:seg[1]||''};
  if(seg[0]==='column') return {view:'col:'+(seg[1]||''),colEntryId:seg[2]||null};
  const p='/'+seg.join('/');
  if(VIEW_BY_ROUTE[p])return {view:VIEW_BY_ROUTE[p],query:q};
  return {view:seg[0]};                          
}

function App(){
  const [view,setView]=useState(VE_PRODUCT==='library'?'library':'home');
  const [current,setCurrent]=useState(null);
  const [search,setSearch]=useState('');
  const [readMode,setReadMode]=useState(false);
  const [toast,setToast]=useState(null);
  const [currentUser,setCurrentUser]=useState(null);
  const [showLogin,setShowLogin]=useState(false);
  const [sections,setSections]=useState([]);
  const [categories,setCategories]=useState([]);
  const [theme,setTheme]=useState(()=>{try{return localStorage.getItem('ve-theme')||'light';}catch{return'light';}});

  const showToast=(m,t='ok')=>setToast({m,t});

  useEffect(()=>{API.get('/api/auth/me').then(u=>setCurrentUser(u||null)).catch(()=>{});},[]);
  useEffect(()=>{API.get('/api/sections').then(s=>setSections(safe(s))).catch(()=>{});},[]);
  useEffect(()=>{API.get('/api/categories').then(c=>setCategories(safe(c))).catch(()=>{});},[]);
  useEffect(()=>{
    document.documentElement.setAttribute('data-theme',theme==='light'?'':theme);
    try{localStorage.setItem('ve-theme',theme);}catch{}
  },[theme]);

  const [viewAuthorId,setViewAuthorId]=useState(null);
  const cycleTheme=()=>setTheme(t=>t==='light'?'sepia':t==='sepia'?'dark':'light');
  const logout=async()=>{await API.post('/api/auth/logout',{}).catch(()=>{});setCurrentUser(null);showToast('Signed out.');};

  const poppingRef=useRef(false);
  const currentRef=useRef(null);
  const authorIdRef=useRef(null);
  const searchRef=useRef('');
  const [colEntryId,setColEntryId]=useState(null);  
  const colEntryRef=useRef(null);
  useEffect(()=>{currentRef.current=current;},[current]);
  useEffect(()=>{authorIdRef.current=viewAuthorId;},[viewAuthorId]);
  useEffect(()=>{searchRef.current=search;},[search]);
  useEffect(()=>{colEntryRef.current=colEntryId;},[colEntryId]);

  useEffect(()=>{
    const r=parseRoute(location.hash);
    if(r.query)setSearch(r.query);
    if(r.authorId){authorIdRef.current=r.authorId;setViewAuthorId(r.authorId);}
    if(r.colEntryId){colEntryRef.current=r.colEntryId;setColEntryId(r.colEntryId);}
    if(r.view==='article'&&r.articleSlug){
      API.get('/api/articles').then(list=>{
        const hit=safe(list).find(a=>String(a.slug)===r.articleSlug||String(a.id)===r.articleSlug);
        if(hit){currentRef.current=hit;setCurrent(hit);setView('article');}
        else setView('home');
      }).catch(()=>setView('home'));
    } else if(r.view&&r.view!=='home'){
      setView(r.view);
    }
    history.replaceState({view:r.view||'home',current:null,authorId:r.authorId||null,
      colEntryId:r.colEntryId||null,scrollY:0},'',location.href);
  },[]);

  useEffect(()=>{
    if(poppingRef.current)return;
    const want=routeFor(view,current,viewAuthorId,search,colEntryId);
    if(location.hash!==want){
      const st=history.state||{};
      history.replaceState({...st,view,current:view==='article'?current:null,
        authorId:viewAuthorId||null,colEntryId:colEntryId||null},'',want);
    }
  },[view,current,viewAuthorId,search,colEntryId]);

  useEffect(()=>{
    const onScroll=()=>{
      if(poppingRef.current)return;
      const st=history.state||{};
      history.replaceState({...st,scrollY:window.scrollY},'',location.href);
    };
    window.addEventListener('scroll',onScroll,{passive:true});
    return ()=>window.removeEventListener('scroll',onScroll);
  },[]);

  const navDepthRef=useRef(0);

  useEffect(()=>{
    const onPop=e=>{
      const st=e.state||(()=>{
        const r=parseRoute(location.hash);
        return {view:r.view||'home',current:null,authorId:r.authorId||null,
                colEntryId:r.colEntryId||null,scrollY:0};
      })();
      poppingRef.current=true;
      navDepthRef.current=Math.max(0,navDepthRef.current-1);
      setCurrent(st.current||null);
      setView(st.view||'home');
      setViewAuthorId(st.authorId||null);
      setColEntryId(st.colEntryId||null);
      setReadMode(false);
      const y=st.scrollY||0;
      if(!y){requestAnimationFrame(()=>{window.scrollTo(0,0);poppingRef.current=false;});return;}
      let tries=0;
      const restore=()=>{
        window.scrollTo(0,y);
        const short=document.documentElement.scrollHeight-window.innerHeight<y;
        if(short&&tries++<30){requestAnimationFrame(restore);return;}
        poppingRef.current=false;
      };
      requestAnimationFrame(restore);
    };
    window.addEventListener('popstate',onPop);
    return ()=>window.removeEventListener('popstate',onPop);
  },[]);

  const navTo=useCallback((newView,extra={})=>{
    const authorId=newView==='authors'?('authorId' in extra?extra.authorId:authorIdRef.current):null;
    const colEntry=newView.indexOf('col:')===0&&('colEntryId' in extra)
      ?extra.colEntryId:null;
    colEntryRef.current=colEntry;
    setColEntryId(colEntry);
    if(!poppingRef.current){
      history.pushState({
        view:newView,
        current:newView==='article'?currentRef.current:null,
        authorId,
        colEntryId:colEntry,
        scrollY:0
      },'',routeFor(newView,currentRef.current,authorId,searchRef.current,colEntry));
      navDepthRef.current+=1;
    }
    setView(newView);
    setReadMode(false);
    window.scrollTo(0,0); 
  },[]);

  const goBack=useCallback(()=>{
    if(navDepthRef.current>0){history.back();}
    else{navTo('home');}
  },[navTo]);

  const goToAuthor=useCallback(id=>{authorIdRef.current=id;setViewAuthorId(id);navTo('authors',{authorId:id});},[navTo]);

  const go=useCallback(articleOrView=>{
    if(typeof articleOrView==='object'&&articleOrView!==null){
      currentRef.current=articleOrView;
      setCurrent(articleOrView);
    } else {
      navTo(articleOrView);
    }
  },[navTo]);

  const nav=useCallback(v=>navTo(v),[navTo]);

  const props={setView:nav,go,toast:showToast,goBack};

  const sectionSlugs=useMemo(()=>new Set(sections.map(s=>s.slug)),[sections]);
  const catSlugs=useMemo(()=>new Set(categories.map(c=>c.slug)),[categories]);

  const renderPage=()=>{
    switch(view){
      case 'home':       return <HomePage {...props} sections={sections}/>;
      case 'article':    return current
        ?<ArticleView article={current} setView={nav} go={obj=>{go(obj);nav('article');}} goBack={goBack} readMode={readMode} setReadMode={setReadMode} toast={showToast} currentUser={currentUser} goToAuthor={goToAuthor}/>
        :<HomePage {...props} sections={sections}/>;
      case 'puzzles':    return <PuzzlesPage toast={showToast}/>;
      case 'timeline':   return <TimelinePage {...props}/>;
      case 'map':        return <MapPage {...props} currentUser={currentUser}/>;
      case 'library':    return <LibraryPage toast={showToast} currentUser={currentUser} setView={nav}/>;
      case 'newsletter': return <NewsletterPage {...props} currentUser={currentUser}/>;
      case 'authors':    return <AuthorsPage {...props} initAuthorId={viewAuthorId} onAuthorShown={()=>setViewAuthorId(null)}/>;
      case 'admin':      return hasCap('admin')?<AdminPanel setView={nav} go={obj=>{go(obj);nav('article');}} currentUser={currentUser}/>:<HomePage {...props} sections={sections}/>;
      case 'search':     return <SearchPage query={search} {...props}/>;
      case 'profile':    return hasCap('accounts')?<MyProfilePage currentUser={currentUser} toast={showToast} setView={nav}/>:<HomePage {...props} sections={sections}/>;
      case 'about':       return <AboutPage setView={nav}/>;
      case 'submissions': return <SubmissionsPage setView={nav}/>;
      case 'ebook':       return hasCap('server_render')?<EbookPage toast={showToast}/>:<PublicEbookRequestPage toast={showToast}/>;
      case 'letters':    return hasCap('accounts')?<LettersPage currentUser={currentUser} toast={showToast}/>:<PublicLettersPage toast={showToast}/>;
      case 'columns':    return <ColumnsPage {...props}/>;
      default:
        if(view.indexOf('col:')===0)return <ColumnPage slug={view.slice(4)} setView={nav}
          entryId={colEntryId} goBack={goBack}
          onOpenEntry={id=>navTo(view,{colEntryId:id})}
          onCloseEntry={()=>navTo(view,{colEntryId:null})}/>;
        if(sectionSlugs.has(view))return <SectionPage section={view} sections={sections} {...props}/>;
        if(catSlugs.has(view))return <CatPage cat={view} {...props}/>;
        return <HomePage {...props} sections={sections}/>;
    }
  };

  useEffect(()=>{if(current&&view!=='article')setView('article');},[current]);

  return(
    <>
      <div id="progress-bar"/>
      <BetaBanner/>
      <Masthead view={view} setView={nav} search={search} setSearch={setSearch} readMode={readMode} setReadMode={setReadMode}
        theme={theme} cycleTheme={cycleTheme} currentUser={currentUser} sections={sections}
        onLogin={()=>setShowLogin(true)} onLogout={logout}/>
      <main>{renderPage()}</main>
      {!readMode&&view!=='home'&&<button className="back-nav" onClick={goBack} title="Back">‹</button>}
      {!readMode&&<Footer setView={nav}/>}
      {toast&&<Toast msg={toast.m} type={toast.t} onDone={()=>setToast(null)}/>}
      {showLogin&&<LoginModal onLogin={u=>{setCurrentUser(u);showToast(`Welcome, ${u.username}!`);}} onClose={()=>setShowLogin(false)}/>}
    </>
  );
}


