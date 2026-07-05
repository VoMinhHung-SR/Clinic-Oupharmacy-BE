"""
Test settings — SQLite in-memory/file to avoid PostgreSQL template collation issues locally.

Usage:
  python manage.py test storeApp.tests.test_category_m2m_api -v 2 --settings=OUPharmacyManagementApp.settings_test
"""
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
