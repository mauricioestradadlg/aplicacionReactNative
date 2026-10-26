"""Pruebas de la base móvil sin leer .env ni conectarse a Neon."""
from .test_settings import *  # noqa: F403

DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
    "movil": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
}
DATABASE_ROUTERS = ["movil.router.MovilRouter"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
