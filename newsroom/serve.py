#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import sys
import threading
import uuid
from datetime import datetime

from flask import Flask, jsonify, request, render_template_string

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
sys.path.insert(0, ROOT)

import ve_pipeline
from ve.db import connect


def _load_config():
    with open(os.path.join(BASE, 'config.json'), encoding='utf-8') as fh:
        cfg = json.load(fh)
    if cfg.get('db_path') and not os.path.isabs(cfg['db_path']):
        cfg['db_path'] = os.path.normpath(os.path.join(BASE, cfg['db_path']))
    return cfg


CFG = _load_config()
DB_PATH = os.environ.get('DB_PATH') or CFG['db_path']
app = Flask(__name__)

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_ACTIVE: str | None = None

ACTIONS = {'collect': ve_pipeline.collect,
           'publish': ve_pipeline.publish,
           'all': ve_pipeline.full}


def _start(action, dry=False):
    global _ACTIVE
    with _LOCK:
        if _ACTIVE and _JOBS.get(_ACTIVE, {}).get('status') == 'running':
            return None, {'id': _ACTIVE, 'error': 'a job is already running'}
        if not dry:
            got, holder = ve_pipeline.acquire_lock()
            if not got:
                return None, {'id': None, 'error': 'another pipeline run holds '
                              '.ve_pipeline.lock (' + holder + ') -- wait for it, '
                              'or delete the file if that run is gone'}
        job_id = uuid.uuid4().hex[:12]
        job = {'id': job_id, 'action': action, 'dry': dry, 'status': 'running', 'lines': [],
               'started_at': datetime.now().isoformat(), 'result': None}
        _JOBS[job_id] = job
        _ACTIVE = job_id

    def work():
        try:
            fn = ACTIONS[action]
            emit = lambda ln: job['lines'].append(ln)
            job['result'] = fn(emit, dry_run=True) if dry else fn(emit)
            job['status'] = 'done' if job['result'].get('ok') else 'failed'
        except Exception as e:
            job['lines'].append(f'!! {type(e).__name__}: {e}')
            job['status'] = 'failed'
        finally:
            job['ended_at'] = datetime.now().isoformat()
            if not dry:
                ve_pipeline.release_lock()

    threading.Thread(target=work, daemon=True).start()
    return job, None


@app.route('/api/run/<action>', methods=['POST'])
def run_action(action):
    if action not in ACTIONS:
        return jsonify({'error': f'unknown action {action}'}), 400
    dry = request.args.get('dry') == '1'
    if dry and action == 'collect':
        return jsonify({'error': 'collect has no preview'}), 400
    job, busy = _start(action, dry)
    if job is None:
        return jsonify({'error': busy['error'], 'job_id': busy['id']}), 409
    return jsonify({'job_id': job['id']})


@app.route('/api/jobs/<job_id>')
def job_status(job_id):
    job = _JOBS.get(job_id)
    if not job:
        return jsonify({'error': 'no such job'}), 404
    since = int(request.args.get('since', 0))
    return jsonify({'id': job['id'], 'action': job['action'], 'dry': job.get('dry', False),
                    'status': job['status'],
                    'lines': job['lines'][since:], 'total': len(job['lines']),
                    'result': job['result']})


@app.route('/api/jobs')
def jobs_recent():
    out = [{'id': j['id'], 'action': j['action'], 'status': j['status'],
            'started_at': j['started_at'],
            'seconds': (j.get('result') or {}).get('seconds')}
           for j in _JOBS.values()]
    return jsonify(sorted(out, key=lambda j: j['started_at'], reverse=True)[:15])


def get_db():
    return connect(DB_PATH)


@app.route('/api/analytics')
def api_analytics():
    days = min(max(int(request.args.get('days', 30)), 1), 3650)
    return jsonify(ve_pipeline.analytics(days))


@app.route('/api/queues')
def api_queues():
    db = get_db()
    tools = CFG.get('tools', {})
    try:
        def rows(sql, args=()):
            return [dict(r) for r in db.execute(sql, args)]

        out = {'comments': rows(
            "SELECT c.id, c.display_name, c.status, c.created_at, "
            "substr(c.content,1,120) AS excerpt, a.title AS article "
            "FROM comments c LEFT JOIN articles a ON a.id=c.article_id "
            "WHERE c.status='pending' ORDER BY c.created_at DESC LIMIT 50")}

        out['letters'] = rows(
            "SELECT l.id, l.guest_name, l.subject, l.created_at FROM letters l "
            "WHERE l.status='open' AND NOT EXISTS (SELECT 1 FROM letter_messages m "
            "WHERE m.letter_id=l.id AND m.sender<>'guest') "
            "ORDER BY l.created_at DESC LIMIT 50")

        out['ebooks'] = []
        if db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                      "AND name='ebook_requests'").fetchone():
            out['ebooks'] = rows(
                "SELECT id, title, requester_name, username, status, publication_id, "
                "error, built_at FROM ebook_requests ORDER BY id DESC LIMIT 50")
        out['tools'] = tools
        return jsonify(out)
    finally:
        db.close()


