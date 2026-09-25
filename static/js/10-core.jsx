const {useState,useEffect,useRef,useCallback,useMemo}=React;

const VE=(typeof window!=='undefined'&&window.VE)||{};
const VE_PRODUCT=VE.product||'full';
const hasCap=k=>{const c=VE.caps;return !c||c[k]!==false;};
const broadsheetLinks=(year,month)=>hasCap('server_render')
  ?{_pdf_url:`/api/newsletters/${year}/${month}/broadsheet?format=pdf`,
    _scroll_url:`/api/newsletters/${year}/${month}/broadsheet?format=scroll`}
  :{_pdf_url:`static/media/broadsheet_${year}_${String(month).padStart(2,'0')}.pdf`,_scroll_url:null};

const API={
  get:u=>fetch(u,{credentials:'include'}).then(r=>{if(!r.ok)throw new Error(r.status);return r.json()}),
  post:(u,d)=>fetch(u,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}).then(r=>r.json()),
  put:(u,d)=>fetch(u,{method:'PUT',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}).then(r=>r.json()),
  del:u=>fetch(u,{method:'DELETE',credentials:'include'}).then(r=>r.json()),
  upload:(u,fd)=>fetch(u,{method:'POST',credentials:'include',body:fd}).then(r=>r.json()),
};

const BETA_REPORT_EMAIL='thevoiceexpress@proton.me';

function BetaBanner(){
  const [hidden,setHidden]=useState(()=>{try{return sessionStorage.getItem('ve-beta-hidden')==='1';}catch{return false;}});
  if(hidden)return null;
  const dismiss=()=>{setHidden(true);try{sessionStorage.setItem('ve-beta-hidden','1');}catch{}};
  const href=`mailto:${BETA_REPORT_EMAIL}?subject=${encodeURIComponent('Error report: The Voice Express')}&body=${encodeURIComponent('Page: '+(typeof location!=='undefined'?location.href:'')+'\n\nWhat went wrong:\n')}`;
  return(
    <div className="beta-banner" role="status">
      <span className="beta-tag">Beta mode</span>
      <span className="beta-text">This site is still being built. Something broken or wrong?</span>
      <a className="beta-link" href={href}>Report an error</a>
      <button className="beta-x" onClick={dismiss} title="Dismiss" aria-label="Dismiss">×</button>
    </div>
  );
}

const LANGS={en:'English',hi:'हिंदी',fr:'Français',es:'Español',ar:'العربية',zh:'中文',de:'Deutsch'};
const TRANSLATABLE_LANGS={hi:'hi',fr:'fr',es:'es',ar:'ar',zh:'zh-CN',de:'de'};

const AUTHOR_TYPES=[
  {value:'reporter',        label:'Reporter'},
  {value:'editor',          label:'Editor'},
  {value:'senior_editor',   label:'Senior Editor'},
  {value:'managing_editor', label:'Managing Editor'},
  {value:'photographer',    label:'Photographer'},
  {value:'videographer',    label:'Videographer'},
  {value:'translator',      label:'Translator'},
  {value:'columnist',       label:'Columnist'},
  {value:'analyst',         label:'Data Analyst'},
  {value:'contributor',     label:'Contributor'},
  {value:'intern',          label:'Intern'},
];

const LINK_TYPES={
  web:       {icon:'🌐',label:'Website'},
  twitter:   {icon:'✕', label:'Twitter / X'},
  instagram: {icon:'◉', label:'Instagram'},
  linkedin:  {icon:'in',label:'LinkedIn'},
  github:    {icon:'⬡', label:'GitHub'},
  youtube:   {icon:'▶', label:'YouTube'},
  email:     {icon:'✉', label:'Email'},
  tiktok:    {icon:'♪', label:'TikTok'},
  substack:  {icon:'✍', label:'Substack'},
  podcast:   {icon:'🎙',label:'Podcast'},
  other:     {icon:'↗', label:'Other'},
};
const CAT_SLUGS=new Set();

