"""Outgoing mail over plain SMTP.

Works with any SMTP account. Settings come from environment variables, or from
`.ve_smtp.json` in the project root (never committed):

    {
      "host": "127.0.0.1",          Proton Mail Bridge: 127.0.0.1, port 1025, STARTTLS
      "port": 1025,                 Hostinger: smtp.hostinger.com, port 465, SSL
      "security": "starttls",       "ssl" | "starttls" | "none"
      "username": "voiceexpress@proton.me",
      "password": "the Bridge or mailbox password",
      "from_name": "The Voice Express",
      "from_addr": "voiceexpress@proton.me",
      "reply_to": "voiceexpress@proton.me"
    }

Environment overrides: VE_SMTP_HOST, VE_SMTP_PORT, VE_SMTP_SECURITY, VE_SMTP_USER,
VE_SMTP_PASSWORD, VE_SMTP_FROM, VE_SMTP_FROM_NAME, VE_SMTP_REPLY_TO.
"""
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT, '.ve_smtp.json')

_ENV = {
    'host': 'VE_SMTP_HOST', 'port': 'VE_SMTP_PORT', 'security': 'VE_SMTP_SECURITY',
    'username': 'VE_SMTP_USER', 'password': 'VE_SMTP_PASSWORD', 'from_addr': 'VE_SMTP_FROM',
    'from_name': 'VE_SMTP_FROM_NAME', 'reply_to': 'VE_SMTP_REPLY_TO',
}


class NotConfigured(RuntimeError):
    pass


def settings():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding='utf-8') as fh:
            cfg = json.load(fh) or {}
    for key, env in _ENV.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    cfg.setdefault('from_name', 'The Voice Express')
    cfg.setdefault('from_addr', cfg.get('username'))
    port = int(cfg.get('port') or 0)
    cfg.setdefault('security', 'ssl' if port == 465 else 'starttls')
    cfg['port'] = port or (465 if cfg['security'] == 'ssl' else 587)
    return cfg


def configured():
    cfg = settings()
    return bool(cfg.get('host') and cfg.get('username') and cfg.get('password'))


def _connect(cfg):
    host, port, sec = cfg['host'], cfg['port'], cfg['security'].lower()
    ctx = ssl.create_default_context()
    if host in ('127.0.0.1', 'localhost'):
        # Proton Mail Bridge listens locally with a self-signed certificate
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    if sec == 'ssl':
        server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        if sec == 'starttls':
            server.starttls(context=ctx)
    server.login(cfg['username'], cfg['password'])
    return server


def send(to, subject, text, html=None, reply_to=None):
    """Send one message. Raises on failure so callers can retry later."""
    cfg = settings()
    if not (cfg.get('host') and cfg.get('username') and cfg.get('password')):
        raise NotConfigured(f'no SMTP settings: add {CONFIG_FILE} or VE_SMTP_* variables')
    msg = EmailMessage()
    msg['From'] = formataddr((cfg['from_name'], cfg['from_addr']))
    msg['To'] = to
    msg['Subject'] = subject
    msg['Message-ID'] = make_msgid(domain=(cfg['from_addr'] or 'localhost').split('@')[-1])
    if reply_to or cfg.get('reply_to'):
        msg['Reply-To'] = reply_to or cfg['reply_to']
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype='html')
    server = _connect(cfg)
    try:
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def check():
    """Log in and log out without sending. Returns (ok, message)."""
    try:
        cfg = settings()
        if not configured():
            return False, 'not configured'
        server = _connect(cfg)
        server.quit()
        return True, f'logged in to {cfg["host"]}:{cfg["port"]} as {cfg["username"]}'
    except Exception as e:
        return False, str(e)


if __name__ == '__main__':
    import sys
    ok, msg = check()
    print(('OK  ' if ok else 'FAIL ') + msg)
    if ok and len(sys.argv) > 1:
        send(sys.argv[1], 'Voice Express desk mail test',
             'This is a test message from the Voice Express desk.')
        print(f'sent a test message to {sys.argv[1]}')
    sys.exit(0 if ok else 1)
