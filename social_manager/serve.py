#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template_string
from werkzeug.security import generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(BASE))
import ve.db as _ve_db
import ve.paths as _ve_paths


def _load_config():
    with open(os.path.join(BASE, 'config.json'), encoding='utf-8') as fh:
        cfg = json.load(fh)
    if cfg.get('db_path') and not os.path.isabs(cfg['db_path']):
        cfg['db_path'] = os.path.normpath(os.path.join(BASE, cfg['db_path']))
    return cfg


CFG = _load_config()
DB_PATH = _ve_paths.db_path(BASE)

app = Flask(__name__)


def get_db():
    return _ve_db.connect(DB_PATH)


def now():
    return datetime.now(timezone.utc).isoformat()


@app.route('/api/users', methods=['GET'])
def list_users():
    db = get_db()
    try:
        rows = db.execute('''SELECT u.id,u.username,u.role,u.email,u.author_id,u.last_login,u.created_at,
            a.name AS author_name FROM users u LEFT JOIN authors a ON u.author_id=a.id ORDER BY u.username''').fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/users/authors', methods=['GET'])
def list_authors_for_link():
    db = get_db()
    try:
        rows = db.execute('SELECT id, name FROM authors ORDER BY name').fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/users', methods=['POST'])
def create_user():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    db = get_db()
    try:
        db.execute('INSERT INTO users (username,password_hash,role,email,author_id,created_at) VALUES (?,?,?,?,?,?)',
                   [username, generate_password_hash(password), data.get('role', 'reader'),
                    data.get('email') or None, data.get('author_id') or None, now()])
        uid = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.commit()
        return jsonify({'id': uid, 'username': username}), 201
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/users/<int:uid>', methods=['PUT'])
def update_user(uid):
    data = request.json or {}
    db = get_db()
    try:
        ex = db.execute('SELECT * FROM users WHERE id=?', [uid]).fetchone()
        if not ex: return jsonify({'error': 'Not found'}), 404
        db.execute('UPDATE users SET role=?,email=?,author_id=? WHERE id=?', [
            data.get('role', ex['role']), data.get('email', ex['email']),
            data.get('author_id', ex['author_id']), uid])
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/users/<int:uid>/password', methods=['PUT'])
def change_password(uid):
    pw = (request.json or {}).get('password', '')
    if len(pw) < 6:
        return jsonify({'error': 'Min 6 characters'}), 400
    db = get_db()
    try:
        db.execute('UPDATE users SET password_hash=? WHERE id=?', [generate_password_hash(pw), uid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/users/<int:uid>', methods=['DELETE'])
def delete_user(uid):
    db = get_db()
    try:
        db.execute('DELETE FROM users WHERE id=?', [uid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/comments', methods=['GET'])
def list_comments():
    status = request.args.get('status', 'pending')
    db = get_db()
    try:
        if status == 'all':
            rows = db.execute('''SELECT c.*,a.title AS article_title FROM comments c
                JOIN articles a ON c.article_id=a.id ORDER BY c.created_at DESC LIMIT 400''').fetchall()
        else:
            rows = db.execute('''SELECT c.*,a.title AS article_title FROM comments c
                JOIN articles a ON c.article_id=a.id WHERE c.status=?
                ORDER BY c.created_at DESC LIMIT 400''', [status]).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/comments/<int:cid>', methods=['PUT'])
def moderate_comment(cid):
    status = (request.json or {}).get('status', 'approved')
    db = get_db()
    try:
        db.execute('UPDATE comments SET status=? WHERE id=?', [status, cid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/comments/<int:cid>', methods=['DELETE'])
def delete_comment(cid):
    db = get_db()
    try:
        db.execute('DELETE FROM comments WHERE id=?', [cid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/letters', methods=['GET'])
def list_letters():
    status = request.args.get('status', 'all')
    db = get_db()
    try:
        q = '''SELECT l.*,u.username,
            (SELECT content FROM letter_messages WHERE letter_id=l.id ORDER BY created_at DESC LIMIT 1) AS last_msg
            FROM letters l LEFT JOIN users u ON l.user_id=u.id'''
        p = []
        if status != 'all':
            q += ' WHERE l.status=?'; p.append(status)
        q += ' ORDER BY l.last_message_at DESC'
        rows = db.execute(q, p).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        db.close()


@app.route('/api/letters/<int:lid>', methods=['GET'])
def get_letter(lid):
    db = get_db()
    try:
        letter = db.execute('SELECT l.*,u.username FROM letters l LEFT JOIN users u ON l.user_id=u.id WHERE l.id=?', [lid]).fetchone()
        if not letter: return jsonify({'error': 'Not found'}), 404
        msgs = db.execute('SELECT * FROM letter_messages WHERE letter_id=? ORDER BY created_at', [lid]).fetchall()
        d = dict(letter); d['messages'] = [dict(m) for m in msgs]
        return jsonify(d)
    finally:
        db.close()


@app.route('/api/letters/<int:lid>/reply', methods=['POST'])
def reply_letter(lid):
    body = (request.json or {}).get('content', '').strip()
    if not body:
        return jsonify({'error': 'Message required'}), 400
    db = get_db()
    try:
        if not db.execute('SELECT 1 FROM letters WHERE id=?', [lid]).fetchone():
            return jsonify({'error': 'Not found'}), 404
        ts = now()
        db.execute('INSERT INTO letter_messages (letter_id,sender,content,created_at) VALUES (?,?,?,?)',
                   [lid, 'admin', body, ts])
        db.execute("UPDATE letters SET last_message_at=?,status='replied' WHERE id=?", [ts, lid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/letters/<int:lid>/public', methods=['POST'])
def set_letter_public(lid):
    want = 1 if (request.json or {}).get('is_public') else 0
    db = get_db()
    try:
        cols = {r[1] for r in db.execute('PRAGMA table_info(letters)')}
        if 'is_public' not in cols:
            return jsonify({'error': 'letters.is_public missing -- run '
                                     'python site_data_get.py once to migrate'}), 400
        if not db.execute('SELECT 1 FROM letters WHERE id=?', [lid]).fetchone():
            return jsonify({'error': 'Not found'}), 404
        db.execute('UPDATE letters SET is_public=? WHERE id=?', [want, lid])
        db.commit(); return jsonify({'success': True, 'is_public': want})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/letters/<int:lid>/close', methods=['POST'])
def close_letter(lid):
    db = get_db()
    try:
        db.execute("UPDATE letters SET status='closed' WHERE id=?", [lid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/api/notifications', methods=['GET'])
def notifications():
    db = get_db()
    try:
        pending_comments = db.execute("SELECT COUNT(*) FROM comments WHERE status='pending'").fetchone()[0]
        open_letters = db.execute("SELECT COUNT(*) FROM letters WHERE status='open'").fetchone()[0]
        return jsonify({'pending_comments': pending_comments, 'open_letters': open_letters})
    finally:
        db.close()


@app.route('/api/letters/<int:lid>/reopen', methods=['POST'])
def reopen_letter(lid):
    db = get_db()
    try:
        db.execute("UPDATE letters SET status='open' WHERE id=?", [lid])
        db.commit(); return jsonify({'success': True})
    except Exception as e:
        db.rollback(); return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/')
def index():
    return render_template_string(INDEX_HTML)


INDEX_HTML = r'''<!doctype html><html><head><meta charset="utf-8">
<title>Social Manager</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--line:#000;--dim:#555;--bg:#fff;--fg:#000;--panel:#f2f2f2}
*{box-sizing:border-box}
body{margin:0;font:13px/1.45 Verdana,Arial,Helvetica,sans-serif;background:var(--bg);color:var(--fg)}
a{color:inherit}
h1,h2,h3{font-family:Georgia,'Times New Roman',serif;font-weight:bold;margin:0}
header{display:flex;align-items:center;gap:1rem;padding:.5rem 1rem;border-bottom:2px solid var(--line);background:var(--panel)}
header h1{font-size:1.05rem}
nav{display:flex;gap:.3rem}
nav button{border:1px solid var(--line);background:#fff;padding:.3rem .8rem;cursor:pointer;font:inherit;border-radius:0}
nav button.is-on{background:#000;color:#fff}
#notifBox{margin-left:auto;border:1px solid var(--line);padding:.25rem .6rem;font-size:.76rem;background:#fff;cursor:default}
#notifBox b{cursor:pointer;text-decoration:underline}
#notifBox b.zero{color:var(--dim);text-decoration:none;cursor:default}
main{display:grid;grid-template-columns:340px 1px 1fr;height:calc(100vh - 46px)}
.divider{background:var(--line)}
.list{overflow:auto;padding:.6rem}
.edit{overflow:auto;padding:1rem 1.4rem}
.mi{border:1px solid var(--line);padding:.4rem .5rem;margin-bottom:.35rem;cursor:pointer;background:#fff}
.mi:hover{background:#f6f6f6}
.mi.is-active{background:var(--panel);font-weight:bold}
.hint{color:var(--dim);font-size:.76rem}
.field{margin-bottom:.7rem}
.field label{display:block;font-size:.72rem;color:var(--dim);margin-bottom:.2rem;text-transform:uppercase;letter-spacing:.02em}
input,select,textarea{width:100%;padding:.4rem .5rem;border:1px solid var(--line);font:inherit;background:#fff;color:#000;border-radius:0}
textarea{min-height:80px;resize:vertical}
.wysiwyg{min-height:110px;border:1px solid var(--line);padding:.5rem}
.row{display:flex;gap:.6rem}
.row>*{flex:1}
.mini{border:1px solid var(--line);background:#fff;padding:.35rem .8rem;cursor:pointer;font-size:.82rem;border-radius:0}
.mini.primary{background:#000;color:#fff}
.badge{display:inline-block;font-size:.68rem;padding:.05rem .4rem;border:1px solid var(--line);background:#eee;color:#333}
.msg{border:1px solid var(--line);padding:.6rem;margin-bottom:.5rem}
.msg.admin{background:#f0f4fa}
.tb{display:flex;gap:.4rem;margin-bottom:.8rem;flex-wrap:wrap}
@media(prefers-color-scheme:dark){
 :root{--line:#ccc;--dim:#aaa;--bg:#111;--fg:#eee;--panel:#1e1e1e}
 nav button,input,select,textarea,.mini,.mi,.wysiwyg,#notifBox{background:#161616;color:#eee;border-color:#ccc}
 .mi.is-active{background:#242424}
 nav button.is-on,.mini.primary{background:#eee;color:#111}
 .msg.admin{background:#182236}
}
.nrlink{margin-left:auto;border:1px solid var(--line);padding:.3rem .7rem;text-decoration:none;color:inherit;font-size:.78rem;background:#fff}
.nrlink:hover{background:#000;color:#fff}
@media(prefers-color-scheme:dark){.nrlink{background:#161616;color:#eee}.nrlink:hover{background:#eee;color:#111}}
</style></head>
<body>
<header>
  <h1>SOCIAL MANAGER</h1>
  <a href="http://localhost:8790" target="_blank" class="nrlink" title="Collect reader data, publish to both sites, analytics">▤ Newsroom</a>
  <nav id="tabs"></nav>
  <div id="notifBox">loading...</div>
</header>
<main>
  <div class="list" id="list"></div>
  <div class="divider"></div>
  <div class="edit" id="edit"></div>
</main>
<script>
const TABS = ['Users','Comments','Mailbox'];
let active = 'Users';
const $list = document.getElementById('list');
const $edit = document.getElementById('edit');
const $tabs = document.getElementById('tabs');
const $notifBox = document.getElementById('notifBox');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const j = (url, opts) => fetch(url, Object.assign({headers:{'Content-Type':'application/json'}}, opts))
  .then(r => r.json().then(d => { if (!r.ok) throw new Error(d.error||r.statusText); return d; }));

async function refreshNotifications(){
  try{
    const n = await j('/api/notifications');
    $notifBox.innerHTML = `<b class="${n.pending_comments?'':'zero'}" id="nComments">${n.pending_comments} pending comment${n.pending_comments===1?'':'s'}</b>` +
      ` &nbsp;|&nbsp; <b class="${n.open_letters?'':'zero'}" id="nLetters">${n.open_letters} open letter${n.open_letters===1?'':'s'}</b>`;
    document.getElementById('nComments').onclick = () => { active='Comments'; renderTabs(); render(); };
    document.getElementById('nLetters').onclick = () => { active='Mailbox'; renderTabs(); render(); };
  } catch(e) { $notifBox.textContent = 'notifications unavailable'; }
}
refreshNotifications();
setInterval(refreshNotifications, 30000);

function renderTabs(){
  $tabs.innerHTML='';
  TABS.forEach(t=>{
    const b=document.createElement('button'); b.textContent=t; b.className = active===t?'is-on':'';
    b.onclick=()=>{active=t; renderTabs(); render();};
    $tabs.appendChild(b);
  });
}
function render(){
  $list.innerHTML=''; $edit.innerHTML='';
  if(active==='Users') return Users.init();
  if(active==='Comments') return Comments.init();
  return Mailbox.init();
}

const Users = {
  items: [], authors: [], cur: null,
  async init(){
    this.items = await j('/api/users');
    this.authors = await j('/api/users/authors');
    this.cur = null;
    this.drawList(); this.drawForm(null);
  },
  drawList(){
    $list.innerHTML='';
    const add = document.createElement('button'); add.className='mini primary'; add.style.width='100%'; add.style.marginBottom='.6rem';
    add.textContent='+ New user'; add.onclick=()=>{this.cur=null; this.drawForm(null);};
    $list.appendChild(add);
    this.items.forEach(u=>{
      const row=document.createElement('div'); row.className='mi'+(this.cur&&this.cur.id===u.id?' is-active':'');
      row.innerHTML = `<b>${esc(u.username)}</b> <span class="badge">${esc(u.role)}</span><br>
        <span class="hint">${esc(u.author_name||'')} ${u.last_login?('· last login '+esc(u.last_login).slice(0,16)):''}</span>`;
      row.onclick=()=>{this.cur=u; this.drawList(); this.drawForm(u);};
      $list.appendChild(row);
    });
  },
  drawForm(u){
    $edit.innerHTML='';
    const isNew = !u;
    const state = isNew ? {username:'',password:'',role:'reader',email:'',author_id:''} : {...u};
    const h=document.createElement('h3'); h.textContent = isNew?'New user':state.username; h.style.marginTop='0';
    $edit.appendChild(h);
    if(isNew){
      $edit.appendChild(field('Username', ()=>state.username, v=>state.username=v));
      $edit.appendChild(field('Password', ()=>state.password, v=>state.password=v, {type:'password'}));
    }
    const row = document.createElement('div'); row.className='row';
    row.append(
      field('Role', ()=>state.role, v=>state.role=v, {select:['admin','editor','author','reader']}),
      field('Email', ()=>state.email, v=>state.email=v),
    );
    $edit.appendChild(row);
    const authSel = field('Linked author', ()=>state.author_id, v=>state.author_id=v,
      {select:[['','(none)'], ...this.authors.map(a=>[String(a.id), a.name])]});
    $edit.appendChild(authSel);

    const btnRow = document.createElement('div'); btnRow.className='tb';
    const saveBtn = mini(isNew?'Create user':'Save', 'primary', async ()=>{
      saveBtn.textContent='Saving…';
      try{
        if(isNew) await j('/api/users', {method:'POST', body: JSON.stringify(state)});
        else await j(`/api/users/${u.id}`, {method:'PUT', body: JSON.stringify(state)});
        await this.init();
      }catch(e){ saveBtn.textContent='Failed: '+e.message; setTimeout(()=>saveBtn.textContent=isNew?'Create user':'Save',1600); }
    });
    btnRow.appendChild(saveBtn);
    if(!isNew){
      const pwBtn = mini('Set new password', '', async ()=>{
        const pw = prompt('New password (min 6 chars)'); if(!pw) return;
        try{ await j(`/api/users/${u.id}/password`, {method:'PUT', body: JSON.stringify({password:pw})}); pwBtn.textContent='Password set'; setTimeout(()=>pwBtn.textContent='Set new password',1400);}
        catch(e){ alert(e.message); }
      });
      const delBtn = mini('Delete user', '', async ()=>{
        if(!confirm(`Delete user "${u.username}"?`)) return;
        await j(`/api/users/${u.id}`, {method:'DELETE'});
        await this.init();
      });
      btnRow.append(pwBtn, delBtn);
    }
    $edit.appendChild(btnRow);
  }
};

const Comments = {
  status: 'pending', items: [],
  async init(){
    this.items = await j('/api/comments?status='+this.status);
    this.drawList();
    $edit.innerHTML = '<div class="hint">Select a comment to moderate.</div>';
  },
  drawList(){
    $list.innerHTML='';
    const filt = document.createElement('div'); filt.className='tb';
    ['pending','approved','rejected','all'].forEach(s=>{
      const b=mini(s, this.status===s?'primary':'', async ()=>{ this.status=s; this.items=await j('/api/comments?status='+s); this.drawList(); });
      filt.appendChild(b);
    });
    $list.appendChild(filt);
    if(!this.items.length) $list.appendChild(Object.assign(document.createElement('div'),{className:'hint',textContent:'No comments.'}));
    this.items.forEach(c=>{
      const row=document.createElement('div'); row.className='mi';
      row.innerHTML = `<b>${esc(c.display_name)}</b> <span class="badge">${esc(c.status)}</span><br>
        <span class="hint">on "${esc(c.article_title)}" · ${esc(c.created_at||'').slice(0,16)}</span>
        <div style="margin-top:.3rem">${esc(c.content).slice(0,140)}</div>`;
      row.onclick=()=>this.drawEdit(c);
      $list.appendChild(row);
    });
  },
  drawEdit(c){
    $edit.innerHTML='';
    const h=document.createElement('h3'); h.textContent=c.display_name; h.style.marginTop='0';
    const sub=document.createElement('div'); sub.className='hint'; sub.style.marginBottom='.8rem';
    sub.textContent = `on "${c.article_title}" · ${(c.created_at||'').slice(0,16)} · ${c.ip_address||''}`;
    const body=document.createElement('div'); body.style.cssText='border:1px solid var(--line);padding:.8rem;margin-bottom:.8rem;white-space:pre-wrap';
    body.textContent=c.content;
    $edit.append(h, sub, body);
    const row=document.createElement('div'); row.className='tb';
    if(c.status!=='approved') row.appendChild(mini('Approve','primary', async ()=>{ await j(`/api/comments/${c.id}`,{method:'PUT',body:JSON.stringify({status:'approved'})}); this.init(); refreshNotifications(); }));
    if(c.status!=='rejected') row.appendChild(mini('Reject','', async ()=>{ await j(`/api/comments/${c.id}`,{method:'PUT',body:JSON.stringify({status:'rejected'})}); this.init(); refreshNotifications(); }));
    row.appendChild(mini('Delete','', async ()=>{ if(!confirm('Delete this comment?'))return; await j(`/api/comments/${c.id}`,{method:'DELETE'}); this.init(); refreshNotifications(); }));
    $edit.appendChild(row);
  }
};

const Mailbox = {
  status: 'all', items: [], cur: null,
  async init(){
    this.items = await j('/api/letters?status='+this.status);
    this.cur=null;
    this.drawList();
    $edit.innerHTML = '<div class="hint">Select a letter thread.</div>';
  },
  drawList(){
    $list.innerHTML='';
    const filt = document.createElement('div'); filt.className='tb';
    ['all','open','replied','closed'].forEach(s=>{
      const b=mini(s, this.status===s?'primary':'', async ()=>{ this.status=s; this.items=await j('/api/letters?status='+s); this.drawList(); });
      filt.appendChild(b);
    });
    $list.appendChild(filt);
    this.items.forEach(l=>{
      const row=document.createElement('div'); row.className='mi'+(this.cur&&this.cur.id===l.id?' is-active':'');
      row.innerHTML = `<b>${esc(l.subject)}</b> <span class="badge">${esc(l.status)}</span><br>
        <span class="hint">${esc(l.username||l.guest_name||'guest')} · ${esc(l.last_message_at||'').slice(0,16)}</span>`;
      row.onclick=async ()=>{ this.cur=l; this.drawList(); const full=await j('/api/letters/'+l.id); this.drawEdit(full); };
      $list.appendChild(row);
    });
  },
  drawEdit(l){
    $edit.innerHTML='';
    const h=document.createElement('h3'); h.textContent=l.subject; h.style.marginTop='0';
    const sub=document.createElement('div'); sub.className='hint'; sub.style.marginBottom='.8rem';
    sub.textContent = `${l.username||l.guest_name||'guest'} · ${l.status}`;
    $edit.append(h, sub);
    (l.messages||[]).forEach(m=>{
      const d=document.createElement('div'); d.className='msg'+(m.sender==='admin'?' admin':'');
      const head=document.createElement('div'); head.className='hint'; head.textContent = `${m.sender} · ${(m.created_at||'').slice(0,16)}`;
      const bodyEl=document.createElement('div');
      if(m.sender==='admin') bodyEl.innerHTML = m.content; else bodyEl.textContent = m.content;
      d.append(head, bodyEl);
      $edit.appendChild(d);
    });
    const replyWrap=document.createElement('div'); replyWrap.className='field'; replyWrap.style.marginTop='.6rem';
    replyWrap.innerHTML='<label>Reply</label>';
    const wtb=document.createElement('div'); wtb.className='tb'; wtb.style.marginBottom='.3rem';
    [['Bold','bold'],['Italic','italic'],['Link','createLink']].forEach(([label,cmd])=>{
      wtb.appendChild(mini(label,'', ()=>{
        if(cmd==='createLink'){ const url=prompt('URL'); if(url) document.execCommand('createLink', false, url); }
        else document.execCommand(cmd);
      }));
    });
    const canvas=document.createElement('div'); canvas.className='wysiwyg'; canvas.contentEditable='true';
    replyWrap.append(wtb, canvas);
    $edit.appendChild(replyWrap);
    const row=document.createElement('div'); row.className='tb';
    row.appendChild(mini('Send reply','primary', async ()=>{
      if(!canvas.innerHTML.trim()) return;
      await j(`/api/letters/${l.id}/reply`, {method:'POST', body: JSON.stringify({content: canvas.innerHTML})});
      const full=await j('/api/letters/'+l.id); this.drawEdit(full); this.init(); refreshNotifications();
    }));
    if(l.status!=='closed') row.appendChild(mini('Close thread','', async ()=>{ await j(`/api/letters/${l.id}/close`,{method:'POST'}); this.init(); refreshNotifications(); }));
    else row.appendChild(mini('Reopen','', async ()=>{ await j(`/api/letters/${l.id}/reopen`,{method:'POST'}); this.init(); }));
    const pub = !!l.is_public;
    row.appendChild(mini(pub?'Public ✓ — unpublish':'Publish on the letters page', pub?'primary':'', async ()=>{
      const r = await j(`/api/letters/${l.id}/public`, {method:'POST', body: JSON.stringify({is_public: !pub})});
      if(r && r.error){ alert(r.error); return; }
      const full=await j('/api/letters/'+l.id); this.drawEdit(full);
    }));
    $edit.appendChild(row);
    $edit.appendChild(Object.assign(document.createElement('p'),{className:'hint',
      textContent:'A reply reaches the reader only after a publish — run it from the Newsroom (localhost:8790).'}));
  }
};

function field(label, get, set, opts={}){
  const w=document.createElement('div'); w.className='field';
  const lab=document.createElement('label'); lab.textContent=label; w.appendChild(lab);
  let i;
  if(opts.select){
    i=document.createElement('select');
    i.innerHTML = opts.select.map(o=>{
      const [val,txt] = Array.isArray(o)?o:[o,o];
      return `<option value="${esc(val)}" ${String(get())===String(val)?'selected':''}>${esc(txt)}</option>`;
    }).join('');
    i.onchange=()=>set(i.value);
  } else {
    i=document.createElement('input'); if(opts.type) i.type=opts.type;
    i.value=get()??''; i.oninput=()=>set(i.value);
  }
  w.appendChild(i); return w;
}
function mini(label, cls, fn){ const b=document.createElement('button'); b.className='mini '+cls; b.textContent=label; b.onclick=fn; return b; }

renderTabs(); render();
</script>
</body></html>'''


if __name__ == '__main__':
    port = CFG.get('port', 8788)
    print(f'Social Manager -> http://localhost:{port}')
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False, threaded=True)
