import hmac, hashlib, base64, json, time, threading, secrets, socket, ipaddress, re
from collections import deque
from urllib.parse import urlparse, urljoin
import requests
from cryptography.fernet import Fernet, InvalidToken
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from config import *
_f = None
def _fer():
    global _f
    if not _f: _f = Fernet(ENCRYPTION_KEY.encode())
    return _f
def enc(s): return _fer().encrypt(s.encode()).decode() if s else ''
def dec(s):
    try: return _fer().decrypt(s.encode()).decode() if s else ''
    except (InvalidToken, ValueError): return ''
_ph = PasswordHasher()
def hash_pw(p): return _ph.hash(p)
def check_pw(h, p):
    try: return _ph.verify(h, p)
    except (VerifyMismatchError, InvalidHashError, Exception): return False
_DUMMY = _ph.hash('dummy-password')
def fake_check(): check_pw(_DUMMY, 'x')
def gen_creds(): return 'user_' + secrets.token_hex(3), secrets.token_urlsafe(10)
def safe_eq(a, b): return hmac.compare_digest(str(a).encode(), str(b).encode())
# ---- rate limit (in-memory, single worker) ----
_rl, _rll = {}, threading.Lock()
def rl(key, limit, window):
    now = time.time()
    with _rll:
        q = _rl.setdefault(key, deque())
        while q and q[0] < now - window: q.popleft()
        if len(q) >= limit: return False
        q.append(now)
        if len(_rl) > 20000:
            for k in [k for k, v in _rl.items() if not v or v[-1] < now - 3600]: _rl.pop(k, None)
        return True
# ---- facebook signatures ----
def verify_sig(raw, header):
    if not header or not header.startswith('sha256=') or not FB_APP_SECRET: return False
    return hmac.compare_digest(hmac.new(FB_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest(), header[7:])
def _b64(s): return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
def parse_signed_request(sr):
    try:
        sig, payload = sr.split('.', 1)
        if not hmac.compare_digest(_b64(sig), hmac.new(FB_APP_SECRET.encode(), payload.encode(), hashlib.sha256).digest()): return None
        return json.loads(_b64(payload))
    except Exception: return None
# ---- SSRF-safe fetching ----
def url_ok(url):
    try:
        p = urlparse(url)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.port not in (None, 80, 443): return False
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80), proto=socket.IPPROTO_TCP)
        return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)
    except Exception: return False
def safe_get(url, max_bytes=1500000, headers=None, hops=4):
    """returns (bytes, content_type). raises ValueError on blocked/too big/error."""
    t0 = time.time()
    for _ in range(hops + 1):
        if not url_ok(url): raise ValueError('blocked or invalid URL')
        r = requests.get(url, headers=dict({'User-Agent': 'Mozilla/5.0 (compatible; PageAIBot/1.0)'}, **(headers or {})), stream=True, allow_redirects=False, timeout=(5, 10))
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get('Location'):
            url = urljoin(url, r.headers['Location']); r.close(); continue
        if r.status_code != 200: r.close(); raise ValueError('HTTP %s' % r.status_code)
        buf = b''
        for ch in r.iter_content(65536):
            buf += ch
            if len(buf) > max_bytes or time.time() - t0 > 20: break
        r.close()
        return buf[:max_bytes], r.headers.get('Content-Type', '')
    raise ValueError('too many redirects')