const fmtDate=d=>{if(!d)return'';try{return new Date(d).toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric'})}catch{return''}};
const fmtShort=d=>{if(!d)return'';try{return new Date(d).toLocaleDateString('en-GB',{day:'numeric',month:'short'})}catch{return''}};
const initials=n=>((n||'').split(' ').map(w=>w[0]||'').join('').slice(0,2).toUpperCase()||'?');
const strip=h=>(h||'').replace(/<[^>]+>/g,'').replace(/&nbsp;/g,' ').trim();
const safe=a=>Array.isArray(a)?a:[];

function Toast({msg,type='ok',onDone}){
  useEffect(()=>{const t=setTimeout(onDone,3400);return()=>clearTimeout(t)},[]);
  return <div className={`toast${type==='err'?' err':''}`}>{msg}</div>;
}

function Avatar({author,size=80}){
  return(
    <div className="avatar" style={{width:size,height:size,minWidth:size,fontSize:size*.36}}>
      {author?.avatar_url?<img src={author.avatar_url} alt={author.name||''} onError={e=>e.target.style.display='none'}/>:initials(author?.name)}
    </div>
  );
}

function useReadingProgress(){
  useEffect(()=>{
    const bar=document.getElementById('progress-bar');
    if(!bar)return;
    const update=()=>{
      const doc=document.documentElement;
      const scrolled=doc.scrollTop||document.body.scrollTop;
      const total=doc.scrollHeight-doc.clientHeight;
      bar.style.width=total>0?(scrolled/total*100)+'%':'0%';
    };
    window.addEventListener('scroll',update,{passive:true});
    return()=>window.removeEventListener('scroll',update);
  },[]);
}

function BackToTop(){
  const [vis,setVis]=useState(false);
  useEffect(()=>{
    const fn=()=>setVis(window.scrollY>600);
    window.addEventListener('scroll',fn,{passive:true});
    return()=>window.removeEventListener('scroll',fn);
  },[]);
  return(
    <button className={`back-top${vis?' visible':''}`} onClick={()=>window.scrollTo({top:0,behavior:'smooth'})} title="Back to top">↑</button>
  );
}

const NAV_GROUPS_STATIC=[
  {id:'home',l:'Home'},
  {id:'columns',l:'Columns'},
  {id:'discover',l:'Discover',items:[
    {id:'timeline',l:'Timeline'},{id:'map',l:'Map'},
    {id:'library',l:'Newsstand'},{id:'puzzles',l:'Puzzles'},{id:'newsletter',l:'Newsletter'},
    {id:'ebook',l:'Create Ebook'},
  ]},
  {id:'people',l:'People',items:[
    {id:'authors',l:'Authors'},{id:'about',l:'About'},{id:'submissions',l:'Submissions'},
    {id:'letters',l:'Letters'},{id:'profile',l:'My Profile'},
  ]},
  {id:'admin',l:'Admin ✦'},
].map(g=>g.id==='people'
  ?{...g,items:g.items.filter(i=>i.id!=='profile'||hasCap('accounts'))}
  :g).filter(g=>g.id!=='admin'||hasCap('admin'));
function NavGrouped({view,go,currentUser,sections}){
  const [open,setOpen]=useState(null);
  const ref=useRef(null);

  useEffect(()=>{
    const fn=e=>{if(ref.current&&!ref.current.contains(e.target))setOpen(null);};
    document.addEventListener('click',fn);
    return()=>document.removeEventListener('click',fn);
  },[]);

  const sectionsGroup=useMemo(()=>{
    if(!safe(sections).length) return null;
    return {id:'sections',l:'Sections',items:sections.map(s=>({id:s.slug,l:s.name}))};
  },[sections]);

  const userGroup=currentUser
    ?{id:'__user',l:`✦ ${currentUser.username}`,items:[
        ...(currentUser.role!=='reader'?[{id:'admin',l:'Editorial Desk ✦'}]:[]),
        {id:'profile',l:'My Profile'},
      ]}
    :null;

  const baseGroups=NAV_GROUPS_STATIC.reduce((acc,g)=>{
    if(g.id==='home') return [...acc,g,...(sectionsGroup?[sectionsGroup]:[])];
    return [...acc,g];
  },[]);
  const allGroups=userGroup?[...baseGroups,userGroup]:baseGroups;

  const renderGroup=g=>{
    if(g.action&&!g.items)return(
      <div key={g.id} className="ng-btn" style={{marginLeft:'auto',color:'var(--g500)'}}
        onClick={()=>{g.action();setOpen(null);}}>
        {g.l}
      </div>
    );
    if(!g.items)return(
      <div key={g.id} className={`ng-btn${view===g.id?' active':''}`} onClick={()=>{go(g.id);setOpen(null);}}>{g.l}</div>
    );
    const grpActive=g.items.some(i=>i.id===view);
    const isOpen=open===g.id;
    const isUser=g.id==='__user';
    return(
      <div key={g.id} style={{position:'relative',marginLeft:isUser?'auto':''}}>
        <div className={`ng-btn has-child${grpActive?' active':''}${isOpen?' grp-active':''}`}
          onClick={e=>{e.stopPropagation();setOpen(isOpen?null:g.id);}}>
          {g.l}
        </div>
        {isOpen&&(
          <div className="ng-drop" style={{right:isUser?0:'auto',left:isUser?'auto':0}}>
            {g.items.map(item=>(
              <div key={item.id}
                className={`ng-drop-item${view===item.id?' active':''}`}
                onClick={()=>{
                  if(item.action){item.action();setOpen(null);}
                  else{go(item.id);setOpen(null);}
                }}>
                {item.l}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return(
    <nav className="nav-grouped" ref={ref} style={{justifyContent:'flex-start'}}>
      {allGroups.map(renderGroup)}
    </nav>
  );
}

function LoginModal({onLogin,onClose}){
  const [tab,setTab]=useState('login');
  const [form,setForm]=useState({username:'',password:'',email:''});
  const [loading,setLoading]=useState(false);
  const [err,setErr]=useState('');

  const setF=(k,v)=>setForm(p=>({...p,[k]:v}));

  const submit=async()=>{
    if(!form.username||!form.password){setErr('Username and password required');return;}
    setLoading(true);setErr('');
    const endpoint=tab==='login'?'/api/auth/login':'/api/auth/register-reader';
    const r=await API.post(endpoint,form).catch(()=>({error:'Network error'}));
    setLoading(false);
    if(r.error){setErr(r.error);return;}
    onLogin(r);onClose();
  };

  return(
    <div className="login-overlay" onClick={onClose}>
      <div className="login-card" onClick={e=>e.stopPropagation()}>
        <div className="login-hdr">
          <span className="login-hdr-title">Voice Express</span>
          <span onClick={onClose} style={{cursor:'pointer',fontSize:'1.1rem',color:'var(--paper)'}}>✕</span>
        </div>
        <div style={{display:'flex',borderBottom:'var(--rt)'}}>
          {[['login','Sign In'],['register','Join']].map(([id,lbl])=>(
            <button key={id} onClick={()=>{setTab(id);setErr('');}}
              style={{flex:1,padding:'.62rem',fontFamily:'var(--fm)',fontSize:'.62rem',letterSpacing:'.1em',textTransform:'uppercase',border:'none',cursor:'pointer',background:tab===id?'var(--paper)':'var(--g100)',color:tab===id?'var(--ink)':'var(--g500)',borderBottom:tab===id?'2px solid var(--ink)':'none'}}>{lbl}</button>
          ))}
        </div>
        <div className="login-body">
          {err&&<div style={{fontFamily:'var(--fm)',fontSize:'.68rem',color:'#b83232',background:'#fdf3f3',border:'1px solid #b83232',padding:'.42rem .72rem',marginBottom:'.72rem'}}>{err}</div>}
          <FormField label="Username"><input value={form.username} onChange={e=>setF('username',e.target.value)} autoFocus onKeyDown={e=>e.key==='Enter'&&submit()}/></FormField>
          <FormField label="Password"><input type="password" value={form.password} onChange={e=>setF('password',e.target.value)} onKeyDown={e=>e.key==='Enter'&&submit()}/></FormField>
          {tab==='login'&&<div style={{fontFamily:'var(--fm)',fontSize:'.59rem',color:'var(--g400)',marginTop:'.32rem'}}>Forgot your password? Ask an admin to reset it.</div>}
          {tab==='register'&&<FormField label="Email (optional)"><input type="email" value={form.email} onChange={e=>setF('email',e.target.value)} placeholder="your@email.com"/></FormField>}
          {tab==='register'&&<div style={{fontFamily:'var(--fm)',fontSize:'.59rem',color:'var(--g400)',marginTop:'.32rem'}}>Create a reader account to track reading history and puzzle scores.</div>}
        </div>
        <div className="login-foot">
          <button className="btn-o" onClick={onClose}>Cancel</button>
          <button className="btn-p" onClick={submit} disabled={loading}>{loading?'…':tab==='login'?'Sign In':'Create Account'}</button>
        </div>
      </div>
    </div>
  );
}

function Masthead({view,setView,search,setSearch,readMode,setReadMode,theme,cycleTheme,currentUser,onLogin,onLogout,sections}){
  const [mob,setMob]=useState(false);
  const [showSearch,setShowSearch]=useState(false);
  const [navFits,setNavFits]=useState(true); 
  const inputRef=useRef(null);
  const measureRef=useRef(null); 
  const today=new Date().toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long',year:'numeric'});
  const themeIcons={light:'○',sepia:'◑',dark:'●'};

  const _product=VE_PRODUCT;
  const navItems=useMemo(()=>{
    if(_product==='library')
      return [{id:'library',l:'Newsstand'},{id:'newsletter',l:'Newsletter'},{id:'about',l:'About'}];
    const items=[
      {id:'home',l:'Home'},
      ...safe(sections).map(s=>({id:s.slug,l:s.name})),
      {id:'columns',l:'Columns'},{id:'library',l:'Newsstand'},{id:'puzzles',l:'Puzzles'},
      {id:'timeline',l:'Timeline'},{id:'map',l:'Map'},
      {id:'newsletter',l:'Newsletter'},{id:'letters',l:'Letters'},
      {id:'ebook',l:'Create Ebook'},
      {id:'authors',l:'Authors'},{id:'about',l:'About'},
    ];
    return _product==='newspaper'?items.filter(n=>n.id!=='library'):items;
  },[sections,_product]);

  useEffect(()=>{
    const check=()=>{
      const measure=measureRef.current;
      const masthead=document.getElementById('masthead');
      if(!measure||!masthead){
        setNavFits(window.innerWidth>1400);
        return;
      }
      const navW=measure.offsetWidth;
      setNavFits(navW<=masthead.clientWidth);
    };
    requestAnimationFrame(check);
    const t=setTimeout(check,150); 
    window.addEventListener('resize',check);
    return()=>{clearTimeout(t);window.removeEventListener('resize',check);};
  },[]);

  useEffect(()=>{
    const fn=e=>{
      if((e.key==='/'||((e.metaKey||e.ctrlKey)&&e.key==='k'))&&e.target.tagName!=='INPUT'&&e.target.tagName!=='TEXTAREA'){
        e.preventDefault();setShowSearch(true);setTimeout(()=>inputRef.current?.focus(),50);
      }
      if(e.key==='Escape'){setShowSearch(false);setSearch('');}
    };
    window.addEventListener('keydown',fn);
    return()=>window.removeEventListener('keydown',fn);
  },[]);

  if(readMode){
    return(
      <header id="masthead" style={{borderBottom:'var(--rt)'}}>
        <div className="mh-top read-mode-bar" style={{padding:'.4rem 2rem'}}>
          <button className="art-back" onClick={()=>setReadMode(false)} title="Exit reading view (Esc)">‹ Back</button>
          <span style={{fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',letterSpacing:'.2em',textTransform:'uppercase'}}>Read Mode</span>
          <div style={{display:'flex',gap:'.4rem'}}>
            <button className="btn-s" style={{fontSize:'.62rem'}} onClick={cycleTheme} title="Cycle theme">{themeIcons[theme]||'○'}</button>
            <button className="btn-s" aria-label="Create Ebook" title="Create Ebook" onClick={()=>setView('ebook')} style={{fontSize:'.62rem'}}>⊞</button>
          </div>
        </div>
      </header>
    );
  }

  const go=id=>{setView(id);setMob(false);};
  return(
    <>
      <div ref={measureRef} aria-hidden="true" style={{
        position:'fixed',top:'-999px',left:0,display:'flex',visibility:'hidden',
        pointerEvents:'none',whiteSpace:'nowrap',flexShrink:0
      }}>
        {navItems.map(n=>(
          <div key={n.id} style={{
            fontFamily:'var(--fm)',fontSize:'.61rem',letterSpacing:'.12em',textTransform:'uppercase',
            padding:'.52rem .82rem',flexShrink:0
          }}>{n.l}</div>
        ))}
      </div>

      <header id="masthead">
        <div className="mh-top">
          <div className="mh-logo-side">
            <img className="mh-logo-img" src="static/tve_logo.png" alt="TVE" onError={e=>e.target.style.display='none'}/>
          </div>
          <div className="mh-brand">
            <h1 onClick={()=>setView('home')}>The Voice Express</h1>
            <div className="mh-tagline">The Truth Takes Time</div>
          </div>
          <div className="mh-date-side">
            <div className="mh-date">{today}<br/>New Delhi · Free</div>
          </div>
        </div>

        <div className="mh-toolbar">
          <div className="mh-toolbar-left">
            <span style={{color:'var(--g600)'}}>Est.&nbsp;2022</span>
            <span style={{color:'var(--g300)'}}>|</span>
            <span>Independent</span>
            <span style={{color:'var(--g300)'}}>|</span>
            <button className="btn-s" style={{fontSize:'.56rem',padding:'.1rem .4rem'}} onClick={()=>setView('submissions')}>Submit a story</button>
          </div>
          <div className="mh-toolbar-center">
            {showSearch
              ?<input ref={inputRef} className="search-inp" style={{fontSize:'.7rem',height:'1.5rem'}} placeholder="Search… (Esc to close)" value={search}
                  onChange={e=>setSearch(e.target.value)}
                  onKeyDown={e=>{
                    if(e.key==='Enter'&&search.trim()){setView('search');setShowSearch(false);}
                    if(e.key==='Escape'){setShowSearch(false);setSearch('');}
                  }}/>
              :<button className="btn-icon" style={{fontSize:'.75rem'}} aria-label="Search" title="Search (press /)" onClick={()=>{setShowSearch(true);setTimeout(()=>inputRef.current?.focus(),50);}}>⌕</button>}
          </div>
          <div className="mh-toolbar-right">
            <button className="btn-icon" aria-label="Newsstand" title="Newsstand — published issues" onClick={()=>setView('library')}
              style={{fontSize:'.72rem',lineHeight:1,opacity:view==='library'?1:.6}}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="3.5" width="8.5" height="10" rx="1"/><path d="M10.5 5.5H14V13a1 1 0 0 1-1 1H4"/>
                <line x1="4" y1="6.2" x2="8.5" y2="6.2"/><line x1="4" y1="8.5" x2="8.5" y2="8.5"/><line x1="4" y1="10.8" x2="7" y2="10.8"/>
              </svg>
            </button>
            <button className="btn-icon" aria-label={`Theme: ${theme}`} title={`Theme: ${theme}`} onClick={cycleTheme} style={{fontSize:'.72rem'}}>{themeIcons[theme]||'○'}</button>
            <button className="btn-icon" aria-label="Create Ebook" title="Create Ebook" onClick={()=>setView('ebook')}
              style={{fontSize:'.78rem',lineHeight:1,opacity:view==='ebook'?1:.55}}>
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="1" width="9" height="12" rx="1"/>
                <line x1="5" y1="4.5" x2="9" y2="4.5"/>
                <line x1="5" y1="7" x2="9" y2="7"/>
                <line x1="5" y1="9.5" x2="7.5" y2="9.5"/>
              </svg>
            </button>
            {currentUser
              ?<><span className="user-pill" onClick={()=>setView(currentUser.role==='reader'?'profile':'admin')} title={currentUser.role}>✦ {currentUser.username}</span>
                <button className="btn-icon" aria-label="Sign out" title="Sign out" onClick={onLogout} style={{fontSize:'.68rem'}}>↩</button></>
              :(hasCap('accounts')
                ?<button className="btn-icon" aria-label="Sign in" title="Sign in" onClick={onLogin} style={{fontSize:'.68rem'}}>⊕</button>
                :null)}
            <div className="mob-btn" onClick={()=>setMob(true)} role="button" aria-label="Open menu"><span/><span/><span/></div>
          </div>
        </div>
        {navFits
          ?<nav className="nav-bar" role="navigation">
              {navItems.map(n=><div key={n.id} className={`nav-item${view===n.id?' active':''}`} onClick={()=>go(n.id)}>{n.l}</div>)}
            </nav>
          :<NavGrouped view={view} go={go} currentUser={currentUser} sections={sections}/>
        }
      </header>
      {mob&&(
        <div className="mob-overlay open" role="dialog" aria-modal="true">
          <button className="mob-close" onClick={()=>setMob(false)}>✕ Close</button>
          <div style={{fontFamily:'var(--fh)',fontSize:'2.4rem',fontWeight:900,textAlign:'center',marginBottom:'2rem',borderBottom:'var(--rule)',paddingBottom:'1.2rem',textTransform:'uppercase'}}>Voice Express</div>
          {navItems.map(n=><div key={n.id} className="mob-nav-item" onClick={()=>go(n.id)}>{n.l}</div>)}
          <div style={{marginTop:'auto',paddingTop:'2rem',fontFamily:'var(--fm)',fontSize:'.58rem',color:'var(--g500)',letterSpacing:'.1em',textTransform:'uppercase'}}>Truth Takes Time</div>
        </div>
      )}
    </>
  );
}

