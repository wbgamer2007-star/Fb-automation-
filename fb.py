import hmac, hashlib, requests, threading
from urllib.parse import urlencode
from config import *
def proof(tok): return hmac.new(FB_APP_SECRET.encode(), tok.encode(), hashlib.sha256).hexdigest()
def call(method, path, token=None, data=None, params=None, files=None, json_body=None, timeout=20):
    p = dict(params or {})
    if token: p.update(access_token=token, appsecret_proof=proof(token))
    url = path if path.startswith('http') else f'{GRAPH}/{path}'
    try:
        if method in ('GET', 'DELETE'): r = requests.request(method, url, params=p, timeout=timeout)
        else: r = requests.post(url, params=p, data=data, files=files, json=json_body, timeout=timeout)
        try: j = r.json()
        except Exception: j = {}
        if r.status_code != 200: log('FB', r.status_code, str(path).split('?')[0][:40], str((j.get('error') or {}).get('message', ''))[:160])
        return r.status_code, j
    except Exception as e: log('FB exception', type(e).__name__); return 0, {}
def login_url(state):
    return f'https://www.facebook.com/{GRAPH_VER}/dialog/oauth?' + urlencode({'client_id': FB_APP_ID, 'redirect_uri': BASE + '/auth/facebook/callback', 'state': state, 'scope': ','.join(SCOPES), 'response_type': 'code'})
def exchange_code(code):
    st, j = call('GET', 'oauth/access_token', params={'client_id': FB_APP_ID, 'client_secret': FB_APP_SECRET, 'redirect_uri': BASE + '/auth/facebook/callback', 'code': code})
    return j.get('access_token') if st == 200 else None
def long_lived(tok):
    st, j = call('GET', 'oauth/access_token', params={'grant_type': 'fb_exchange_token', 'client_id': FB_APP_ID, 'client_secret': FB_APP_SECRET, 'fb_exchange_token': tok})
    return j.get('access_token') if st == 200 else None
def me(tok):
    st, j = call('GET', 'me', tok, params={'fields': 'id,name'}); return j if st == 200 else None
def accounts(tok):
    out, url, params = [], 'me/accounts', {'fields': 'id,name,access_token', 'limit': 100}
    for _ in range(5):
        st, j = call('GET', url, tok, params=params)
        if st != 200: return None if not out else out
        out += j.get('data', [])
        nxt = (j.get('paging') or {}).get('next')
        if not nxt: break
        url, params = nxt, {}  # next URL already carries token params
    return out
def subscribe(pid, ptok):
    st, j = call('POST', f'{pid}/subscribed_apps', ptok, data={'subscribed_fields': SUB_FIELDS}); return st == 200 and j.get('success')
def unsubscribe(pid, ptok): return call('DELETE', f'{pid}/subscribed_apps', ptok)[0] == 200
own_sent, _l = {}, threading.Lock()
def send_text(ptok, psid, text):
    t, ok = (text or '').strip(), True
    while t:
        if len(t) <= 1900: chunk, t = t, ''
        else:
            cut = t.rfind('\n', 0, 1900); cut = cut if cut > 500 else (t.rfind(' ', 0, 1900) if t.rfind(' ', 0, 1900) > 500 else 1900)
            chunk, t = t[:cut].strip(), t[cut:].strip()
        with _l: own_sent[psid] = (own_sent.get(psid, []) + [chunk])[-20:]
        body = {'recipient': {'id': psid}, 'message': {'text': chunk}}
        st, _ = call('POST', 'me/messages', ptok, json_body=dict(body, messaging_type='RESPONSE'))
        if st != 200: st, _ = call('POST', 'me/messages', ptok, json_body=dict(body, messaging_type='MESSAGE_TAG', tag='HUMAN_AGENT'))
        ok = ok and st == 200
    return ok
