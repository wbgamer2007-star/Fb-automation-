import re, hashlib, time
from html.parser import HTMLParser
import db, security
URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')
def urls_in(t): return list(dict.fromkeys(u.rstrip('.,;:!?)') for u in URL_RE.findall(t or '')))[:10]
def export_url(u):
    m = re.search(r'docs\.google\.com/spreadsheets/d/([\w-]+)', u)
    if m:
        g = re.search(r'gid=(\d+)', u); return f'https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv' + (f'&gid={g.group(1)}' if g else '')
    m = re.search(r'docs\.google\.com/document/d/([\w-]+)', u)
    return f'https://docs.google.com/document/d/{m.group(1)}/export?format=txt' if m else u
class _T(HTMLParser):
    def __init__(s): super().__init__(); s.o, s.skip = [], 0
    def handle_starttag(s, t, a):
        if t in ('script', 'style', 'noscript', 'svg'): s.skip += 1
        elif t in ('p', 'br', 'div', 'li', 'tr', 'h1', 'h2', 'h3'): s.o.append('\n')
    def handle_endtag(s, t):
        if t in ('script', 'style', 'noscript', 'svg') and s.skip: s.skip -= 1
    def handle_data(s, d):
        if not s.skip: s.o.append(d)
def to_text(b, ct):
    try: s = b.decode('utf-8')
    except UnicodeDecodeError: s = b.decode('latin-1', 'ignore')
    if 'html' in ct.lower() or s.lstrip()[:15].lower().startswith(('<!doctype', '<html')):
        p = _T(); p.feed(s); s = ''.join(p.o)
    return re.sub(r'\n\s*\n+', '\n', re.sub(r'[ \t]+', ' ', s)).strip()
def fetch(uid, url, ttl_min=60, force=False, limit=30000):
    """returns (text, error). cached per owner."""
    cid = hashlib.sha1((uid + url).encode()).hexdigest()
    c = None if force else db.get('link_cache', cid)
    if c and time.time() - c.get('fetchedAt', 0) < ttl_min * 60: return c['text'], ''
    try:
        b, ct = security.safe_get(export_url(url))
        txt = to_text(b, ct)[:limit]
    except Exception as e:
        return (c or {}).get('text', ''), str(e)[:120]
    db.put('link_cache', cid, {'ownerUid': uid, 'url': url, 'text': txt, 'fetchedAt': time.time()}, merge=False)
    return txt, ''
def reference(uid, urls, ttl_min=60, force=False, total=40000):
    out, left, errs = [], total, {}
    for i, u in enumerate(urls, 1):
        if left < 500: break
        t, e = fetch(uid, u, ttl_min, force, min(30000, left))
        if e: errs[u] = e
        if t: out.append(f'[SOURCE {i}: {u}]\n{t}'); left -= len(t)
    return '\n\n'.join(out), errs
