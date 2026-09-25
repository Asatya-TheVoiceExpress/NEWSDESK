function AdminPages({toast}){
  const [pages,setPages]=useState([]);
  const [editing,setEditing]=useState(null); 
  const [saving,setSaving]=useState(false);
  const editorRef=useRef(null);
  const quillRef=useRef(null);

  useEffect(()=>{
    API.get('/api/pages').then(setPages).catch(()=>{});
  },[]);

  const openPage=async(slug)=>{
    const d=await API.get('/api/pages/'+slug).catch(()=>null);
    if(!d)return;
    setEditing({...d});
    setTimeout(()=>{
      if(!quillRef.current&&editorRef.current){
        quillRef.current=new Quill(editorRef.current,{theme:'snow',modules:{toolbar:[
          [{header:[1,2,3,false]}],['bold','italic','underline'],
          [{list:'ordered'},{list:'bullet'}],['link'],['clean']
        ]}});
        quillRef.current.on('text-change',()=>{
          setEditing(p=>({...p,content:quillRef.current.root.innerHTML}));
        });
      }
      if(quillRef.current) quillRef.current.root.innerHTML=d.content||'';
    },80);
  };

  const closeEditor=()=>{
    setEditing(null);
    if(quillRef.current){quillRef.current=null;}
  };

  const save=async()=>{
    if(!editing)return;
    setSaving(true);
    const r=await API.put('/api/pages/'+editing.slug,{title:editing.title,content:editing.content}).catch(()=>({error:'Network error'}));
    setSaving(false);
    if(r.error){toast(r.error,'err');return;}
    toast('Page saved.');
    setPages(ps=>ps.map(p=>p.slug===editing.slug?{...p,title:editing.title}:p));
    closeEditor();
  };

  if(editing) return(
    <div style={{padding:'1.5rem'}}>
      <div style={{display:'flex',gap:'.5rem',alignItems:'center',marginBottom:'1rem'}}>
        <button className="btn-s" onClick={closeEditor}>← Back</button>
        <span style={{fontFamily:'var(--fm)',fontSize:'.68rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.1em'}}>
          Editing: {editing.slug}
        </span>
      </div>
      <div style={{marginBottom:'.75rem'}}>
        <div className="form-lbl">Page Title</div>
        <input className="form-inp" value={editing.title}
          onChange={e=>setEditing(p=>({...p,title:e.target.value}))}/>
      </div>
      <div className="form-lbl" style={{marginBottom:'.4rem'}}>Content</div>
      <div ref={editorRef} style={{minHeight:'380px',background:'var(--paper)',color:'var(--ink)'}}/>
      <div style={{marginTop:'1rem',display:'flex',gap:'.5rem'}}>
        <button className="btn-p" onClick={save} disabled={saving}>{saving?'Saving…':'Save Page'}</button>
        <button className="btn-o" onClick={closeEditor}>Cancel</button>
      </div>
    </div>
  );

  return(
    <div style={{padding:'1.5rem'}}>
      <div style={{fontFamily:'var(--fm)',fontSize:'.65rem',textTransform:'uppercase',letterSpacing:'.12em',color:'var(--g500)',marginBottom:'1.2rem'}}>
        Editable Pages — About, Submissions, and other static content
      </div>
      {pages.map(p=>(
        <div key={p.slug} style={{display:'flex',alignItems:'center',gap:'1rem',padding:'.8rem 1rem',border:'var(--rt)',marginBottom:'.5rem',background:'var(--g100)'}}>
          <div style={{flex:1}}>
            <div style={{fontFamily:'var(--fb)',fontWeight:600}}>{p.title}</div>
            <div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g500)',marginTop:'.15rem'}}>/{p.slug} · updated {(p.updated_at||'').slice(0,10)}</div>
          </div>
          <button className="btn-s" onClick={()=>openPage(p.slug)}>Edit →</button>
        </div>
      ))}
      {pages.length===0&&<div style={{color:'var(--g400)',fontStyle:'italic'}}>No pages found.</div>}
    </div>
  );
}

function LineChart({data}){
  if(!data||!data.labels||data.labels.length<2)return null;
  const W=540,H=170,PL=36,PR=6,PT=6,PB=26;
  const iW=W-PL-PR,iH=H-PT-PB,n=data.labels.length;
  const allVals=data.series.flatMap(s=>s.values);
  const maxVal=Math.max(...allVals,1);
  const xp=i=>PL+i*(iW/Math.max(n-1,1));
  const yp=v=>PT+iH-(v/maxVal)*iH;
  const bezier=vals=>{
    const pts=vals.map((v,i)=>[xp(i),yp(v)]);
    let d=`M${pts[0][0]},${pts[0][1]}`;
    for(let i=1;i<pts.length;i++){
      const cx=(pts[i-1][0]+pts[i][0])/2;
      d+=` C${cx},${pts[i-1][1]} ${cx},${pts[i][1]} ${pts[i][0]},${pts[i][1]}`;
    }
    return d;
  };
  const step=Math.max(1,Math.ceil(n/9));
  const ticks=[0,Math.round(maxVal/2),maxVal];
  const strokes=['currentColor','#a8a8a6','#d0d0ce'];
  const sw=[2,1.5,1.5];
  return(
    <svg viewBox={`0 0 ${W} ${H}`} style={{width:'100%',height:'auto',display:'block',overflow:'visible'}}>
      {ticks.map((v,i)=>(
        <g key={i}>
          <line x1={PL} y1={yp(v)} x2={W-PR} y2={yp(v)} stroke="currentColor" strokeOpacity=".08" strokeWidth="1"/>
          <text x={PL-3} y={yp(v)+4} textAnchor="end" fontSize="8" fill="currentColor" fillOpacity=".4" fontFamily="monospace">{v}</text>
        </g>
      ))}
      {data.labels.map((lbl,i)=>{
        if(i%step!==0&&i!==n-1)return null;
        return <text key={i} x={xp(i)} y={H-2} textAnchor="middle" fontSize="8" fill="currentColor" fillOpacity=".4" fontFamily="monospace">{lbl.slice(5)}</text>;
      })}
      {data.series.map((s,si)=>(
        <g key={s.name}>
          <path d={bezier(s.values)} fill="none" stroke={strokes[si]} strokeWidth={sw[si]} strokeOpacity={si===0?1:.7} strokeLinejoin="round"/>
          {s.values.map((v,i)=>v>0&&(
            <circle key={i} cx={xp(i)} cy={yp(v)} r={si===0?3:2} fill={strokes[si]} fillOpacity={si===0?1:.7}>
              <title>{data.labels[i]}: {v}</title>
            </circle>
          ))}
        </g>
      ))}
    </svg>
  );
}

