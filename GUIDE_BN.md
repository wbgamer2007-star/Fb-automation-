# Page AI Bot — সম্পূর্ণ গাইড (সহজ বাংলায়)

## ১. ফোল্ডার কাঠামো
```
app.py          ← ওয়েবসাইট, লগইন, ওয়েবহুক, API, অ্যাডমিন
config.py       ← env ভ্যারিয়েবল, Graph API ভার্সন (GRAPH_VER এক জায়গায়)
security.py     ← এনক্রিপশন, পাসওয়ার্ড হ্যাশ, rate limit, SSRF সুরক্ষা
db.py           ← Firestore
ai.py           ← AI রোটেশন (Gemini/Groq/Mistral/Cerebras/OpenRouter/Custom)
fb.py           ← Facebook Graph API, মেসেজ পাঠানো (২৪ ঘণ্টা + HUMAN_AGENT)
linkreader.py   ← Google Sheet/Doc/ওয়েবপেজ পড়া
pipeline.py     ← মেসেজ ও কমেন্টের AI রিপ্লাই
tasks.py        ← পোস্ট কমান্ড, দৈনিক রিপোর্ট, ক্লিনআপ
templates/ static/  ← ড্যাশবোর্ড (বাংলা UI)
firestore.rules, firestore.indexes.json, requirements.txt, Procfile, render.yaml
tools/make_secrets.py ← গোপন কী বানানোর স্ক্রিপ্ট
```
**আমার সিদ্ধান্ত (এক লাইনে):** একটি gunicorn worker + ১৬ thread (ডুপ্লিকেট/লক মেমরিতে নিরাপদ); কথোপকথনের শেষ ৪০টি মেসেজ একই ডকুমেন্টে রাখা হয় (লেখা কম লাগে, ইনডেক্স কম); কমেন্টে গালির ডিফল্ট অ্যাকশন “লুকানো” (মুছে ফেলা সেটিংসে বেছে নেওয়া যায়)।

## ২. Firestore ডেটা মডেল
`users` (fbId, username, passHash, userToken-এনক্রিপ্টেড, ai{mode,keys-এনক্রিপ্টেড}, disabled, dailyLimit) · `pages` (ownerUid, token-এনক্রিপ্টেড, instructions, linkSources, autoReplyEnabled, commentsEnabled, dailyReportEnabled, abuseAction) · `conversations` (ownerUid, pageId, psid, msgs[ ], manual) · `comments` · `reports` · `usage` (ইউজার+তারিখ অনুযায়ী কাউন্টার) · `link_cache` · `admin_config/main` (master prompt, লিমিট, রিটেনশন) · `errors` · `deletions`। প্রতিটি ডকুমেন্টে `ownerUid` আছে।
**লেখার হিসাব (ফ্রি ২০ হাজার/দিন):** প্রতি কাস্টমার-মেসেজে ≈ ৩টি লেখা (মেসেজ সেভ, উত্তর সেভ, ব্যবহার-কাউন্টার) → দিনে প্রায় ৬ হাজার মেসেজ-আদান-প্রদান পর্যন্ত ফ্রি।

## ৩. Environment Variables (Render > Environment)
| নাম | কী | কোথায় পাবেন |
|---|---|---|
| FIREBASE_SERVICE_ACCOUNT_JSON | Firebase সার্ভিস অ্যাকাউন্ট JSON (পুরো লেখা, বা base64) | Firebase Console > ⚙ Project settings > Service accounts > Generate new private key |
| FB_APP_ID / FB_APP_SECRET | Facebook অ্যাপের ID ও Secret | developers.facebook.com > App > Settings > Basic |
| FB_VERIFY_TOKEN | ওয়েবহুকের যাচাই-শব্দ (নিজে বানান) | `make_secrets.py` দেয় |
| APP_BASE_URL | যেমন `https://your-app.onrender.com` (শেষে / নেই) | Render সার্ভিসের URL |
| SESSION_SECRET | কুকি সাইন করার গোপন কী | `make_secrets.py` |
| ENCRYPTION_KEY | Fernet কী (টোকেন/কী এনক্রিপ্ট) — **হারালে সব পেজ আবার কানেক্ট করতে হবে** | `make_secrets.py` |
| ADMIN_USERNAME | আপনার অ্যাডমিন ইউজারনেম | নিজে ঠিক করুন |
| ADMIN_PASSWORD_HASH | অ্যাডমিন পাসওয়ার্ডের argon2 হ্যাশ | `make_secrets.py` |
| CRON_SECRET | cron URL-এর গোপন শব্দ | `make_secrets.py` |
| DEFAULT_GEMINI_KEY, DEFAULT_GROQ_KEY (ঐচ্ছিক) | আপনার ডিফল্ট AI কী (ইউজারদের জন্য, দৈনিক লিমিটসহ) | aistudio.google.com, console.groq.com |
| DEFAULT_MISTRAL_KEY / _CEREBRAS_KEY / _OPENROUTER_KEY (ঐচ্ছিক) | অতিরিক্ত ডিফল্ট কী | সংশ্লিষ্ট সাইট |
| TZ_OFFSET_HOURS (ঐচ্ছিক) | সময় অঞ্চল, ডিফল্ট 6 (বাংলাদেশ) | — |

