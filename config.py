import os, time
GRAPH_VER = 'v23.0'  # keep in ONE place; verify latest stable version in Meta docs
GRAPH = f'https://graph.facebook.com/{GRAPH_VER}'
def env(k, d=''): return os.getenv(k, d).strip()
FB_APP_ID, FB_APP_SECRET, FB_VERIFY_TOKEN = env('FB_APP_ID'), env('FB_APP_SECRET'), env('FB_VERIFY_TOKEN')
BASE = env('APP_BASE_URL').rstrip('/')
SESSION_SECRET, ENCRYPTION_KEY, CRON_SECRET = env('SESSION_SECRET'), env('ENCRYPTION_KEY'), env('CRON_SECRET')
ADMIN_USERNAME, ADMIN_PASSWORD_HASH = env('ADMIN_USERNAME'), env('ADMIN_PASSWORD_HASH')
TZ_OFFSET = int(env('TZ_OFFSET_HOURS', '6'))  # Bangladesh = +6
SCOPES = ['public_profile', 'pages_show_list', 'pages_messaging', 'pages_manage_metadata',
          'pages_read_engagement', 'pages_manage_engagement', 'pages_manage_posts']
SUB_FIELDS = 'messages,messaging_postbacks,feed'
DEFAULT_KEYS = {'gemini': env('DEFAULT_GEMINI_KEY'), 'groq': env('DEFAULT_GROQ_KEY'), 'mistral': env('DEFAULT_MISTRAL_KEY'),
                'cerebras': env('DEFAULT_CEREBRAS_KEY'), 'openrouter': env('DEFAULT_OPENROUTER_KEY')}
OWNED = ('pages', 'conversations', 'comments', 'reports', 'usage', 'link_cache')
def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)
def today(ts=None): return time.strftime('%Y-%m-%d', time.gmtime((ts or time.time()) + TZ_OFFSET * 3600))
def missing():
    need = ['FIREBASE_SERVICE_ACCOUNT_JSON', 'FB_APP_ID', 'FB_APP_SECRET', 'FB_VERIFY_TOKEN', 'APP_BASE_URL', 'SESSION_SECRET', 'ENCRYPTION_KEY', 'ADMIN_USERNAME', 'ADMIN_PASSWORD_HASH', 'CRON_SECRET']
    return [k for k in need if not env(k)]
