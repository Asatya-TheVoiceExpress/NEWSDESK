function seededRng(seed){
  let s=(seed^0x9e3779b9)>>>0||1;
  return{
    next(){s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)/0x100000000;},
    int(n){return Math.floor(this.next()*n);},
    shuffle(a){a=[...a];for(let i=a.length-1;i>0;i--){const j=this.int(i+1);[a[i],a[j]]=[a[j],a[i]];}return a;}
  };
}
function strToSeed(s){let h=5381;for(let i=0;i<s.length;i++)h=(((h<<5)+h)^s.charCodeAt(i))>>>0;return h||1;}
function todayStr(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
function shiftDay(ds,n){const d=new Date(ds+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);}
function pzFmtDate(s){try{return new Date(s+'T12:00:00').toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short',year:'numeric'});}catch{return s;}}
function fmtMin(s){return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;}
function dayOfYear(ds){const d=new Date(ds+'T12:00:00');return Math.floor((d-new Date(d.getFullYear(),0,0))/864e5);}

function sdkOk(g,r,c,n){
  for(let i=0;i<9;i++)if(g[r][i]===n||g[i][c]===n)return false;
  const br=Math.floor(r/3)*3,bc=Math.floor(c/3)*3;
  for(let i=0;i<3;i++)for(let j=0;j<3;j++)if(g[br+i][bc+j]===n)return false;
  return true;
}
function sdkFill(g,pos=0){
  if(pos===81)return true;
  const r=Math.floor(pos/9),c=pos%9;
  if(g[r][c]!==0)return sdkFill(g,pos+1);
  for(let n=1;n<=9;n++){if(sdkOk(g,r,c,n)){g[r][c]=n;if(sdkFill(g,pos+1))return true;g[r][c]=0;}}
  return false;
}
function genSudoku(seed,difficulty){
  const rng=seededRng(seed);
  const g=Array.from({length:9},()=>Array(9).fill(0));
  for(let b=0;b<3;b++){const ns=rng.shuffle([1,2,3,4,5,6,7,8,9]);for(let i=0;i<3;i++)for(let j=0;j<3;j++)g[b*3+i][b*3+j]=ns[i*3+j];}
  sdkFill(g);
  const solution=g.map(r=>[...r]);
  const removes={easy:35,medium:46,hard:55}[difficulty]||46;
  const puzzle=solution.map(r=>[...r]);
  const cells=rng.shuffle([...Array(81).keys()]);
  for(let i=0;i<removes;i++){const r=Math.floor(cells[i]/9),c=cells[i]%9;puzzle[r][c]=0;}
  return{puzzle,solution};
}

const CWS=13;
const DAILY_TOPICS=['history','science','nature','art','music','film','literature',
  'geography','food','sports','technology','philosophy','astronomy','medicine',
  'architecture','mathematics','biology','chemistry','physics','economics',
  'psychology','mythology','language','culture','environment','ocean','space',
  'theatre','poetry','democracy','climate','innovation','tradition','discovery'];

function cleanClue(def,topic){
  let s=(def||'').replace(/^[a-z]+\t/,'').trim();
  let depth=0,cut=-1;
  for(let i=0;i<s.length;i++){
    const ch=s[i];
    if(ch==='(')depth++;
    else if(ch===')')depth=Math.max(0,depth-1);
    else if((ch===';'||ch===',')&&depth===0){cut=i;break;}
  }
  if(cut>=0)s=s.slice(0,cut);
  const open=s.lastIndexOf('(');
  if(open>=0&&s.indexOf(')',open)===-1)s=s.slice(0,open);   
  s=s.trim().replace(/[\s(,;]+$/,'').trim();
  return s||`A word related to ${topic}`;
}

function buildCrossword(words,size=CWS){
  const G=Array.from({length:size},()=>Array(size).fill(null));
  const placed=[];
  function ok(r,c){return r>=0&&r<size&&c>=0&&c<size;}
  function canPlace(w,r,c,dir){
    const dr=dir==='V'?1:0,dc=dir==='H'?1:0;
    const er=r+dr*(w.length-1),ec=c+dc*(w.length-1);
    if(!ok(r,c)||!ok(er,ec))return false;
    if(ok(r-dr,c-dc)&&G[r-dr][c-dc]!==null)return false;
    if(ok(er+dr,ec+dc)&&G[er+dr][ec+dc]!==null)return false;
    let hits=placed.length===0;
    for(let i=0;i<w.length;i++){
      const cr=r+dr*i,cc=c+dc*i;
      if(G[cr][cc]!==null){if(G[cr][cc]!==w[i])return false;hits=true;}
      else{
        if(dir==='H'){if(ok(cr-1,cc)&&G[cr-1][cc]!==null)return false;if(ok(cr+1,cc)&&G[cr+1][cc]!==null)return false;}
        else{if(ok(cr,cc-1)&&G[cr][cc-1]!==null)return false;if(ok(cr,cc+1)&&G[cr][cc+1]!==null)return false;}
      }
    }
    return hits;
  }
  function putWord(w,clue,r,c,dir){
    const dr=dir==='V'?1:0,dc=dir==='H'?1:0;
    for(let i=0;i<w.length;i++)G[r+dr*i][c+dc*i]=w[i];
    placed.push({word:w,clue,r,c,dir});
  }
  if(!words.length)return null;
  const fw=words[0];
  putWord(fw.word,fw.clue,Math.floor(size/2),Math.max(0,Math.floor((size-fw.word.length)/2)),'H');
  for(let wi=1;wi<words.length;wi++){
    const{word,clue}=words[wi];
    let best=null,bsc=-1;
    for(let li=0;li<word.length;li++){
      const ch=word[li];
      for(let gr=0;gr<size;gr++)for(let gc=0;gc<size;gc++){
        if(G[gr][gc]!==ch)continue;
        for(const[r,c,dir]of[[gr,gc-li,'H'],[gr-li,gc,'V']]){
          if(!canPlace(word,r,c,dir))continue;
          const dr=dir==='V'?1:0,dc=dir==='H'?1:0;
          let sc=0;for(let i=0;i<word.length;i++)if(G[r+dr*i][c+dc*i]===word[i])sc++;
          if(sc>bsc){bsc=sc;best={r,c,dir};}
        }
      }
    }
    if(best)putWord(word,clue,best.r,best.c,best.dir);
  }
  let num=1;
  const nums=Array.from({length:size},()=>Array(size).fill(0));
  for(let r=0;r<size;r++)for(let c=0;c<size;c++){
    if(G[r][c]===null)continue;
    const sH=(c===0||G[r][c-1]===null)&&c+1<size&&G[r][c+1]!==null;
    const sV=(r===0||G[r-1][c]===null)&&r+1<size&&G[r+1][c]!==null;
    if(sH||sV)nums[r][c]=num++;
  }
  const across=[],down=[];
  for(const p of placed){
    const n=nums[p.r][p.c];
    if(!n)continue;
    (p.dir==='H'?across:down).push({num:n,...p,len:p.word.length});
  }
  across.sort((a,b)=>a.num-b.num);down.sort((a,b)=>a.num-b.num);
  return{grid:G,nums,across,down,size};
}

function PuzzleCalendar({puzzleType,difficulty,onPick,onBack,title}){
  const today=todayStr();
  const [archive,setArchive]=useState({});
  const [loading,setLoading]=useState(true);

  useEffect(()=>{
    const q=`?type=${puzzleType}&difficulty=${difficulty||''}`;
    API.get(`/api/puzzles/archive${q}`)
      .then(rows=>{
        const m={};
        safe(rows).forEach(r=>{m[r.puzzle_date]={completed:!!r.completed,elapsed:r.elapsed||0};});
        setArchive(m);
      })
      .catch(()=>{})
      .finally(()=>setLoading(false));
  },[puzzleType,difficulty]);

  const days=Array.from({length:30},(_,i)=>shiftDay(today,-i));
  const months={};
  days.forEach(d=>{const m=d.slice(0,7);(months[m]=months[m]||[]).push(d);});

  return(
    <div>
      <button className="btn-o" style={{marginBottom:'1.2rem'}} onClick={onBack}>← Back to Puzzle</button>
      <div className="sec-lbl"><span>{title}</span></div>
      {loading&&<div className="loading">Loading archive</div>}
      {!loading&&Object.entries(months).sort(([a],[b])=>b.localeCompare(a)).map(([mon,ds])=>{
        const[y,m]=mon.split('-');
        const label=new Date(parseInt(y),parseInt(m)-1,1).toLocaleString('default',{month:'long',year:'numeric'});
        return(
          <div key={mon} style={{marginBottom:'1.6rem'}}>
            <div className="pz-cal-year">{label}</div>
            <div className="pz-cal-grid">
              {ds.map(d=>{
                const done=archive[d]?.completed;
                const dayN=new Date(d+'T12:00:00').getDate();
                return(
                  <div key={d} className={`pz-cal-cell${done?' done':''}`} onClick={()=>onPick(d)} title={pzFmtDate(d)}>
                    <span style={{fontWeight:700}}>{dayN}</span>
                    {done&&<span style={{fontSize:'.46rem'}}>✓</span>}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SudokuPage({toast}){
  const today=todayStr();
  const [date,setDate]=useState(today);
  const [diff,setDiff]=useState('medium');
  const [puzzle,setPuzzle]=useState(null);
  const [solution,setSolution]=useState(null);
  const [board,setBoard]=useState(null);
  const [nGrid,setNGrid]=useState(null); 
  const [sel,setSel]=useState(null);
  const [notesMode,setNotesMode]=useState(false);
  const [checking,setChecking]=useState(false);
  const [completed,setCompleted]=useState(false);
  const [elapsed,setElapsed]=useState(0);
  const [tab,setTab]=useState('play');
  const timerRef=useRef(null);
  const t0Ref=useRef(null);
  const saveRef=useRef(null);

  useEffect(()=>{
    const seed=strToSeed(`${date}-${diff}`);
    const{puzzle:p,solution:s}=genSudoku(seed,diff);
    setPuzzle(p);setSolution(s);
    setSel(null);setChecking(false);setNotesMode(false);
    setBoard(p.map(r=>[...r]));
    setNGrid(Array.from({length:9},()=>Array.from({length:9},()=>new Set())));
    setElapsed(0);setCompleted(false);
    API.get(`/api/puzzles/session?type=sudoku&date=${date}&difficulty=${diff}`)
      .then(sv=>{
        if(!sv||!sv.state)return;
        const st=typeof sv.state==='string'?JSON.parse(sv.state):sv.state;
        if(st.board)setBoard(st.board);
        if(st.notes)setNGrid(st.notes.map(r=>r.map(a=>new Set(a))));
        setElapsed(sv.elapsed||0);
        setCompleted(!!sv.completed);
      })
      .catch(()=>{});
  },[date,diff]);

  useEffect(()=>{
    clearInterval(timerRef.current);
    if(completed||tab!=='play'||!board)return;
    t0Ref.current=Date.now()-elapsed*1000;
    timerRef.current=setInterval(()=>setElapsed(Math.floor((Date.now()-t0Ref.current)/1000)),500);
    return()=>clearInterval(timerRef.current);
  },[tab,completed,!!board]);

  useEffect(()=>{
    if(!board||!nGrid)return;
    clearTimeout(saveRef.current);
    saveRef.current=setTimeout(()=>{
      API.post('/api/puzzles/session',{
        type:'sudoku',date,difficulty:diff,
        state:{board,notes:nGrid.map(r=>r.map(s=>[...s]))},
        elapsed,completed:completed?1:0
      }).catch(()=>{});
    },600);
    return()=>clearTimeout(saveRef.current);
  },[board,nGrid,elapsed,completed]);

  const isGiven=(r,c)=>puzzle?.[r]?.[c]!==0;

  const enter=(n)=>{
    if(!sel||!board||!puzzle)return;
    const[r,c]=sel;
    if(isGiven(r,c))return;
    if(notesMode){
      setNGrid(prev=>{const next=prev.map(row=>row.map(s=>new Set(s)));if(n===0)next[r][c].clear();else if(next[r][c].has(n))next[r][c].delete(n);else next[r][c].add(n);return next;});
    } else {
      const nb=board.map(rr=>[...rr]);
      nb[r][c]=nb[r][c]===n?0:n;
      setBoard(nb);
      setNGrid(prev=>{const next=prev.map(row=>row.map(s=>new Set(s)));next[r][c].clear();return next;});
      if(nb.every((rr,ri)=>rr.every((v,ci)=>v!==0&&v===solution[ri][ci]))){setCompleted(true);toast('Sudoku complete! ✓');API.post('/api/reader/puzzle-complete',{type:'sudoku',date,difficulty:diff,elapsed}).catch(()=>{});}
    }
  };

  const hl=useMemo(()=>{
    if(!sel||!board)return new Set();
    const[sr,sc]=sel,s=new Set();
    for(let r=0;r<9;r++)for(let c=0;c<9;c++)
      if(r===sr||c===sc||(Math.floor(r/3)===Math.floor(sr/3)&&Math.floor(c/3)===Math.floor(sc/3)))s.add(`${r},${c}`);
    return s;
  },[sel]);

  const sameN=useMemo(()=>{
    if(!sel||!board)return new Set();
    const[sr,sc]=sel,n=board[sr][sc],s=new Set();
    if(!n)return s;
    for(let r=0;r<9;r++)for(let c=0;c<9;c++)if(board[r][c]===n)s.add(`${r},${c}`);
    return s;
  },[sel,board]);

  if(tab==='archive')return(
    <PuzzleCalendar puzzleType="sudoku" difficulty={diff} title="Sudoku Archive — Last 30 Days"
      onPick={d=>{setDate(d);setTab('play');}} onBack={()=>setTab('play')}/>
  );
  if(!board||!puzzle)return <div className="loading">Generating puzzle</div>;

  return(
    <div className="su-wrap">
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1rem',flexWrap:'wrap',gap:'.5rem'}}>
        <div style={{display:'flex',alignItems:'center',gap:'.4rem'}}>
          <button className="btn-s" onClick={()=>setDate(shiftDay(date,-1))}>◀</button>
          <span style={{fontFamily:'var(--fm)',fontSize:'.62rem',letterSpacing:'.06em',textTransform:'uppercase',color:'var(--g500)',minWidth:148,textAlign:'center'}}>{pzFmtDate(date)}{date===today?' · Today':''}</span>
          <button className="btn-s" onClick={()=>setDate(shiftDay(date,1))} disabled={date>=today}>▶</button>
        </div>
        <div style={{display:'flex',gap:'.28rem'}}>
          {['easy','medium','hard'].map(d=><button key={d} className={`btn-s${diff===d?' on':''}`} onClick={()=>setDiff(d)}>{d[0].toUpperCase()+d.slice(1)}</button>)}
        </div>
        <div style={{display:'flex',alignItems:'center',gap:'.5rem'}}>
          <span style={{fontFamily:'var(--fm)',fontSize:'.82rem',minWidth:46}}>{fmtMin(elapsed)}</span>
          <button className="btn-s" onClick={()=>setTab('archive')}>Archive</button>
        </div>
      </div>

      {completed&&<div style={{padding:'.65rem',background:'var(--ink)',color:'var(--paper)',fontFamily:'var(--fm)',fontSize:'.7rem',letterSpacing:'.12em',textTransform:'uppercase',marginBottom:'1rem',textAlign:'center'}}>Solved · {fmtMin(elapsed)}</div>}

      <div className="su-grid"
        tabIndex={0} style={{outline:'none'}}
        onKeyDown={e=>{
          if(!sel)return;
          const[r,c]=sel;
          const mv={ArrowUp:[-1,0],ArrowDown:[1,0],ArrowLeft:[0,-1],ArrowRight:[0,1]};
          if(mv[e.key]){e.preventDefault();const[dr,dc]=mv[e.key];setSel([Math.max(0,Math.min(8,r+dr)),Math.max(0,Math.min(8,c+dc))]);}
          else if(e.key>='1'&&e.key<='9')enter(parseInt(e.key));
          else if(e.key==='0'||e.key==='Backspace'||e.key==='Delete')enter(0);
          else if(e.key==='n'||e.key==='N'){e.preventDefault();setNotesMode(v=>!v);}
        }}>
        {board.map((row,r)=>row.map((val,c)=>{
          const k=`${r},${c}`;
          const isSel=sel&&sel[0]===r&&sel[1]===c;
          const isHl=!isSel&&hl.has(k);
          const isSN=!isSel&&!isHl&&sameN.has(k);
          const isErr=checking&&!isGiven(r,c)&&val!==0&&val!==solution[r][c];
          const isOk=checking&&!isGiven(r,c)&&val!==0&&val===solution[r][c];
          return(
            <div key={k}
              className={`su-cell${isGiven(r,c)?' given':' entry'}${isSel?' sel':''}${isHl?' hl':''}${isSN?' sn':''}${isErr?' err':''}${isOk?' ok':''}${c%3===2&&c<8?' bxr':''}${r%3===2&&r<8?' bxb':''}`}
              onClick={()=>setSel([r,c])}>
              {val!==0&&val}
              {val===0&&nGrid[r][c].size>0&&(
                <div className="su-notes">
                  {[1,2,3,4,5,6,7,8,9].map(n=><div key={n} className="su-note">{nGrid[r][c].has(n)?n:''}</div>)}
                </div>
              )}
            </div>
          );
        }))}
      </div>

      <div className="su-numpad">
        {[1,2,3,4,5,6,7,8,9].map(n=><button key={n} onClick={()=>enter(n)}>{n}</button>)}
        <button className="erase" onClick={()=>enter(0)}>Erase</button>
        <button className={`notes-btn${notesMode?' on':''}`} onClick={()=>setNotesMode(v=>!v)}>Notes{notesMode?' ON':' OFF'}</button>
      </div>

      <div style={{display:'flex',gap:'.38rem',justifyContent:'center',flexWrap:'wrap',marginBottom:'.75rem'}}>
        <button className={`btn-s${checking?' on':''}`} onClick={()=>setChecking(v=>!v)}>Check</button>
        <button className="btn-s" onClick={()=>{if(window.confirm('Reveal the full solution?')){setBoard(solution.map(r=>[...r]));setCompleted(false);}}}>Reveal</button>
        <button className="btn-s" onClick={()=>{const s=strToSeed(`${date}-${diff}`);const{puzzle:p,solution:sv}=genSudoku(s,diff);setPuzzle(p);setSolution(sv);setBoard(p.map(r=>[...r]));setNGrid(Array.from({length:9},()=>Array.from({length:9},()=>new Set())));setElapsed(0);setCompleted(false);setSel(null);setChecking(false);API.post('/api/puzzles/session',{type:'sudoku',date,difficulty:diff,state:{board:p.map(r=>[...r]),notes:[]},elapsed:0,completed:0}).catch(()=>{});}}>Reset</button>
      </div>
      <div style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g400)',letterSpacing:'.06em',textTransform:'uppercase'}}>Click a cell · Type 1–9 · Arrow keys navigate · N toggles notes</div>
    </div>
  );
}

function CrosswordPage({toast}){
  const today=todayStr();
  const [date,setDate]=useState(today);
  const [cw,setCw]=useState(null);
  const [userG,setUserG]=useState(null);
  const [loading,setLoading]=useState(false);
  const [sel,setSel]=useState(null); 
  const [dir,setDir]=useState('H');
  const [checking,setChecking]=useState(false);
  const [completed,setCompleted]=useState(false);
  const [elapsed,setElapsed]=useState(0);
  const [topic,setTopic]=useState('');
  const [tab,setTab]=useState('play');
  const timerRef=useRef(null);
  const t0Ref=useRef(null);
  const hidRef=useRef(null);
  const cwSaveRef=useRef(null);

  useEffect(()=>{loadCW(date);},[date]);

  async function loadCW(d){
    setLoading(true);setCw(null);setSel(null);setChecking(false);setDir('H');
    try{
      let wdata=await API.get(`/api/puzzles/wordcache?date=${d}`).catch(()=>null);
      if(!wdata){
        const doy=dayOfYear(d);
        const tp=DAILY_TOPICS[doy%DAILY_TOPICS.length];
        const res=await fetch(`https://api.datamuse.com/words?rel_trg=${encodeURIComponent(tp)}&max=70&md=d`);
        const raw=await res.json();
        const words=raw
          .filter(w=>/^[a-z]+$/.test(w.word)&&w.word.length>=4&&w.word.length<=9)
          .map(w=>({word:w.word.toUpperCase(),clue:cleanClue(w.defs?.[0],tp)}))
          .filter((w,i,a)=>i===a.findIndex(x=>x.word===w.word));
        words.sort((a,b)=>b.word.length-a.word.length);
        wdata={words:words.slice(0,22),topic:tp};
        API.post('/api/puzzles/wordcache',{date:d,...wdata}).catch(()=>{});
      }
      setTopic(wdata.topic);
      const built=buildCrossword((wdata.words||[]).map(w=>({...w,clue:cleanClue(w.clue,wdata.topic)})));
      if(!built||built.across.length<3){toast('Could not build crossword — will retry with a different source','err');setLoading(false);return;}
      setCw(built);
      const sv=await API.get(`/api/puzzles/session?type=crossword&date=${d}&difficulty=`).catch(()=>null);
      if(sv&&sv.state){
        const st=typeof sv.state==='string'?JSON.parse(sv.state):sv.state;
        setUserG(st.grid||Array.from({length:CWS},()=>Array(CWS).fill('')));
        setElapsed(sv.elapsed||0);setCompleted(!!sv.completed);
      } else {
        setUserG(Array.from({length:CWS},()=>Array(CWS).fill('')));setElapsed(0);setCompleted(false);
      }
    }catch(e){toast('Failed to load crossword: '+e.message,'err');}
    setLoading(false);
  }

  useEffect(()=>{
    clearInterval(timerRef.current);
    if(completed||tab!=='play'||!cw)return;
    t0Ref.current=Date.now()-elapsed*1000;
    timerRef.current=setInterval(()=>setElapsed(Math.floor((Date.now()-t0Ref.current)/1000)),500);
    return()=>clearInterval(timerRef.current);
  },[tab,completed,!!cw]);

  useEffect(()=>{
    if(!userG||!cw)return;
    clearTimeout(cwSaveRef.current);
    cwSaveRef.current=setTimeout(()=>{
      API.post('/api/puzzles/session',{
        type:'crossword',date,difficulty:'',
        state:{grid:userG},elapsed,completed:completed?1:0
      }).catch(()=>{});
    },600);
    return()=>clearTimeout(cwSaveRef.current);
  },[userG,elapsed,completed]);

  useEffect(()=>{if(sel&&hidRef.current)hidRef.current.focus();},[sel]);

  function wordAt(r,c,d){
    if(!cw)return null;
    return(d==='H'?cw.across:cw.down).find(w=>{
      const dr=d==='V'?1:0,dc=d==='H'?1:0;
      for(let i=0;i<w.len;i++)if(w.r+dr*i===r&&w.c+dc*i===c)return true;
      return false;
    });
  }

  function cellsOf(w){
    if(!w)return new Set();
    const dr=w.dir==='V'?1:0,dc=w.dir==='H'?1:0,s=new Set();
    for(let i=0;i<w.len;i++)s.add(`${w.r+dr*i},${w.c+dc*i}`);
    return s;
  }

  function advance(r,c,d,grid){
    const w=wordAt(r,c,d);if(!w)return;
    const dr=d==='V'?1:0,dc=d==='H'?1:0;
    let found=false;
    for(let i=0;i<w.len;i++){
      const nr=w.r+dr*i,nc=w.c+dc*i;
      if(nr===r&&nc===c){found=true;continue;}
      if(found&&cw.grid[nr][nc]!==null&&!(grid||userG)[nr][nc]){setSel([nr,nc]);return;}
    }
  }

  function retreat(r,c,d){
    const w=wordAt(r,c,d);if(!w)return;
    const dr=d==='V'?1:0,dc=d==='H'?1:0;
    let prev=null;
    for(let i=0;i<w.len;i++){const nr=w.r+dr*i,nc=w.c+dc*i;if(nr===r&&nc===c)break;prev=[nr,nc];}
    if(prev)setSel(prev);
  }

  function moveCell(r,c,dr,dc){
    if(!cw)return null;
    let nr=r+dr,nc=c+dc;
    while(nr>=0&&nr<CWS&&nc>=0&&nc<CWS&&cw.grid[nr][nc]===null){nr+=dr;nc+=dc;}
    return(nr>=0&&nr<CWS&&nc>=0&&nc<CWS)?[nr,nc]:null;
  }

  function typeLetter(ch){
    if(!sel||!cw||!userG)return;
    const[r,c]=sel;
    if(cw.grid[r][c]===null)return;
    const ng=userG.map(row=>[...row]);ng[r][c]=ch.toUpperCase();setUserG(ng);advance(r,c,dir,ng);
    const allW=[...cw.across,...cw.down];
    if(allW.every(w=>{const dr=w.dir==='V'?1:0,dc=w.dir==='H'?1:0;for(let i=0;i<w.len;i++)if(ng[w.r+dr*i][w.c+dc*i]!==w.word[i])return false;return true;})){setCompleted(true);toast('Crossword complete! Brilliant! ✓');API.post('/api/reader/puzzle-complete',{type:'crossword',date,difficulty:'',elapsed}).catch(()=>{});}
  }

  function doBackspace(){
    if(!sel||!cw||!userG)return;
    const[r,c]=sel;
    if(cw.grid[r][c]===null)return;
    const ng=userG.map(row=>[...row]);
    if(ng[r][c]){ng[r][c]='';setUserG(ng);}
    else{retreat(r,c,dir);ng[r][c]='';setUserG(ng);}
  }

  const ARROW_DELTA={ArrowUp:[-1,0],ArrowDown:[1,0],ArrowLeft:[0,-1],ArrowRight:[0,1]};

  function inputKey(e){
    if(!sel||!cw||!userG)return;
    const[r,c]=sel;
    if(cw.grid[r][c]===null)return;
    if((e.ctrlKey||e.metaKey)&&ARROW_DELTA[e.key]){
      e.preventDefault();
      const[dr,dc]=ARROW_DELTA[e.key];
      const next=moveCell(r,c,dr,dc);
      if(next){setSel(next);if(dc!==0)setDir('H');else if(dr!==0)setDir('V');}
      return;
    }
    if(e.key==='ArrowLeft'||e.key==='ArrowRight'){
      e.preventDefault();
      if(dir==='H'){if(e.key==='ArrowRight')advance(r,c,'H',null);else retreat(r,c,'H');}
      else setDir('H');
      return;
    }
    if(e.key==='ArrowUp'||e.key==='ArrowDown'){
      e.preventDefault();
      if(dir==='V'){if(e.key==='ArrowDown')advance(r,c,'V',null);else retreat(r,c,'V');}
      else setDir('V');
      return;
    }
    if(e.key==='Tab'){e.preventDefault();const list=dir==='H'?cw.across:cw.down;const cur=wordAt(r,c,dir);if(cur){const idx=list.findIndex(w=>w.num===cur.num);const nxt=list[(idx+1)%list.length];setSel([nxt.r,nxt.c]);}return;}
    if(/^[a-zA-Z]$/.test(e.key)){e.preventDefault();typeLetter(e.key);}
    else if(e.key==='Backspace'||e.key==='Delete'){e.preventDefault();doBackspace();}
  }

  const selWord=sel?wordAt(sel[0],sel[1],dir):null;
  const wCells=cellsOf(selWord);

  if(tab==='archive')return(
    <PuzzleCalendar puzzleType="crossword" difficulty="" title="Crossword Archive — Last 30 Days"
      onPick={d=>{setDate(d);setTab('play');}} onBack={()=>setTab('play')}/>
  );

  return(
    <div>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1rem',flexWrap:'wrap',gap:'.5rem'}}>
        <div style={{display:'flex',alignItems:'center',gap:'.4rem'}}>
          <button className="btn-s" onClick={()=>setDate(shiftDay(date,-1))}>◀</button>
          <span style={{fontFamily:'var(--fm)',fontSize:'.62rem',letterSpacing:'.06em',textTransform:'uppercase',color:'var(--g500)',minWidth:148,textAlign:'center'}}>{pzFmtDate(date)}{date===today?' · Today':''}</span>
          <button className="btn-s" onClick={()=>setDate(shiftDay(date,1))} disabled={date>=today}>▶</button>
        </div>
        {topic&&<span style={{fontFamily:'var(--fm)',fontSize:'.59rem',letterSpacing:'.1em',textTransform:'uppercase',color:'var(--g500)'}}>Theme: <strong style={{color:'var(--ink)'}}>{topic}</strong></span>}
        <div style={{display:'flex',alignItems:'center',gap:'.5rem'}}>
          <span style={{fontFamily:'var(--fm)',fontSize:'.82rem',minWidth:44}}>{fmtMin(elapsed)}</span>
          <button className="btn-s" onClick={()=>setTab('archive')}>Archive</button>
        </div>
      </div>

      {completed&&<div style={{padding:'.65rem',background:'var(--ink)',color:'var(--paper)',fontFamily:'var(--fm)',fontSize:'.7rem',letterSpacing:'.12em',textTransform:'uppercase',marginBottom:'1rem',textAlign:'center'}}>Crossword Solved · {fmtMin(elapsed)}</div>}
      {loading&&<div className="loading">Fetching words from Datamuse</div>}

      {!loading&&cw&&userG&&(
        <>
          <input ref={hidRef} style={{position:'fixed',top:'-999px',left:'-999px',opacity:0,width:1,height:1,fontSize:16,pointerEvents:'none'}}
            onKeyDown={inputKey} readOnly inputMode="text" autoCapitalize="off" autoCorrect="off" autoComplete="off" spellCheck="false"/>

          <div className="cw-layout">
            <div>
              <div className="cw-active-clue">
                {selWord
                  ? <><span className="cw-clue-n">{selWord.num}{dir==='H'?'A':'D'}</span>{selWord.clue}</>
                  : <span style={{opacity:.55}}>Select a cell to see its clue</span>}
              </div>
              <div className="cw-outer">
                <div className="cw-grid" style={{gridTemplateColumns:`repeat(${CWS},var(--cw-cell,38px))`}}>
                  {cw.grid.map((row,r)=>row.map((ch,c)=>{
                    const k=`${r},${c}`;
                    const isSel=sel&&sel[0]===r&&sel[1]===c;
                    const isWhl=!isSel&&wCells.has(k);
                    const num=cw.nums[r][c];
                    const val=userG[r][c]||'';
                    const isBlk=ch===null;
                    const isErr=checking&&!isBlk&&val&&val!==ch;
                    const isOk=checking&&!isBlk&&val&&val===ch;
                    return(
                      <div key={k}
                        className={`cw-cell${isBlk?' blk':''}${isSel?' sel':''}${isWhl?' whl':''}${isErr?' err':''}${isOk?' ok':''}`}
                        onClick={()=>{
                          if(isBlk)return;
                          if(sel&&sel[0]===r&&sel[1]===c){setDir(d=>d==='H'?'V':'H');}
                          else{
                            setSel([r,c]);
                            const hW=wordAt(r,c,'H'),vW=wordAt(r,c,'V');
                            if(hW&&!vW)setDir('H');else if(vW&&!hW)setDir('V');
                          }
                          hidRef.current?.focus();
                        }}>
                        {!isBlk&&num>0&&<span className="cw-num">{num}</span>}
                        {!isBlk&&val}
                      </div>
                    );
                  }))}
                </div>
              </div>
              <div className="cw-keyboard">
                {['QWERTYUIOP','ASDFGHJKL','ZXCVBNM'].map((row,i)=>(
                  <div key={i} className="cw-kb-row">
                    {row.split('').map(ch=><button key={ch} type="button" onClick={()=>typeLetter(ch)}>{ch}</button>)}
                  </div>
                ))}
                <div className="cw-kb-row">
                  <button type="button" className="cw-kb-wide" onClick={doBackspace}>⌫ Delete</button>
                </div>
              </div>
              <div style={{display:'flex',gap:'.32rem',flexWrap:'wrap',marginTop:'.72rem'}}>
                <button className={`btn-s${checking?' on':''}`} onClick={()=>setChecking(v=>!v)}>Check</button>
                <button className="btn-s" onClick={()=>{
                  if(!selWord)return;
                  const ng=userG.map(r=>[...r]);
                  const dr=selWord.dir==='V'?1:0,dc=selWord.dir==='H'?1:0;
                  for(let i=0;i<selWord.len;i++)ng[selWord.r+dr*i][selWord.c+dc*i]=selWord.word[i];
                  setUserG(ng);toast('Word revealed.');
                }}>Reveal Word</button>
                <button className="btn-s" onClick={()=>{
                  if(!window.confirm('Reveal all answers?'))return;
                  const ng=Array.from({length:CWS},()=>Array(CWS).fill(''));
                  [...cw.across,...cw.down].forEach(w=>{const dr=w.dir==='V'?1:0,dc=w.dir==='H'?1:0;for(let i=0;i<w.len;i++)ng[w.r+dr*i][w.c+dc*i]=w.word[i];});
                  setUserG(ng);
                }}>Reveal All</button>
                <button className="btn-s" onClick={()=>setUserG(Array.from({length:CWS},()=>Array(CWS).fill('')))}>Reset</button>
              </div>
              <div style={{fontFamily:'var(--fm)',fontSize:'.56rem',color:'var(--g400)',marginTop:'.45rem',letterSpacing:'.06em',textTransform:'uppercase'}}>
                Click cell · Type letters · Click again to flip direction · Tab for next word
              </div>
            </div>

            <div className="cw-clues-panel">
              <h4>Across</h4>
              {cw.across.map(w=>(
                <div key={w.num} className={`cw-clue${selWord&&selWord.num===w.num&&dir==='H'?' act':''}`}
                  onClick={()=>{setSel([w.r,w.c]);setDir('H');hidRef.current?.focus();}}>
                  <span className="cw-clue-n">{w.num}</span>{w.clue}
                </div>
              ))}
              <h4>Down</h4>
              {cw.down.map(w=>(
                <div key={w.num} className={`cw-clue${selWord&&selWord.num===w.num&&dir==='V'?' act':''}`}
                  onClick={()=>{setSel([w.r,w.c]);setDir('V');hidRef.current?.focus();}}>
                  <span className="cw-clue-n">{w.num}</span>{w.clue}
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function PuzzlesPage({toast}){
  const [active,setActive]=useState('hub');
  const today=todayStr();
  const [sdkDone,setSdkDone]=useState(false);
  const [cwDone,setCwDone]=useState(false);

  useEffect(()=>{
    API.get(`/api/puzzles/session?type=sudoku&date=${today}&difficulty=medium`).then(r=>setSdkDone(!!r?.completed)).catch(()=>{});
    API.get(`/api/puzzles/session?type=crossword&date=${today}&difficulty=`).then(r=>setCwDone(!!r?.completed)).catch(()=>{});
  },[]);

  if(active==='sudoku')return(
    <div className="pz-page">
      <div className="pz-back">
        <button className="btn-o" onClick={()=>setActive('hub')}>← Puzzles</button>
        <span style={{fontFamily:'var(--fh)',fontSize:'1.35rem',fontWeight:700}}>Sudoku</span>
      </div>
      <SudokuPage toast={toast}/>
    </div>
  );
  if(active==='crossword')return(
    <div className="pz-page">
      <div className="pz-back">
        <button className="btn-o" onClick={()=>setActive('hub')}>← Puzzles</button>
        <span style={{fontFamily:'var(--fh)',fontSize:'1.35rem',fontWeight:700}}>Crossword</span>
      </div>
      <CrosswordPage toast={toast}/>
    </div>
  );

  return(
    <div className="pz-page">
      <div className="sec-lbl"><span>Daily Puzzles</span></div>
      <p style={{fontFamily:'var(--fb)',fontStyle:'italic',color:'var(--g600)',fontSize:'1rem',lineHeight:1.6,marginBottom:'0'}}>Two fresh puzzles every day. Come back tomorrow for a new set. Archives available for the past 30 days.</p>
      <div className="pz-hub-grid">
        <div className="pz-hub-card" onClick={()=>setActive('sudoku')}>
          <div style={{fontFamily:'var(--fm)',fontSize:'.55rem',letterSpacing:'.18em',textTransform:'uppercase',color:'var(--g500)',marginBottom:'.35rem'}}>Daily · No.{today.replace(/-/g,'')}</div>
          <div className="pz-hub-name">SUDOKU{sdkDone&&<span style={{fontFamily:'var(--fm)',fontSize:'.65rem',marginLeft:'.5rem',color:'var(--g500)',fontWeight:400}}>✓ Solved</span>}</div>
          <p className="pz-hub-desc">Fill every row, column, and 3×3 box with digits 1–9. Three difficulty levels. Notes mode included.</p>
          <button className="btn-p" style={{fontSize:'.62rem'}} onClick={e=>{e.stopPropagation();setActive('sudoku');}}>{sdkDone?'Play Again →':'Play Today\'s →'}</button>
        </div>
        <div className="pz-hub-card" onClick={()=>setActive('crossword')}>
          <div style={{fontFamily:'var(--fm)',fontSize:'.55rem',letterSpacing:'.18em',textTransform:'uppercase',color:'var(--g500)',marginBottom:'.35rem'}}>Daily · Themed</div>
          <div className="pz-hub-name">CROSSWORD{cwDone&&<span style={{fontFamily:'var(--fm)',fontSize:'.65rem',marginLeft:'.5rem',color:'var(--g500)',fontWeight:400}}>✓ Solved</span>}</div>
          <p className="pz-hub-desc">A themed crossword generated fresh every day using live word data from the Datamuse lexicon. Click a cell, then type.</p>
          <button className="btn-p" style={{fontSize:'.62rem'}} onClick={e=>{e.stopPropagation();setActive('crossword');}}>{cwDone?'Play Again →':'Play Today\'s →'}</button>
        </div>
      </div>
    </div>
  );
}
