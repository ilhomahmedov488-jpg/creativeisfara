import os

os.environ['TESTING'] = 'true'
os.environ.setdefault('SECRET_KEY', 'only-for-tests-' + 'x' * 60)
os.environ['DEBUG'] = 'true'
os.environ['SMS_BACKEND'] = 'memory'
from .settings import *  # noqa: F403, E402

ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
