#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from queue import Queue, Empty

import tkinter as tk
from tkinter import ttk, messagebox

BASE = os.path.dirname(os.path.abspath(__file__))

TOOLS = [
    ('Newsroom',       os.path.join('newsroom', 'serve.py'),       8790,
     'Collect reader data, publish to both sites, analytics'),
    ('Desk Editor',    os.path.join('desk_editor', 'serve.py'),    8787,
     'Articles, authors, taxonomy, pages, config'),
    ('Social Manager', os.path.join('social_manager', 'serve.py'), 8788,
     'Users, comment moderation, letters'),
    ('Columnroom',     os.path.join('columnroom', 'serve.py'),     8789,
     'Column entries, timelines, templates'),
    ('dtp',            'dtp.py',                                    8797,
     'Page layout and publication design'),
    ('Reader site',    'app.py',                                    5000,
     "app.py -- what office wifi visitors read"),
]

POLL_MS = 1500


def port_open(port, host='127.0.0.1', timeout=0.25):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


class Office(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Voice Express Office')
        self.minsize(760, 520)
        self.procs: dict[str, subprocess.Popen] = {}
        self.rows: dict[str, dict] = {}
        self.logq: Queue[str] = Queue()
        self._build()
        self.after(200, self._drain_log)
        self.after(300, self._poll)
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    def _build(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('TButton', padding=(10, 4))
        style.configure('Head.TLabel', font=('Georgia', 15, 'bold'))
        style.configure('Sub.TLabel', foreground='#555')
        style.configure('Tool.TLabel', font=('Verdana', 10, 'bold'))
        style.configure('Blurb.TLabel', foreground='#555', font=('Verdana', 8))

        head = ttk.Frame(self, padding=(14, 12, 14, 6))
        head.pack(fill='x')
        ttk.Label(head, text='THE VOICE EXPRESS', style='Head.TLabel').pack(anchor='w')
        ttk.Label(head, text='Office tools — start what you need, then work in the browser.',
                  style='Sub.TLabel').pack(anchor='w')

        bar = ttk.Frame(self, padding=(14, 0, 14, 8))
        bar.pack(fill='x')
        ttk.Button(bar, text='Start everything', command=self.start_all).pack(side='left')
        ttk.Button(bar, text='Stop everything', command=self.stop_all).pack(side='left', padx=(6, 0))
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=10)
        ttk.Button(bar, text='⇩ Collect', command=lambda: self.pipeline('collect')).pack(side='left')
        ttk.Button(bar, text='⇪ Publish', command=lambda: self.pipeline('publish')).pack(side='left', padx=(6, 0))

        grid = ttk.Frame(self, padding=(14, 0, 14, 8))
        grid.pack(fill='x')
        grid.columnconfigure(1, weight=1)
        for i, (name, script, port, blurb) in enumerate(TOOLS):
            dot = tk.Canvas(grid, width=14, height=14, highlightthickness=0, bd=0)
            oval = dot.create_oval(3, 3, 12, 12, fill='#c9ccd2', outline='')
            dot.grid(row=i, column=0, padx=(0, 8), pady=5)

            text = ttk.Frame(grid)
            text.grid(row=i, column=1, sticky='w')
            ttk.Label(text, text=name, style='Tool.TLabel').pack(anchor='w')
            ttk.Label(text, text=f'{blurb}  ·  :{port}', style='Blurb.TLabel').pack(anchor='w')

            state = ttk.Label(grid, text='stopped', style='Blurb.TLabel', width=10)
            state.grid(row=i, column=2, padx=6)

            btn_start = ttk.Button(grid, text='Start', width=7,
                                   command=lambda n=name: self.start(n))
            btn_start.grid(row=i, column=3, padx=2)
            btn_open = ttk.Button(grid, text='Open', width=7,
                                  command=lambda p=port: webbrowser.open(f'http://localhost:{p}'))
            btn_open.grid(row=i, column=4, padx=2)
            btn_stop = ttk.Button(grid, text='Stop', width=7,
                                  command=lambda n=name: self.stop(n))
            btn_stop.grid(row=i, column=5, padx=2)

            self.rows[name] = {'script': script, 'port': port, 'dot': dot, 'oval': oval,
                               'state': state, 'start': btn_start, 'open': btn_open,
                               'stop': btn_stop}

        ttk.Separator(self, orient='horizontal').pack(fill='x', padx=14, pady=(2, 6))
        logwrap = ttk.Frame(self, padding=(14, 0, 14, 10))
        logwrap.pack(fill='both', expand=True)
        ttk.Label(logwrap, text='Log', style='Blurb.TLabel').pack(anchor='w')
        self.log = tk.Text(logwrap, height=10, wrap='word', bg='#0f1115', fg='#d7f5e6',
                           insertbackground='#d7f5e6', relief='flat',
                           font=('Consolas', 9), padx=8, pady=6)
        self.log.pack(fill='both', expand=True, side='left')
        sb = ttk.Scrollbar(logwrap, command=self.log.yview)
        sb.pack(fill='y', side='right')
        self.log.configure(yscrollcommand=sb.set, state='disabled')

    def say(self, line):
        self.logq.put(line)

    def _drain_log(self):
        wrote = False
        try:
            while True:
                line = self.logq.get_nowait()
                if not wrote:
                    self.log.configure(state='normal')
                    wrote = True
                self.log.insert('end', line.rstrip() + '\n')
        except Empty:
            pass
        if wrote:
            self.log.see('end')
            self.log.configure(state='disabled')
        self.after(200, self._drain_log)

    def _poll(self):
        for name, r in self.rows.items():
            up = port_open(r['port'])
            mine = name in self.procs and self.procs[name].poll() is None
            if up:
                label, colour = ('running', '#1a9e5c') if mine else ('running*', '#b8860b')
            else:
                label, colour = 'stopped', '#c9ccd2'
                if mine:
                    label, colour = 'starting…', '#b8860b'
            r['state'].configure(text=label)
            r['dot'].itemconfigure(r['oval'], fill=colour)
            r['start'].configure(state='disabled' if up else 'normal')
            r['open'].configure(state='normal' if up else 'disabled')
            r['stop'].configure(state='normal' if mine else 'disabled')
        self.after(POLL_MS, self._poll)

    def start(self, name):
        r = self.rows[name]
        if port_open(r['port']):
            self.say(f'{name}: already running on :{r["port"]}')
            return
        path = os.path.join(BASE, r['script'])
        if not os.path.exists(path):
            self.say(f'{name}: {r["script"]} not found')
            return
        self.say(f'{name}: starting…')
        try:
            proc = subprocess.Popen(
                [sys.executable, '-u', path], cwd=BASE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, encoding='utf-8', errors='replace',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception as e:
            self.say(f'{name}: could not start -- {e}')
            return
        self.procs[name] = proc
        threading.Thread(target=self._pump, args=(name, proc), daemon=True).start()

    def _pump(self, name, proc):
        for line in proc.stdout:
            self.say(f'[{name}] {line.rstrip()}')
        code = proc.wait()
        if code not in (0, None):
            self.say(f'[{name}] exited with code {code}')

    def stop(self, name):
        proc = self.procs.get(name)
        if not proc or proc.poll() is not None:
            self.say(f'{name}: not started from here')
            return
        self.say(f'{name}: stopping…')
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
        self.procs.pop(name, None)

    def start_all(self):
        for name in self.rows:
            if not port_open(self.rows[name]['port']):
                self.start(name)

    def stop_all(self):
        for name in list(self.procs):
            self.stop(name)

    def _run_pipeline(self, args):
        proc = subprocess.Popen(
            [sys.executable, '-u', os.path.join(BASE, 've_pipeline.py'), *args],
            cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        lines = []
        for line in proc.stdout:
            lines.append(line.rstrip())
            self.say(line.rstrip())
        proc.wait()
        return proc.returncode, lines

    @staticmethod
    def _dry_counts(lines):
        try:
            start = lines.index('{')
            return json.loads('\n'.join(lines[start:])).get('counts')
        except (ValueError, TypeError):
            return None

    def _confirm_publish(self, counts):
        if counts:
            text = (f"Publishing will:\n\n"
                    f"  - email {counts.get('would_mail', 0)} ebook request(s)\n"
                    f"  - delete {counts.get('would_prune', 0)} reader ebook(s)\n"
                    f"  - write {counts.get('sheet_writes', 0)} update(s) to the live Sheet\n\n"
                    f"Continue?")
        else:
            text = 'The preview could not be read. Publish anyway?'
        answer = {}
        done = threading.Event()

        def ask():
            answer['ok'] = messagebox.askokcancel('Publish', text)
            done.set()

        self.after(0, ask)
        done.wait()
        return answer['ok']

    def pipeline(self, action):
        if getattr(self, '_pipe_busy', False):
            self.say('a pipeline run is already going -- wait for it to finish')
            return
        self._pipe_busy = True
        self.say(f'--- {action} ---')

        def work():
            try:
                if action == 'publish':
                    code, lines = self._run_pipeline(['publish', '--dry-run'])
                    if code != 0:
                        self.say('publish preview failed -- nothing was run')
                        return
                    if not self._confirm_publish(self._dry_counts(lines)):
                        self.say('publish cancelled -- nothing was run')
                        return
                self._run_pipeline([action])
            except Exception as e:
                self.say(f'{action} failed: {e}')
            finally:
                self._pipe_busy = False

        threading.Thread(target=work, daemon=True).start()

    def _on_close(self):
        if self.procs and not messagebox.askokcancel(
                'Quit', 'Stop the tools started here and quit?'):
            return
        self.stop_all()
        self.destroy()


if __name__ == '__main__':
    Office().mainloop()
