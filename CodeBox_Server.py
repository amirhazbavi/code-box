#!/usr/bin/env python3
"""CodeBox shared auth, website and gated release server.

Local development: python CodeBox_Server.py
Production: serve behind HTTPS reverse proxy, configure environment variables and persistent storage.
"""
from __future__ import annotations
import os, re, json, time, secrets, hashlib, sqlite3, smtplib, ssl, urllib.parse, webbrowser
from pathlib import Path
from email.message import EmailMessage
from functools import wraps
from contextlib import contextmanager
from datetime import datetime, timezone

import requests
from flask import Flask, request, jsonify, send_file, redirect, session, make_response
from werkzeug.security import generate_password_hash, check_password_hash

ROOT = Path(__file__).resolve().parent


def load_local_env():
    """Load simple KEY=value settings from a local .env file without extra packages."""
    env_file = ROOT / '.env'
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key and key.isidentifier():
            os.environ.setdefault(key, value)


load_local_env()
DB_PATH = Path(os.environ.get('CODEBOX_DB_PATH', str(ROOT / 'codebox_accounts.sqlite3')))
DOWNLOADS_DIR = Path(os.environ.get('CODEBOX_DOWNLOADS_DIR', str(ROOT / 'downloads')))
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_URL = os.environ.get('CODEBOX_PUBLIC_URL', '').rstrip('/')
COOKIE_SECURE = os.environ.get('CODEBOX_COOKIE_SECURE', '0').lower() in ('1','true','yes')
SESSION_DAYS = 7
OTP_TTL = 300

app = Flask(__name__)
_configured_secret = os.environ.get('CODEBOX_SECRET_KEY', '').strip()
if not _configured_secret or 'replace-with' in _configured_secret.lower() or len(_configured_secret) < 32:
    _configured_secret = secrets.token_urlsafe(48)
app.config.update(
    SECRET_KEY=_configured_secret,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)

EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


