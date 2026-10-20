# Run on your phone/PC:  pip install cryptography argon2-cffi  &&  python make_secrets.py
import secrets, getpass
from cryptography.fernet import Fernet
from argon2 import PasswordHasher
print('ENCRYPTION_KEY =', Fernet.generate_key().decode())
print('SESSION_SECRET =', secrets.token_urlsafe(48))
print('CRON_SECRET    =', secrets.token_urlsafe(24))
print('FB_VERIFY_TOKEN=', secrets.token_urlsafe(16))
pw = getpass.getpass('Choose ADMIN password: ')
print('ADMIN_PASSWORD_HASH =', PasswordHasher().hash(pw))