**গোপন কী বানানো:** Termux/কম্পিউটারে: `pip install cryptography argon2-cffi` তারপর `python tools/make_secrets.py` — যা দেখাবে Render-এ বসান। এগুলো কাউকে দেখাবেন না, GitHub-এ দেবেন না।

## ৪. Firebase সেটআপ
1. console.firebase.google.com > Add project > Build > **Firestore Database** > Create (Production mode)।
2. Firestore > **Rules** ট্যাব > সব মুছে `firestore.rules`-এর লেখা paste > **Publish**। (এতে ব্রাউজার থেকে সরাসরি ডেটা পড়া সম্পূর্ণ বন্ধ; শুধু আপনার সার্ভার Admin SDK দিয়ে পারে। ইউজারদের ডেটা আলাদা রাখা হয় সার্ভারের কোডে — প্রতিটি endpoint-এ ownerUid যাচাই।)
3. **Indexes:** প্রথমবার ড্যাশবোর্ডে ইনবক্স/কমেন্ট/রিপোর্ট খুললে Render Logs-এ “requires an index” লিংক আসতে পারে — লিংকে ক্লিক করে Create দিন। অথবা Firestore > Indexes > Composite-এ `firestore.indexes.json`-এর ৫টি ইনডেক্স হাতে বানান (collection, দুই ফিল্ড, ordering)। তৈরি হতে ২-৫ মিনিট লাগে।
4. Service accounts থেকে JSON নামিয়ে পুরো লেখাটি `FIREBASE_SERVICE_ACCOUNT_JSON`-এ paste।

## ৫. GitHub ও Render
1. GitHub > New repository (Private)। এই প্রজেক্টের সব ফাইল/ফোল্ডার আপলোড করুন (Add file > Upload files; ফোল্ডার সহ drag করুন)।
2. render.com > New > **Web Service** > GitHub রিপো সিলেক্ট। Runtime: Python 3; Build: `pip install -r requirements.txt`; Start: `gunicorn app:app --workers 1 --threads 16 --timeout 120 --bind 0.0.0.0:$PORT`; Plan: Free। (render.yaml থাকলে Blueprint দিয়েও হয়।) Environment ট্যাবে `PYTHON_VERSION = 3.11.9` যোগ করুন।
3. উপরের টেবিলের সব env বসিয়ে Deploy। URL পেলে `APP_BASE_URL`-এ বসিয়ে Save।
4. পরীক্ষা: `https://আপনার-url/health` খুললে `ok` দেখাবে।

## ৬. Facebook অ্যাপ সেটআপ
developers.facebook.com > Create App (Business type) > Add products: **Facebook Login for Business/Facebook Login** ও **Messenger**।
- Settings > Basic: Privacy Policy URL = `APP_BASE_URL/privacy`; Terms = `/terms`; **Data Deletion Callback URL** = `APP_BASE_URL/fb/data-deletion`; App Domains = আপনার ডোমেইন।
- Facebook Login > Settings: **Valid OAuth Redirect URIs** = `APP_BASE_URL/auth/facebook/callback`।
- Webhooks > **Page** object: Callback URL = `APP_BASE_URL/webhook`, Verify Token = আপনার `FB_VERIFY_TOKEN`; fields subscribe করুন: `messages`, `messaging_postbacks`, `feed`।
- Deauthorize Callback URL = `APP_BASE_URL/fb/deauthorize`।
- App Mode: শুরুতে Development (শুধু আপনি ও যোগ করা Tester/Admin ব্যবহার করতে পারবেন)। অন্য মানুষের পেজের জন্য **App Review + Business Verification** লাগবে।
- রিভিউয়ে যে পারমিশন চাইবেন ও স্ক্রিনকাস্টে কী দেখাবেন:
  - `pages_show_list` — ফেসবুক লগইন করে পেজের তালিকা থেকে পেজ বাছাই।
  - `pages_messaging` — কাস্টমার মেসেঞ্জারে লিখছে → AI উত্তর দিচ্ছে → ড্যাশবোর্ড ইনবক্সে দেখা যাচ্ছে।
  - `pages_manage_metadata` — পেজ কানেক্ট করার সময় অটো ওয়েবহুক সাবস্ক্রিপশন।
  - `pages_read_engagement` — কমেন্ট/পোস্টের লেখা পড়ে উত্তর তৈরি।
  - `pages_manage_engagement` — পেজ পোস্টে কমেন্টের AI রিপ্লাই ও গালি লুকানো/মোছা।
  - `pages_manage_posts` — “বট কমান্ড” বক্সে লিখে (ছবিসহ) পেজে পোস্ট।
  প্রতিটির ভিডিওতে: লগইন → পারমিশন দেওয়ার স্ক্রিন → ফিচার ব্যবহার → ড্যাশবোর্ডে ফলাফল; ইংরেজিতে ছোট ক্যাপশন দিন।
