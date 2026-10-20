import json, base64, time, threading
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import Increment
from google.cloud.firestore_v1.base_query import FieldFilter
from config import *
_db, _c, _l = None, {}, threading.Lock()
def D():
    global _db
    if _db: return _db
    with _l:
        if _db: return _db
        raw = env('FIREBASE_SERVICE_ACCOUNT_JSON')
        try: info = json.loads(raw)
        except Exception: info = json.loads(base64.b64decode(raw).decode())
        if 'private_key' in info: info['private_key'] = info['private_key'].replace('\\n', '\n')
        firebase_admin.initialize_app(credentials.Certificate(info))
        _db = firestore.client()
    return _db
def get(c, i, ttl=0):
    k = (c, i)
    if ttl and k in _c and _c[k][0] > time.time(): return _c[k][1]
    s = D().collection(c).document(i).get(); d = s.to_dict() if s.exists else None
    if ttl: _c[k] = (time.time() + ttl, d)
    return d
def put(c, i, data, merge=True): _c.pop((c, i), None); D().collection(c).document(i).set(data, merge=merge)
def update(c, i, fields): _c.pop((c, i), None); D().collection(c).document(i).update(fields)
def delete(c, i): _c.pop((c, i), None); D().collection(c).document(i).delete()
def inc(c, i, fields, extra=None):
    d = {k: Increment(v) for k, v in fields.items()}; d.update(extra or {}); _c.pop((c, i), None)
    D().collection(c).document(i).set(d, merge=True)
def get_all(c, ids):
    refs = [D().collection(c).document(i) for i in ids]
    return {s.id: s.to_dict() for s in D().get_all(refs) if s.exists}
def q(c, where=(), order=None, desc=False, limit=None):
    r = D().collection(c)
    for f, op, v in where: r = r.where(filter=FieldFilter(f, op, v))
    if order: r = r.order_by(order, direction='DESCENDING' if desc else 'ASCENDING')
    if limit: r = r.limit(limit)
    out = []
    for s in r.stream(): d = s.to_dict(); d['_id'] = s.id; out.append(d)
    return out
def delete_where(c, f, op, v, cap=5000):
    n = 0
    while n < cap:
        docs = list(D().collection(c).where(filter=FieldFilter(f, op, v)).limit(400).stream())
        if not docs: break
        b = D().batch()
        for d in docs: b.delete(d.reference)
        b.commit(); n += len(docs)
        if len(docs) < 400: break
    return n
def delete_user_data(uid):
    for c in OWNED: delete_where(c, 'ownerUid', '==', uid)
    delete('users', uid)
