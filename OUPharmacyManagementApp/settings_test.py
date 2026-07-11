"""
Test settings — SQLite in-memory/file to avoid PostgreSQL template collation issues locally.

Usage:
  python manage.py test storeApp.tests -v 2 --settings=OUPharmacyManagementApp.settings_test

CI: `.github/workflows/test-storeapp.yml` (GitHub Actions, Python 3.10).
"""
import os

# Safe defaults for local/CI when .env is absent (must run before importing production settings).
os.environ.setdefault("SECRET_KEY", "django-insecure-storeapp-tests-only")
os.environ.setdefault("FIREBASE_SKIP_INIT", "1")
os.environ.setdefault("OAUTH2_CLIENT_ID", "test-oauth-client-id")
os.environ.setdefault("OAUTH2_CLIENT_SECRET", "test-oauth-client-secret")
os.environ.setdefault("CLOUDINARY_NAME", "test")
os.environ.setdefault("CLOUDINARY_API_KEY", "test")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test")

from pathlib import Path

from OUPharmacyManagementApp.settings import *  # noqa: F401,F403

_BASE = Path(__file__).resolve().parent.parent
_TEST_DIR = _BASE / ".test_databases"
_TEST_DIR.mkdir(exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(_TEST_DIR / "default.sqlite3"),
        "TEST": {"NAME": str(_TEST_DIR / "default_test.sqlite3")},
    },
    "store": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(_TEST_DIR / "store.sqlite3"),
        "TEST": {"NAME": str(_TEST_DIR / "store_test.sqlite3")},
    },
}

# Faster tests — no password hashing cost
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
