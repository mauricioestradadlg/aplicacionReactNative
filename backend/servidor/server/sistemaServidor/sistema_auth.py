"""
Autenticación privada de Proyectos MEG:
POST /api/sistema/login/
POST /api/sistema/verificar/
GET  /api/sistema/yo/
POST /api/sistema/salir/

Requiere NEON_DATABASE_URL, RESEND_API_KEY y RESEND_SENDER_EMAIL.
Almacenamiento en PostgreSQL/Neon. Autenticación por cookie segura y CSRF.
"""
import hashlib
import hmac
import json
import logging
import re
import secrets
from datetime import timedelta
from html import escape
from uuid import UUID, uuid4

import requests
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import DatabaseError, connections, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from ..resend_service import enviar_correo_resend

logger = logging.getLogger(__name__)

DURACION_CODIGO_MIN = 10
DURACION_SESION_DIAS = 30
NOMBRE_COOKIE_SESION = "meg_sistema_sesion"
RUTA_COOKIE_SESION = "/api/sistema/"
INTENTOS_MAX_CLAVE = 5
INTENTOS_MAX_CODIGO = 5
BLOQUEO_MIN = 15
INTERVALO_ENVIO_SEG = 60
MAX_CODIGOS_POR_HORA = 5
ERROR_CREDENCIALES = "Usuario o contraseña incorrectos, o acceso temporalmente bloqueado."
# Hash de relleno para evitar respuestas instantáneas con usuario inexistente.
HASH_RELLENO = make_password("contraseña de relleno que no pertenece a ningún usuario")


def _secret_key_segura():
    clave = settings.SECRET_KEY
    return bool(clave and len(clave) >= 32 and
                clave != "django-insecure-development-key")


def _respuesta(datos, estado=200):
    respuesta = JsonResponse(datos, status=estado)
    respuesta["Cache-Control"] = "no-store"
    respuesta["Pragma"] = "no-cache"
    return respuesta


def _leer_json(request):
    if not request.content_type or request.content_type.split(";")[0] != "application/json":
        raise ValueError("Envía JSON (Content-Type: application/json).")
    if len(request.body) > 8192:
        raise ValueError("Solicitud demasiado grande.")
    try:
        datos = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("JSON inválido.")
    if not isinstance(datos, dict):
        raise ValueError("Se esperaba un objeto JSON.")
    return datos


def _tiene_neon():
    return "neon" in connections.databases


def _codigo_hash(verificacion_id, codigo):
    """MAC con SECRET_KEY; no permite recuperar códigos si se filtra la tabla."""
    dato = f"sistema-login:{verificacion_id}:{codigo}".encode("utf-8")
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), dato, hashlib.sha256).hexdigest()


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _usuario_publico(registro):
    """registro: (id, nombre_completo, usuario, correo, rol)."""
    return {
        "id": registro[0],
        "nombre_completo": registro[1],
        "usuario": registro[2],
        "correo": registro[3],
        "rol": registro[4],
    }


def _correo_oculto(correo):
    try:
        nombre, dominio = correo.split("@", 1)
        return nombre[:2] + "***@" + dominio
    except ValueError:
        return "***"


def _extraer_token(request):
    """Bearer para apps nativas; cookie HttpOnly para la web, sin mezclar identidades."""
    if "HTTP_AUTHORIZATION" in request.META:
        return _extraer_bearer(request)
    token = request.COOKIES.get(NOMBRE_COOKIE_SESION, "")
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{32,160}", token):
        return None
    return token


def _extraer_bearer(request):
    cabecera = request.META.get("HTTP_AUTHORIZATION", "")
    if not isinstance(cabecera, str):
        return None
    coincidencia = re.fullmatch(r"Bearer ([A-Za-z0-9_\-]{32,160})", cabecera, re.IGNORECASE)
    return coincidencia.group(1) if coincidencia else None


def _establecer_cookie_sesion(respuesta, token):
    respuesta.set_cookie(
        NOMBRE_COOKIE_SESION,
        token,
        max_age=DURACION_SESION_DIAS * 24 * 60 * 60,
        path=RUTA_COOKIE_SESION,
        secure=not settings.DEBUG,
        httponly=True,
        samesite="Lax",
    )
    return respuesta


def _eliminar_cookie_sesion(respuesta):
    respuesta.delete_cookie(
        NOMBRE_COOKIE_SESION,
        path=RUTA_COOKIE_SESION,
        samesite="Lax",
    )
    return respuesta