@contextmanager
def db():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT UNIQUE NOT NULL COLLATE NOCASE,
          username TEXT NOT NULL,
          password_hash TEXT,
          plan TEXT NOT NULL DEFAULT 'free' CHECK(plan IN ('free','plus')),
          github_id TEXT UNIQUE,
          google_sub TEXT UNIQUE,
          created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires_at INTEGER NOT NULL,
          created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions(user_id);
        CREATE TABLE IF NOT EXISTS login_attempts (
          ip TEXT PRIMARY KEY,
          window_started INTEGER NOT NULL,
          failures INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS otp_codes (
          email TEXT PRIMARY KEY COLLATE NOCASE,
          code_hash TEXT NOT NULL,
          expires_at INTEGER NOT NULL,
          sent_at INTEGER NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS oauth_transactions (
          state TEXT PRIMARY KEY,
          provider TEXT NOT NULL,
          mode TEXT NOT NULL,
          redirect_uri TEXT,
          expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS handoff_codes (
          code_hash TEXT PRIMARY KEY,
          user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires_at INTEGER NOT NULL,
          consumed INTEGER NOT NULL DEFAULT 0
        );
        ''')


def iso_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def otp_hash(email: str, code: str) -> str:
    pepper = app.config['SECRET_KEY']
    return hashlib.sha256((pepper + '|' + email.lower() + '|' + code).encode('utf-8')).hexdigest()


def public_base():
    return PUBLIC_URL or request.url_root.rstrip('/')


def user_public(row):
    return {'id': row['id'], 'email': row['email'], 'username': row['username'], 'plan': row['plan'], 'created_at': row['created_at']}


def get_user_by_id(user_id):
    with db() as con:
        return con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()


def current_user():
    auth = request.headers.get('Authorization', '')
    token = auth[7:].strip() if auth.lower().startswith('bearer ') else request.cookies.get('codebox_session', '')
    if token:
        now = int(time.time())
        with db() as con:
            row = con.execute('''SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id
                                 WHERE sessions.token_hash=? AND sessions.expires_at>?''', (token_hash(token), now)).fetchone()
        if row:
            return row
    uid = session.get('codebox_user_id')
    return get_user_by_id(int(uid)) if uid else None


def issue_session(user_id):
    token = secrets.token_urlsafe(42)
    now = int(time.time())
    with db() as con:
        con.execute('INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)',
                    (token_hash(token), user_id, now + SESSION_DAYS * 86400, now))
        con.execute('DELETE FROM sessions WHERE expires_at < ?', (now,))
    user = get_user_by_id(user_id)
    response = jsonify({'ok': True, 'token': token, 'user': user_public(user)})
    response.set_cookie('codebox_session', token, max_age=SESSION_DAYS * 86400, httponly=True,
                        secure=COOKIE_SECURE, samesite='Lax', path='/')
    return response


def require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user():
            return jsonify({'error': 'Sign in is required.'}), 401
        return func(*args, **kwargs)
    return wrapper


def get_json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@app.after_request
def set_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    if request.path == '/' or request.path.endswith('.html'):
        response.headers.setdefault('Cache-Control', 'no-store')
    return response


@app.get('/')
def homepage():
    return send_file(ROOT / 'CodeBox_Website.html')


@app.get('/health')
def health():
    return jsonify({'ok': True, 'app': 'CodeBox Nexus Studio', 'utc': iso_now()})


@app.post('/api/register')
def register():
    data = get_json()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    username = str(data.get('username') or email.split('@')[0]).strip()[:50]
    if not EMAIL_RE.match(email) or len(email) > 254:
        return jsonify({'error': 'Enter a valid email address.'}), 400
    if len(password) < 10 or len(password) > 256:
        return jsonify({'error': 'Password must be 10-256 characters.'}), 400
    if not username:
        username = 'CodeBox User'
    try:
        with db() as con:
            cur = con.execute('INSERT INTO users(email,username,password_hash,created_at) VALUES(?,?,?,?)',
                              (email, username, generate_password_hash(password), int(time.time())))
            uid = cur.lastrowid
    except sqlite3.IntegrityError:
        return jsonify({'error': 'An account with this email already exists. Sign in instead.'}), 409
    return issue_session(uid), 201


@app.post('/api/login')
def login():
    data = get_json()
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    now = int(time.time())
    client_ip = request.remote_addr or 'unknown'
    with db() as con:
        attempt = con.execute('SELECT * FROM login_attempts WHERE ip=?', (client_ip,)).fetchone()
        if attempt and now - attempt['window_started'] < 600 and attempt['failures'] >= 15:
            return jsonify({'error': 'Too many sign-in attempts. Wait 10 minutes before trying again.'}), 429
        row = con.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        valid = bool(row and row['password_hash'] and check_password_hash(row['password_hash'], password))
        if not valid:
            if not attempt or now - attempt['window_started'] >= 600:
                con.execute('INSERT INTO login_attempts(ip,window_started,failures) VALUES(?,?,1) ON CONFLICT(ip) DO UPDATE SET window_started=excluded.window_started,failures=1', (client_ip, now))
            else:
                con.execute('UPDATE login_attempts SET failures=failures+1 WHERE ip=?', (client_ip,))
        else:
            con.execute('DELETE FROM login_attempts WHERE ip=?', (client_ip,))
    if not valid:
        # Same response for unknown email and wrong password.
        return jsonify({'error': 'Email or password is incorrect.'}), 401
    return issue_session(row['id'])


@app.get('/api/me')
@require_auth
def api_me():
    user = current_user()
    return jsonify({'ok': True, 'user': user_public(user)})


@app.post('/api/logout')
def logout():
    auth = request.headers.get('Authorization', '')
    token = auth[7:].strip() if auth.lower().startswith('bearer ') else request.cookies.get('codebox_session', '')
    if token:
        with db() as con:
            con.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(token),))
    session.pop('codebox_user_id', None)
    response = jsonify({'ok': True})
    response.delete_cookie('codebox_session', path='/')
    return response


@app.post('/api/auth/send-code')
def send_email_code():
    data = get_json()
    email = str(data.get('email', '')).strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({'error': 'Enter a valid email address.'}), 400
    host = os.environ.get('CODEBOX_SMTP_HOST', '').strip()
    from_email = os.environ.get('CODEBOX_SMTP_FROM', os.environ.get('CODEBOX_SMTP_USER', '')).strip()
    if not host or not from_email:
        return jsonify({'error': 'Email-code login is not configured yet. Set CODEBOX_SMTP_HOST, CODEBOX_SMTP_FROM, and the SMTP credentials in the server environment.'}), 503
    now = int(time.time())
    with db() as con:
        existing = con.execute('SELECT sent_at FROM otp_codes WHERE email=?', (email,)).fetchone()
        if existing and now - existing['sent_at'] < 60:
            return jsonify({'error': f"Please wait {60 - (now-existing['sent_at'])} seconds before requesting another code."}), 429
    code = f'{secrets.randbelow(1_000_000):06d}'
    msg = EmailMessage()
    msg['Subject'] = 'Your CodeBox sign-in code'
    msg['From'] = from_email
    msg['To'] = email
    msg.set_content(f'Your CodeBox verification code is {code}. It expires in 5 minutes. If you did not request it, you can ignore this email.')
    port = int(os.environ.get('CODEBOX_SMTP_PORT', '587'))
    username = os.environ.get('CODEBOX_SMTP_USER', '')
    password = os.environ.get('CODEBOX_SMTP_PASSWORD', '')
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as smtp:
                if username: smtp.login(username, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo(); smtp.starttls(context=ssl.create_default_context()); smtp.ehlo()
                if username: smtp.login(username, password)
                smtp.send_message(msg)
    except Exception:
        app.logger.exception('Email OTP delivery failed')
        return jsonify({'error': 'The verification email could not be sent. Check the SMTP settings on the server.'}), 502
    with db() as con:
        con.execute('INSERT INTO otp_codes(email,code_hash,expires_at,sent_at,attempts) VALUES(?,?,?,?,0) '
                    'ON CONFLICT(email) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,sent_at=excluded.sent_at,attempts=0',
                    (email, otp_hash(email, code), now + OTP_TTL, now))
    return jsonify({'ok': True, 'message': 'A verification code was sent. It expires in 5 minutes.'})


@app.post('/api/auth/verify-code')
def verify_email_code():
    data = get_json()
    email = str(data.get('email', '')).strip().lower()
    code = str(data.get('code', '')).strip()
    now = int(time.time())
    if not EMAIL_RE.match(email) or not re.fullmatch(r'\d{6}', code):
        return jsonify({'error': 'Enter your email and the 6-digit code.'}), 400
    with db() as con:
        row = con.execute('SELECT * FROM otp_codes WHERE email=?', (email,)).fetchone()
        if not row or row['expires_at'] < now or row['attempts'] >= 5:
            return jsonify({'error': 'The code expired or was not requested. Request a new code.'}), 400
        expected = otp_hash(email, code)
        if not secrets.compare_digest(row['code_hash'], expected):
            con.execute('UPDATE otp_codes SET attempts=attempts+1 WHERE email=?', (email,))
            return jsonify({'error': 'Incorrect code.'}), 401
        con.execute('DELETE FROM otp_codes WHERE email=?', (email,))
        user = con.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
        if user:
            uid = user['id']
        else:
            username = email.split('@')[0][:50] or 'CodeBox User'
            cur = con.execute('INSERT INTO users(email,username,created_at) VALUES(?,?,?)', (email, username, now))
            uid = cur.lastrowid
    return issue_session(uid)


def provider_config(provider):
    if provider == 'github':
        return os.environ.get('CODEBOX_GITHUB_CLIENT_ID', ''), os.environ.get('CODEBOX_GITHUB_CLIENT_SECRET', '')
    if provider == 'google':
        return os.environ.get('CODEBOX_GOOGLE_CLIENT_ID', ''), os.environ.get('CODEBOX_GOOGLE_CLIENT_SECRET', '')
    return '', ''


@app.get('/auth/<provider>/start')
def oauth_start(provider):
    if provider not in ('github', 'google'):
        return 'Unsupported identity provider', 404
    client_id, client_secret = provider_config(provider)
    if not client_id or not client_secret:
        return (f'{provider.title()} sign-in is not configured. Set the CODEBOX_{provider.upper()}_CLIENT_ID and CODEBOX_{provider.upper()}_CLIENT_SECRET environment variables.', 503)
    mode = request.args.get('client', 'web').lower()
    if mode not in ('web', 'desktop'):
        return 'Invalid OAuth client mode', 400
    redirect_uri = request.args.get('redirect_uri', '')
    if mode == 'desktop':
        parsed = urllib.parse.urlparse(redirect_uri)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.path != '/oauth/callback':
            return 'Desktop sign-in must use a loopback callback.', 400
    else:
        redirect_uri = ''
    state = secrets.token_urlsafe(32)
    with db() as con:
        con.execute('INSERT INTO oauth_transactions(state,provider,mode,redirect_uri,expires_at) VALUES(?,?,?,?,?)',
                    (state, provider, mode, redirect_uri, int(time.time()) + 600))
    callback = public_base() + f'/auth/{provider}/callback'
    if provider == 'github':
        params = {'client_id': client_id, 'redirect_uri': callback, 'scope': 'read:user user:email', 'state': state}
        return redirect('https://github.com/login/oauth/authorize?' + urllib.parse.urlencode(params))
    params = {'client_id': client_id, 'redirect_uri': callback, 'response_type': 'code', 'scope': 'openid email profile', 'state': state}
    return redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params))


def oauth_get_or_create(provider, profile):
    now = int(time.time())
    email = (profile.get('email') or '').strip().lower()
    username = str(profile.get('username') or profile.get('name') or email.split('@')[0] or provider.title() + ' user')[:50]
    external_id = str(profile.get('id') or profile.get('sub') or '')
    if provider == 'github':
        with db() as con:
            row = con.execute('SELECT id FROM users WHERE github_id=?', (external_id,)).fetchone()
            if row: return row['id']
        if not email:
            email = f'github-{external_id}@oauth.codebox.invalid'
        with db() as con:
            row = con.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
            if row:
                con.execute('UPDATE users SET github_id=?, username=? WHERE id=?', (external_id, username, row['id']))
                return row['id']
            cur = con.execute('INSERT INTO users(email,username,github_id,created_at) VALUES(?,?,?,?)', (email, username, external_id, now))
            return cur.lastrowid
    else:
        with db() as con:
            row = con.execute('SELECT id FROM users WHERE google_sub=?', (external_id,)).fetchone()
            if row: return row['id']
        if not email:
            raise RuntimeError('Google did not return an email address.')
        with db() as con:
            row = con.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
            if row:
                con.execute('UPDATE users SET google_sub=?, username=? WHERE id=?', (external_id, username, row['id']))
                return row['id']
            cur = con.execute('INSERT INTO users(email,username,google_sub,created_at) VALUES(?,?,?,?)', (email, username, external_id, now))
            return cur.lastrowid


@app.get('/auth/<provider>/callback')
def oauth_callback(provider):
    if provider not in ('github', 'google'):
        return 'Unsupported provider', 404
    state = request.args.get('state', '')
    with db() as con:
        state_row = con.execute('SELECT * FROM oauth_transactions WHERE state=? AND provider=?', (state, provider)).fetchone()
        if state_row:
            con.execute('DELETE FROM oauth_transactions WHERE state=?', (state,))
    if not state_row or state_row['expires_at'] < int(time.time()):
        return 'Sign-in state expired. Start again from CodeBox.', 400
    if request.args.get('error'):
        return 'Sign-in was cancelled or denied. Return to CodeBox and try again.', 400
    code = request.args.get('code', '')
    if not code:
        return 'Provider did not return an authorization code.', 400
    client_id, client_secret = provider_config(provider)
    callback = public_base() + f'/auth/{provider}/callback'
    try:
        if provider == 'github':
            r = requests.post('https://github.com/login/oauth/access_token',
                              headers={'Accept':'application/json'},
                              data={'client_id':client_id,'client_secret':client_secret,'code':code}, timeout=20)
            r.raise_for_status(); access_token = r.json().get('access_token')
            if not access_token: raise RuntimeError('GitHub did not return an access token.')
            headers = {'Authorization': 'Bearer ' + access_token, 'Accept': 'application/vnd.github+json', 'User-Agent': 'CodeBox-Nexus'}
            profile_r = requests.get('https://api.github.com/user', headers=headers, timeout=20); profile_r.raise_for_status()
            profile = profile_r.json()
            emails_r = requests.get('https://api.github.com/user/emails', headers=headers, timeout=20)
            email = ''
            if emails_r.ok:
                emails = emails_r.json()
                primary = next((e for e in emails if e.get('primary') and e.get('verified')), None)
                any_verified = next((e for e in emails if e.get('verified')), None)
                email = (primary or any_verified or {}).get('email', '')
            uid = oauth_get_or_create('github', {'id':profile.get('id'), 'username':profile.get('login'), 'name':profile.get('name'), 'email':email})
        else:
            r = requests.post('https://oauth2.googleapis.com/token', data={
                'client_id':client_id, 'client_secret':client_secret, 'code':code,
                'grant_type':'authorization_code', 'redirect_uri':callback
            }, timeout=20)
            r.raise_for_status(); data = r.json(); access_token = data.get('access_token')
            if not access_token: raise RuntimeError('Google did not return an access token.')
            profile_r = requests.get('https://openidconnect.googleapis.com/v1/userinfo', headers={'Authorization':'Bearer '+access_token}, timeout=20)
            profile_r.raise_for_status(); profile = profile_r.json()
            if not profile.get('email_verified'): raise RuntimeError('Google email is not verified.')
            uid = oauth_get_or_create('google', {'sub':profile.get('sub'), 'username':profile.get('name'), 'email':profile.get('email')})
    except Exception as exc:
        app.logger.exception('OAuth callback failed')
        return 'Sign-in failed. Check the server configuration and logs, then try again.', 502
    if state_row['mode'] == 'desktop':
        redirect_uri = state_row['redirect_uri']
        handoff = secrets.token_urlsafe(36)
        with db() as con:
            con.execute('INSERT INTO handoff_codes(code_hash,user_id,expires_at,consumed) VALUES(?,?,?,0)',
                        (token_hash(handoff), uid, int(time.time()) + 180))
        return redirect(redirect_uri + '?code=' + urllib.parse.quote(handoff))
    session['codebox_user_id'] = uid
    return redirect(public_base() + '/?login=success')


@app.post('/api/auth/exchange-code')
def exchange_code():
    code = str(get_json().get('code', '')).strip()
    if not code:
        return jsonify({'error':'Missing one-time sign-in code.'}), 400
    now = int(time.time())
    with db() as con:
        row = con.execute('SELECT * FROM handoff_codes WHERE code_hash=? AND consumed=0 AND expires_at>?', (token_hash(code), now)).fetchone()
        if not row:
            return jsonify({'error':'The one-time code is invalid or expired. Try signing in again.'}), 401
        con.execute('UPDATE handoff_codes SET consumed=1 WHERE code_hash=?', (token_hash(code),))
    token = secrets.token_urlsafe(42)
    with db() as con:
        con.execute('INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES(?,?,?,?)',
                    (token_hash(token), row['user_id'], now + SESSION_DAYS * 86400, now))
    user = get_user_by_id(row['user_id'])
    return jsonify({'ok':True,'token':token,'user':user_public(user)})


@app.get('/api/download/free')
@require_auth
def download_free():
    binary = DOWNLOADS_DIR / 'CodeBox_Free.exe'
    source = DOWNLOADS_DIR / 'CodeBox_Free.py'
    candidate = binary if binary.is_file() else source
    if not candidate.is_file(): return jsonify({'error':'Free release is missing. Build the release or put CodeBox_Free.py in the downloads folder.'}), 404
    media = 'application/vnd.microsoft.portable-executable' if candidate.suffix.lower() == '.exe' else 'text/x-python'
    return send_file(candidate, as_attachment=True, download_name=candidate.name, mimetype=media)


@app.get('/api/download/plus')
@require_auth
def download_plus():
    user = current_user()
    if user['plan'] != 'plus':
        return jsonify({'error':'CodeBox Plus is locked. Sign in to an account with an active Plus entitlement.'}), 403
    binary = DOWNLOADS_DIR / 'CodeBox_Plus.exe'
    source = DOWNLOADS_DIR / 'CodeBox_Plus.py'
    candidate = binary if binary.is_file() else source
    if not candidate.is_file(): return jsonify({'error':'Plus release is missing. Build the release or put CodeBox_Plus.py in the downloads folder.'}), 404
    media = 'application/vnd.microsoft.portable-executable' if candidate.suffix.lower() == '.exe' else 'text/x-python'
    return send_file(candidate, as_attachment=True, download_name=candidate.name, mimetype=media)


@app.post('/api/admin/grant-plus')
def grant_plus():
    admin_key = os.environ.get('CODEBOX_ADMIN_KEY', '')
    if not admin_key or 'replace-with' in admin_key.lower() or len(admin_key) < 32:
        return jsonify({'error':'Admin plan activation is disabled until CODEBOX_ADMIN_KEY is configured on the server.'}), 503
    supplied = request.headers.get('X-Admin-Key', '')
    if not secrets.compare_digest(supplied, admin_key):
        return jsonify({'error':'Forbidden.'}), 403
    data = get_json(); email = str(data.get('email','')).strip().lower(); plan = str(data.get('plan','plus')).lower()
    if not EMAIL_RE.match(email) or plan not in ('free','plus'):
        return jsonify({'error':'Provide a valid email and plan=free or plan=plus.'}), 400
    with db() as con:
        cur = con.execute('UPDATE users SET plan=? WHERE email=?', (plan,email))
        if cur.rowcount == 0: return jsonify({'error':'No account was found for that email.'}), 404
    return jsonify({'ok':True,'email':email,'plan':plan})


@app.get('/api/public-config')
def public_config():
    # Never returns OAuth secrets; booleans only control whether provider buttons appear.
    return jsonify({'github_enabled':bool(os.environ.get('CODEBOX_GITHUB_CLIENT_ID') and os.environ.get('CODEBOX_GITHUB_CLIENT_SECRET')),
                    'google_enabled':bool(os.environ.get('CODEBOX_GOOGLE_CLIENT_ID') and os.environ.get('CODEBOX_GOOGLE_CLIENT_SECRET')),
                    'email_code_enabled':bool(os.environ.get('CODEBOX_SMTP_HOST') and os.environ.get('CODEBOX_SMTP_FROM', os.environ.get('CODEBOX_SMTP_USER'))),
                    'plus_enabled':True})


# Initialize the small SQLite store for both the development server and WSGI imports.
init_db()

if __name__ == '__main__':
    host = os.environ.get('CODEBOX_HOST', '127.0.0.1')
    port = int(os.environ.get('CODEBOX_PORT', '8765'))
    print('╭─ CodeBox Nexus Studio Server ─────────────────────────────╮')
    print(f'│ Website: http://127.0.0.1:{port}')
    print(f'│ Database: {DB_PATH}')
    print('│ Login: email/password; email-code and OAuth are optional.')
    configured_secret = os.environ.get('CODEBOX_SECRET_KEY', '')
    if not configured_secret or 'replace-with' in configured_secret.lower() or len(configured_secret) < 32:
        print('│ WARNING: generated temporary SECRET_KEY. Configure a 32+ character secret for deployment.')
    configured_admin = os.environ.get('CODEBOX_ADMIN_KEY', '')
    if not configured_admin or 'replace-with' in configured_admin.lower() or len(configured_admin) < 32:
        print('│ Plus activation is disabled until CODEBOX_ADMIN_KEY is configured.')
    print('╰───────────────────────────────────────────────────────────╯')
    app.run(host=host, port=port, debug=False, threaded=True)