@app.route('/api/subscribers.csv')
def subscribers_csv():
    db = get_db()
    try:
        rows = db.execute('SELECT email, subscribed_at FROM newsletter_subscribers '
                          'ORDER BY subscribed_at DESC').fetchall()
        body = 'email,subscribed_at\n' + '\n'.join(
            f'"{r["email"]}","{r["subscribed_at"] or ""}"' for r in rows)
        return app.response_class(body, mimetype='text/csv', headers={
            'Content-Disposition': 'attachment; filename=ve-subscribers.csv'})
    finally:
        db.close()


@app.route('/')
def index():
    return render_template_string(INDEX_HTML, tools=json.dumps(CFG.get('tools', {})))


INDEX_HTML = r'''<!doctype html><html><head><meta charset="utf-8">
<title>Newsroom</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--line:#000;--dim:#555;--bg:#fff;--fg:#000;--panel:#f2f2f2;--ok:#0a6b2e;--bad:#a4161a;--wait:#8a5a00}
*{box-sizing:border-box}
body{margin:0;font:13px/1.45 Verdana,Arial,Helvetica,sans-serif;background:var(--bg);color:var(--fg)}
h1,h2,h3{font-family:Georgia,'Times New Roman',serif;font-weight:bold;margin:0}
header{display:flex;align-items:center;gap:1rem;padding:.5rem 1rem;border-bottom:2px solid var(--line);background:var(--panel)}
header h1{font-size:1.05rem}
nav{display:flex;gap:.3rem}
nav button{border:1px solid var(--line);background:#fff;padding:.3rem .8rem;cursor:pointer;font:inherit;border-radius:0}
nav button.is-on{background:#000;color:#fff}
#links{margin-left:auto;display:flex;gap:.4rem;font-size:.74rem}
a{color:inherit;text-decoration:underline}
#links a{text-decoration:none}
#links a:hover{text-decoration:underline}
main{padding:1rem 1.2rem;max-width:70rem}
.tb{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:.9rem;align-items:center}
.mini{border:1px solid var(--line);background:#fff;padding:.4rem .9rem;cursor:pointer;font:inherit;font-size:.85rem;border-radius:0}
.mini.primary{background:#000;color:#fff}
.mini:disabled{opacity:.45;cursor:not-allowed}
.hint{color:var(--dim);font-size:.76rem}
.log{background:#0f1115;color:#d7f5e6;font-family:ui-monospace,Consolas,monospace;font-size:.76rem;
 padding:.7rem .8rem;max-height:52vh;overflow:auto;white-space:pre-wrap;border:1px solid var(--line)}
.log .step{color:#9fd0ff}
.log .err{color:#ff9b9b}
.log .cmd{color:#ffe08a}
.cards{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1rem}
.card{border:1px solid var(--line);padding:.5rem .8rem;min-width:8rem;background:#fff}
.card b{display:block;font-family:Georgia,serif;font-size:1.4rem;line-height:1.1}
.card span{font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
.card.alert{background:#fdf0f0}
table{border-collapse:collapse;width:100%;margin-bottom:1rem;font-size:.82rem}
th,td{border:1px solid var(--line);padding:.3rem .5rem;text-align:left;vertical-align:top}
th{background:var(--panel);font-size:.7rem;text-transform:uppercase;letter-spacing:.05em}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.bar{background:#000;height:.6rem;display:block}
.sec{margin:1.4rem 0 .5rem;font-family:Georgia,serif;font-size:1rem;border-bottom:1px solid var(--line);padding-bottom:.2rem}
.limits{border:1px dashed var(--line);background:var(--panel);padding:.6rem .8rem;font-size:.76rem;margin-bottom:1rem}
.limits li{margin:.15rem 0}
.panel{border:2px solid var(--line);background:var(--panel);padding:.7rem .9rem;margin:0 0 .9rem}
.panel ul{margin:.4rem 0 .7rem 1.1rem;padding:0}
.panel li{margin:.15rem 0}
.panel .tb{margin:0}
.st{font-size:.7rem;padding:.05rem .4rem;border:1px solid var(--line);background:#eee}
.st.ok{color:var(--ok)} .st.bad{color:var(--bad)} .st.wait{color:var(--wait)}
@media(prefers-color-scheme:dark){
 :root{--line:#ccc;--dim:#aaa;--bg:#111;--fg:#eee;--panel:#1e1e1e;--ok:#5fc7a0;--bad:#f08a8d;--wait:#e3b255}
 .panel{background:#1e1e1e}
 nav button,.mini,.card,td,th{background:#161616;color:#eee;border-color:#ccc}
 th{background:#1e1e1e}
 nav button.is-on,.mini.primary{background:#eee;color:#111}
 .card.alert{background:#2e1a1c}
 .st{background:#222;color:#ddd}
 .bar{background:#eee}
}
</style></head>
<body>
<header>
  <h1>NEWSROOM</h1>
  <nav id="tabs"></nav>
  <div id="links"></div>
</header>
<main id="view"></main>
<script>
const TOOLS = {{ tools|safe }};
const $ = s => document.querySelector(s);
const el = (t,c,x) => { const n=document.createElement(t); if(c)n.className=c; if(x!=null)n.textContent=x; return n; };
async function j(u,o){ const r=await fetch(u,o); if(!r.ok&&r.status!==409) throw new Error(await r.text()); return r.json(); }
const num = n => (n==null?'--':Number(n).toLocaleString());
const fmt = d => { if(!d) return ''; const t=new Date(d); return isNaN(t)?String(d).slice(0,16):t.toLocaleString(); };

let TAB='run', poll=null, seen=0, jobId=null;

function drawLinks(){
  const box=$('#links'); box.textContent='';
  const names={desk_editor:'Desk Editor',social_manager:'Social Manager',columnroom:'Columnroom',dtp:'dtp'};
  Object.entries(TOOLS).forEach(([k,url])=>{
    const a=el('a',null,names[k]||k); a.href=url; a.target='_blank'; box.appendChild(a);
  });
  const r=el('a',null,'Reader site'); r.href='http://localhost:5000'; r.target='_blank'; box.appendChild(r);
}
function drawTabs(){
  const box=$('#tabs'); box.textContent='';
  [['run','Run'],['analytics','Analytics'],['queues','Waiting on you']].forEach(([k,label])=>{
    const b=el('button',TAB===k?'is-on':'',label);
    b.onclick=()=>{ TAB=k; drawTabs(); draw(); };
    box.appendChild(b);
  });
}

function runView(){
  const v=$('#view'); v.textContent='';
  const tb=el('div','tb');
  const mk=(id,label,cls)=>{ const b=el('button','mini'+(cls?' '+cls:''),label); b.id=id; tb.appendChild(b); return b; };
  const bC=mk('bC','⇩ Collect reader input');
  const bP=mk('bP','⇪ Publish to both sites','primary');
  const bA=mk('bA','↻ Full cycle');
  const status=el('span','hint'); tb.appendChild(status);
  v.appendChild(tb);
  v.appendChild(el('p','hint',
    'Collect pulls comments, letters, likes, subscribers, activity and ebook requests out of the shared Sheet. '
  + 'Publish builds artifacts, pushes moderation decisions back to the Sheet, then rebuilds the emag and the Newsstand — in that order.'));
  v.appendChild(el('p','hint','Collect reads from the Sheet (it only flags imported letters and ebook results there). Publish and Full cycle show a preview first.'));
  const panel=el('div','panel'); panel.id='panel'; panel.hidden=true; v.appendChild(panel);
  const log=el('div','log'); log.id='log'; log.hidden=true; v.appendChild(log);

  const all=[bC,bP,bA];
  const start = async (action,dry)=>{
    all.forEach(b=>b.disabled=true);
    panel.hidden=true; panel.textContent='';
    log.hidden=false; log.textContent=''; seen=0;
    status.textContent='starting…';
    try{
      const r=await j('/api/run/'+action+(dry?'?dry=1':''),{method:'POST'});
      if(r.error){ status.textContent=r.error; all.forEach(b=>b.disabled=false); return; }
      jobId=r.job_id;
      watch(status,all,dry?(d)=>preview(action,d):null);
    }catch(e){ status.textContent='failed: '+e.message; all.forEach(b=>b.disabled=false); }
  };
  const preview = (action,d)=>{
    panel.textContent=''; panel.hidden=false;
    const res=d.result||{}, c=res.counts;
    if(!c){ panel.appendChild(el('p',null,'The preview failed — nothing was changed. See the log below.')); return; }
    const st=o=>Object.keys(o||{}).length?Object.entries(o).map(([k,n])=>n+' '+(k||'(none)')).join(', '):'none';
    panel.appendChild(el('b',null,(action==='all'?'Full cycle':'Publish')+' — this will:'));
    const ul=el('ul');
    [`Send ${num(c.would_mail)} ebook email(s) to readers`,
     `Delete ${num(c.would_prune)} old reader ebook(s) and their files`,
     `Write ${num(c.sheet_writes)} update(s) to the Sheet`,
     `Rebuild the emag and the Newsstand (writes files in both site folders)`].forEach(t=>ul.appendChild(el('li',null,t)));
    panel.appendChild(ul);
    panel.appendChild(el('p','hint',`Queues now — ebook requests: ${st(c.ebook_requests)}; comments: ${st(c.comments)}; newsletter subscribers: ${num(c.newsletter_subscribers)}.`+(action==='all'?' Full cycle also runs Collect first.':'')));
    const row=el('div','tb');
    const ok=el('button','mini primary','Confirm'); ok.id='bConfirm';
    const no=el('button','mini','Cancel'); no.id='bCancel';
    ok.onclick=()=>{ start(action,false); };
    no.onclick=()=>{ panel.hidden=true; panel.textContent=''; status.textContent='cancelled — nothing was run'; };
    row.appendChild(ok); row.appendChild(no); panel.appendChild(row);
  };
  bC.onclick=()=>start('collect',false); bP.onclick=()=>start('publish',true); bA.onclick=()=>start('all',true);
  if(jobId) watch(status,[bC,bP,bA]);
}
function watch(status,btns,onDone){
  clearInterval(poll);
  const log=$('#log'); if(log) log.hidden=false;
  poll=setInterval(async ()=>{
    let d; try{ d=await j(`/api/jobs/${jobId}?since=${seen}`); }catch(e){ return; }
    seen=d.total;
    const box=$('#log'); if(!box) return;
    const atEnd = box.scrollTop+box.clientHeight >= box.scrollHeight-30;
    d.lines.forEach(line=>{
      const cls = line.startsWith('---')?'step' : line.startsWith('!!')||line.startsWith('**')?'err'
                : line.startsWith('$')?'cmd' : '';
      const s=el('span',cls,line+'\n'); box.appendChild(s);
    });
    if(atEnd) box.scrollTop=box.scrollHeight;
    if(status) status.textContent = d.status==='running' ? 'running…'
      : d.status==='done' ? 'done' : 'finished with errors';
    if(d.status!=='running'){
      clearInterval(poll); poll=null; jobId=null;
      (btns||[]).forEach(b=>b.disabled=false);
      if(onDone) onDone(d);
    }
  },900);
}

async function analyticsView(){
  const v=$('#view'); v.textContent=''; v.appendChild(el('p','hint','Loading…'));
  let d; try{ d=await j('/api/analytics?days=90'); }catch(e){ v.textContent='Failed: '+e.message; return; }
  v.textContent='';
  const cards=el('div','cards');
  const T=d.totals||{};
  [['Articles',T.articles],['Publications',T.publications],['Readers',T.readers],
   ['Comments',T.comments],['Letters',T.letters],['Subscribers',T.subscribers],
   ['Likes',T.likes_total],['Messages',T.messages]].forEach(([k,n])=>{
    const c=el('div','card'); c.appendChild(el('b',null,num(n))); c.appendChild(el('span',null,k)); cards.appendChild(c);
  });
  v.appendChild(cards);

  const lim=el('div','limits');
  lim.appendChild(el('b',null,'What these numbers can and cannot tell you'));
  const ul=el('ul'); (d.limits||[]).forEach(t=>ul.appendChild(el('li',null,t))); lim.appendChild(ul);
  v.appendChild(lim);

  const A=d.activity||{};
  v.appendChild(el('h3','sec','Newsstand activity — last 90 days'));
  if(!(A.by_kind||[]).length){ v.appendChild(el('p','hint','No activity recorded in this window.')); }
  else{
    v.appendChild(table(['Event','Count'], A.by_kind.map(r=>[r.kind,{n:r.n}])));
    if((A.by_day||[]).length) v.appendChild(spark(A.by_day));
    v.appendChild(el('p','hint',`Distinct signed-in readers in window: ${num(A.readers)}`));
  }
  if((A.top_titles||[]).length){
    v.appendChild(el('h3','sec','Most opened'));
    v.appendChild(table(['Title','Event','Count'], A.top_titles.map(r=>[r.title,r.kind,{n:r.n}])));
  }
  if((A.revenue||[]).length){
    v.appendChild(el('h3','sec','Support taps'));
    v.appendChild(table(['Rail','Currency','Taps','Total'],
      A.revenue.map(r=>[r.via,r.currency||'',{n:r.taps},{n:(r.total||0)}])));
  }
  if((d.top_commented||[]).length){
    v.appendChild(el('h3','sec','Most discussed articles'));
    v.appendChild(table(['Article','Comments'], d.top_commented.map(r=>[r.title,{n:r.n}])));
  }
  if((d.top_liked||[]).length){
    v.appendChild(el('h3','sec','Most liked articles'));
    v.appendChild(table(['Article','Likes'], d.top_liked.map(r=>[r.title,{n:r.n}])));
  }
}
function table(head, rows){
  const t=el('table'), thead=el('thead'), tr=el('tr');
  head.forEach(h=>tr.appendChild(el('th',null,h))); thead.appendChild(tr); t.appendChild(thead);
  const tb=el('tbody');
  rows.forEach(r=>{ const row=el('tr');
    r.forEach(c=>{ if(c&&typeof c==='object'&&'n' in c){ row.appendChild(el('td','num',num(c.n))); }
                   else row.appendChild(el('td',null,c==null?'':String(c))); });
    tb.appendChild(row); });
  t.appendChild(tb); return t;
}
function spark(days){
  const wrap=el('div'); const max=Math.max(...days.map(d=>d.n),1);
  const t=el('table'), tb=el('tbody');
  days.slice(-21).forEach(d=>{ const tr=el('tr');
    tr.appendChild(el('td',null,d.day));
    tr.appendChild(el('td','num',num(d.n)));
    const td=el('td'); const b=el('span','bar'); b.style.width=Math.round(d.n/max*100)+'%';
    td.appendChild(b); tr.appendChild(td); tb.appendChild(tr); });
  t.appendChild(tb); wrap.appendChild(t); return wrap;
}

async function queuesView(){
  const v=$('#view'); v.textContent=''; v.appendChild(el('p','hint','Loading…'));
  let d; try{ d=await j('/api/queues'); }catch(e){ v.textContent='Failed: '+e.message; return; }
  v.textContent='';
  const sm=(d.tools||{}).social_manager||'#';

  const cards=el('div','cards');
  [['Comments to review',(d.comments||[]).length,sm],
   ['Letters unanswered',(d.letters||[]).length,sm],
   ['Ebooks failed',(d.ebooks||[]).filter(e=>e.status==='failed').length,null]].forEach(([k,n,url])=>{
    const c=el('div','card'+(n?' alert':'')); c.appendChild(el('b',null,num(n))); c.appendChild(el('span',null,k));
    if(url&&n){ const a=el('a',null,'open →'); a.href=url; a.target='_blank'; a.style.fontSize='.7rem'; c.appendChild(a); }
    cards.appendChild(c);
  });
  v.appendChild(cards);

  v.appendChild(el('h3','sec','Comments awaiting review'));
  if(!(d.comments||[]).length) v.appendChild(el('p','hint','Nothing pending.'));
  else v.appendChild(table(['Who','Article','Comment','When'],
    d.comments.map(c=>[c.display_name,c.article||'—',c.excerpt,fmt(c.created_at)])));

  v.appendChild(el('h3','sec','Letters with no reply yet'));
  if(!(d.letters||[]).length) v.appendChild(el('p','hint','All answered.'));
  else v.appendChild(table(['Who','Subject','When'],
    d.letters.map(l=>[l.guest_name,l.subject,fmt(l.created_at)])));
  v.appendChild(el('p','hint','Reply in Social Manager, then Publish — a reply only reaches the reader after a publish.'));

  v.appendChild(el('h3','sec','Ebook requests'));
  if(!(d.ebooks||[]).length) v.appendChild(el('p','hint','No requests.'));
  else v.appendChild(table(['Title','Requested by','Status','Note'],
    d.ebooks.map(e=>[e.title,e.requester_name||e.username||'—',e.status,e.error||''])));

  v.appendChild(el('h3','sec','Newsletter subscribers'));
  const p=el('p','hint');
  p.textContent='Nothing in this repo sends email, so a subscription is currently an unfulfilled promise. Export the list to send from elsewhere — or stop collecting them. ';
  const a=el('a',null,'Download CSV'); a.href='/api/subscribers.csv'; p.appendChild(a);
  v.appendChild(p);
}

function draw(){ if(TAB==='run') runView(); else if(TAB==='analytics') analyticsView(); else queuesView(); }
drawLinks(); drawTabs(); draw();
</script>
</body></html>'''


if __name__ == '__main__':
    port = int(os.environ.get('NEWSROOM_PORT') or CFG.get('port', 8790))
    print(f'Newsroom -> http://localhost:{port}')
    app.run(port=port, threaded=True)
