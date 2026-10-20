import secrets, json, time, threading, hmac
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, session, redirect, jsonify, render_template, abort, g
import db, fb, security as S, pipeline as P, linkreader as L, tasks as T
from config import *
app = Flask(__name__); app.secret_key = SESSION_SECRET or 'dev-only'
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=BASE.startswith('https'), SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=14 * 86400, MAX_CONTENT_LENGTH=10 * 1024 * 1024)
EX = ThreadPoolExecutor(16)
if missing(): log('MISSING ENV VARS:', ', '.join(missing()))
def jerr(m, c=400): return jsonify(error=m), c
def ip(): return (request.headers.get('X-Forwarded-For', request.remote_addr) or '').split(',')[0].strip()
@app.before_request
def csrf_guard():
    p = request.path
    if p == '/health' or p.startswith(('/static', '/webhook', '/cron', '/fb/')): return
    session.permanent = True
    if 'csrf' not in session: session['csrf'] = secrets.token_urlsafe(24)
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        t = request.headers.get('X-CSRF-Token') or request.form.get('csrf') or ''
        if not S.safe_eq(t, session['csrf']): abort(403)
@app.after_request
def headers(r):
    r.headers.update({'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'same-origin',
                      'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'"})
    return r
def login_required(f):
    @wraps(f)
    def w(*a, **k):
        uid = session.get('uid'); u = db.get('users', uid, ttl=15) if uid else None
        if not u or u.get('disabled'):
            session.pop('uid', None)
            return jerr('login required', 401) if request.path.startswith('/api/') else redirect('/login')
        if request.path.startswith('/api/') and not S.rl('u:' + uid, 240, 60): return jerr('too many requests', 429)
        g.uid, g.user = uid, u; return f(*a, **k)
    return w
def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get('admin'): return jerr('admin only', 401) if request.path.startswith('/admin/api/') else redirect('/admin/login')
        return f(*a, **k)
    return w
def own_page(pid):
    p = db.get('pages', str(pid))
    if not p or p.get('ownerUid') != g.uid: abort(404)
    return p
def own_conv(cid):
    c = db.get('conversations', cid)
    if not c or c.get('ownerUid') != g.uid: abort(404)
    return c
def body(): return request.get_json(silent=True) or {}
# ---------------- public pages ----------------
@app.route('/')
def index(): return render_template('index.html', csrf=session.get('csrf'))
@app.route('/privacy')
def privacy(): return render_template('privacy.html', base=BASE)
@app.route('/terms')
def terms(): return render_template('terms.html')
@app.route('/health')
def health(): return 'ok'
@app.route('/deletion-status')
def deletion_status():
    d = db.get('deletions', request.args.get('code', '-')[:60]); return render_template('deleted.html', done=bool(d))
# ---------------- auth ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET': return render_template('login.html', csrf=session['csrf'], err='')
    u, p = (request.form.get('username') or '')[:60], (request.form.get('password') or '')[:200]
    if not S.rl('l:' + ip(), 10, 600) or not S.rl('lu:' + u, 10, 600): return render_template('login.html', csrf=session['csrf'], err='অনেকবার চেষ্টা হয়েছে, কিছুক্ষণ পর আবার চেষ্টা করুন।'), 429
    r = db.q('users', [('username', '==', u)], limit=1)
    if r and S.check_pw(r[0].get('passHash', ''), p) and not r[0].get('disabled'):
        session.clear(); session['uid'] = r[0]['_id']; session['csrf'] = secrets.token_urlsafe(24); return redirect('/app')
    if not r: S.fake_check()
    return render_template('login.html', csrf=session['csrf'], err='ইউজারনেম বা পাসওয়ার্ড ভুল।'), 401
@app.route('/logout', methods=['POST'])
def logout(): session.clear(); return redirect('/')
@app.route('/auth/facebook')
def fb_login():
    if not S.rl('o:' + ip(), 30, 600): abort(429)
    session['oauth_state'] = secrets.token_urlsafe(20); return redirect(fb.login_url(session['oauth_state']))
@app.route('/auth/facebook/callback')
def fb_callback():
    st = session.pop('oauth_state', None)
    if not st or not S.safe_eq(request.args.get('state', ''), st) or not request.args.get('code'): return 'লগইন ব্যর্থ। আবার চেষ্টা করুন: <a href="/">হোম</a>', 400
    tok = fb.exchange_code(request.args['code']); tok = (tok and fb.long_lived(tok)) or tok
    info = tok and fb.me(tok)
    if not info: return 'ফেসবুক থেকে তথ্য পাওয়া যায়নি। <a href="/">আবার চেষ্টা করুন</a>', 400
    uid, new = 'fb_' + info['id'], False; u = db.get('users', uid)
    if u and u.get('disabled'): return 'এই অ্যাকাউন্ট বন্ধ আছে।', 403
    if not u:
        un, pw = S.gen_creds(); new = True
        db.put('users', uid, {'fbId': info['id'], 'name': info.get('name', ''), 'username': un, 'passHash': S.hash_pw(pw), 'createdAt': time.time(), 'disabled': False, 'ai': {'mode': 'default'}}, merge=False)
    db.put('users', uid, {'userToken': S.enc(tok), 'name': info.get('name', ''), 'lastLogin': time.time()})
    session.clear(); session['uid'] = uid; session['csrf'] = secrets.token_urlsafe(24)
    if new: session['creds'] = [un, pw]; return redirect('/credentials')
    return redirect('/app' if db.q('pages', [('ownerUid', '==', uid)], limit=1) else '/connect')
@app.route('/credentials')
@login_required
def credentials():
    c = session.pop('creds', None)
    if not c: return redirect('/app')
    return render_template('credentials.html', u=c[0], p=c[1])
@app.route('/connect', methods=['GET', 'POST'])
@login_required
def connect():
    tok = S.dec(g.user.get('userToken', '')); acc = fb.accounts(tok) if tok else None
    if acc is None: return redirect('/auth/facebook')
    if request.method == 'GET': return render_template('select_pages.html', pages=[{'id': a['id'], 'name': a['name']} for a in acc], csrf=session['csrf'])
    want, done, bad = set(request.form.getlist('page')), [], []
    for a in acc:
        if a['id'] not in want: continue
        ex = db.get('pages', a['id'])
        if ex and ex['ownerUid'] != g.uid and ex.get('connected', True): bad.append(a['name']); continue
        ok = fb.subscribe(a['id'], a['access_token'])
        data = {'ownerUid': g.uid, 'name': a['name'], 'token': S.enc(a['access_token']), 'connected': True, 'subscribed': bool(ok), 'connectedAt': time.time()}
        if not ex or ex['ownerUid'] != g.uid: data.update(autoReplyEnabled=True, commentsEnabled=False, dailyReportEnabled=False, instructions='', linkSources=[], abuseAction='hide')
        db.put('pages', a['id'], data); done.append(a['name'])
    return redirect('/app')
# ---------------- Facebook callbacks ----------------
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and S.safe_eq(request.args.get('hub.verify_token', ''), FB_VERIFY_TOKEN): return request.args.get('hub.challenge', ''), 200
        return 'forbidden', 403
    raw = request.get_data()
    if not S.verify_sig(raw, request.headers.get('X-Hub-Signature-256')): return 'bad signature', 403
    try: data = json.loads(raw)
    except Exception: return 'ok', 200
    if data.get('object') == 'page':
        for e in data.get('entry', []): EX.submit(P.handle_entry, e)
    return 'ok', 200
@app.route('/fb/deauthorize', methods=['POST'])
def deauth():
    d = S.parse_signed_request(request.form.get('signed_request', ''))
    if not d: return 'bad', 400
    uid = 'fb_' + str(d.get('user_id'))
    for p in db.q('pages', [('ownerUid', '==', uid)]): db.put('pages', p['_id'], {'connected': False, 'token': '', 'autoReplyEnabled': False, 'commentsEnabled': False})
    db.put('users', uid, {'userToken': ''}) if db.get('users', uid) else None
    return 'ok'
@app.route('/fb/data-deletion', methods=['POST'])
def data_deletion():
    d = S.parse_signed_request(request.form.get('signed_request', ''))
    if not d: return 'bad', 400
    uid, code = 'fb_' + str(d.get('user_id')), secrets.token_urlsafe(12)
    db.delete_user_data(uid); db.put('deletions', code, {'ts': time.time(), 'status': 'complete'}, merge=False)
    return jsonify(url=f'{BASE}/deletion-status?code={code}', confirmation_code=code)
# ---------------- cron ----------------
def cron_ok(): return S.safe_eq(request.args.get('secret', ''), CRON_SECRET) and bool(CRON_SECRET)
@app.route('/cron/daily-report')
def cron_report():
    if not cron_ok(): abort(403)
    threading.Thread(target=T.daily_reports, daemon=True).start(); return jsonify(started=True), 202
@app.route('/cron/cleanup')
def cron_clean():
    if not cron_ok(): abort(403)
    return jsonify(T.cleanup())
# ---------------- dashboard ----------------
@app.route('/app')
@login_required
def dashboard(): return render_template('dashboard.html', csrf=session['csrf'])
def page_view(p): return {k: p.get(k) for k in ('name', 'autoReplyEnabled', 'commentsEnabled', 'dailyReportEnabled', 'instructions', 'linkSources', 'abuseAction', 'connected')} | {'id': p['_id'] if '_id' in p else p.get('id')}
@app.route('/api/bootstrap')
@login_required
def bootstrap():
    pages = db.q('pages', [('ownerUid', '==', g.uid)]); a = g.user.get('ai') or {}
    return jsonify(user={'name': g.user.get('name'), 'username': g.user.get('username')}, pages=[page_view(p) for p in pages if p.get('connected', True)],
                   ai={'mode': a.get('mode', 'default'), 'has': {k: bool(v) for k, v in (a.get('keys') or {}).items()}, 'models': a.get('models') or {}, 'customBaseUrl': a.get('customBaseUrl', ''), 'defaultAvailable': any(DEFAULT_KEYS.values())},
                   limit=int(g.user.get('dailyLimit') or P.cfg()['defaultDailyLimit']), used=P.used_today(g.uid))
@app.route('/api/page/<pid>/settings', methods=['POST'])
@login_required
def page_settings(pid):
    own_page(pid); b, upd = body(), {}
    for k in ('autoReplyEnabled', 'commentsEnabled', 'dailyReportEnabled'):
        if k in b: upd[k] = bool(b[k])
    if 'instructions' in b:
        if not isinstance(b['instructions'], str) or len(b['instructions']) > 20000: return jerr('নির্দেশনা সর্বোচ্চ ২০০০০ অক্ষর')
        upd['instructions'] = b['instructions']
    if 'linkSources' in b:
        ls = b['linkSources']
        if not isinstance(ls, list) or len(ls) > 10 or any(not isinstance(x, str) or not x.startswith(('http://', 'https://')) or len(x) > 500 for x in ls): return jerr('সর্বোচ্চ ১০টি বৈধ http/https লিংক দিন')
        upd['linkSources'] = ls
    if b.get('abuseAction') in ('hide', 'delete', 'none'): upd['abuseAction'] = b['abuseAction']
    if upd: db.put('pages', pid, upd)
    return jsonify(ok=True)
@app.route('/api/page/<pid>/links/refresh', methods=['POST'])
@login_required
def refresh_links(pid):
    p = own_page(pid)
    if not S.rl('rf:' + g.uid, 6, 60): return jerr('একটু পরে চেষ্টা করুন', 429)
    urls = list(dict.fromkeys((p.get('linkSources') or []) + L.urls_in(p.get('instructions', ''))))[:10]
    res = [{'url': u, 'chars': len(t), 'error': e} for u in urls for t, e in [L.fetch(g.uid, u, force=True)]]
    return jsonify(results=res)
@app.route('/api/page/<pid>/disconnect', methods=['POST'])
@login_required
def disconnect(pid):
    p = own_page(pid); fb.unsubscribe(pid, S.dec(p['token']))
    db.put('pages', pid, {'connected': False, 'token': '', 'autoReplyEnabled': False, 'commentsEnabled': False}); return jsonify(ok=True)
@app.route('/api/conversations')
@login_required
def conversations():
    names = {p['_id']: p.get('name', '') for p in db.q('pages', [('ownerUid', '==', g.uid)])}
    rows = db.q('conversations', [('ownerUid', '==', g.uid)], order='updatedAt', desc=True, limit=50)
    return jsonify([{'id': c['_id'], 'page': names.get(c['pageId'], ''), 'name': c.get('name') or c['psid'][-6:], 'last': c.get('last', ''), 'lastRole': c.get('lastRole'), 'updatedAt': c.get('updatedAt'), 'manual': bool(c.get('manual'))} for c in rows])
@app.route('/api/conversation/<cid>')
@login_required
def conversation(cid):
    c = own_conv(cid); return jsonify(id=cid, name=c.get('name'), manual=bool(c.get('manual')), msgs=[{'r': m['r'], 't': m['t'], 'ts': m['ts']} for m in c['msgs']])
@app.route('/api/conversation/<cid>/takeover', methods=['POST'])
@login_required
def takeover(cid): own_conv(cid); db.put('conversations', cid, {'manual': bool(body().get('on'))}); return jsonify(ok=True)
@app.route('/api/conversation/<cid>/reply', methods=['POST'])
@login_required
def manual_reply(cid):
    c = own_conv(cid); t = str(body().get('text', '')).strip()[:2000]
    if not t: return jerr('খালি মেসেজ')
    if not S.rl('mr:' + g.uid, 30, 60): return jerr('অনেক দ্রুত', 429)
    p = own_page(c['pageId'])
    if not fb.send_text(S.dec(p['token']), c['psid'], t): return jerr('পাঠানো যায়নি (২৪ ঘণ্টার জানালা পেরিয়ে গেছে হতে পারে)', 502)
    P.add_msg(p, c['psid'], 'human', t); return jsonify(ok=True)
@app.route('/api/comments')
@login_required
def comments():
    return jsonify([{k: c.get(k) for k in ('from', 'message', 'type', 'reply', 'action', 'ts', 'pageId')} for c in db.q('comments', [('ownerUid', '==', g.uid)], order='ts', desc=True, limit=50)])
@app.route('/api/analytics')
@login_required
def analytics():
    days = [today(time.time() - i * 86400) for i in range(7)]; u = db.get_all('usage', [f'{g.uid}_{d}' for d in days])
    rows = [{'date': d, **{k: int((u.get(f'{g.uid}_{d}') or {}).get(k, 0)) for k in ('messages_in', 'ai_replies', 'comments', 'comment_replies')}} for d in days]
    topics = {}
    for r in db.q('reports', [('ownerUid', '==', g.uid)], order='date', desc=True, limit=7):
        for t in r.get('asked') or []: topics[str(t)[:80]] = topics.get(str(t)[:80], 0) + 1
    return jsonify(days=rows, topics=sorted(topics, key=topics.get, reverse=True)[:10])
@app.route('/api/reports')
@login_required
def reports(): return jsonify([{k: r.get(k) for k in ('date', 'pageName', 'summary', 'liked', 'disliked', 'asked', 'sentiment', 'suggestions', 'msgCount', 'commentCount')} for r in db.q('reports', [('ownerUid', '==', g.uid)], order='date', desc=True, limit=14)])
@app.route('/api/ai', methods=['POST'])
@login_required
def save_ai():
    b = body(); a = dict(g.user.get('ai') or {}); a['mode'] = 'own' if b.get('mode') == 'own' else 'default'
    keys, models = dict(a.get('keys') or {}), dict(a.get('models') or {})
    for k in ('gemini', 'groq', 'mistral', 'cerebras', 'openrouter', 'custom'):
        v = str((b.get('keys') or {}).get(k, '')).strip()[:300]; kk = k + 'Key' if k == 'custom' else k
        if v == '__clear__': keys.pop(kk, None)
        elif v: keys[kk] = S.enc(v)
        if k in (b.get('models') or {}): models[k] = str(b['models'][k])[:300]
    cu = str(b.get('customBaseUrl', '')).strip()[:300]
    if cu and not S.url_ok(cu): return jerr('Custom base URL বৈধ/সর্বজনীন নয়')
    a.update(keys=keys, models=models, customBaseUrl=cu); db.update('users', g.uid, {'ai': a}); return jsonify(ok=True)
@app.route('/api/command', methods=['POST'])
@login_required
def command():
    if not S.rl('cmd:' + g.uid, 8, 60): return jerr('অনেক দ্রুত', 429)
    p = own_page(request.form.get('pageId', '')); img = None; f = request.files.get('image')
    if f:
        raw = f.read(8_000_001)
        if len(raw) > 8_000_000: return jerr('ছবি ৮MB-এর বেশি')
        m = T.img_mime(raw)
        if not m: return jerr('শুধু JPG/PNG/GIF/WEBP ছবি')
        img = (raw, m)
    t = (request.form.get('text') or '').strip()[:5000]
    if not t and not img: return jerr('কমান্ড লিখুন')
    ok, msg = T.run_command(p, g.user, t, img); return jsonify(ok=ok, message=msg)
@app.route('/api/password', methods=['POST'])
@login_required
def regen_pw():
    pw = secrets.token_urlsafe(10); db.put('users', g.uid, {'passHash': S.hash_pw(pw)}); return jsonify(username=g.user.get('username'), password=pw)
# ---------------- admin ----------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET': return render_template('login.html', csrf=session['csrf'], err='', admin=True)
    if not S.rl('al:' + ip(), 5, 600): return 'too many attempts', 429
    ok = S.safe_eq(request.form.get('username', ''), ADMIN_USERNAME) and S.check_pw(ADMIN_PASSWORD_HASH, request.form.get('password', ''))
    if not ok: return render_template('login.html', csrf=session['csrf'], err='ভুল তথ্য', admin=True), 401
    session.clear(); session['admin'] = True; session['csrf'] = secrets.token_urlsafe(24); return redirect('/admin')
@app.route('/admin')
@admin_required
def admin_page(): return render_template('admin.html', csrf=session['csrf'])
@app.route('/admin/api/overview')
@admin_required
def admin_overview():
    us = db.q('users', limit=300); usage_today = {u['ownerUid']: u for u in db.q('usage', [('date', '==', today())], limit=500)}
    return jsonify(cfg=P.cfg(), users=[{'id': u['_id'], 'name': u.get('name'), 'username': u.get('username'), 'disabled': bool(u.get('disabled')), 'dailyLimit': u.get('dailyLimit'), 'mode': (u.get('ai') or {}).get('mode', 'default'),
                   'today': {k: (usage_today.get(u['_id']) or {}).get(k, 0) for k in ('messages_in', 'ai_replies', 'comments', 'limit_hits')}} for u in us],
                   pages=[{'id': p['_id'], 'name': p.get('name'), 'owner': p.get('ownerUid'), 'connected': p.get('connected', True), 'auto': p.get('autoReplyEnabled'), 'comments': p.get('commentsEnabled')} for p in db.q('pages', limit=300)],
                   errors=[{'where': e.get('where'), 'msg': e.get('msg'), 'ts': e.get('ts')} for e in db.q('errors', order='ts', desc=True, limit=50)])
@app.route('/admin/api/config', methods=['POST'])
@admin_required
def admin_config():
    b = body(); mp = str(b.get('masterPrompt', ''))[:20000]
    if len(mp) < 50: return jerr('Master prompt খুব ছোট')
    db.put('admin_config', 'main', {'masterPrompt': mp, 'defaultDailyLimit': max(1, int(b.get('defaultDailyLimit') or 200)), 'retentionDays': max(1, int(b.get('retentionDays') or 30)), 'linkTtlMinutes': max(1, int(b.get('linkTtlMinutes') or 60)), 'updatedAt': time.time()}); return jsonify(ok=True)
@app.route('/admin/api/user/<uid>', methods=['POST'])
@admin_required
def admin_user(uid):
    if not db.get('users', uid): abort(404)
    b, upd = body(), {}
    if 'disabled' in b: upd['disabled'] = bool(b['disabled'])
    if 'dailyLimit' in b: upd['dailyLimit'] = int(b['dailyLimit']) if b['dailyLimit'] else None
    db.put('users', uid, upd); return jsonify(ok=True)
@app.route('/admin/logout', methods=['POST'])
def admin_logout(): session.clear(); return redirect('/')
if __name__ == '__main__': app.run(port=int(env('PORT', '8080')))