@ensure_csrf_cookie
def sistema_csrf(request):
    """Emite CSRF utilizable desde el frontend, sin exponer el token de sesión."""
    if request.method != "GET":
        return _respuesta({"ok": False, "mensaje": "Método no permitido."}, 405)
    return _respuesta({"ok": True, "csrfToken": get_token(request)})


def _buscar_usuario_sesion(token):
    if not token:
        return None
    with connections["neon"].cursor() as cursor:
        cursor.execute(
            """
            SELECT u.id, u.nombre_completo, u.usuario, u.correo, u.rol
            FROM public.sesiones_sistema s
            JOIN public.usuarios_sistema u ON u.id = s.usuario_id
            WHERE s.token_hash = %s
              AND s.revocado_en IS NULL
              AND s.expira_en > NOW()
              AND u.activo = TRUE
            LIMIT 1
            """,
            [_token_hash(token)],
        )
        return cursor.fetchone()


@require_POST
def sistema_login(request):
    if not _tiene_neon():
        return _respuesta({"ok": False, "mensaje": "Neon no está configurado."}, 503)
    if not _secret_key_segura():
        logger.error("Configura una SECRET_KEY larga, única y segura en Django.")
        return _respuesta({"ok": False, "mensaje": "Configuración de seguridad incompleta."}, 503)

    try:
        datos = _leer_json(request)
        usuario = datos.get("usuario", "")
        contrasena = datos.get("contrasena", "")
        if not isinstance(usuario, str) or not isinstance(contrasena, str):
            raise ValueError("Completa usuario y contraseña.")
        usuario = usuario.strip().lower()
        if not usuario or not contrasena or len(usuario) > 80 or len(contrasena) > 256:
            raise ValueError("Completa usuario y contraseña.")
    except ValueError as error:
        return _respuesta({"ok": False, "mensaje": str(error)}, 400)

    if not settings.RESEND_API_KEY or not settings.RESEND_SENDER_EMAIL:
        logger.error("Resend sin API KEY o remitente.")
        return _respuesta({"ok": False, "mensaje": "Servicio de correo no disponible."}, 503)

    ahora = timezone.now()
    codigo = f"{secrets.randbelow(1000000):06d}"
    codigo_id = uuid4()

    try:
        with transaction.atomic(using="neon"):
            with connections["neon"].cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, nombre_completo, usuario, correo, contrasena_hash,
                           activo, intentos_fallidos, bloqueado_hasta
                    FROM public.usuarios_sistema
                    WHERE usuario = %s
                    FOR UPDATE
                    """,
                    [usuario],
                )
                fila = cursor.fetchone()

                if not fila:
                    # Evita respuestas más rápidas para usuarios inexistentes.
                    check_password(contrasena, HASH_RELLENO)
                    return _respuesta({"ok": False, "mensaje": ERROR_CREDENCIALES}, 401)

                (id_usuario, nombre_completo, nombre_usuario, correo, password_hash,
                 activo, intentos_fallidos, bloqueado_hasta) = fila

                if not activo or (bloqueado_hasta and bloqueado_hasta > ahora):
                    return _respuesta({"ok": False, "mensaje": ERROR_CREDENCIALES}, 401)

                if not check_password(contrasena, password_hash):
                    intentos = intentos_fallidos + 1
                    bloqueo = ahora + timedelta(minutes=BLOQUEO_MIN) if intentos >= INTENTOS_MAX_CLAVE else None
                    cursor.execute(
                        """
                        UPDATE public.usuarios_sistema
                        SET intentos_fallidos = %s, bloqueado_hasta = %s
                        WHERE id = %s
                        """,
                        [intentos, bloqueo, id_usuario],
                    )
                    # IMPORTANTE: la transacción se confirma al retornar normalmente.
                    return _respuesta({"ok": False, "mensaje": ERROR_CREDENCIALES}, 401)

                # Límite de códigos; no dejar que usen Resend para generar spam.
                cursor.execute(
                    """
                    SELECT COUNT(*), MAX(creado_en)
                    FROM public.codigos_login_sistema
                    WHERE usuario_id = %s AND creado_en > %s
                    """,
                    [id_usuario, ahora - timedelta(hours=1)],
                )
                enviados_en_hora, ultimo_envio = cursor.fetchone()
                if (ultimo_envio and
                    (ahora - ultimo_envio).total_seconds() < INTERVALO_ENVIO_SEG):
                    return _respuesta({
                        "ok": False,
                        "mensaje": "Espera 60 segundos antes de solicitar otro código.",
                    }, 429)
                if enviados_en_hora >= MAX_CODIGOS_POR_HORA:
                    return _respuesta({
                        "ok": False,
                        "mensaje": "Se alcanzó el límite de envíos. Intenta más tarde.",
                    }, 429)

                cursor.execute(
                    """
                    UPDATE public.usuarios_sistema
                    SET intentos_fallidos = 0, bloqueado_hasta = NULL
                    WHERE id = %s
                    """,
                    [id_usuario],
                )
                cursor.execute(
                    """
                    UPDATE public.codigos_login_sistema
                    SET usado_en = NOW()
                    WHERE usuario_id = %s AND usado_en IS NULL
                    """,
                    [id_usuario],
                )
                cursor.execute(
                    """
                    INSERT INTO public.codigos_login_sistema
                        (id, usuario_id, codigo_hash, expira_en)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [
                        str(codigo_id), id_usuario, _codigo_hash(codigo_id, codigo),
                        ahora + timedelta(minutes=DURACION_CODIGO_MIN),
                    ],
                )

    except DatabaseError:
        logger.exception("Neon: fallo al iniciar sesión.")
        return _respuesta({"ok": False, "mensaje": "Servicio temporalmente no disponible."}, 503)

    # Enviar correo SOLO después de confirmar la transacción de Neon.
    nombre_seguro = escape(nombre_completo.split()[0])
    html = f"""
    <div style="font-family:Arial,sans-serif;background:#f3f7fd;padding:32px;color:#13223d">
      <div style="max-width:520px;margin:auto;background:white;border-radius:14px;padding:30px">
        <div style="color:#176cf2;font-size:12px;font-weight:bold;letter-spacing:2px">
          PROYECTOS MEG · SISTEMA INTERNO
        </div>
        <h1 style="font-size:25px;margin:18px 0 8px">Verificación de acceso</h1>
        <p>Hola {nombre_seguro}, usa este código para ingresar al sistema:</p>
        <p style="font-size:36px;letter-spacing:9px;font-weight:bold;
                  color:#176cf2;margin:26px 0">{codigo}</p>
        <p>Este código vence en {DURACION_CODIGO_MIN} minutos.</p>
        <p style="font-size:13px;color:#68768d">
          Si no intentaste iniciar sesión, ignora este mensaje.
          Nunca compartas tu código.
        </p>
      </div>
    </div>
    """

    try:
        enviar_correo_resend(
            destinatario=correo,
            asunto="Tu código de acceso | Proyectos MEG",
            contenido_html=html,
        )
    except (requests.RequestException, ValueError):
        logger.exception("Resend: error enviando código de acceso.")
        try:
            with connections["neon"].cursor() as cursor:
                cursor.execute(
                    "UPDATE public.codigos_login_sistema SET usado_en = NOW() WHERE id = %s",
                    [str(codigo_id)],
                )
        except DatabaseError:
            logger.exception("No se pudo invalidar código tras fallo de Resend.")
        return _respuesta({
            "ok": False,
            "mensaje": "No fue posible enviar el código. Intenta más tarde.",
        }, 502)

    return _respuesta({
        "ok": True,
        "verificacion_id": str(codigo_id),
        "correo_oculto": _correo_oculto(correo),
        "mensaje": "Código enviado. Revisa tu correo.",
    })


