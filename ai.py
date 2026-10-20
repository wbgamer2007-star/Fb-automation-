import re, time, json, hashlib, threading, base64, requests
from config import log
from security import url_ok
GEM = 'https://generativelanguage.googleapis.com/v1beta'
# Default model names: providers rename models often; users/admin can override per provider. Verify periodically.
DEF = {'gemini': ['gemini-2.5-flash', 'gemini-2.5-flash-lite'], 'groq': ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant'],
       'mistral': ['mistral-small-latest'], 'cerebras': ['llama-3.3-70b', 'llama3.1-8b'], 'openrouter': ['meta-llama/llama-3.3-70b-instruct:free']}
BASES = {'groq': 'https://api.groq.com/openai/v1', 'mistral': 'https://api.mistral.ai/v1', 'cerebras': 'https://api.cerebras.ai/v1', 'openrouter': 'https://openrouter.ai/api/v1'}
cool, _rr, _l = {}, {}, threading.Lock()
def csv(v): return [x.strip() for x in str(v or '').split(',') if x.strip()]
def kid(k): return hashlib.sha1(k.encode()).hexdigest()[:8]
def http(url, body, headers, timeout=60):
    try:
        r = requests.post(url, json=body, headers=headers, timeout=timeout)
        try: b = r.json()
        except Exception: b = {'raw': r.text[:300]}
        return r.status_code, b, r.headers
    except Exception as e: return 0, {'err': type(e).__name__}, {}
def providers(keys, audio=False):
    out = []
    if keys.get('gemini'): out.append({'id': 'gemini' + kid(keys['gemini']), 'type': 'gemini', 'key': keys['gemini'], 'models': csv(keys.get('geminiModels')) or DEF['gemini']})
    if not audio:
        for p in ('groq', 'mistral', 'cerebras', 'openrouter'):
            if keys.get(p): out.append({'id': p + kid(keys[p]), 'type': 'openai', 'key': keys[p], 'base': BASES[p], 'models': csv(keys.get(p + 'Models')) or DEF[p]})
        if keys.get('customKey') and keys.get('customBaseUrl') and csv(keys.get('customModels')) and url_ok(keys['customBaseUrl']):
            out.append({'id': 'custom' + kid(keys['customKey']), 'type': 'openai', 'key': keys['customKey'], 'base': keys['customBaseUrl'].rstrip('/'), 'models': csv(keys['customModels'])})
    return out
def call_gemini(p, m, system, hist, text, audio, jm):
    contents = [{'role': r, 'parts': [{'text': t}]} for r, t in hist]
    st, b, hd = 0, {}, {}
    for mime in (audio['mimes'] if audio else [None]):
        parts = ([{'inline_data': {'mime_type': mime, 'data': audio['b64']}}] if audio else []) + [{'text': text}]
        gc = {'temperature': 0.3 if jm else 0.5, 'maxOutputTokens': 8192}
        if jm: gc['responseMimeType'] = 'application/json'
        st, b, hd = http(f'{GEM}/models/{m}:generateContent', {'system_instruction': {'parts': [{'text': system}]}, 'contents': contents + [{'role': 'user', 'parts': parts}], 'generationConfig': gc}, {'x-goog-api-key': p['key']})
        if st == 400 and audio: continue
        break
    t = ''
    if st == 200:
        try: t = ''.join(x.get('text', '') for x in b['candidates'][0]['content']['parts']).strip()
        except Exception: pass
    return st, t, json.dumps(b, ensure_ascii=False)[:800], hd
def call_openai(p, m, system, hist, text, audio, jm):
    hh, tot = [], 0
    for r, t in reversed(hist):
        tot += len(t)
        if tot > 14000 and hh: break
        hh.append((r, t))
    hh.reverse()
    while hh and hh[0][0] != 'user': hh.pop(0)
    msgs = [{'role': 'system', 'content': system}] + [{'role': 'assistant' if r == 'model' else 'user', 'content': t} for r, t in hh] + [{'role': 'user', 'content': text}]
    st, b, hd = http(p['base'] + '/chat/completions', {'model': m, 'messages': msgs, 'temperature': 0.3 if jm else 0.5, 'max_tokens': 4096}, {'Authorization': 'Bearer ' + p['key']})
    t = ''
    if st == 200:
        try: t = (b['choices'][0]['message']['content'] or '').strip()
        except Exception: pass
    return st, t, json.dumps(b, ensure_ascii=False)[:800], hd
def judge(p, m, st, t, body, hd):
    if st == 200 and t: return True
    key, ms = f"{p['id']}:{m}", 60
    if st == 429 or st >= 500:
        if re.search(r'per ?day|daily|PerDay|RPD|TPD', body, re.I): ms = 3600
        else:
            try: ms = min(int(hd.get('retry-after')), 3600)
            except Exception: pass
        cool[key] = time.time() + ms
    elif st in (401, 403): cool[p['id'] + ':*'] = time.time() + 3600; log(p['id'][:6], 'key/permission problem', st)
    elif st in (404, 422): cool[key] = time.time() + 6 * 3600; log(key[:30], 'model not working, skipped', st)
    elif st >= 400: cool[key] = time.time() + 3600
    else: cool[key] = time.time() + 20
    return False
def clean(t): return re.sub(r'^#{1,6}\s*', '', re.sub(r'\*\*', '', re.sub(r'<think>[\s\S]*?</think>', '', t, flags=re.I)), flags=re.M).strip()
def pool(keys, audio):
    now, ready, rest = time.time(), [], []
    for p in providers(keys, audio):
        if cool.get(p['id'] + ':*', 0) > now: continue
        rl, ol = [], []
        for m in p['models']: (rl if cool.get(f"{p['id']}:{m}", 0) <= now else ol).append((p, m))
        ready.append(rl); rest.append(ol)
    return ready, rest
def mix(lists, rotate):
    lists = [l for l in lists if l]
    if not lists: return []
    if not rotate: return [x for l in lists for x in l]
    with _l:
        lists = sorted(lists, key=lambda l: _rr.get(l[0][0]['id'], 0))
        lists = [l[_rr.get(l[0][0]['id'], 0) % len(l):] + l[:_rr.get(l[0][0]['id'], 0) % len(l)] for l in lists]
    return [l[i] for i in range(max(len(l) for l in lists)) for l in lists if i < len(l)]
def generate(keys, system, hist, text, audio=None, json_mode=False, rot=True):
    """hist: [(role,text)] role in user/model. returns cleaned text or None."""
    for rnd in (1, 2):
        ready, rest = pool(keys, bool(audio))
        lst = mix(ready, rot) or (mix(rest, rot) if rnd == 1 else [])
        for p, m in lst[:20]:
            st, t, body, hd = (call_gemini if p['type'] == 'gemini' else call_openai)(p, m, system, hist, text, audio, json_mode)
            if judge(p, m, st, t, body, hd):
                with _l: _rr[p['id']] = _rr.get(p['id'], 0) + 1
                return clean(t)
        if rnd == 1: time.sleep(2)
    log('all AI providers failed'); return None
def transcribe(keys, audio_bytes):
    mimes = ['audio/mp4', 'audio/mpeg', 'audio/ogg', 'audio/wav']
    out = generate({'gemini': keys.get('gemini'), 'geminiModels': keys.get('geminiModels')}, 'You transcribe audio. Output only the exact spoken words, in the original language. If nothing is intelligible output EMPTY.',
                   [], 'Transcribe this voice message.', audio={'mimes': mimes, 'b64': base64.b64encode(audio_bytes).decode()}, rot=False)
    return '' if not out or out.strip().upper() == 'EMPTY' else out.strip()
