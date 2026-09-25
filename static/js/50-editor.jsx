function FormField({label,children}){
  return <div className="form-g"><label className="form-lbl">{label}</label>{children}</div>;
}

function ArticleEditor({article,onSave,onCancel,authors,categories,allSections,tags,allSeries,toast}){
  const [form,setForm]=useState({
    title:article?.title||'',subtitle:article?.subtitle||'',excerpt:article?.excerpt||'',
    seo_description:article?.seo_description||'',seo_keywords:article?.seo_keywords||'',
    author_id:article?.author_id||'',byline:article?.byline||'',
    authors:(article?.authors&&article.authors.length
      ?article.authors.map(a=>({author_id:String(a.id),role:a.role||'author',sort_order:a.sort_order||0}))
      :(article?.author_id?[{author_id:String(article.author_id),role:'author',sort_order:0}]:[])),
    category_id:article?.category_id||'',section_id:article?.section_id||'',language:article?.language||'en',
    published_at:(article?.published_at||'').slice(0,10),
    featured_image:article?.featured_image||'',
    latitude:article?.latitude||'',longitude:article?.longitude||'',
    location_name:article?.location_name||'',
    is_featured:!!(article?.is_featured),
    tag_ids:safe(article?.tags).map(t=>t.id),
    citations:safe(article?.citations),
    series_id:article?.series_id||'',
    series_order:article?.series_order||''
  });
  const [content,setContent]=useState(article?.content||'');
  const [localTags,setLocalTags]=useState(safe(tags));
  const [saving,setSaving]=useState(false);
  const [uploading,setUploading]=useState(false);
  const [preview,setPreview]=useState(false);
  const [activeTab,setActiveTab]=useState('content');
  const [newCit,setNewCit]=useState({reference_text:'',url:'',author:'',published_date:''});
  const [translations,setTranslations]=useState([]);
  const [editingTrans,setEditingTrans]=useState(null);
  const [savingTrans,setSavingTrans]=useState(false);
  const [newTrans,setNewTrans]=useState({language:'hi',title:'',excerpt:'',content:''});
  const [transCompose,setTransCompose]=useState(true);
  const [corrections,setCorrections]=useState(safe(article?.corrections));
  const [newCorrection,setNewCorrection]=useState({title:'',body:'',severity:'minor'});
  const [savingCorrection,setSavingCorrection]=useState(false);
  const liveRef=useRef(null);
  const fileRef=useRef(null);
  const imgFileRef=useRef(null);
  const saveRef=useRef(null);
  const [editorMode,setEditorMode]=useState(article?.id&&(article?.content||'').trim()?'compose':'rich');
  const [versions,setVersions]=useState(null);
  const [viewingV,setViewingV]=useState(null);
  const [showImgModal,setShowImgModal]=useState(false);
  const [imgUrl,setImgUrl]=useState('');
  const [imgUploading,setImgUploading]=useState(false);
  const [showShortcuts,setShowShortcuts]=useState(false);

  useEffect(()=>{
    if(article?.id){
      API.get(`/api/articles/${article.id}/translations`)
        .then(d=>setTranslations(safe(d)))
        .catch(()=>{});
    }
  },[article?.id]);

  const loadVersions=()=>{
    if(!article?.id)return;
    API.get(`/api/articles/${article.id}/versions`).then(d=>setVersions(safe(d))).catch(()=>setVersions([]));
  };
  useEffect(()=>{ if(activeTab==='history')loadVersions(); },[activeTab,article?.id]);
  const viewVersion=async(vid)=>{
    const d=await API.get(`/api/articles/${article.id}/versions/${vid}`).catch(()=>null);
    if(d&&!d.error)setViewingV(d);
  };
  const restoreVersion=async(vid)=>{
    if(!confirm('Restore this version? The current text becomes a new version in the history, so nothing is lost.'))return;
    const r=await API.post(`/api/articles/${article.id}/versions/${vid}/restore`,{}).catch(()=>({error:'Failed'}));
    if(r.error){toast(r.error,'err');return;}
    toast('Version restored.');
    loadVersions();
    onSave();
  };

  const set=(k,v)=>setForm(f=>({...f,[k]:v}));
  const toggleTag=id=>set('tag_ids',form.tag_ids.includes(id)?form.tag_ids.filter(t=>t!==id):[...form.tag_ids,id]);
  const addCit=()=>{
    if(!newCit.reference_text.trim())return;
    set('citations',[...form.citations,{...newCit}]);
    setNewCit({reference_text:'',url:'',author:'',published_date:''});
  };

  const handleUpload=async e=>{
    const f=e.target.files?.[0];if(!f)return;
    setUploading(true);
    const fd=new FormData();fd.append('file',f);
    const d=await API.upload('/api/upload',fd).catch(()=>({}));
    if(d.url)set('featured_image',d.url);
    else toast('Upload failed','err');
    setUploading(false);
    if(fileRef.current)fileRef.current.value='';
  };

  const switchEditorMode=mode=>{ setEditorMode(mode); };

  const insertImage=url=>{
    if(!url)return;
    const frag=`<div class="photo-unit" data-type="captioned"><figure><img src="${url}" alt=""><figcaption data-text-role="caption">Caption…</figcaption></figure></div>`;
    if(editorMode==='rich'&&liveRef.current){ liveRef.current.insertHtml(frag); }
    else{ setContent((content||'')+'\n'+frag+'\n'); }
    setShowImgModal(false);
    setImgUrl('');
    if(imgFileRef.current)imgFileRef.current.value='';
  };

  const handleImgUpload=async e=>{
    const f=e.target.files?.[0];if(!f)return;
    setImgUploading(true);
    const fd=new FormData();fd.append('file',f);
    const d=await API.upload('/api/upload',fd).catch(()=>({}));
    if(d.url)insertImage(d.url);
    else{toast('Upload failed','err');setImgUploading(false);}
  };

  const htmlRef=useRef(null);
  const SEM_BLOCKS=[
    {l:'Section',     h:'\n<div class="article-section" data-section-index="">\n  <h2 class="section-heading">$SEL</h2>\n  <p>Write here…</p>\n</div>\n', ph:'Section title'},
    {l:'Lede',        h:'\n<p data-text-role="lede">$SEL</p>\n', ph:'Opening paragraph that sets the scene…'},
    {l:'Pull quote',  h:'\n<blockquote class="pull-quote">$SEL<cite>— Source</cite></blockquote>\n', ph:'A line worth enlarging.'},
    {l:'Field quote', h:'\n<blockquote class="field-quote">$SEL<cite>— Name, role</cite></blockquote>\n', ph:'Something said in the field.'},
    {l:'Q&A',         h:'\n<p class="qa-line"><span class="qa-speaker">Name:</span> $SEL</p>\n', ph:'their answer…'},
    {l:'Photo',       h:'\n<div class="photo-unit" data-type="captioned">\n  <figure><img src="" alt="describe the image"><figcaption data-text-role="caption">$SEL</figcaption></figure>\n</div>\n', ph:'Caption…'},
    {l:'Gallery',     h:'\n<div class="photo-group" data-type="dump">\n  <figure><img src="" alt=""></figure>\n  <figure><img src="" alt=""></figure>\n</div>\n', ph:''},
    {l:'Collage',     h:'\n<div class="photo-group" data-type="grid">\n  <figure><img src="" alt=""></figure>\n  <figure><img src="" alt=""></figure>\n  <figure><img src="" alt=""></figure>\n</div>\n', ph:''},
    {l:'Sequence',    h:'\n<div class="photo-group" data-type="sequence">\n  <figure><img src="" alt=""><figcaption data-text-role="caption">$SEL</figcaption></figure>\n  <figure><img src="" alt=""><figcaption data-text-role="caption">…</figcaption></figure>\n</div>\n', ph:'Step 1'},
    {l:'Comic',       h:'\n<div class="photo-group" data-type="comic">\n  <figure class="panel"><img src="" alt=""><figcaption class="panel-caption">$SEL</figcaption></figure>\n  <figure class="panel"><img src="" alt=""><figcaption class="panel-caption">…</figcaption></figure>\n</div>\n', ph:'Panel 1'},
    {l:'Reference',   h:'\n<div class="photo-unit" data-type="reference">\n  <figure><img src="" alt=""><figcaption data-text-role="caption"><span class="reference-label">Fig. A</span> $SEL</figcaption></figure>\n</div>\n', ph:'what it shows'},
    {l:'Quote+credit',h:'\n<blockquote class="field-quote"><img class="quote-credit" src="" alt="">$SEL<cite>— Name, role</cite></blockquote>\n', ph:'the quote…'},
    {l:'Comparison',  h:'\n<div class="comparison" data-count="2">\n  <div class="compare-item"><div class="compare-label">$SEL</div><p>…</p></div>\n  <div class="compare-item"><div class="compare-label">Then</div><p>…</p></div>\n</div>\n', ph:'Now'},
    {l:'Note',        h:'\n<p class="intro-note">$SEL</p>\n', ph:'Editor’s note…'},
    {l:'Divider',     h:'\n<hr class="section-divider">\n', ph:''},
  ];
  const PROSE_ROLES=['analysis','context','scene','testimony','resolution','note','dateline'];
  const insertSem=(item)=>{
    if(editorMode==='rich'&&liveRef.current){ 
      liveRef.current.insertHtml(item.h.replace('$SEL',item.ph||''));
      return;
    }
    const ta=htmlRef.current;
    const inHtml=editorMode==='html'&&ta&&typeof ta.selectionStart==='number';
    const cur=content||'';
    const s=inHtml?ta.selectionStart:cur.length, e=inHtml?ta.selectionEnd:cur.length;
    const sel=inHtml?cur.slice(s,e):'';
    const frag=item.h.replace('$SEL',sel||item.ph);
    setContent(cur.slice(0,s)+frag+cur.slice(e));
    if(!inHtml)switchEditorMode('html');
    setTimeout(()=>{const t=htmlRef.current;if(t){t.focus();const pos=s+frag.length;t.setSelectionRange(pos,pos);}},0);
  };
  const tagRole=(role)=>{ if(role) insertSem({h:'\n<p data-text-role="'+role+'">$SEL</p>\n',ph:'…'}); };

  const AUTHOR_ROLES=['author','co-author','photographer','illustrator','translator','editor','reporting'];
  const addAuthor=()=>set('authors',[...form.authors,{author_id:'',role:'author',sort_order:form.authors.length}]);
  const setAuthor=(i,k,v)=>set('authors',form.authors.map((a,j)=>j===i?{...a,[k]:v}:a));
  const rmAuthor=(i)=>set('authors',form.authors.filter((_,j)=>j!==i).map((a,j)=>({...a,sort_order:j})));
  const moveAuthor=(i,d)=>{const n=[...form.authors];const j=i+d;if(j<0||j>=n.length)return;[n[i],n[j]]=[n[j],n[i]];set('authors',n.map((a,k)=>({...a,sort_order:k})));};

  useEffect(()=>{saveRef.current=save;});
  useEffect(()=>{
    const handler=e=>{
      if((e.ctrlKey||e.metaKey)&&e.key==='s'){e.preventDefault();saveRef.current&&saveRef.current('draft');}
    };
    document.addEventListener('keydown',handler);
    return()=>document.removeEventListener('keydown',handler);
  },[]);

  const save=async(status)=>{
    if(!form.title.trim()){toast('Headline is required','err');return;}
    setSaving(true);
    try{
      const payload={...form,content,status};
      const r=article?.id
        ?await API.put(`/api/articles/${article.id}`,payload)
        :await API.post('/api/articles',payload);
      if(r.error){toast(r.error,'err');setSaving(false);return;}
      toast(status==='published'?'Article published!':'Draft saved.');
      onSave();
    }catch{toast('Save failed — check your connection','err');}
    setSaving(false);
  };

  const saveTrans=async(data)=>{
    if(!article?.id){toast('Save the article before adding translations','err');return;}
    setSavingTrans(true);
    const d=await API.post(`/api/articles/${article.id}/translations`,data).catch(()=>({error:'Failed'}));
    if(d.error){toast(d.error,'err');}
    else{
      setTranslations(prev=>{
        const ex=prev.find(t=>t.language===d.language);
        return ex?prev.map(t=>t.language===d.language?d:t):[...prev,d];
      });
      toast('Translation saved.');
    }
    setSavingTrans(false);
    return !d.error;
  };

  const deleteTrans=async lang=>{
    if(!article?.id)return;
    await API.del(`/api/articles/${article.id}/translation/${lang}`).catch(()=>{});
    setTranslations(prev=>prev.filter(t=>t.language!==lang));
    if(editingTrans?.language===lang)setEditingTrans(null);
    toast('Translation removed.');
  };

  const TRANS_LANGS=Object.entries(LANGS).filter(([c])=>c!=='en');
  const usedLangs=translations.map(t=>t.language);

  return(
    <div>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1rem',flexWrap:'wrap',gap:'.45rem',paddingBottom:'.95rem',borderBottom:'var(--rt)'}}>
        <div style={{fontFamily:'var(--fh)',fontSize:'1.42rem',fontWeight:700}}>{article?'Edit Article':'New Article'}</div>
        <div style={{display:'flex',gap:'.32rem',flexWrap:'wrap'}}>
          {activeTab==='content'&&<button className="btn-s" onClick={()=>setPreview(v=>!v)}>{preview?'← Edit':'Preview ↗'}</button>}
          <button className="btn-o" onClick={onCancel} disabled={saving}>Cancel</button>
          <button className="btn-o" onClick={()=>save('draft')} disabled={saving}>Save Draft</button>
          <button className="btn-p" onClick={()=>save('published')} disabled={saving}>{saving?'Saving…':article?.status==='published'?'Update':'Publish'}</button>
        </div>
      </div>

      <div style={{display:'flex',borderBottom:'var(--rule)',marginBottom:'1.35rem'}}>
        {[['content','Content'],['translations',`Translations${translations.length?` (${translations.length})`:''}`],['corrections',`Corrections${corrections.length?` (${corrections.length})`:''}`],...(article?.id?[['history','History']]:[])].map(([id,lbl])=>(
          <div key={id} className={`a-tab${activeTab===id?' on':''}`} style={{borderLeft:id==='content'?'var(--rt)':'none'}}
            onClick={()=>setActiveTab(id)}>{lbl}</div>
        ))}
      </div>

      {activeTab==='content'&&(preview?(
        <div>
          {form.featured_image&&<img src={form.featured_image} alt="" style={{width:'100%',maxHeight:280,objectFit:'cover',marginBottom:'1rem'}} onError={e=>e.target.style.display='none'}/>}
          {form.title&&<h1 className="art-title">{form.title}</h1>}
          {form.subtitle&&<div className="art-subtitle" style={{margin:'.4rem 0',fontStyle:'italic'}}>{form.subtitle}</div>}
          {form.excerpt&&<div className="art-deck" style={{margin:'.75rem 0'}}>{form.excerpt}</div>}
          {form.byline&&<div className="art-byline" style={{margin:'.5rem 0'}}><strong>{form.byline}</strong></div>}
          <div className="art-content dropcap" style={{marginTop:'1.2rem'}} dangerouslySetInnerHTML={{__html:content||'<p style="color:var(--g400);font-style:italic">No content yet…</p>'}}/>
        </div>
      ):(
        <>
          <FormField label="Headline *">
            <input value={form.title} onChange={e=>set('title',e.target.value)} placeholder="Article headline…"/>
          </FormField>
          <FormField label="Subtitle / Deck">
            <input value={form.subtitle} onChange={e=>set('subtitle',e.target.value)} placeholder="A short sentence under the headline (the deck)…"/>
          </FormField>
          <FormField label="Abstract / Excerpt">
            <textarea value={form.excerpt} onChange={e=>set('excerpt',e.target.value)} placeholder="One or two sentence summary shown on the front page…" style={{minHeight:60}}/>
          </FormField>
          <FormField label="Featured Image">
            <div className="form-row" style={{marginBottom:form.featured_image?'.62rem':0}}>
              <div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.55rem',letterSpacing:'.08em',textTransform:'uppercase',color:'var(--g500)',marginBottom:'.28rem'}}>URL</div>
                <input value={form.featured_image} onChange={e=>set('featured_image',e.target.value)} placeholder="https://… or use upload →"/>
              </div>
              <div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.55rem',letterSpacing:'.08em',textTransform:'uppercase',color:'var(--g500)',marginBottom:'.28rem'}}>{uploading?'Uploading…':'Upload File'}</div>
                <input type="file" accept="image/*" ref={fileRef} onChange={handleUpload} style={{border:'none',padding:0}} disabled={uploading}/>
              </div>
            </div>
            {form.featured_image&&(
              <div style={{position:'relative',display:'inline-block',marginTop:'.2rem'}}>
                <img src={form.featured_image} alt="Featured" style={{maxHeight:200,maxWidth:'100%',objectFit:'cover',border:'var(--rt)',display:'block'}} onError={e=>{e.target.closest('div').style.display='none';}}/>
                <button onClick={()=>set('featured_image','')} title="Remove image"
                  style={{position:'absolute',top:6,right:6,background:'rgba(10,10,10,.82)',color:'#fff',border:'none',width:24,height:24,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'center',fontSize:'.72rem',lineHeight:1}}>✕</button>
              </div>
            )}
            <label style={{display:'flex',alignItems:'center',gap:'.45rem',cursor:'pointer',fontFamily:'var(--fm)',fontSize:'.59rem',letterSpacing:'.1em',textTransform:'uppercase',width:'auto',marginTop:'.55rem'}}>
              <input type="checkbox" checked={form.is_featured} onChange={e=>set('is_featured',e.target.checked)} style={{width:'auto',border:'none'}}/>
              Feature on homepage
            </label>
          </FormField>
          <FormField label="Authors">
            <div style={{display:'flex',flexDirection:'column',gap:'.32rem'}}>
              {form.authors.map((a,i)=>{
                const btn={fontFamily:'var(--fm)',fontSize:'.62rem',padding:'.24rem .42rem',border:'var(--rt)',background:'var(--paper)',color:'var(--ink)',cursor:'pointer'};
                return (
                <div key={i} style={{display:'flex',gap:'.3rem',alignItems:'center'}}>
                  <select value={a.author_id} onChange={e=>setAuthor(i,'author_id',e.target.value)} style={{flex:2}}>
                    <option value="">Select author…</option>
                    {authors.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}
                  </select>
                  <select value={a.role} onChange={e=>setAuthor(i,'role',e.target.value)} style={{flex:1,width:'auto'}}>
                    {AUTHOR_ROLES.map(r=><option key={r} value={r}>{r}</option>)}
                  </select>
                  <button type="button" style={btn} onClick={()=>moveAuthor(i,-1)} title="Move up">↑</button>
                  <button type="button" style={btn} onClick={()=>moveAuthor(i,1)} title="Move down">↓</button>
                  <button type="button" style={btn} onClick={()=>rmAuthor(i)} title="Remove">✕</button>
                </div>);
              })}
              {!form.authors.length&&<div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g400)',fontStyle:'italic'}}>No authors yet.</div>}
              <button type="button" className="btn-s" onClick={addAuthor} style={{alignSelf:'flex-start',fontSize:'.58rem',padding:'.24rem .6rem'}}>+ Add author</button>
            </div>
          </FormField>
          <FormField label="Printed Byline (override — leave blank to auto-build from authors)">
            <input value={form.byline} onChange={e=>set('byline',e.target.value)} placeholder="auto: e.g. Jane Smith & Sara Iyer - Photos by Mira Das"/>
          </FormField>
          <div className="form-row">
            <FormField label="Section (Topic Beat)">
              <select value={form.section_id} onChange={e=>set('section_id',e.target.value)}>
                <option value="">Select section…</option>
                {safe(allSections).map(s=><option key={s.id} value={s.id}>{s.name} — {s.description||''}</option>)}
              </select>
            </FormField>
            <FormField label="Category (Content Format)">
              <select value={form.category_id} onChange={e=>set('category_id',e.target.value)}>
                <option value="">Select category…</option>
                {categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </FormField>
          </div>
          <div className="form-row">
            <FormField label="Language">
              <select value={form.language} onChange={e=>set('language',e.target.value)}>
                {Object.entries(LANGS).map(([code,name])=><option key={code} value={code}>{name}</option>)}
              </select>
            </FormField>
            <FormField label="Publication date">
              <input type="date" value={form.published_at} onChange={e=>set('published_at',e.target.value)}/>
              <div style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',marginTop:'.25rem'}}>The editorial date of record — drives archive, timeline and the monthly newsletter. Leave blank to stamp now on publish.</div>
            </FormField>
          </div>
          {safe(allSeries).length>0&&(
            <div className="form-row">
              <FormField label="Article Series">
                <select value={form.series_id} onChange={e=>set('series_id',e.target.value)}>
                  <option value="">Not part of a series</option>
                  {allSeries.map(s=><option key={s.id} value={s.id}>{s.title}</option>)}
                </select>
              </FormField>
              <FormField label="Order in Series">
                <input type="number" min="1" value={form.series_order} onChange={e=>set('series_order',e.target.value)} placeholder="e.g. 1" disabled={!form.series_id}/>
              </FormField>
            </div>
          )}
          <FormField label="Tags">
            <TagInput allTags={localTags} value={form.tag_ids}
              onChange={ids=>set('tag_ids',ids)}
              onCreated={t=>setLocalTags(p=>[...p,t])}/>
          </FormField>
          <details className="seo-box">
            <summary>Search / SEO</summary>
            <FormField label="Meta description (≈155 chars)">
              <textarea value={form.seo_description} onChange={e=>set('seo_description',e.target.value)}
                placeholder="One-sentence summary for search engines + social cards…" style={{minHeight:54}} maxLength={300}/>
              <div style={{fontFamily:'var(--fm)',fontSize:'.55rem',color:(form.seo_description.length>160?'var(--err,#b00)':'var(--g500)')}}>{form.seo_description.length} chars{form.seo_description.length>160?' — over 160':''}</div>
            </FormField>
            <FormField label="SEO keywords (comma-separated)">
              <input value={form.seo_keywords} onChange={e=>set('seo_keywords',e.target.value)} placeholder="topic, person, place, issue…"/>
            </FormField>
            <button type="button" className="btn-s" style={{fontSize:'.58rem'}}
              onClick={()=>{if(!form.seo_description&&form.excerpt)set('seo_description',form.excerpt.slice(0,157));}}>
              Use abstract as meta description
            </button>
          </details>
          <div className="form-g">
            <label className="form-lbl">Body Content</label>
            <div className="ed-mode-bar">
              <div className="ed-tabs">
                {[['rich','Live'],['compose','Typeset'],['html','HTML'],['preview','Preview']].map(([m,l])=>(
                  <div key={m} className={`ed-tab${editorMode===m?' on':''}`} onClick={()=>switchEditorMode(m)}>{l}</div>
                ))}
              </div>
              <button className="btn-s" style={{fontSize:'.55rem',padding:'.2rem .58rem',marginBottom:'.02rem'}} onClick={()=>setShowShortcuts(v=>!v)}>
                {showShortcuts?'Hide shortcuts':'⌨ Shortcuts'}
              </button>
            </div>
            {showShortcuts&&(
              <div className="shortcuts-grid">
                {[['Bold','Ctrl+B'],['Italic','Ctrl+I'],['Underline','Ctrl+U'],['Strikethrough','Ctrl+Shift+S'],
                  ['Undo','Ctrl+Z'],['Redo','Ctrl+Y'],['Link','Ctrl+K'],
                  ['Save Draft','Ctrl+S'],['Select All','Ctrl+A'],['Clean Format','select → toolbar Clean']
                ].map(([n,k])=>(
                  <div key={n} style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:'.35rem'}}>
                    <span style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g600)'}}>{n}</span>
                    <span className="kbd-chip">{k}</span>
                  </div>
                ))}
              </div>
            )}
            {(editorMode==='rich'||editorMode==='html')&&(
            <div style={{display:'flex',flexWrap:'wrap',alignItems:'center',gap:'.3rem',margin:'.4rem 0',padding:'.42rem .5rem',border:'var(--rt)',background:'var(--g100)'}}>
              <span style={{fontFamily:'var(--fm)',fontSize:'.55rem',letterSpacing:'.08em',textTransform:'uppercase',color:'var(--g500)',marginRight:'.15rem'}}>Insert block</span>
              {SEM_BLOCKS.map(it=>(
                <button type="button" key={it.l} onClick={()=>insertSem(it)} title={`Insert ${it.l} (wraps selected text in HTML mode)`}
                  style={{fontFamily:'var(--fm)',fontSize:'.58rem',padding:'.22rem .5rem',border:'var(--rt)',background:'var(--paper)',color:'var(--ink)',cursor:'pointer'}}>{it.l}</button>
              ))}
              <select defaultValue="" onChange={e=>{tagRole(e.target.value);e.target.value='';}}
                style={{fontFamily:'var(--fm)',fontSize:'.58rem',width:'auto',padding:'.2rem .4rem'}} title="Tag a paragraph with a narrative role">
                <option value="">Tag ¶ role…</option>
                {PROSE_ROLES.map(r=><option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            )}
            {editorMode==='compose'&&(
              <SemanticComposer value={content} onChange={setContent}/>
            )}
            {editorMode==='rich'&&(
              <LiveEditor ref={liveRef} value={content} onChange={setContent}
                onRequestImage={()=>{setImgUrl('');setShowImgModal(true);}}/>
            )}
            {editorMode==='html'&&(
              <textarea ref={htmlRef} className="html-src" value={content} spellCheck={false}
                onChange={e=>setContent(e.target.value)}
                placeholder="<!-- paste or type HTML here… -->"/>
            )}
            {editorMode==='preview'&&(
              <div className="ed-preview-body art-content dropcap"
                dangerouslySetInnerHTML={{__html:content||'<p style="color:var(--g400);font-style:italic">No content yet…</p>'}}/>
            )}
          </div>

          <div className="form-row3">
            <FormField label="Location Name"><input value={form.location_name} onChange={e=>set('location_name',e.target.value)} placeholder="City, Country"/></FormField>
            <FormField label="Latitude"><input type="number" step="any" value={form.latitude} onChange={e=>set('latitude',e.target.value)} placeholder="e.g. 28.6139"/></FormField>
            <FormField label="Longitude"><input type="number" step="any" value={form.longitude} onChange={e=>set('longitude',e.target.value)} placeholder="e.g. 77.2090"/></FormField>
          </div>
          <FormField label="References & Citations">
            {form.citations.map((c,i)=>(
              <div key={i} style={{display:'flex',gap:'.38rem',marginBottom:'.28rem',alignItems:'center',background:'var(--g100)',padding:'.42rem .68rem'}}>
                <span style={{fontFamily:'var(--fm)',fontSize:'.59rem',color:'var(--g500)',minWidth:'1.5rem'}}>[{i+1}]</span>
                <span style={{flex:1,fontSize:'.83rem',lineHeight:1.4}}>{c.reference_text}{c.author?` — ${c.author}`:''}{c.url&&<> · <a href={c.url} target="_blank" style={{textDecoration:'underline'}}>Link</a></>}</span>
                <button className="btn-s" style={{padding:'.17rem .42rem'}} onClick={()=>set('citations',form.citations.filter((_,j)=>j!==i))}>✕</button>
              </div>
            ))}
            <div style={{display:'grid',gridTemplateColumns:'2fr 1fr 1fr',gap:'.32rem',marginTop:'.32rem'}}>
              <input placeholder="Reference text *" value={newCit.reference_text} onChange={e=>setNewCit(p=>({...p,reference_text:e.target.value}))} onKeyDown={e=>e.key==='Enter'&&addCit()}/>
              <input placeholder="Author" value={newCit.author} onChange={e=>setNewCit(p=>({...p,author:e.target.value}))}/>
              <input placeholder="URL" value={newCit.url} onChange={e=>setNewCit(p=>({...p,url:e.target.value}))}/>
            </div>
            <button className="btn-o" style={{marginTop:'.32rem',fontSize:'.58rem'}} onClick={addCit}>+ Add Citation</button>
          </FormField>
        </>
      ))}

      {activeTab==='translations'&&(
        <div>
          {!article?.id&&(
            <div style={{padding:'1.2rem',background:'var(--g100)',border:'var(--rt)',fontFamily:'var(--fm)',fontSize:'.68rem',color:'var(--g600)',marginBottom:'1.35rem',lineHeight:1.6}}>
              Save the article first (use "Save Draft" or "Publish"), then come back here to add translations.
            </div>
          )}
          {article?.id&&(
            <>
              {translations.length>0&&(
                <div style={{marginBottom:'1.85rem'}}>
                  <div className="form-lbl" style={{marginBottom:'.72rem'}}>Existing Translations</div>
                  {translations.map(t=>(
                    <div key={t.language} style={{marginBottom:'2px'}}>
                      <div style={{padding:'.72rem 1rem',border:'var(--rt)',display:'flex',justifyContent:'space-between',alignItems:'center',gap:'1rem',background:editingTrans?.language===t.language?'var(--g100)':'var(--paper)'}}>
                        <div>
                          <div style={{fontFamily:'var(--fh)',fontWeight:700,marginBottom:'.1rem'}}>{LANGS[t.language]||t.language}
                            <span style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g400)',fontWeight:400,textTransform:'uppercase',letterSpacing:'.06em',marginLeft:'.38rem'}}>{t.language}</span>
                          </div>
                          <div style={{fontFamily:'var(--fm)',fontSize:'.63rem',color:'var(--g500)'}}>{(t.title||'').slice(0,80)}{(t.title||'').length>80?'…':''}</div>
                        </div>
                        <div style={{display:'flex',gap:'.32rem',flexShrink:0}}>
                          <button className="btn-s" onClick={()=>setEditingTrans(editingTrans?.language===t.language?null:{...t})}>{editingTrans?.language===t.language?'Cancel':'Edit'}</button>
                          <button className="btn-s" onClick={()=>deleteTrans(t.language)}>✕</button>
                        </div>
                      </div>
                      {editingTrans?.language===t.language&&(
                        <div style={{padding:'1rem',background:'var(--g100)',border:'var(--rt)',borderTop:'none'}}>
                          <div className="form-g"><label className="form-lbl">Translated Title</label>
                            <input value={editingTrans.title||''} onChange={e=>setEditingTrans(p=>({...p,title:e.target.value}))}/></div>
                          <div className="form-g"><label className="form-lbl">Translated Excerpt</label>
                            <textarea value={editingTrans.excerpt||''} onChange={e=>setEditingTrans(p=>({...p,excerpt:e.target.value}))} style={{minHeight:60}}/></div>
                          <div className="form-g">
                            <label className="form-lbl" style={{display:'flex',alignItems:'center',gap:'.5rem'}}>Translated Content
                              <span className="ed-tabs" style={{marginLeft:'auto'}}>
                                <span className={`ed-tab${transCompose?' on':''}`} onClick={()=>setTransCompose(true)}>Typeset</span>
                                <span className={`ed-tab${!transCompose?' on':''}`} onClick={()=>setTransCompose(false)}>HTML</span>
                              </span></label>
                            {transCompose
                              ? <SemanticComposer value={editingTrans.content||''} onChange={v=>setEditingTrans(p=>({...p,content:v}))}/>
                              : <textarea value={editingTrans.content||''} onChange={e=>setEditingTrans(p=>({...p,content:e.target.value}))} style={{minHeight:200,fontFamily:'var(--fm)',fontSize:'.78rem'}}/>}
                          </div>
                          <button className="btn-p" disabled={savingTrans} onClick={async()=>{
                            const ok=await saveTrans(editingTrans);
                            if(ok)setEditingTrans(null);
                          }}>{savingTrans?'Saving…':'Save Changes'}</button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <div style={{padding:'1.2rem',border:'var(--rt)',background:'var(--paper)'}}>
                <div className="form-lbl" style={{marginBottom:'.72rem'}}>Add / Replace Translation</div>
                <div className="form-row" style={{marginBottom:'.72rem'}}>
                  <div className="form-g" style={{marginBottom:0}}>
                    <label className="form-lbl">Language</label>
                    <select value={newTrans.language} onChange={e=>setNewTrans(p=>({...p,language:e.target.value}))}>
                      {TRANS_LANGS.map(([code,name])=>(
                        <option key={code} value={code}>{name} ({code}){usedLangs.includes(code)?' ✓ exists':''}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-g" style={{marginBottom:0}}>
                    <label className="form-lbl">Translated Title</label>
                    <input value={newTrans.title} onChange={e=>setNewTrans(p=>({...p,title:e.target.value}))} placeholder="Headline in target language…"/>
                  </div>
                </div>
                <div className="form-g"><label className="form-lbl">Translated Excerpt</label>
                  <textarea value={newTrans.excerpt} onChange={e=>setNewTrans(p=>({...p,excerpt:e.target.value}))} placeholder="Summary in target language…" style={{minHeight:55}}/></div>
                <div className="form-g"><label className="form-lbl">Translated Content (HTML)</label>
                  <textarea value={newTrans.content} onChange={e=>setNewTrans(p=>({...p,content:e.target.value}))} placeholder="Paste translated HTML content here… (leave blank to use the original)" style={{minHeight:170,fontFamily:'var(--fm)',fontSize:'.78rem'}}/></div>
                <button className="btn-p" onClick={async()=>{
                  const ok=await saveTrans(newTrans);
                  if(ok)setNewTrans({language:'hi',title:'',excerpt:'',content:''});
                }} disabled={savingTrans}>{savingTrans?'Saving…':'Save Translation'}</button>
              </div>
            </>
          )}
        </div>
      )}

      {activeTab==='corrections'&&(
        <div>
          {!article?.id&&(
            <div style={{padding:'1.2rem',background:'var(--g100)',border:'var(--rt)',fontFamily:'var(--fm)',fontSize:'.68rem',color:'var(--g600)',marginBottom:'1.35rem',lineHeight:1.6}}>
              Save the article first, then come back here to publish corrections or retractions.
            </div>
          )}
          {article?.id&&(
            <>
              {corrections.length>0&&(
                <div style={{marginBottom:'1.85rem'}}>
                  <div className="form-lbl" style={{marginBottom:'.72rem'}}>Published Corrections</div>
                  {corrections.map(c=>(
                    <div key={c.id} style={{padding:'.72rem 1rem',border:'var(--rt)',marginBottom:'2px',display:'flex',justifyContent:'space-between',alignItems:'flex-start',gap:'1rem'}}>
                      <div>
                        <div style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:'.2rem'}}>
                          {c.severity} · {fmtDate(c.published_at)}
                        </div>
                        <div style={{fontFamily:'var(--fh)',fontWeight:700,marginBottom:'.15rem'}}>{c.title}</div>
                        <div style={{fontFamily:'var(--fb)',fontSize:'.85rem',color:'var(--g700)'}}>{c.body}</div>
                      </div>
                      <button className="btn-s" style={{flexShrink:0}} onClick={async()=>{
                        await API.del(`/api/corrections/${c.id}`).catch(()=>{});
                        setCorrections(prev=>prev.filter(x=>x.id!==c.id));
                      }}>✕</button>
                    </div>
                  ))}
                </div>
              )}
              <div style={{padding:'1.2rem',border:'var(--rt)',background:'var(--paper)'}}>
                <div className="form-lbl" style={{marginBottom:'.72rem'}}>Publish a Correction</div>
                <div className="form-row" style={{marginBottom:'.72rem'}}>
                  <div className="form-g" style={{marginBottom:0}}>
                    <label className="form-lbl">Title</label>
                    <input value={newCorrection.title} onChange={e=>setNewCorrection(p=>({...p,title:e.target.value}))} placeholder="Correction: date of the incident"/>
                  </div>
                  <div className="form-g" style={{marginBottom:0}}>
                    <label className="form-lbl">Severity</label>
                    <select value={newCorrection.severity} onChange={e=>setNewCorrection(p=>({...p,severity:e.target.value}))}>
                      <option value="minor">Minor</option>
                      <option value="major">Major</option>
                      <option value="retraction">Retraction</option>
                    </select>
                  </div>
                </div>
                <div className="form-g"><label className="form-lbl">What changed and why</label>
                  <textarea value={newCorrection.body} onChange={e=>setNewCorrection(p=>({...p,body:e.target.value}))} placeholder="An earlier version of this article stated…" style={{minHeight:90}}/></div>
                <button className="btn-p" disabled={savingCorrection} onClick={async()=>{
                  if(!newCorrection.title.trim()||!newCorrection.body.trim()){toast('Title and body required','err');return;}
                  setSavingCorrection(true);
                  const d=await API.post(`/api/articles/${article.id}/corrections`,newCorrection).catch(()=>({error:'Failed'}));
                  setSavingCorrection(false);
                  if(d.error){toast(d.error,'err');return;}
                  setCorrections(prev=>[d,...prev]);
                  setNewCorrection({title:'',body:'',severity:'minor'});
                  toast('Correction published.');
                }}>{savingCorrection?'Publishing…':'Publish Correction'}</button>
              </div>
            </>
          )}
        </div>
      )}

      {activeTab==='history'&&(
        <div>
          <div className="sec-lbl"><span>Version History</span></div>
          <p style={{fontFamily:'var(--fb)',fontStyle:'italic',color:'var(--g600)',marginBottom:'1.2rem',fontSize:'.95rem',lineHeight:1.6}}>
            Every save is snapshotted. View any past version, or restore it — the current text is kept as a new version, so nothing is ever lost.
          </p>
          {versions===null&&<div style={{color:'var(--g400)',fontFamily:'var(--fm)',fontSize:'.65rem'}}>Loading history…</div>}
          {versions&&versions.length===0&&<div style={{color:'var(--g400)',fontStyle:'italic',fontSize:'.9rem'}}>No versions yet — save the article to start its history.</div>}
          {versions&&versions.map((v,i)=>(
            <div key={v.id} style={{display:'flex',alignItems:'center',gap:'.6rem',padding:'.62rem 0',borderBottom:'var(--rt)'}}>
              <span style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g500)',minWidth:'2.6rem'}}>#{v.id}</span>
              <div style={{flex:1}}>
                <div style={{fontFamily:'var(--fh)',fontSize:'.92rem',fontWeight:600}}>
                  {v.message||'edited'}
                  {i===0&&<span className="tag on" style={{marginLeft:'.5rem',fontSize:'.5rem',padding:'.05rem .35rem'}}>current</span>}
                </div>
                <div style={{fontFamily:'var(--fm)',fontSize:'.57rem',color:'var(--g500)',marginTop:'.12rem'}}>
                  {v.display_name||'—'} · {(v.created_at||'').replace('T',' ').slice(0,16)} · {(v.size/1024).toFixed(1)} KB
                </div>
              </div>
              <button className="btn-s" onClick={()=>viewVersion(v.id)}>View</button>
              {i!==0&&<button className="btn-o" onClick={()=>restoreVersion(v.id)}>Restore</button>}
            </div>
          ))}
          {viewingV&&(
            <div className="img-modal-bg" onClick={e=>{if(e.target===e.currentTarget)setViewingV(null);}}>
              <div className="img-modal-box" style={{maxWidth:'780px',maxHeight:'84vh',overflowY:'auto'}}>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'.85rem'}}>
                  <div style={{fontFamily:'var(--fh)',fontWeight:700,fontSize:'1.05rem'}}>Version #{viewingV.id} · {viewingV.message}</div>
                  <button className="btn-o" onClick={()=>setViewingV(null)}>Close</button>
                </div>
                <h1 className="art-title" style={{fontSize:'1.5rem',marginBottom:'.4rem'}}>{viewingV.snapshot.title}</h1>
                {viewingV.snapshot.excerpt&&<div className="art-deck" style={{marginBottom:'.6rem'}}>{viewingV.snapshot.excerpt}</div>}
                <div className="art-content" dangerouslySetInnerHTML={{__html:viewingV.snapshot.content||'<p><em>empty</em></p>'}}/>
                <div style={{marginTop:'1.1rem',display:'flex',justifyContent:'flex-end'}}>
                  <button className="btn-p" onClick={()=>{const id=viewingV.id;setViewingV(null);restoreVersion(id);}}>Restore this version</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {showImgModal&&(
        <div className="img-modal-bg" onClick={e=>{if(e.target===e.currentTarget){setShowImgModal(false);setImgUploading(false);}}}>
          <div className="img-modal-box">
            <div style={{fontFamily:'var(--fh)',fontSize:'1.15rem',fontWeight:700,marginBottom:'1.15rem'}}>Insert Image</div>

            <div style={{marginBottom:'1.1rem'}}>
              <div className="form-lbl" style={{marginBottom:'.38rem'}}>Upload from device</div>
              <input type="file" accept="image/*" ref={imgFileRef} onChange={handleImgUpload} disabled={imgUploading} style={{border:'none',padding:0}}/>
              {imgUploading&&<div style={{marginTop:'.4rem',fontFamily:'var(--fm)',fontSize:'.62rem',color:'var(--g500)'}}>Uploading…</div>}
            </div>

            <div style={{textAlign:'center',fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g400)',margin:'.65rem 0'}}>— or —</div>

            <div>
              <div className="form-lbl" style={{marginBottom:'.38rem'}}>Image URL</div>
              <div style={{display:'flex',gap:'.45rem'}}>
                <input value={imgUrl} onChange={e=>setImgUrl(e.target.value)} placeholder="https://…"
                  onKeyDown={e=>{if(e.key==='Enter')insertImage(imgUrl);}}
                  disabled={imgUploading}/>
                <button className="btn-p" onClick={()=>insertImage(imgUrl)} disabled={!imgUrl.trim()||imgUploading}>Insert</button>
              </div>
            </div>

            <div style={{marginTop:'1.1rem',display:'flex',justifyContent:'flex-end'}}>
              <button className="btn-o" onClick={()=>{setShowImgModal(false);setImgUploading(false);}}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FormLabel({label,children}){
  return <div className="form-g"><label className="form-lbl">{label}</label>{children}</div>;
}

function AdminNewsletterTab({toast,setView}){
  const [newsletters,setNewsletters]=useState([]);
  const [loading,setLoading]=useState(true);

  useEffect(()=>{
    API.get('/api/newsletters')
      .then(d=>{setNewsletters(safe(d));setLoading(false);})
      .catch(()=>setLoading(false));
  },[]);

  const regen=async()=>{
    await API.post('/api/newsletters/regenerate',{}).catch(()=>{});
    const d=await API.get('/api/newsletters').catch(()=>[]);
    setNewsletters(safe(d));
    toast('Newsletter regenerated for this month!');
  };

  const del=async(n)=>{
    if(!confirm(`Delete "${n.title}"?\nThis cannot be undone.`))return;
    const r=await API.del(`/api/newsletters/${n.id}`).catch(()=>null);
    if(r&&r.success){
      setNewsletters(ns=>ns.filter(x=>x.id!==n.id));
      toast('Edition deleted');
    }else{
      toast('Delete failed','err');
    }
  };

  return(
    <div>
      <div className="sec-lbl"><span>Newsletter Manager</span></div>
      <p style={{fontFamily:'var(--fb)',fontStyle:'italic',color:'var(--g600)',marginBottom:'1.35rem',lineHeight:1.65,fontSize:'1rem'}}>
        The monthly newsletter auto-assembles from the latest published articles on first access each month.
        Regenerate to rebuild with fresh content after adding new stories.
      </p>
      <div style={{display:'flex',gap:'.45rem',flexWrap:'wrap',marginBottom:'1.8rem'}}>
        <button className="btn-p" onClick={regen}>↻ Regenerate This Month</button>
        <button className="btn-o" onClick={()=>setView('newsletter')}>View Newsletter →</button>
      </div>

      {loading&&<div style={{color:'var(--g400)',fontFamily:'var(--fm)',fontSize:'.65rem'}}>Loading…</div>}
      {!loading&&newsletters.length===0&&(
        <div style={{color:'var(--g400)',fontFamily:'var(--fb)',fontStyle:'italic',fontSize:'.9rem'}}>
          No newsletter editions yet.
        </div>
      )}
      {!loading&&newsletters.length>0&&(
        <>
          <div style={{fontFamily:'var(--fm)',fontSize:'.57rem',letterSpacing:'.14em',textTransform:'uppercase',
            color:'var(--g500)',borderBottom:'var(--rt)',paddingBottom:'.35rem',marginBottom:'.5rem'}}>
            All Editions ({newsletters.length})
          </div>
          {newsletters.map(n=>{
            const monthStr=new Date(2000,(n.month||1)-1).toLocaleString('default',{month:'long'});
            return(
              <div key={n.id} style={{display:'flex',alignItems:'center',gap:'.6rem',
                padding:'.55rem 0',borderBottom:'var(--rt)'}}>
                <span style={{flex:1,fontFamily:'var(--fh)',fontSize:'.9rem',fontWeight:600,lineHeight:1.3}}>
                  {n.title}
                </span>
                <span style={{fontFamily:'var(--fm)',fontSize:'.52rem',color:'var(--g400)',
                  letterSpacing:'.05em',flexShrink:0,whiteSpace:'nowrap'}}>
                  {monthStr} {n.year}
                </span>
                {window.DesignDashboard&&<button className="btn-s"
                  style={{fontSize:'.5rem',flexShrink:0}}
                  title="Custom PDF design: preview, custom CSS, screenshot-verify"
                  onClick={()=>window.DesignDashboard.showModal('broadsheet',n.id,`Design Editor: ${n.title}`)}>
                  🎨 Design
                </button>}
                <button className="btn-s"
                  style={{fontSize:'.5rem',borderColor:'#c44',color:'#c44',flexShrink:0}}
                  onClick={()=>del(n)}>
                  ✕ Delete
                </button>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}