@require_POST
def sistema_verificar(request):
    return _verificar_codigo(request)


@require_POST
def sistema_movil_login(request):
    """Reutiliza contraseña, bloqueo, envío y límites del acceso web."""
    return sistema_login(request)


@require_POST
def sistema_movil_verificar(request):
    """Entrega una credencial nativa únicamente después del segundo factor."""
    return _verificar_codigo(request, entregar_token=True)


def _verificar_codigo(request, entregar_token=False):
    if not _tiene_neon():
        return _respuesta({"ok": False, "mensaje": "Neon no está configurado."}, 503)

    try:
        datos = _leer_json(request)
        verificacion_id = str(UUID(str(datos.get("verificacion_id", ""))))
        codigo = datos.get("codigo", "")
        if not isinstance(codigo, str) or not re.fullmatch(r"\d{6}", codigo):
            raise ValueError("Ingresa los seis dígitos del código.")
    except (ValueError, TypeError, AttributeError):
        return _respuesta({"ok": False, "mensaje": "Código o identificador inválido."}, 400)

    try:
        with transaction.atomic(using="neon"):
            with connections["neon"].cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.usuario_id, c.codigo_hash, c.expira_en,
                           c.intentos, c.usado_en, u.activo
                    FROM public.codigos_login_sistema c
                    JOIN public.usuarios_sistema u ON u.id = c.usuario_id
                    WHERE c.id = %s
                    FOR UPDATE OF c
                    """,
                    [verificacion_id],
                )
                fila = cursor.fetchone()
                if not fila:
                    return _respuesta({"ok": False, "mensaje": "Código inválido o vencido."}, 401)

                usuario_id, hash_guardado, expira, intentos, usado, activo = fila
                if not activo or usado or expira <= timezone.now() or intentos >= INTENTOS_MAX_CODIGO:
                    return _respuesta({"ok": False, "mensaje": "Código inválido o vencido."}, 401)

                valido = hmac.compare_digest(
                    str(hash_guardado).strip(),
                    _codigo_hash(verificacion_id, codigo),
                )
                if not valido:
                    cursor.execute(
                        """
                        UPDATE public.codigos_login_sistema
                        SET intentos = intentos + 1,
                            usado_en = CASE WHEN intentos + 1 >= %s
                                            THEN NOW() ELSE usado_en END
                        WHERE id = %s
                        """,
                        [INTENTOS_MAX_CODIGO, verificacion_id],
                    )
                    return _respuesta({"ok": False, "mensaje": "Código incorrecto o vencido."}, 401)

                cursor.execute(
                    "UPDATE public.codigos_login_sistema SET usado_en = NOW() WHERE id = %s",
                    [verificacion_id],
                )
                token = secrets.token_urlsafe(48)
                caduca = timezone.now() + timedelta(days=DURACION_SESION_DIAS)
                cursor.execute(
                    """
                    INSERT INTO public.sesiones_sistema
                        (id, usuario_id, token_hash, expira_en)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [str(uuid4()), usuario_id, _token_hash(token), caduca],
                )
                cursor.execute(
                    """
                    UPDATE public.usuarios_sistema SET ultimo_acceso = NOW()
                    WHERE id = %s
                    """,
                    [usuario_id],
                )
    except DatabaseError:
        logger.exception("Neon: fallo confirmando verificación.")
        return _respuesta({"ok": False, "mensaje": "Servicio temporalmente no disponible."}, 503)

    if entregar_token:
        return _respuesta({
            "ok": True,
            "token": token,
            "expira_en": caduca.isoformat(),
            "mensaje": "Verificación completada. Sesión móvil iniciada.",
        })

    respuesta = _respuesta({
        "ok": True,
        "expira_en": caduca.isoformat(),
        "mensaje": "Verificación completada. Este navegador permanecerá conectado durante 30 días.",
    })
    return _establecer_cookie_sesion(respuesta, token)