- ⚠️ Graph API ভার্সন (`config.py`-এ `GRAPH_VER`), পারমিশনের নাম ও রিভিউ নিয়ম Meta বদলাতে পারে — developers.facebook.com/docs থেকে যাচাই করে নিন। Firebase ফ্রি-লিমিটও যাচাই করুন। AI মডেলের নামও (`ai.py`-র DEF) প্রোভাইডাররা বদলায়; কাজ না করলে ড্যাশবোর্ডের “AI কী” ট্যাবে মডেল নাম লিখে দিন।

## ৭. cron-job.org
- Job ১: `APP_BASE_URL/health` — প্রতি ৫ মিনিট (Render ঘুমানো ঠেকায়)।
- Job ২: `APP_BASE_URL/cron/daily-report?secret=CRON_SECRET` — প্রতিদিন রাত ১১:৫৫ (আপনার সময়)।
- Job ৩: `APP_BASE_URL/cron/cleanup?secret=CRON_SECRET` — সপ্তাহে একবার (পুরনো ডেটা মোছে; ডিফল্ট ৩০ দিন, অ্যাডমিন থেকে বদলানো যায়)।

## ৮. টেস্ট চেকলিস্ট
1. `/health` → ok। 2. `/admin/login` → master prompt দেখা যায়, সেভ হয়। 3. হোমে “Facebook দিয়ে লগইন” → পারমিশন → ইউজারনেম/পাসওয়ার্ড লিখে রাখুন → পেজ বাছুন → ড্যাশবোর্ড। 4. “নির্দেশনা”য় লিখুন ও সেভ; AI কী ট্যাবে নিজের কী দিন (বা আপনার ডিফল্ট কী)। 5. অন্য অ্যাকাউন্ট থেকে পেজে মেসেজ দিন → উত্তর আসে, ইনবক্সে দেখা যায়। 6. “নিজে হাতে নিন” চাপলে AI থামে; ড্যাশবোর্ড থেকে উত্তর যায়। 7. কমেন্ট চালু করে পোস্টে কমেন্ট করুন। 8. কমান্ড বক্সে ছবিসহ পোস্ট। 9. লিংক সোর্সে Google Sheet (Anyone with link → Viewer) দিয়ে “লিংক রিফ্রেশ”। 10. ভয়েস মেসেজ পাঠান (Gemini কী লাগবে)। 11. cron URL ব্রাউজারে খুলে রিপোর্ট দেখুন।
**Render Logs-এ** কোনো “MISSING ENV VARS” লাইন এলে সেই ভ্যারিয়েবল বসান।

## ৯. নিরাপত্তা ও সীমাবদ্ধতা (সৎ কথা)
- টোকেন/কী এনক্রিপ্টেড; পাসওয়ার্ড argon2; CSRF, secure কুকি, rate limit, ওয়েবহুক সিগনেচার, SSRF ব্লক (প্রাইভেট IP/অ-http)।
- সীমাবদ্ধতা: rate limit ও ডুপ্লিকেট-চেক মেমরিতে (রিস্টার্টে রিসেট; একটাই worker চলে)। DNS-rebinding-এর মতো অতি উন্নত SSRF পুরোপুরি ঠেকানো হয়নি। AI ভুল করতে পারে — ইনবক্স দেখুন।
- ভবিষ্যতে করা যায়: আউটগোয়িং ভয়েস (text-to-speech) — এখন নেই।