function AdminAnalytics(){
  const [period,setPeriod]=useState('90');
  const [analytics,setAnalytics]=useState(null);
  const [loading,setLoading]=useState(false);
  const [locations,setLocations]=useState(null);
  const [locLoading,setLocLoading]=useState(false);
  const [artSort,setArtSort]=useState('reads');
  const locMapRef=useRef(null);
  const locMapInst=useRef(null);

  const load=useCallback(()=>{
    setLoading(true);
    API.get(`/api/analytics?period=${period}`)
      .then(d=>setAnalytics(d)).catch(()=>{}).finally(()=>setLoading(false));
  },[period]);
  useEffect(()=>{load();},[load]);

  const loadLocations=async()=>{
    setLocLoading(true);
    const d=await API.get('/api/analytics/locations').catch(()=>null);
    setLocations(d);setLocLoading(false);
  };

  const chartData=useMemo(()=>{
    if(!analytics)return null;
    const allM=new Set([
      ...(analytics.monthly_pubs||[]).map(r=>r.month),
      ...(analytics.monthly_reads||[]).map(r=>r.month),
      ...(analytics.monthly_comments||[]).map(r=>r.month),
    ]);
    const labels=[...allM].sort();
    if(!labels.length)return null;
    const pm=Object.fromEntries((analytics.monthly_pubs||[]).map(r=>[r.month,r.count]));
    const rm=Object.fromEntries((analytics.monthly_reads||[]).map(r=>[r.month,r.count]));
    const cm=Object.fromEntries((analytics.monthly_comments||[]).map(r=>[r.month,r.count]));
    return{labels,series:[
      {name:'Published', values:labels.map(m=>pm[m]||0)},
      {name:'Reads',     values:labels.map(m=>rm[m]||0)},
      {name:'Comments',  values:labels.map(m=>cm[m]||0)},
    ]};
  },[analytics]);

  useEffect(()=>{
    if(!locations?.locations?.length||!locMapRef.current)return;
    if(locMapInst.current){try{locMapInst.current.remove();}catch{}locMapInst.current=null;}
    setTimeout(()=>{
      const el=locMapRef.current;if(!el)return;
      const map=L.map(el).setView([20,0],2);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(map);
      locMapInst.current=map;
      locations.locations.forEach(l=>{
        L.circleMarker([l.lat,l.lon],{radius:Math.max(4,Math.min(16,Math.sqrt(l.count)*5)),
          color:'#0a0a0a',fillColor:'#0a0a0a',fillOpacity:.45,weight:1})
          .addTo(map).bindPopup(`${l.city?l.city+', ':''}${l.country||'Unknown'} (${l.count})`);
      });
    },80);
    return()=>{if(locMapInst.current){try{locMapInst.current.remove();}catch{}locMapInst.current=null;}};
  },[locations]);

  const sortedArts=useMemo(()=>{
    const a=safe(analytics?.article_analytics);
    if(artSort==='comments')return[...a].sort((x,y)=>y.comment_count-x.comment_count);
    if(artSort==='date')return[...a].sort((x,y)=>new Date(y.published_at)-new Date(x.published_at));
    return[...a].sort((x,y)=>y.total_reads-x.total_reads);
  },[analytics,artSort]);

  return(
    <div>
      <div style={{display:'flex',gap:'.32rem',marginBottom:'1.35rem',flexWrap:'wrap',alignItems:'center'}}>
        {[['30','30 days'],['90','90 days'],['365','1 year'],['all','All time']].map(([v,l])=>(
          <button key={v} className={`btn-s${period===v?' on':''}`} onClick={()=>setPeriod(v)}>{l}</button>
        ))}
        <button className="btn-s" style={{marginLeft:'auto'}} onClick={load}>↻ Refresh</button>
      </div>

      {loading&&<div className="loading">Loading analytics</div>}
      {!loading&&!analytics&&<div className="empty"><div className="empty-sub">No data yet.</div></div>}

      {analytics&&(
        <>
          <div className="stats-grid" style={{marginBottom:'1.85rem'}}>
            {[['Published',(analytics.monthly_pubs||[]).reduce((s,r)=>s+r.count,0)],
              ['Total Reads',analytics.total_reads||0],
              ['Readers',analytics.reader_count||0],
              ['Comments',analytics.comment_count||0],
              ['Pending ↩',analytics.pending_comments||0],
              ['Letters',analytics.letter_count||0],
              ['Puzzles',analytics.puzzle_count||0],
            ].map(([l,n])=>(
              <div key={l} className="stat-box"><div className="stat-num">{n}</div><div className="stat-lbl">{l}</div></div>
            ))}
          </div>

          {chartData&&(
            <div style={{marginBottom:'1.85rem'}}>
              <div className="sec-lbl"><span>Activity Over Time</span></div>
              <div style={{display:'flex',gap:'1rem',marginBottom:'.42rem',flexWrap:'wrap'}}>
                {['Published','Reads','Comments'].map((n,i)=>(
                  <span key={n} style={{fontFamily:'var(--fm)',fontSize:'.58rem',letterSpacing:'.06em',textTransform:'uppercase',display:'flex',alignItems:'center',gap:'.3rem',opacity:[1,.7,.55][i]}}>
                    <span style={{width:16,height:2,background:'currentColor',display:'inline-block',verticalAlign:'middle'}}/>
                    {n}
                  </span>
                ))}
              </div>
              <LineChart data={chartData}/>
            </div>
          )}

          <div style={{marginBottom:'1.85rem'}}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'.72rem',flexWrap:'wrap',gap:'.32rem'}}>
              <div className="sec-lbl" style={{margin:0}}><span>Article Performance</span></div>
              <div style={{display:'flex',gap:'.25rem'}}>
                {[['reads','Reads'],['comments','Comments'],['date','Date']].map(([v,l])=>(
                  <button key={v} className={`btn-s${artSort===v?' on':''}`} onClick={()=>setArtSort(v)} style={{fontSize:'.56rem'}}>{l}</button>
                ))}
              </div>
            </div>
            <div style={{overflowX:'auto'}}>
              <table className="art-tbl">
                <thead><tr><th>Title</th><th>Author</th><th>Section</th><th>Published</th><th style={{textAlign:'right'}}>Reads</th><th style={{textAlign:'right'}}>Comments</th><th style={{textAlign:'right'}}>Min</th></tr></thead>
                <tbody>
                  {sortedArts.map(a=>(
                    <tr key={a.id}>
                      <td style={{fontFamily:'var(--fh)',fontWeight:600,maxWidth:200,wordBreak:'break-word',lineHeight:1.3,fontSize:'.85rem'}}>{a.title}</td>
                      <td style={{fontFamily:'var(--fm)',fontSize:'.65rem',whiteSpace:'nowrap'}}>{a.author_name||'—'}</td>
                      <td style={{fontFamily:'var(--fm)',fontSize:'.63rem'}}>{a.category_name||'—'}</td>
                      <td style={{fontFamily:'var(--fm)',fontSize:'.63rem',whiteSpace:'nowrap'}}>{fmtShort(a.published_at)}</td>
                      <td style={{fontFamily:'var(--fh)',fontWeight:700,textAlign:'right'}}>{a.total_reads||0}</td>
                      <td style={{fontFamily:'var(--fh)',fontWeight:700,textAlign:'right'}}>{a.comment_count||0}</td>
                      <td style={{fontFamily:'var(--fm)',fontSize:'.65rem',textAlign:'right',color:'var(--g500)'}}>{a.reading_time||1}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {chartData&&chartData.labels.length>1&&(
            <div style={{marginBottom:'1.85rem'}}>
              <div className="sec-lbl"><span>Month by Month</span></div>
              <div style={{overflowX:'auto'}}>
                <table className="art-tbl">
                  <thead><tr><th>Month</th><th style={{textAlign:'right'}}>Published</th><th style={{textAlign:'right'}}>Reads</th><th style={{textAlign:'right'}}>Comments</th></tr></thead>
                  <tbody>
                    {[...chartData.labels].reverse().map(m=>{
                      const idx=chartData.labels.indexOf(m);
                      const name=new Date(m+'-15').toLocaleDateString('en-GB',{month:'long',year:'numeric'});
                      return(
                        <tr key={m}>
                          <td style={{fontFamily:'var(--fh)',fontWeight:600}}>{name}</td>
                          <td style={{fontFamily:'var(--fh)',fontWeight:700,textAlign:'right'}}>{chartData.series[0].values[idx]||0}</td>
                          <td style={{fontFamily:'var(--fh)',fontWeight:700,textAlign:'right'}}>{chartData.series[1].values[idx]||0}</td>
                          <td style={{fontFamily:'var(--fh)',fontWeight:700,textAlign:'right'}}>{chartData.series[2].values[idx]||0}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div style={{marginBottom:'1.85rem'}}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'.72rem',flexWrap:'wrap',gap:'.32rem'}}>
              <div className="sec-lbl" style={{margin:0}}><span>Reader Locations</span></div>
              <button className="btn-s" onClick={loadLocations} disabled={locLoading}>
                {locLoading?'Geolocating…':'⊕ Geolocate Reader IPs'}
              </button>
            </div>
            {locations&&<div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g500)',marginBottom:'.52rem'}}>{locations.geolocated} locations from {locations.total_ips} unique IPs (from comments + letters)</div>}
            {locLoading&&<div className="loading" style={{minHeight:'10vh'}}>Contacting ip-api.com</div>}
            {locations?.locations?.length>0&&(
              <div ref={locMapRef} style={{height:280,border:'var(--rule)'}}/>
            )}
            {locations&&!locations.locations?.length&&!locLoading&&(
              <div style={{padding:'1.1rem',background:'var(--g100)',border:'var(--rt)',fontFamily:'var(--fb)',fontStyle:'italic',color:'var(--g500)',fontSize:'.9rem'}}>
                No public IPs on record yet. Submit a comment or letter to start tracking.
              </div>
            )}
          </div>

          <div className="form-row" style={{alignItems:'start',gap:'2rem'}}>
            {analytics.top_authors?.length>0&&(
              <div>
                <div className="sec-lbl"><span>Top Authors</span></div>
                {analytics.top_authors.map(a=>(
                  <div key={a.name} style={{display:'flex',justifyContent:'space-between',padding:'.32rem 0',borderBottom:'var(--rt)'}}>
                    <span style={{fontFamily:'var(--fh)',fontWeight:600,fontSize:'.88rem'}}>{a.name}</span>
                    <span style={{fontFamily:'var(--fm)',fontSize:'.62rem',color:'var(--g500)'}}>{a.count}</span>
                  </div>
                ))}
              </div>
            )}
            {analytics.top_tags?.length>0&&(
              <div>
                <div className="sec-lbl"><span>Popular Tags</span></div>
                <div style={{display:'flex',flexWrap:'wrap',gap:'.28rem'}}>
                  {analytics.top_tags.map(t=>(
                    <span key={t.name} className="tag on" style={{fontSize:'.58rem'}}>{t.name} <span style={{opacity:.55}}>({t.count})</span></span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function AdminMailbox({toast,currentUser}){
  const [letters,setLetters]=useState([]);
  const [open,setOpen]=useState(null);
  const [thread,setThread]=useState(null);
  const [reply,setReply]=useState('');
  const [loading,setLoading]=useState(true);

  useEffect(()=>{
    API.get('/api/letters').then(d=>{setLetters(safe(d));setLoading(false);}).catch(()=>{setLoading(false);});
  },[]);

  const openThread=async id=>{
    setOpen(id);
    const d=await API.get(`/api/letters/${id}`).catch(()=>null);
    if(d)setThread(d);
  };
  const sendReply=async()=>{
    if(!reply.trim())return;
    const r=await API.post(`/api/letters/${open}/reply`,{content:reply}).catch(()=>({error:'Failed'}));
    if(r.error){toast(r.error,'err');return;}
    setReply('');openThread(open);toast('Reply sent.');
  };
  const closeThread=async()=>{
    await API.post(`/api/letters/${open}/close`,{});
    setThread(t=>t?{...t,status:'closed'}:t);
    setLetters(p=>p.map(l=>l.id===open?{...l,status:'closed'}:l));
  };

  const statusBadge={open:'var(--g500)',replied:'var(--ink)',closed:'var(--g300)'};

  if(open&&thread){
    return(
      <div>
        <button className="btn-o" style={{marginBottom:'1.2rem'}} onClick={()=>{setOpen(null);setThread(null);}}>← Mailbox</button>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1rem',flexWrap:'wrap',gap:'.5rem'}}>
          <div>
            <div style={{fontFamily:'var(--fh)',fontSize:'1.22rem',fontWeight:700}}>{thread.subject}</div>
            <div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.06em',marginTop:'.15rem'}}>
              From: {thread.username||thread.guest_name||'Anonymous'} · Status: <span style={{color:statusBadge[thread.status]}}>{thread.status}</span>
            </div>
          </div>
          {thread.status!=='closed'&&<button className="btn-s" onClick={closeThread}>Close Thread</button>}
        </div>
        <div style={{border:'var(--rule)',marginBottom:'1rem'}}>
          {safe(thread.messages).map((m,i)=>(
            <div key={i} style={{padding:'.88rem 1.1rem',borderBottom:'var(--rt)',background:m.sender==='admin'?'var(--g100)':'var(--paper)',borderLeft:m.sender==='admin'?'3px solid var(--ink)':'none'}}>
              <div style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:'.32rem'}}>
                {m.sender==='admin'?'Voice Express Editorial':'Reader'} · {fmtDate(m.created_at)}
              </div>
              <div style={{fontFamily:'var(--fb)',fontSize:'.95rem',lineHeight:1.65,whiteSpace:'pre-wrap'}}>{m.content}</div>
            </div>
          ))}
        </div>
        {thread.status!=='closed'&&(
          <div>
            <textarea value={reply} onChange={e=>setReply(e.target.value)} placeholder="Write a reply from the editorial team…" style={{minHeight:90,marginBottom:'.5rem'}}/>
            <button className="btn-p" onClick={sendReply} disabled={!reply.trim()}>Send Reply</button>
          </div>
        )}
      </div>
    );
  }

  return(
    <div>
      <div className="sec-lbl"><span>Mailbox — Reader Letters</span></div>
      {loading&&<div className="loading">Loading</div>}
      {!loading&&!letters.length&&<div className="empty"><div className="empty-title">No letters yet</div></div>}
      {letters.map(l=>(
        <div key={l.id} style={{padding:'.72rem 1rem',border:'var(--rt)',marginBottom:'2px',cursor:'pointer',display:'grid',gridTemplateColumns:'1fr auto',gap:'1rem',alignItems:'center',background:'var(--paper)'}}
          onClick={()=>openThread(l.id)}
          onMouseOver={e=>e.currentTarget.style.background='var(--g100)'}
          onMouseOut={e=>e.currentTarget.style.background='var(--paper)'}>
          <div>
            <div style={{fontFamily:'var(--fh)',fontWeight:700,fontSize:'.92rem'}}>{l.subject}</div>
            <div style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',textTransform:'uppercase',marginTop:'.1rem'}}>
              {l.username||l.guest_name||'Anonymous'} · {fmtDate(l.last_message_at)}
            </div>
            {l.last_msg&&<div style={{fontFamily:'var(--fb)',fontSize:'.8rem',color:'var(--g600)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',marginTop:'.1rem'}}>{l.last_msg}</div>}
          </div>
          <span style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:statusBadge[l.status]||'var(--ink)',textTransform:'uppercase',letterSpacing:'.06em',flexShrink:0}}>{l.status}</span>
        </div>
      ))}
    </div>
  );
}

function AdminComments({toast}){
  const [comments,setComments]=useState([]);
  const [statusFilter,setStatusFilter]=useState('pending');
  const [loading,setLoading]=useState(false);

  const load=s=>{
    setLoading(true);
    API.get(`/api/comments?status=${s||statusFilter}`)
      .then(d=>{setComments(safe(d));setLoading(false);})
      .catch(()=>setLoading(false));
  };
  useEffect(()=>{load();},[]);

  const moderate=(id,status)=>{
    API.put(`/api/comments/${id}`,{status}).then(()=>{
      setComments(p=>p.filter(c=>c.id!==id));
      toast(`Comment ${status}.`);
    }).catch(()=>toast('Failed','err'));
  };
  const del=(id)=>{
    API.del(`/api/comments/${id}`).then(()=>{
      setComments(p=>p.filter(c=>c.id!==id));
      toast('Deleted.');
    }).catch(()=>toast('Failed','err'));
  };
  const changeFilter=s=>{setStatusFilter(s);load(s);};

  return(
    <div>
      <div style={{display:'flex',gap:'.32rem',marginBottom:'1.35rem',flexWrap:'wrap'}}>
        {['pending','approved','rejected','spam'].map(s=>(
          <button key={s} className={`btn-s${statusFilter===s?' on':''}`} onClick={()=>changeFilter(s)}>{s.charAt(0).toUpperCase()+s.slice(1)}</button>
        ))}
        <button className="btn-s" style={{marginLeft:'auto'}} onClick={()=>load()}>↻ Refresh</button>
      </div>
      {loading&&<div className="loading">Loading</div>}
      {!loading&&!comments.length&&<div className="empty"><div className="empty-title">No {statusFilter} comments</div></div>}
      {comments.map(c=>(
        <div key={c.id} style={{padding:'.82rem 1rem',border:'var(--rt)',marginBottom:'2px',background:'var(--paper)'}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',gap:'1rem',flexWrap:'wrap'}}>
            <div style={{flex:1}}>
              <div style={{display:'flex',alignItems:'center',gap:'.52rem',flexWrap:'wrap',marginBottom:'.32rem'}}>
                <span style={{fontFamily:'var(--fh)',fontWeight:700,fontSize:'.92rem'}}>{c.display_name}</span>
                <span style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)'}}>{fmtDate(c.created_at)}</span>
                <span style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g400)',background:'var(--g100)',padding:'.06rem .35rem'}}>IP: {c.ip_address||'unknown'}</span>
              </div>
              <div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g600)',marginBottom:'.28rem'}}>
                On: <em>{c.article_title}</em>
              </div>
              <div style={{fontFamily:'var(--fb)',fontSize:'.9rem',lineHeight:1.55,color:'var(--g700)'}}>{c.content}</div>
            </div>
            <div style={{display:'flex',gap:'.25rem',flexShrink:0,flexWrap:'wrap'}}>
              {statusFilter!=='approved'&&<button className="btn-s" onClick={()=>moderate(c.id,'approved')}>✓ Approve</button>}
              {statusFilter!=='rejected'&&<button className="btn-s" onClick={()=>moderate(c.id,'rejected')}>✕ Reject</button>}
              {statusFilter!=='spam'&&<button className="btn-s" onClick={()=>moderate(c.id,'spam')}>⊘ Spam</button>}
              <button className="btn-s" onClick={()=>del(c.id)}>Delete</button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function AdminSheetMirrors({toast}){
  const TABS=[
    ['subscribers','Subscribers','/api/admin/subscribers'],
    ['messages','Messages','/api/admin/site-messages'],
    ['activity','Activity','/api/admin/activity'],
    ['accounts','Newsstand Accounts','/api/admin/newsstand-accounts'],
    ['annotations','Annotations','/api/admin/sheet-annotations'],
  ];
  const [sub,setSub]=useState('subscribers');
  const [rows,setRows]=useState([]);
  const [loading,setLoading]=useState(true);

  const load=key=>{
    const t=TABS.find(x=>x[0]===(key||sub));
    setLoading(true);
    API.get(t[2]).then(d=>{setRows(safe(d));setLoading(false);}).catch(()=>{setRows([]);setLoading(false);toast('Failed to load','err');});
  };
  useEffect(()=>{load(sub);},[sub]);

  return(
    <div>
      <div className="sec-lbl"><span>Sheet Data — Newsstand / static-build Google Sheet</span></div>
      <div style={{display:'flex',gap:'.32rem',marginBottom:'.7rem',flexWrap:'wrap'}}>
        {TABS.map(([k,l])=>(
          <button key={k} className={`btn-s${sub===k?' on':''}`} onClick={()=>setSub(k)}>{l}</button>
        ))}
        <button className="btn-s" style={{marginLeft:'auto'}} onClick={()=>load()}>↻ Refresh</button>
      </div>
      <div style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',marginBottom:'1.35rem'}}>
        Read-only. Run <code>python site_data_get.py</code> to pull fresh data out of the Sheet into these tables.
      </div>
      {loading&&<div className="loading">Loading</div>}
      {!loading&&!rows.length&&<div className="empty"><div className="empty-title">Nothing here yet</div></div>}

      {!loading&&sub==='subscribers'&&rows.length>0&&(
        <table className="art-tbl">
          <thead><tr><th>Email</th><th>Subscribed</th><th>IP</th></tr></thead>
          <tbody>{rows.map(r=>(
            <tr key={r.id}>
              <td style={{fontFamily:'var(--fm)',fontSize:'.75rem'}}>{r.email}</td>
              <td style={{fontFamily:'var(--fm)',fontSize:'.65rem'}}>{fmtDate(r.subscribed_at)}</td>
              <td style={{fontFamily:'var(--fm)',fontSize:'.65rem',color:'var(--g500)'}}>{r.ip_address||'—'}</td>
            </tr>
          ))}</tbody>
        </table>
      )}

      {!loading&&sub==='messages'&&rows.map(r=>(
        <div key={r.id} style={{padding:'.82rem 1rem',border:'var(--rt)',marginBottom:'2px',background:'var(--paper)'}}>
          <div style={{display:'flex',alignItems:'center',gap:'.52rem',flexWrap:'wrap',marginBottom:'.32rem'}}>
            <span style={{fontFamily:'var(--fh)',fontWeight:700,fontSize:'.92rem'}}>{r.from_name||'Anonymous'}</span>
            <span style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)'}}>{fmtDate(r.created_at)}</span>
            {r.ip_address&&<span style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g400)',background:'var(--g100)',padding:'.06rem .35rem'}}>IP: {r.ip_address}</span>}
          </div>
          {r.about&&<div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g600)',marginBottom:'.28rem'}}>About: <em>{r.about}</em></div>}
          <div style={{fontFamily:'var(--fb)',fontSize:'.9rem',lineHeight:1.55,color:'var(--g700)',whiteSpace:'pre-wrap'}}>{r.body}</div>
        </div>
      ))}

      {!loading&&sub==='activity'&&rows.length>0&&(
        <table className="art-tbl">
          <thead><tr><th>Time</th><th>Kind</th><th>Title / Ref</th><th>Amount</th><th>Via</th><th>User</th><th>IP</th></tr></thead>
          <tbody>{rows.map(r=>(
            <tr key={r.id}>
              <td style={{fontFamily:'var(--fm)',fontSize:'.62rem',whiteSpace:'nowrap'}}>{fmtDate(r.occurred_at)}</td>
              <td><span className="s-badge">{r.kind}</span></td>
              <td style={{fontSize:'.8rem',maxWidth:220,wordBreak:'break-word'}}>{r.title||r.ref||'—'}</td>
              <td style={{fontFamily:'var(--fm)',fontSize:'.68rem'}}>{r.amount?`${r.amount} ${r.currency||''}`:'—'}</td>
              <td style={{fontFamily:'var(--fm)',fontSize:'.65rem'}}>{r.via||'—'}</td>
              <td style={{fontFamily:'var(--fm)',fontSize:'.65rem'}}>{r.username||'—'}</td>
              <td style={{fontFamily:'var(--fm)',fontSize:'.62rem',color:'var(--g500)'}}>{r.ip_address||'—'}</td>
            </tr>
          ))}</tbody>
        </table>
      )}

      {!loading&&sub==='accounts'&&rows.length>0&&(
        <table className="art-tbl">
          <thead><tr><th>Username</th><th>Library</th><th>Hearts</th><th>Created</th></tr></thead>
          <tbody>{rows.map(r=>{
            let libCount=0; try{libCount=(JSON.parse(r.library||'[]')||[]).length;}catch(e){}
            return (
              <tr key={r.username}>
                <td style={{fontFamily:'var(--fh)',fontWeight:600}}>{r.username}</td>
                <td style={{fontFamily:'var(--fm)',fontSize:'.68rem'}}>{libCount} saved</td>
                <td style={{fontFamily:'var(--fm)',fontSize:'.68rem'}}>{r.hearts||0}</td>
                <td style={{fontFamily:'var(--fm)',fontSize:'.65rem'}}>{fmtDate(r.created_at)}</td>
              </tr>
            );
          })}</tbody>
        </table>
      )}

      {!loading&&sub==='annotations'&&rows.map(r=>(
        <div key={r.id} style={{padding:'.82rem 1rem',border:'var(--rt)',marginBottom:'2px',background:'var(--paper)'}}>
          <div style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',marginBottom:'.32rem'}}>
            Article #{r.article_id||'—'} · {fmtDate(r.created_at)}
          </div>
          {r.selected_text&&<div style={{fontFamily:'var(--fb)',fontSize:'.82rem',fontStyle:'italic',color:'var(--g600)',borderLeft:'3px solid var(--g300)',paddingLeft:'.6rem',marginBottom:'.32rem'}}>“{r.selected_text}”</div>}
          <div style={{fontFamily:'var(--fb)',fontSize:'.9rem',lineHeight:1.55}}>{r.note}</div>
        </div>
      ))}
    </div>
  );
}

function EbookPage({toast}){
  const [articles,setArticles]=useState([]);
  const [loading,setLoading]=useState(true);
  const [search,setSearch]=useState('');
  const [selected,setSelected]=useState([]);   
  const [title,setTitle]=useState('My Voice Express Collection');
  const [creator,setCreator]=useState('');
  const [description,setDescription]=useState('');
  const [generating,setGenerating]=useState(false);
  const [genType,setGenType]=useState('epub'); 

  useEffect(()=>{
    API.get('/api/articles?status=published&limit=200')
      .then(data=>{ setArticles(Array.isArray(data)?data:(data.articles||[])); setLoading(false); })
      .catch(()=>setLoading(false));
  },[]);

  const inSel=id=>selected.some(a=>a.id===id);

  const toggle=art=>{
    if(inSel(art.id)) setSelected(s=>s.filter(a=>a.id!==art.id));
    else setSelected(s=>[...s,art]);
  };

  const remove=id=>setSelected(s=>s.filter(a=>a.id!==id));

  const moveUp=idx=>{
    if(idx===0)return;
    setSelected(s=>{const n=[...s];[n[idx-1],n[idx]]=[n[idx],n[idx-1]];return n;});
  };
  const moveDown=idx=>{
    setSelected(s=>{if(idx>=s.length-1)return s;const n=[...s];[n[idx],n[idx+1]]=[n[idx+1],n[idx]];return n;});
  };

  const generate=async(type)=>{
    if(!selected.length){toast('Select at least one article','err');return;}
    setGenType(type); setGenerating(true);
    const endpoints={
      'epub':'/api/ebook/generate',
      'magazine':'/api/magazine/generate',
      'magazine-pdf':'/api/magazine/generate-pdf'
    };
    const exts={'epub':'.epub','magazine':'_magazine.html','magazine-pdf':'.pdf'};
    try{
      const resp=await fetch(endpoints[type],{
        method:'POST',credentials:'include',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          article_ids:selected.map(a=>a.id),
          title:title.trim()||'Voice Express Collection',
          creator:creator.trim()||'',
          description:description.trim(),
        })
      });
      if(!resp.ok){
        const e=await resp.json().catch(()=>({}));
        toast(e.error||'Generation failed','err'); return;
      }
      const blob=await resp.blob();
      const url=URL.createObjectURL(blob);
      const a=document.createElement('a');
      a.href=url;
      a.download=(title.trim().replace(/\s+/g,'_').slice(0,60)||type)+(exts[type]||'');
      document.body.appendChild(a);a.click();document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast({
        'epub':`EPUB downloaded — ${selected.length} article${selected.length!==1?'s':''}`,
        'magazine':'Magazine HTML downloaded — open in Chrome to print/save PDF',
        'magazine-pdf':'PDF downloaded — print-ready A4'
      }[type]||'Downloaded!');
    }catch(e){
      toast('Error generating printable','err');
    }finally{setGenerating(false);}
  };

  const filtered=articles.filter(a=>
    !search||a.title.toLowerCase().includes(search.toLowerCase())
    ||(a.author_name||'').toLowerCase().includes(search.toLowerCase())
  );

  return(
    <div className="ebook-page">
      <h1>Create Ebook</h1>
      <p>Select articles, arrange them, and download as an <strong>EPUB</strong> (e-readers) or a <strong>Print Magazine</strong> (editorial layout, A4 — PDF or browser-printable HTML).</p>
      <p style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g500)',letterSpacing:'.07em',marginTop:'-.4rem',marginBottom:'1rem'}}>
        ✦ Every generation is automatically saved to the <strong>Newsstand</strong> — readers can browse and support your work there.
      </p>
      <div className="ebook-layout">

        <div className="ebook-browser">
          <div className="ebook-browser-hd">
            <strong>All Published Articles</strong>
            <span style={{fontFamily:'var(--fm)',fontSize:'.62rem',color:'var(--g500)'}}>{filtered.length} shown</span>
          </div>
          <div className="ebook-search">
            <input type="text" placeholder="Filter by title or author…" value={search}
              onChange={e=>setSearch(e.target.value)}/>
          </div>
          <div className="ebook-art-list">
            {loading&&<div style={{padding:'2rem',textAlign:'center',color:'var(--g400)'}}>Loading…</div>}
            {!loading&&filtered.length===0&&<div style={{padding:'2rem',textAlign:'center',color:'var(--g400)'}}>No articles found.</div>}
            {filtered.map(art=>(
              <div key={art.id} className={`ebook-art-row${inSel(art.id)?' in-sel':''}`}
                onClick={()=>toggle(art)}>
                <span className="ebook-check">{inSel(art.id)?'☑':'☐'}</span>
                <div>
                  <div className="ebook-art-title">{art.title}</div>
                  <div className="ebook-art-meta">
                    {[art.author_name||art.byline,art.category_name,(art.published_at||'').slice(0,10)].filter(Boolean).join(' · ')}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="ebook-config">
          <div className="ebook-sel-hd">
            <strong>Selected ({selected.length})</strong>
            {selected.length>0&&
              <button className="btn-sm" onClick={()=>setSelected([])}>Clear all</button>}
          </div>

          <div className="ebook-sel-list">
            {selected.length===0&&
              <div className="ebook-empty-sel">No articles selected yet.<br/>Click articles on the left to add them.</div>}
            {selected.map((art,idx)=>(
              <div key={art.id} className="ebook-sel-item">
                <span className="ebook-sel-num">{idx+1}</span>
                <span className="ebook-sel-title" title={art.title}>{art.title}</span>
                <div className="ebook-sel-btns">
                  <button onClick={()=>moveUp(idx)} disabled={idx===0} title="Move up">↑</button>
                  <button onClick={()=>moveDown(idx)} disabled={idx===selected.length-1} title="Move down">↓</button>
                  <button onClick={()=>remove(art.id)} title="Remove">×</button>
                </div>
              </div>
            ))}
          </div>

          <div className="ebook-meta-form">
            <h3>Ebook Details</h3>
            <label>Title
              <input type="text" value={title} onChange={e=>setTitle(e.target.value)}
                placeholder="My Voice Express Collection"/>
            </label>
            <label>Author / Curator name
              <input type="text" value={creator} onChange={e=>setCreator(e.target.value)}
                placeholder="Your name (optional)"/>
            </label>
            <label>Description
              <textarea rows={3} value={description} onChange={e=>setDescription(e.target.value)}
                placeholder="A brief description of this collection…"/>
            </label>
            <div style={{display:'flex',flexDirection:'column',gap:'.45rem'}}>
              <button className="ebook-generate-btn" onClick={()=>generate('epub')}
                disabled={generating||selected.length===0}
                style={{fontSize:'.85rem'}}>
                {generating&&genType==='epub'?'Generating EPUB…':('↓ EPUB'+( selected.length?' ('+selected.length+')'  :''))}
              </button>
              <button className="ebook-generate-btn" onClick={()=>generate('magazine-pdf')}
                disabled={generating||selected.length===0}
                style={{fontSize:'.85rem',background:'#1a1a1a',color:'#f5f5f0'}}>
                {generating&&genType==='magazine-pdf'?'Building PDF…':'↓ Print Magazine (PDF)'}
              </button>
              <button className="ebook-generate-btn" onClick={()=>generate('magazine')}
                disabled={generating||selected.length===0}
                style={{fontSize:'.85rem',background:'var(--g700)'}}>
                {generating&&genType==='magazine'?'Building HTML…':'↓ Print Magazine (HTML)'}
              </button>
            </div>
            <p style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',marginTop:'.3rem',lineHeight:1.5}}>
              <strong>PDF</strong>: direct print-ready A4 via PyMuPDF (requires fitz).
              <strong>HTML</strong>: open in Chrome → Ctrl+P → Save as PDF if PDF unavailable.
              For the vintage newspaper broadsheet, see <strong>Print broadsheet</strong> on any month's Newsletter.
            </p>
          </div>
        </div>

      </div>
    </div>
  );
}

function PublicEbookRequestPage({toast}){
  const [articles,setArticles]=useState([]);
  const [loading,setLoading]=useState(true);
  const [search,setSearch]=useState('');
  const [selected,setSelected]=useState([]);
  const [title,setTitle]=useState('My Voice Express Collection');
  const [creator,setCreator]=useState('');
  const [description,setDescription]=useState('');
  const [name,setName]=useState('');
  const [email,setEmail]=useState('');
  const [sending,setSending]=useState(false);
  const [sent,setSent]=useState(false);

  useEffect(()=>{
    API.get('/api/articles?status=published&limit=200')
      .then(data=>{ setArticles(Array.isArray(data)?data:(data.articles||[])); setLoading(false); })
      .catch(()=>setLoading(false));
  },[]);

  const inSel=id=>selected.some(a=>a.id===id);
  const toggle=art=>{
    if(inSel(art.id)) setSelected(s=>s.filter(a=>a.id!==art.id));
    else if(selected.length<50) setSelected(s=>[...s,art]);
    else toast('Max 50 articles per request','err');
  };
  const remove=id=>setSelected(s=>s.filter(a=>a.id!==id));
  const moveUp=idx=>{ if(idx===0)return; setSelected(s=>{const n=[...s];[n[idx-1],n[idx]]=[n[idx],n[idx-1]];return n;}); };
  const moveDown=idx=>{ setSelected(s=>{if(idx>=s.length-1)return s;const n=[...s];[n[idx],n[idx+1]]=[n[idx+1],n[idx]];return n;}); };

  const submit=async()=>{
    if(!selected.length){toast('Select at least one article','err');return;}
    if(!title.trim()){toast('Title required','err');return;}
    setSending(true);
    const r=await API.post('/api/ebook-requests',{
      name:name.trim(), email:email.trim(),
      title:title.trim(), creator:creator.trim(), description:description.trim(),
      article_ids:selected.map(a=>a.id).join(','),
    }).catch(()=>({error:'Failed'}));
    setSending(false);
    if(r&&r.error){toast(r.error,'err');return;}
    setSent(true);
    toast('Request submitted!');
  };

  const filtered=articles.filter(a=>
    !search||a.title.toLowerCase().includes(search.toLowerCase())
    ||(a.author_name||'').toLowerCase().includes(search.toLowerCase())
  );

  if(sent){
    return(
      <div className="ebook-page">
        <h1>Request Submitted</h1>
        <div style={{padding:'1.2rem',border:'var(--rt)',background:'var(--g100)',fontFamily:'var(--fb)',fontSize:'.95rem',lineHeight:1.6}}>
          Thanks — your collection <strong>“{title}”</strong> ({selected.length} article{selected.length!==1?'s':''}) has been submitted.
          This static build can't generate the file instantly: once the next batch of requests is pulled from the Sheet, your ePub will
          be built and will appear in the <strong>Newsstand</strong>. Check back soon.
        </div>
        <button className="btn-o" style={{marginTop:'1rem'}} onClick={()=>{setSent(false);setSelected([]);setTitle('My Voice Express Collection');setCreator('');setDescription('');}}>
          ← Request another
        </button>
      </div>
    );
  }

  return(
    <div className="ebook-page">
      <h1>Request an Ebook</h1>
      <p>Select articles and arrange them into a collection. This static build can't generate the file instantly — your request is
        queued for the next batch, and the finished <strong>EPUB</strong> appears in the Newsstand once it's been built.</p>
      <div className="ebook-layout">

        <div className="ebook-browser">
          <div className="ebook-browser-hd">
            <strong>All Published Articles</strong>
            <span style={{fontFamily:'var(--fm)',fontSize:'.62rem',color:'var(--g500)'}}>{filtered.length} shown</span>
          </div>
          <div className="ebook-search">
            <input type="text" placeholder="Filter by title or author…" value={search}
              onChange={e=>setSearch(e.target.value)}/>
          </div>
          <div className="ebook-art-list">
            {loading&&<div style={{padding:'2rem',textAlign:'center',color:'var(--g400)'}}>Loading…</div>}
            {!loading&&filtered.length===0&&<div style={{padding:'2rem',textAlign:'center',color:'var(--g400)'}}>No articles found.</div>}
            {filtered.map(art=>(
              <div key={art.id} className={`ebook-art-row${inSel(art.id)?' in-sel':''}`}
                onClick={()=>toggle(art)}>
                <span className="ebook-check">{inSel(art.id)?'☑':'☐'}</span>
                <div>
                  <div className="ebook-art-title">{art.title}</div>
                  <div className="ebook-art-meta">
                    {[art.author_name||art.byline,art.category_name,(art.published_at||'').slice(0,10)].filter(Boolean).join(' · ')}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="ebook-config">
          <div className="ebook-sel-hd">
            <strong>Selected ({selected.length})</strong>
            {selected.length>0&&
              <button className="btn-sm" onClick={()=>setSelected([])}>Clear all</button>}
          </div>

          <div className="ebook-sel-list">
            {selected.length===0&&
              <div className="ebook-empty-sel">No articles selected yet.<br/>Click articles on the left to add them.</div>}
            {selected.map((art,idx)=>(
              <div key={art.id} className="ebook-sel-item">
                <span className="ebook-sel-num">{idx+1}</span>
                <span className="ebook-sel-title" title={art.title}>{art.title}</span>
                <div className="ebook-sel-btns">
                  <button onClick={()=>moveUp(idx)} disabled={idx===0} title="Move up">↑</button>
                  <button onClick={()=>moveDown(idx)} disabled={idx===selected.length-1} title="Move down">↓</button>
                  <button onClick={()=>remove(art.id)} title="Remove">×</button>
                </div>
              </div>
            ))}
          </div>

          <div className="ebook-meta-form">
            <h3>Ebook Details</h3>
            <label>Title
              <input type="text" value={title} onChange={e=>setTitle(e.target.value)}
                placeholder="My Voice Express Collection"/>
            </label>
            <label>Author / Curator name
              <input type="text" value={creator} onChange={e=>setCreator(e.target.value)}
                placeholder="Your name (optional)"/>
            </label>
            <label>Description
              <textarea rows={3} value={description} onChange={e=>setDescription(e.target.value)}
                placeholder="A brief description of this collection…"/>
            </label>
            <label>Your Name (optional)
              <input type="text" value={name} onChange={e=>setName(e.target.value)}
                placeholder="Shown to the editors only"/>
            </label>
            <label>Your Email (optional)
              <input type="email" value={email} onChange={e=>setEmail(e.target.value)}
                placeholder="If you'd like to be notified"/>
            </label>
            <button className="ebook-generate-btn" onClick={submit}
              disabled={sending||selected.length===0}
              style={{fontSize:'.85rem'}}>
              {sending?'Submitting…':('Submit Request'+(selected.length?` (${selected.length})`:''))}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}


const PUB_TYPE_CONFIG = {
  magazine_pdf:  {label:'Magazine PDF',  icon:'📰', color:'#1a1a1a', accent:'#f0ece4'},
  magazine_html: {label:'Magazine',      icon:'§', color:'#2b2416', accent:'#f5f1e8'},
  pdf:           {label:'PDF',           icon:'▤', color:'#1c1c1c', accent:'#ececec'},
  epub:          {label:'E-Book',        icon:'❧', color:'#0f1f0f', accent:'#e8f5e8'},
  newsletter:    {label:'Newsletter',    icon:'✉', color:'#1c1020', accent:'#f0e8f5'},
};

function LibraryPage({toast, currentUser, setView}){
  const [pubs,setPubs]=useState([]);
  const [newsletters,setNewsletters]=useState([]);
  const [loading,setLoading]=useState(true);
  const [typeFilter,setTypeFilter]=useState('all');
  const [selected,setSelected]=useState(null);
  const [payAmount,setPayAmount]=useState(0);
  const [showUp,setShowUp]=useState(false);
  const isAdmin=currentUser&&(currentUser.role==='admin'||currentUser.role==='editor');

  const getNlC=n=>{
    if(n.content&&typeof n.content==='object')return n.content;
    try{return JSON.parse(n.content||'{}')}catch{return{};}
  };

  const reload=()=>{
    setLoading(true);
    const endpoint=isAdmin?'/api/publications/all':'/api/publications';
    Promise.all([
      API.get(endpoint).catch(()=>({publications:[]})),
      API.get('/api/newsletters/months').catch(()=>[]),
    ]).then(([pd,nd])=>{
      setPubs(pd.publications||[]);
      setNewsletters(safe(nd));
      setLoading(false);
    }).catch(()=>setLoading(false));
  };

  useEffect(()=>{reload();},[]);

  const toggleVisible=async(pub)=>{
    try{
      await API.put(`/api/publications/${pub.id}`,{is_visible:pub.is_visible?0:1});
      setPubs(ps=>ps.map(p=>p.id===pub.id?{...p,is_visible:pub.is_visible?0:1}:p));
      toast(pub.is_visible?'Hidden from Newsstand':'Visible in Newsstand');
    }catch(e){toast('Update failed','err');}
  };

  const toggleFeatured=async(pub)=>{
    const next=pub.is_featured?0:1;
    try{
      await API.put(`/api/publications/${pub.id}`,{is_featured:next});
      setPubs(ps=>ps.map(p=>p.id===pub.id?{...p,is_featured:next}:p));
      toast(next
        ? (pub.pub_type==='epub'?'Featured — this ebook will be kept':'Featured')
        : (pub.pub_type==='epub'?'No longer featured — prunable after 30 days':'No longer featured'));
    }catch(e){toast('Update failed','err');}
  };

  const deletePub=async(pub)=>{
    if(!confirm(`Delete "${pub.title}"? This cannot be undone.`))return;
    try{
      await API.del(`/api/publications/${pub.id}`);
      setPubs(ps=>ps.filter(p=>p.id!==pub.id));
      toast('Deleted');
    }catch(e){toast('Delete failed','err');}
  };

  const openPub=pub=>{
    if(pub.pub_type==='newsletter'){
      setSelected({...pub, _nl_id:true, _nl:{year:pub._year,month:pub._month},
        ...broadsheetLinks(pub._year,pub._month),
        description:'Read this edition online, or take it as a vintage newspaper broadsheet — PDF, plotter-ready.'});
      setPayAmount(0);return;
    }
    setSelected(pub);setPayAmount(pub.price_suggested||0);
  };

  const uploadPdf=async(fd)=>{
    const r=await fetch('/api/publications/upload',{method:'POST',credentials:'include',body:fd});
    if(!r.ok){const e=await r.json().catch(()=>({}));toast(e.error||'Upload failed','err');return false;}
    toast('PDF added to the Newsstand');setShowUp(false);reload();return true;
  };

  const nlCards=newsletters.map(n=>{
    const ym=`${n.year}-${String(n.month).padStart(2,'0')}`;
    const fi=n.cover_image;
    const coverUrl=fi?(fi.startsWith('/')?fi:'/static/uploads/'+fi):null;
    return{
      id:`nl_${n.year}_${n.month}`,_year:n.year,_month:n.month,
      title:n.title,pub_type:'newsletter',
      created_at:`${ym}-01`,
      article_count:n.article_count||0,
      is_visible:1,cover_image:coverUrl,
      file_size:0,price_max:0,price_suggested:0,
    };
  });
  const shelfPubs=safe(pubs).filter(p=>p.pub_type==='pdf'||(isAdmin&&p.pub_type==='epub'));
  const allCards=[...shelfPubs,...nlCards].sort((a,b)=>new Date(b.created_at||0)-new Date(a.created_at||0));
  const types=[...new Set(allCards.map(p=>p.pub_type))];
  const filtered=typeFilter==='all'?allCards:allCards.filter(p=>p.pub_type===typeFilter);
  const visible=isAdmin?filtered:filtered.filter(p=>p.is_visible!==0);

  if(loading) return(
    <div className="newsstand">
      <div style={{textAlign:'center',padding:'5rem 2rem',color:'var(--g400)',fontFamily:'var(--fm)',
        fontSize:'.68rem',letterSpacing:'.22em',textTransform:'uppercase'}}>Loading Newsstand…</div>
    </div>
  );

  return(
    <div className="newsstand">
      <div className="newsstand-hdr">
        <div className="sec-lbl"><span>The Newsstand</span></div>
        <p className="newsstand-deck">
          Every issue, broadsheet, and collection we've made — pay what you feel is fair.{' '}
          All support goes directly to sustaining independent journalism.
        </p>
        {types.length>1&&(
          <div style={{display:'flex',gap:'.3rem',flexWrap:'wrap'}}>
            <span className={`tag${typeFilter==='all'?' on':''}`} onClick={()=>setTypeFilter('all')}>All</span>
            {types.map(t=>(
              <span key={t} className={`tag${typeFilter===t?' on':''}`} onClick={()=>setTypeFilter(t)}>
                {(PUB_TYPE_CONFIG[t]||{}).label||t}
              </span>
            ))}
          </div>
        )}
        {isAdmin&&(
          <div style={{marginTop:'.8rem',display:'flex',alignItems:'center',gap:'.8rem',flexWrap:'wrap'}}>
            <button className="btn-s" onClick={()=>setShowUp(true)}>+ Upload PDF</button>
            <span style={{fontFamily:'var(--fm)',fontSize:'.55rem',color:'var(--g400)',
              letterSpacing:'.08em',textTransform:'uppercase'}}>
              Editorial view — {allCards.length} item{allCards.length!==1?'s':''}
            </span>
          </div>
        )}
      </div>

      {visible.length===0&&(
        <div style={{textAlign:'center',padding:'5rem 2rem'}}>
          <div style={{fontFamily:'var(--fh)',fontStyle:'italic',fontSize:'1.3rem',
            color:'var(--g400)',marginBottom:'1rem'}}>
            {allCards.length===0
              ? 'The newsstand is empty.'
              : 'No publications of this type.'}
          </div>
          <p style={{fontFamily:'var(--fb)',fontSize:'.88rem',color:'var(--g500)',maxWidth:'380px',
            margin:'0 auto',lineHeight:1.6}}>
            {allCards.length===0&&'Generate a magazine, broadsheet, or ebook from the Create Ebook page — it will appear here automatically.'}
          </p>
        </div>
      )}

      <div className="pub-grid">
        {visible.map(pub=>(
          <PublicationCard
            key={pub.id}
            pub={pub}
            isAdmin={isAdmin}
            onGet={()=>openPub(pub)}
            onToggleVisible={()=>toggleVisible(pub)}
            onToggleFeatured={()=>toggleFeatured(pub)}
            onDelete={()=>deletePub(pub)}
          />
        ))}
      </div>

      {selected&&(
        <PaymentModal
          pub={selected}
          amount={payAmount}
          setAmount={setPayAmount}
          onClose={()=>setSelected(null)}
          toast={toast}
          setView={setView}
        />
      )}
      {showUp&&<UploadPdfModal onClose={()=>setShowUp(false)} onUpload={uploadPdf} toast={toast}/>}
    </div>
  );
}

function UploadPdfModal({onClose,onUpload,toast}){
  const [title,setTitle]=useState('');
  const [file,setFile]=useState(null);
  const [cover,setCover]=useState(null);
  const [desc,setDesc]=useState('');
  const [busy,setBusy]=useState(false);
  const submit=async()=>{
    if(!file){toast('Choose a PDF file','err');return;}
    setBusy(true);
    const fd=new FormData();
    fd.append('file',file);
    fd.append('title',title||file.name.replace(/\.pdf$/i,''));
    fd.append('description',desc);
    if(cover)fd.append('cover',cover);
    await onUpload(fd);
    setBusy(false);
  };
  return(
    <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&onClose()}>
      <div className="modal" style={{maxWidth:'440px'}}>
        <div className="sec-lbl"><span>Upload a PDF to the Newsstand</span></div>
        <label style={{display:'block',margin:'.7rem 0 .2rem',fontSize:'.7rem',letterSpacing:'.08em',textTransform:'uppercase'}}>Title</label>
        <input type="text" value={title} onChange={e=>setTitle(e.target.value)} placeholder="Defaults to the file name" style={{width:'100%'}}/>
        <label style={{display:'block',margin:'.7rem 0 .2rem',fontSize:'.7rem',letterSpacing:'.08em',textTransform:'uppercase'}}>PDF file *</label>
        <input type="file" accept="application/pdf,.pdf" onChange={e=>setFile(e.target.files[0]||null)}/>
        <label style={{display:'block',margin:'.7rem 0 .2rem',fontSize:'.7rem',letterSpacing:'.08em',textTransform:'uppercase'}}>Cover image (optional)</label>
        <input type="file" accept="image/*" onChange={e=>setCover(e.target.files[0]||null)}/>
        <label style={{display:'block',margin:'.7rem 0 .2rem',fontSize:'.7rem',letterSpacing:'.08em',textTransform:'uppercase'}}>Description (optional)</label>
        <textarea rows={2} value={desc} onChange={e=>setDesc(e.target.value)} style={{width:'100%'}}/>
        <div style={{display:'flex',gap:'.5rem',marginTop:'1rem',justifyContent:'flex-end'}}>
          <button className="btn-s" onClick={onClose}>Cancel</button>
          <button className="btn-p" onClick={submit} disabled={busy}>{busy?'Uploading…':'Add to Newsstand'}</button>
        </div>
      </div>
    </div>
  );
}

function PublicationCard({pub, isAdmin, onGet, onToggleVisible, onToggleFeatured, onDelete}){
  const tc=PUB_TYPE_CONFIG[pub.pub_type]||{label:pub.pub_type,icon:'◆',color:'#1a1a1a',accent:'#f5f5f0'};
  const date=(pub.created_at||'').slice(0,10);
  const isHidden=isAdmin&&!pub.is_visible;

  return(
    <div className="pub-card" style={{opacity:isHidden?.55:1}}>
      <div className="pub-cover" style={{background:tc.color}} onClick={onGet}>
        <div className="pub-cover-ph">
          <div style={{fontSize:'2rem',marginBottom:'.4rem',filter:'drop-shadow(0 2px 4px rgba(0,0,0,.4))'}}>{tc.icon}</div>
          <div style={{fontFamily:'var(--fh)',fontWeight:900,fontSize:'.68rem',letterSpacing:'.14em',
            textTransform:'uppercase',color:'rgba(255,255,255,.55)',lineHeight:1.3}}>
            The Voice<br/>Express
          </div>
          {pub.issue_number&&(
            <div style={{fontFamily:'var(--fm)',fontSize:'.46rem',letterSpacing:'.18em',
              textTransform:'uppercase',color:'rgba(255,255,255,.35)',marginTop:'.38rem'}}>
              Issue {pub.issue_number}
            </div>
          )}
        </div>
        {pub.cover_image&&(
          <img src={pub.cover_image} alt={pub.title} onError={e=>e.target.style.display='none'}/>
        )}
        <div className="pub-badge">{tc.label}{isHidden&&' · Hidden'}</div>
        {isAdmin&&pub.is_featured&&(
          <div style={{position:'absolute',top:'.4rem',left:'.4rem',fontSize:'.8rem',
            color:'#f5c451',textShadow:'0 1px 3px rgba(0,0,0,.6)'}} title="Featured — kept permanently">★</div>
        )}
        {isAdmin&&!pub.is_featured&&pub.pub_type==='epub'&&(
          <div style={{position:'absolute',top:'.4rem',left:'.4rem',fontFamily:'var(--fm)',
            fontSize:'.42rem',letterSpacing:'.08em',textTransform:'uppercase',
            background:'rgba(0,0,0,.55)',color:'rgba(255,255,255,.75)',padding:'.12rem .3rem'}}
            title="Reader-built ebooks are deleted 30 days after they are made unless featured">
            temporary
          </div>
        )}
      </div>

      <div className="pub-info">
        <div className="pub-title" onClick={onGet}>{pub.title}</div>
        <div className="pub-meta">
          {date&&<span>{date}</span>}
          {pub.article_count>0&&<span> · {pub.article_count} art{pub.article_count!==1?'s':''}</span>}
          {pub.file_size>0&&<span> · {(pub.file_size/1024).toFixed(0)} KB</span>}
        </div>
        <button className="btn-p pub-get-btn" onClick={onGet}>
          {pub.pub_type==='newsletter'?'Read Edition →':'Get This Issue →'}
        </button>
        {isAdmin&&(
          <div className="pub-admin-strip">
            <button className="btn-s" style={{fontSize:'.48rem'}} onClick={onToggleVisible}>
              {pub.is_visible?'Hide':'Show'}
            </button>
            <button className="btn-s"
              style={{fontSize:'.48rem',color:pub.is_featured?'#9a7b1f':undefined}}
              title={pub.pub_type==='epub'
                ? 'Featured ebooks are kept permanently; the rest are pruned after 30 days'
                : 'Featured publications are promoted on the shelf and never pruned'}
              onClick={onToggleFeatured}>
              {pub.is_featured?'★ Featured':'☆ Feature'}
            </button>
            <button className="btn-s" style={{fontSize:'.48rem',color:'#a33'}} onClick={onDelete}>
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function PaymentModal({pub, amount, setAmount, onClose, toast, setView}){
  const tc=PUB_TYPE_CONFIG[pub.pub_type]||{label:pub.pub_type,icon:'◆',color:'#1a1a1a'};
  const priceMax=pub.price_max||500;
  const kofiUrl='';   
  const razorpayBase='https://razorpay.me/@mitaliaayatmahnoorsharma';
  const payLink=amount>0?`${razorpayBase}/${Math.round(amount)}`:razorpayBase;
  const presets=[0,25,50,100,200].filter(p=>p<=priceMax);
  const isFree=amount===0;

  const handleDownload=()=>{
    window.open(pub.download_url?pub.download_url.replace(/^\//,''):`/api/publications/${pub.id}/download`,'_blank');
    toast(isFree
      ?'Downloading — if you enjoy the work, consider supporting us!'
      :`₹${amount} selected — thank you! Downloading now.`);
    onClose();
  };

  return(
    <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&onClose()}>
      <div className="modal pay-modal">

        <div className="modal-hdr">
          <span className="modal-title">{pub.title}</span>
          <span className="modal-close" onClick={onClose}>✕</span>
        </div>

        <div className="pay-cover-strip" style={{background:tc.color}}>
          {pub.cover_image
            ? <img src={pub.cover_image} alt={pub.title} onError={e=>e.target.style.display='none'}/>
            : null}
          <div style={{position:'absolute',inset:0,display:'flex',flexDirection:'column',
            alignItems:'center',justifyContent:'center',
            background:pub.cover_image?'rgba(0,0,0,.35)':'transparent',
            pointerEvents:'none'}}>
            <div style={{fontSize:'2.8rem'}}>{tc.icon}</div>
            <div style={{fontFamily:'var(--fh)',fontWeight:900,fontSize:'1rem',letterSpacing:'.1em',
              textTransform:'uppercase',color:'rgba(255,255,255,.8)',marginTop:'.25rem'}}>
              The Voice Express
            </div>
            {pub.issue_number&&(
              <div style={{fontFamily:'var(--fm)',fontSize:'.52rem',letterSpacing:'.2em',
                textTransform:'uppercase',color:'rgba(255,255,255,.55)',marginTop:'.2rem'}}>
                Issue {pub.issue_number}
              </div>
            )}
          </div>
        </div>

        <div className="pay-inner">
          <div className="pay-pub-meta">
            <span>{tc.label}</span>
            {pub.article_count>0&&<span> · {pub.article_count} articles</span>}
            {pub.created_at&&<span> · {pub.created_at.slice(0,10)}</span>}
            {pub.file_size>0&&<span> · {(pub.file_size/1024).toFixed(0)} KB</span>}
          </div>

          {pub.description&&<p className="pay-desc">{pub.description}</p>}

          <div className="pay-section-lbl">Pay What You Want</div>

          <div className="pay-presets">
            {presets.map(p=>(
              <button key={p} className={`btn-s${amount===p?' on':''}`}
                style={{fontSize:'.6rem',padding:'.32rem .7rem'}}
                onClick={()=>setAmount(p)}>
                {p===0?'Free':`₹${p}`}
              </button>
            ))}
          </div>

          {!isFree&&(
            <div className="pay-btns">
              <a href={payLink} target="_blank" rel="noopener noreferrer"
                className="btn-p"
                style={{textAlign:'center',textDecoration:'none',display:'block',fontSize:'.66rem'}}>
                Pay ₹{amount}
              </a>
              {kofiUrl&&<a href={kofiUrl} target="_blank" rel="noopener noreferrer"
                className="btn-o"
                style={{textAlign:'center',textDecoration:'none',display:'block',fontSize:'.66rem'}}>
                Ko-fi
              </a>}
            </div>
          )}

          <hr className="pay-divider"/>

          {pub._pdf_url?(
            <div className="pay-btns" style={{flexDirection:'column'}}>
              <button className="btn-p" style={{width:'100%',fontSize:'.7rem'}}
                onClick={()=>{window.open(pub._pdf_url);onClose();}}>
                ↓ Download Broadsheet PDF{isFree?'':' (Thank you!)'}
              </button>
              <button className="btn-o" style={{width:'100%',fontSize:'.7rem'}}
                onClick={()=>{if(pub._nl&&setView){window.__nlGoto=pub._nl;setView('newsletter');}else if(setView)setView('newsletter');onClose();}}>
                → Read this edition online
              </button>
              {pub._scroll_url&&<button className="btn-o" style={{width:'100%',fontSize:'.7rem'}}
                onClick={()=>{window.open(pub._scroll_url);onClose();}}
                title="Open this edition as one continuous scrolling vintage-newspaper page">
                📰 Read as a Vintage Paper
              </button>}
            </div>
          ):pub._nl_id?(
            <button className="btn-p" style={{width:'100%',fontSize:'.7rem'}}
              onClick={()=>{if(setView)setView('newsletter');onClose();}}>
              → Read This Edition Online
            </button>
          ):(
            <button className="btn-p" style={{width:'100%',fontSize:'.7rem'}} onClick={handleDownload}>
              ↓ Download{isFree?' for Free':' (Thank you!)'}
            </button>
          )}

          <p className="pay-honor-note">
            {pub._nl_id
              ? 'Free to read online — pick an amount above to support independent journalism if you can.'
              : isFree
                ? 'Free to download — pick an amount above to support independent journalism if you can.'
                : 'Please complete payment above, then download. Honor system — your support keeps us independent.'}
          </p>

          <p style={{fontFamily:'var(--fm)',fontSize:'.5rem',color:'var(--g300)',textAlign:'center',
            marginTop:'.3rem',letterSpacing:'.06em'}}>
            Cards · UPI · net banking, via Razorpay
          </p>
        </div>
      </div>
    </div>
  );
}

function StaticPage({slug,setView,extraActions}){
  const [page,setPage]=useState(null);
  const [loading,setLoading]=useState(true);
  useEffect(()=>{
    API.get('/api/pages/'+slug)
      .then(d=>{setPage(d);setLoading(false);})
      .catch(()=>setLoading(false));
  },[slug]);
  if(loading)return <div className="loading">Loading…</div>;
  if(!page)return <div className="about-page"><p style={{color:'var(--g400)'}}>Page not found.</p></div>;
  return(
    <div className={slug==='submissions'?'submissions-page':'about-page'}>
      <div className="sec-lbl"><span>{page.title}</span></div>
      {slug==='about'&&(
        <div className="about-lede">The Truth Takes Time.</div>
      )}
      {slug==='submissions'&&(
        <div className="submissions-lede">We accept submissions all year round.</div>
      )}
      <div className="art-content" dangerouslySetInnerHTML={{__html:page.content}}/>
      {extraActions&&<div style={{marginTop:'2rem',display:'flex',gap:'.5rem',flexWrap:'wrap'}}>{extraActions(setView)}</div>}
    </div>
  );
}

function AboutPage({setView}){
  return <StaticPage slug="about" setView={setView} extraActions={sv=>(
    <>
      <button className="btn-p" onClick={()=>sv('authors')}>Meet the Contributors →</button>
      <button className="btn-o" onClick={()=>sv('letters')}>Write to the Editor →</button>
      <button className="btn-o" onClick={()=>sv('submissions')}>Submissions →</button>
    </>
  )}/>;
}

function SubmissionsPage({setView}){
  return <StaticPage slug="submissions" setView={setView} extraActions={sv=>(
    <button className="btn-o" onClick={()=>sv('about')}>← About Us</button>
  )}/>;
}

function PublicLettersPage({toast}){
  const [letters,setLetters]=useState([]);
  const [loading,setLoading]=useState(true);
  const [form,setForm]=useState({guest_name:'',subject:'',content:''});
  const [composing,setComposing]=useState(false);
  const [sending,setSending]=useState(false);
  const [sent,setSent]=useState(false);

  useEffect(()=>{
    API.get('/api/letters').then(d=>setLetters(safe(d))).catch(()=>{}).finally(()=>setLoading(false));
  },[]);

  const submit=async()=>{
    if(!form.subject.trim()||!form.content.trim()){toast('Subject and message required','err');return;}
    setSending(true);
    const r=await API.post('/api/letters',form).catch(()=>({error:'Failed'}));
    setSending(false);
    if(r.error){toast(r.error,'err');return;}
    setSent(true);setComposing(false);setForm({guest_name:'',subject:'',content:''});
    toast('Letter sent — thank you!');
  };

  return(
    <div className="letters-page">
      <div className="sec-lbl"><span>Letters to the Editor</span></div>
      {!composing&&!sent&&<button className="btn-p" style={{marginBottom:'1.35rem'}} onClick={()=>setComposing(true)}>+ Write a Letter</button>}
      {composing&&(
        <div style={{padding:'1.2rem',border:'var(--rk)',marginBottom:'1.35rem',background:'var(--g100)'}}>
          <div className="form-lbl" style={{marginBottom:'.72rem',fontSize:'.65rem'}}>Write to the Editor</div>
          <FormField label="Your Name (optional)"><input value={form.guest_name} onChange={e=>setForm(p=>({...p,guest_name:e.target.value}))} placeholder="Displayed publicly if your letter is featured"/></FormField>
          <FormField label="Subject"><input value={form.subject} onChange={e=>setForm(p=>({...p,subject:e.target.value}))} placeholder="What is this about?"/></FormField>
          <FormField label="Message"><textarea value={form.content} onChange={e=>setForm(p=>({...p,content:e.target.value}))} placeholder="Your message…" style={{minHeight:120}}/></FormField>
          <div style={{display:'flex',gap:'.5rem'}}>
            <button className="btn-p" onClick={submit} disabled={sending}>{sending?'Sending…':'Send Letter'}</button>
            <button className="btn-o" onClick={()=>setComposing(false)}>Cancel</button>
          </div>
        </div>
      )}
      {sent&&<div style={{padding:'1rem',background:'var(--g100)',border:'var(--rt)',marginBottom:'1.35rem',fontFamily:'var(--fm)',fontSize:'.68rem',color:'var(--g600)'}}>
        Letter sent — thank you! It may take a little while to appear below.
      </div>}
      {loading&&<div className="loading">Loading letters</div>}
      {!loading&&!letters.length&&<div className="empty"><div className="empty-title">No letters yet</div><div className="empty-sub">Be the first to write in</div></div>}
      {letters.map(l=>(
        <div key={l.id} style={{padding:'1rem',border:'var(--rt)',marginBottom:'2px',background:'var(--paper)'}}>
          <div style={{fontFamily:'var(--fh)',fontWeight:700,fontSize:'.97rem',marginBottom:'.15rem'}}>{l.subject}</div>
          <div style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.04em',marginBottom:'.5rem'}}>
            {l.guest_name||l.name||'A Reader'} · {fmtDate(l.created_at)}
          </div>
          {safe(l.messages).map((m,i)=>(
            <div key={i} className={`letter-msg ${m.sender==='admin'?'admin-msg':'user-msg'}`} style={{marginBottom:'.4rem'}}>
              {m.sender==='admin'&&<div className="letter-msg-meta">Voice Express Editorial</div>}
              <div className="letter-msg-body" style={{whiteSpace:'pre-wrap'}}>{m.content}</div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function LettersPage({currentUser,toast}){
  const [letters,setLetters]=useState([]);
  const [open,setOpen]=useState(null);
  const [thread,setThread]=useState(null);
  const [reply,setReply]=useState('');
  const [form,setForm]=useState({subject:'',content:'',guest_name:''});
  const [composing,setComposing]=useState(false);
  const [loading,setLoading]=useState(false);

  const load=()=>{
    if(!currentUser)return;
    setLoading(true);
    API.get('/api/letters').then(d=>setLetters(safe(d))).catch(()=>toast('Failed to load','err')).finally(()=>setLoading(false));
  };
  useEffect(()=>{load();},[currentUser]);

  const openThread=async id=>{
    setOpen(id);
    const d=await API.get(`/api/letters/${id}`).catch(()=>null);
    if(d)setThread(d);
  };

  const sendReply=async()=>{
    if(!reply.trim())return;
    const r=await API.post(`/api/letters/${open}/reply`,{content:reply}).catch(()=>({error:'Failed'}));
    if(r.error){toast(r.error,'err');return;}
    setReply('');
    openThread(open);toast('Sent.');
  };

  const sendNew=async()=>{
    if(!form.subject.trim()||!form.content.trim()){toast('Subject and message required','err');return;}
    const r=await API.post('/api/letters',form).catch(()=>({error:'Failed'}));
    if(r.error){toast(r.error,'err');return;}
    toast('Letter sent!');setComposing(false);setForm({subject:'',content:'',guest_name:''});load();
  };

  const statusColors={open:'var(--g500)',replied:'var(--ink)',closed:'var(--g300)'};

  if(open&&thread){
    return(
      <div className="letters-page">
        <button className="btn-o" style={{marginBottom:'1.2rem'}} onClick={()=>{setOpen(null);setThread(null);}}>← Back to Letters</button>
        <div style={{fontFamily:'var(--fh)',fontSize:'1.35rem',fontWeight:700,marginBottom:'.45rem'}}>{thread.subject}</div>
        <div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:'1.2rem'}}>
          Status: <span style={{color:statusColors[thread.status]||'var(--ink)',fontWeight:700}}>{thread.status}</span>
        </div>
        <div className="letter-thread">
          {safe(thread.messages).map((m,i)=>(
            <div key={i} className={`letter-msg ${m.sender==='admin'?'admin-msg':'user-msg'}`}>
              <div className="letter-msg-meta">{m.sender==='admin'?'Voice Express Editorial':'You'} · {fmtDate(m.created_at)}</div>
              <div className="letter-msg-body" style={{whiteSpace:'pre-wrap'}}>{m.content}</div>
            </div>
          ))}
        </div>
        {thread.status!=='closed'&&(
          <div style={{marginTop:'1rem'}}>
            <textarea value={reply} onChange={e=>setReply(e.target.value)} placeholder="Write your reply…" style={{minHeight:90,marginBottom:'.5rem'}}/>
            <button className="btn-p" onClick={sendReply} disabled={!reply.trim()}>Send Reply</button>
          </div>
        )}
      </div>
    );
  }

  if(!currentUser)return(
    <div className="letters-page">
      <div className="sec-lbl"><span>Write to the Editor</span></div>
      <div className="empty">
        <div className="empty-icon">✉</div>
        <div className="empty-title">Create a reader account</div>
        <div className="empty-sub">Sign in or join to write private letters to Voice Express. No email required.</div>
      </div>
    </div>
  );

  return(
    <div className="letters-page">
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1.35rem',flexWrap:'wrap',gap:'.5rem'}}>
        <div className="sec-lbl" style={{margin:0}}><span>My Letters</span></div>
        <button className="btn-p" onClick={()=>setComposing(v=>!v)}>{composing?'Cancel':'+ New Letter'}</button>
      </div>
      {composing&&(
        <div style={{padding:'1.2rem',border:'var(--rk)',marginBottom:'1.35rem',background:'var(--g100)'}}>
          <div className="form-lbl" style={{marginBottom:'.72rem',fontSize:'.65rem'}}>Write to the Editor</div>
          <FormField label="Subject"><input value={form.subject} onChange={e=>setForm(p=>({...p,subject:e.target.value}))} placeholder="What is this about?"/></FormField>
          <FormField label="Message"><textarea value={form.content} onChange={e=>setForm(p=>({...p,content:e.target.value}))} placeholder="Your message…" style={{minHeight:120}}/></FormField>
          <button className="btn-p" onClick={sendNew}>Send Letter</button>
        </div>
      )}
      {loading&&<div className="loading">Loading letters</div>}
      {!loading&&!letters.length&&<div className="empty"><div className="empty-title">No letters yet</div><div className="empty-sub">Write your first letter to the editorial team</div></div>}
      {letters.map(l=>(
        <div key={l.id} style={{padding:'.82rem 1rem',border:'var(--rt)',marginBottom:'2px',cursor:'pointer',display:'flex',justifyContent:'space-between',alignItems:'center',gap:'1rem',background:'var(--paper)'}}
          onClick={()=>openThread(l.id)}
          onMouseOver={e=>e.currentTarget.style.background='var(--g100)'}
          onMouseOut={e=>e.currentTarget.style.background='var(--paper)'}>
          <div style={{flex:1,minWidth:0}}>
            <div style={{fontFamily:'var(--fh)',fontWeight:700,fontSize:'.97rem',marginBottom:'.12rem'}}>{l.subject}</div>
            <div style={{fontFamily:'var(--fm)',fontSize:'.6rem',color:'var(--g500)',textTransform:'uppercase',letterSpacing:'.04em'}}>
              {fmtDate(l.last_message_at)} · {l.username||'You'}
            </div>
            {l.last_msg&&<div style={{fontFamily:'var(--fb)',fontSize:'.82rem',color:'var(--g600)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',marginTop:'.15rem'}}>{l.last_msg}</div>}
          </div>
          <span style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:statusColors[l.status]||'var(--ink)',textTransform:'uppercase',letterSpacing:'.06em',flexShrink:0}}>{l.status}</span>
        </div>
      ))}
    </div>
  );
}

function LikeButton({articleId}){
  const [count,setCount]=useState(null);
  const [liked,setLiked]=useState(false);
  const LS_KEY='ve-liked-articles';

  useEffect(()=>{
    API.get(`/api/articles/${articleId}/likes`).then(d=>setCount(d&&typeof d.count==='number'?d.count:0)).catch(()=>setCount(0));
    try{
      const liked_ids=JSON.parse(localStorage.getItem(LS_KEY)||'[]');
      setLiked(liked_ids.includes(articleId));
    }catch(e){}
  },[articleId]);

  const like=async()=>{
    if(liked)return;
    setLiked(true);
    setCount(c=>(c||0)+1);
    try{
      const ids=JSON.parse(localStorage.getItem(LS_KEY)||'[]');
      localStorage.setItem(LS_KEY,JSON.stringify([...ids,articleId]));
    }catch(e){}
    const r=await API.post(`/api/articles/${articleId}/like`,{}).catch(()=>null);
    if(r&&typeof r.count==='number')setCount(r.count);
  };

  return(
    <button className={`btn-o${liked?' on':''}`} onClick={like} disabled={liked}
      style={{display:'inline-flex',alignItems:'center',gap:'.4rem',marginBottom:'1.4rem'}}
      title={liked?'You liked this article':'Like this article'}>
      <span style={{fontSize:'.9rem'}}>{liked?'♥':'♡'}</span>
      <span>{liked?'Liked':'Like'}{count!==null&&count>0?` · ${count}`:''}</span>
    </button>
  );
}

function SubscribeBox({toast}){
  const [email,setEmail]=useState('');
  const [sending,setSending]=useState(false);
  const [done,setDone]=useState(false);

  const submit=async()=>{
    if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())){toast('Enter a valid email','err');return;}
    setSending(true);
    const r=await API.post('/api/subscribe',{email:email.trim()}).catch(()=>({error:'Failed'}));
    setSending(false);
    if(r.error){toast(r.error,'err');return;}
    setDone(true);toast(r.already?'Already subscribed!':'Subscribed!');
  };

  if(done)return(
    <div style={{padding:'1rem',border:'var(--rt)',background:'var(--g100)',marginBottom:'1.3rem',fontFamily:'var(--fm)',fontSize:'.68rem',color:'var(--g600)'}}>
      ✓ You're on the list — thanks for subscribing.
    </div>
  );

  return(
    <div style={{padding:'1rem',border:'var(--rt)',background:'var(--g100)',marginBottom:'1.3rem',display:'flex',gap:'.5rem',flexWrap:'wrap',alignItems:'center'}}>
      <span style={{fontFamily:'var(--fm)',fontSize:'.62rem',textTransform:'uppercase',letterSpacing:'.06em',color:'var(--g600)'}}>Get the newsletter in your inbox</span>
      <input type="email" value={email} onChange={e=>setEmail(e.target.value)} onKeyDown={e=>e.key==='Enter'&&submit()}
        placeholder="you@example.com" style={{flex:'1 1 200px',minWidth:0}}/>
      <button className="btn-p" onClick={submit} disabled={sending}>{sending?'…':'Subscribe'}</button>
    </div>
  );
}

function CommentsSection({articleId,toast}){
  const [comments,setComments]=useState([]);
  const [form,setForm]=useState({display_name:'',content:''});
  const [sending,setSending]=useState(false);
  const [sent,setSent]=useState(false);

  useEffect(()=>{
    API.get(`/api/articles/${articleId}/comments`).then(d=>setComments(safe(d))).catch(()=>{});
  },[articleId]);

  const submit=async()=>{
    if(!form.display_name.trim()||!form.content.trim()){toast('Name and comment required','err');return;}
    setSending(true);
    const r=await API.post(`/api/articles/${articleId}/comments`,form).catch(()=>({error:'Failed'}));
    setSending(false);
    if(r.error){toast(r.error,'err');return;}
    setSent(true);setForm({display_name:'',content:''});
    toast('Comment submitted for moderation — thank you!');
  };

  return(
    <div className="comments-sect">
      <h3 style={{fontFamily:'var(--fm)',fontSize:'.59rem',letterSpacing:'.2em',textTransform:'uppercase',marginBottom:'.95rem'}}>
        Discussion {comments.length>0&&`(${comments.length})`}
      </h3>
      {comments.map(c=>(
        <div key={c.id} className="comment-item">
          <span className="comment-name">{c.display_name}</span>
          <span className="comment-date">{fmtDate(c.created_at)}</span>
          <div className="comment-body">{c.content}</div>
        </div>
      ))}
      {!sent?(
        <div style={{marginTop:'1.4rem',padding:'1.1rem',border:'var(--rt)',background:'var(--g100)'}}>
          <div className="form-lbl" style={{marginBottom:'.72rem',fontSize:'.65rem'}}>Leave a Comment</div>
          <div className="form-row">
            <FormField label="Your Name *"><input value={form.display_name} onChange={e=>setForm(p=>({...p,display_name:e.target.value}))} placeholder="Displayed publicly"/></FormField>
          </div>
          <FormField label="Comment *"><textarea value={form.content} onChange={e=>setForm(p=>({...p,content:e.target.value}))} placeholder="Join the discussion…" style={{minHeight:75}}/></FormField>
          <div style={{display:'flex',alignItems:'center',gap:'1rem',flexWrap:'wrap'}}>
            <button className="btn-p" onClick={submit} disabled={sending}>{sending?'Sending…':'Post Comment'}</button>
            <span style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g400)'}}>No email required · Comments are moderated</span>
          </div>
        </div>
      ):(
        <div style={{padding:'1rem',background:'var(--g100)',border:'var(--rt)',marginTop:'1rem',fontFamily:'var(--fm)',fontSize:'.68rem',color:'var(--g600)'}}>
          Comment submitted — thank you! It will appear after moderation.
        </div>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);