@require_GET
def sistema_yo(request):
    if not _tiene_neon():
        return _respuesta({"ok": False, "mensaje": "Neon no está configurado."}, 503)

    token = _extraer_token(request)
    if not token:
        return _respuesta({"ok": False, "mensaje": "No autorizado."}, 401)

    try:
        usuario = _buscar_usuario_sesion(token)
    except DatabaseError:
        logger.exception("Neon: fallo consultando sesión.")
        return _respuesta({"ok": False, "mensaje": "Servicio temporalmente no disponible."}, 503)

    if not usuario:
        return _respuesta({"ok": False, "mensaje": "Sesión inválida o caducada."}, 401)
    return _respuesta({"ok": True, "usuario": _usuario_publico(usuario)})


@require_POST
def sistema_salir(request):
    if not _tiene_neon():
        return _respuesta({"ok": False, "mensaje": "Neon no está configurado."}, 503)

    token = _extraer_token(request)
    if not token:
        return _eliminar_cookie_sesion(_respuesta({"ok": True, "mensaje": "Sesión cerrada."}))

    try:
        with connections["neon"].cursor() as cursor:
            cursor.execute(
                """
                UPDATE public.sesiones_sistema
                SET revocado_en = NOW()
                WHERE token_hash = %s AND revocado_en IS NULL
                """,
                [_token_hash(token)],
            )
    except DatabaseError:
        logger.exception("Neon: fallo cerrando sesión.")
        return _respuesta({"ok": False, "mensaje": "No se pudo cerrar la sesión."}, 503)

    return _eliminar_cookie_sesion(_respuesta({"ok": True, "mensaje": "Sesión cerrada."}))
