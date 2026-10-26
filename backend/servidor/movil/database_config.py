"""Valida la conexión independiente sin abrir conexiones ni leer secretos."""
from urllib.parse import unquote, urlsplit


def _identidad_base(partes):
    host = (partes.hostname or "").lower().rstrip(".")
    # Neon expone el mismo endpoint con conexión directa o mediante pooler.
    # Diferentes usuarios, parámetros SSL o passwords no cambian la base.
    if host.endswith(".neon.tech"):
        etiqueta, resto = host.split(".", 1)
        host = etiqueta.removesuffix("-pooler") + "." + resto
    return host, partes.port or 5432, unquote(partes.path.lstrip("/"))


def configuracion_neon_movil(url_movil, url_original=""):
    if not url_movil:
        return None
    partes = urlsplit(url_movil)
    if partes.scheme not in ("postgresql", "postgres") or not partes.hostname or not partes.path.lstrip("/"):
        raise ValueError("NEON_MOBILE_DATABASE_URL debe ser una conexión PostgreSQL válida")
    if url_original and _identidad_base(partes) == _identidad_base(urlsplit(url_original)):
        raise ValueError("La aplicación móvil requiere una base distinta a la del sistema original")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(partes.path.lstrip("/")),
        "USER": unquote(partes.username or ""),
        "PASSWORD": unquote(partes.password or ""),
        "HOST": partes.hostname,
        "PORT": partes.port or 5432,
        # Evita esperar indefinidamente si Neon no acepta la conexión.
        "OPTIONS": {"sslmode": "require", "connect_timeout": 8},
        "CONN_MAX_AGE": 0,
    }
