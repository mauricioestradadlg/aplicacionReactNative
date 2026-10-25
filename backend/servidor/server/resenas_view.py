"""Reseñas públicas con confirmación por correo previa a moderación.

POST /api/resenas/           registra reseña pendiente y manda OTP por Resend.
POST /api/resenas/verificar/ confirma OTP (NO publica automáticamente).
GET  /api/resenas/publicas/  testimonios ya aprobados.

Una coincidencia en public.clientes NO prueba control del correo.
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
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import DatabaseError, connections, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .resend_service import enviar_correo_resend

logger = logging.getLogger(__name__)
SERVICIOS_RESEÑA = {'landing-page', 'sitio-web', 'diseno-web', 'otro'}


def _respuesta(datos, estado=200):
    resp = JsonResponse(datos, status=estado)
    resp['Cache-Control'] = 'no-store'
    return resp


def _texto(datos, campo, maximo, obligatorio=False):
    valor = datos.get(campo, '')
    if valor is None:
        valor = ''
    if not isinstance(valor, str):
        raise ValueError(f'El campo {campo} debe ser texto.')
    valor = valor.strip()
    if len(valor) > maximo or (obligatorio and not valor):
        raise ValueError(f'Revisa el campo {campo} (máximo {maximo} caracteres).')
    return valor


def _json(request):
    if request.content_type.split(';', 1)[0].lower() != 'application/json':
        raise ValueError('Envía datos JSON.')
    if len(request.body) > 16384:
        raise ValueError('Solicitud demasiado grande.')
    datos = json.loads(request.body.decode('utf-8'))
    if not isinstance(datos, dict):
        raise ValueError('Formato JSON inválido.')
    return datos


def _hash_codigo(identificador, codigo):
    raw = f'resena:email:{identificador}:{codigo}'.encode('utf-8')
    return hmac.new(settings.SECRET_KEY.encode('utf-8'), raw, hashlib.sha256).hexdigest()


def _ocultar_correo(correo):
    nombre, dominio = correo.split('@', 1)
    return f'{nombre[:2]}***@{dominio}'


@csrf_exempt  # Usa peticiones JSON sin cookies de autenticación. Rate limit: SeguridadAPIMiddleware.
@require_POST
def registrar_resena(request):
    if 'neon' not in connections.databases or not settings.RESEND_API_KEY or not settings.RESEND_SENDER_EMAIL:
        return _respuesta({'ok': False, 'mensaje': 'Servicio temporalmente no disponible.'}, 503)
    if len(settings.SECRET_KEY) < 32:
        return _respuesta({'ok': False, 'mensaje': 'Configuración de seguridad incompleta.'}, 503)

    try:
        datos = _json(request)
        nombre = _texto(datos, 'nombre', 70, True)
        negocio = _texto(datos, 'negocio', 80)
        correo = _texto(datos, 'correo', 120, True).lower()
        servicio = _texto(datos, 'servicio', 30, True)
        titulo = _texto(datos, 'titulo', 100)
        comentario = _texto(datos, 'comentario', 700, True)
        calificacion = datos.get('calificacion')
        validate_email(correo)
        if servicio not in SERVICIOS_RESEÑA:
            raise ValueError('Servicio inválido.')
        if type(calificacion) is not int or not 1 <= calificacion <= 5:
            raise ValueError('Calificación inválida.')
        if len(comentario) < 25:
            raise ValueError('Escribe al menos 25 caracteres.')
        if datos.get('autoriza_publicacion') is not True:
            raise ValueError('Debes aceptar la autorización de publicación.')
    except ValidationError:
        return _respuesta({'ok': False, 'mensaje': 'Correo inválido.'}, 400)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)

    id_codigo = uuid4()
    codigo = f'{secrets.randbelow(1000000):06d}'
    nuevo_id = None

    try:
        with transaction.atomic(using='neon'):
            with connections['neon'].cursor() as cursor:
                cursor.execute('''
                    SELECT id, servicio_contratado
                    FROM public.clientes WHERE correo = %s LIMIT 1
                ''', [correo])
                cliente = cursor.fetchone()
                if not cliente or cliente[1] != servicio:
                    return _respuesta({
                        'ok': False,
                        'mensaje': 'No pudimos confirmar tu contratación. Revisa los datos o contáctanos.',
                    }, 403)
                cursor.execute('''
                    INSERT INTO public.resenas_clientes
                    (cliente_id, nombre, negocio, correo, servicio, calificacion, titulo,
                     comentario, autoriza_publicacion, estado, verificada, correo_verificado)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, 'pendiente', FALSE, FALSE)
                    RETURNING id
                ''', [cliente[0], nombre, negocio or None, correo, servicio,
                      calificacion, titulo or None, comentario])
                nuevo_id = cursor.fetchone()[0]
                cursor.execute('''
                    INSERT INTO public.verificaciones_resenas
                        (id, resena_id, codigo_hash, expira_en)
                    VALUES (%s, %s, %s, %s)
                ''', [str(id_codigo), str(nuevo_id), _hash_codigo(id_codigo, codigo),
                      timezone.now() + timedelta(minutes=10)])
    except DatabaseError:
        logger.exception('Error creando reseña y su código en Neon.')
        return _respuesta({'ok': False, 'mensaje': 'No pudimos registrar la reseña.'}, 503)

    html = f'''<div style="font-family:Arial,sans-serif;padding:24px;color:#102038">
       <h2>Confirma tu reseña | Proyectos MEG</h2>
       <p>Hola {escape(nombre)}, tu código para confirmar el correo es:</p>
       <p style="font-size:34px;font-weight:bold;letter-spacing:6px">{codigo}</p>
       <p>Caduca en 10 minutos. No compartas este código.</p>
       <p>Confirmarlo no publica automáticamente tu comentario. El equipo lo revisará.</p>
       <p>Si no solicitaste esto, ignora este mensaje.</p></div>'''
    try:
        enviar_correo_resend(destinatario=correo,
                             asunto='Confirma tu reseña | Proyectos MEG',
                             contenido_html=html)
    except (requests.RequestException, ValueError):
        logger.exception('Falló Resend al confirmar autoría de reseña.')
        # Limpiar solamente la nueva reseña aún no confirmada; permite reintentar.
        if nuevo_id is not None:
            try:
                with connections['neon'].cursor() as cursor:
                    cursor.execute('''DELETE FROM public.resenas_clientes
                        WHERE id = %s AND estado = 'pendiente' AND correo_verificado = FALSE''',
                        [str(nuevo_id)])
            except DatabaseError:
                logger.exception('Fallo eliminando reseña pendiente sin correo enviado.')
        return _respuesta({'ok': False, 'mensaje': 'No fue posible enviar el código. Intenta más tarde.'}, 502)

    return _respuesta({
        'ok': True,
        'mensaje': 'Revisa tu correo e ingresa el código para confirmar la reseña.',
        'verificacion_id': str(id_codigo),
        'correo_oculto': _ocultar_correo(correo),
        'estado': 'pendiente_confirmacion',
    }, 201)


@csrf_exempt
@require_POST
def verificar_correo_resena(request):
    if 'neon' not in connections.databases or len(settings.SECRET_KEY) < 32:
        return _respuesta({'ok': False, 'mensaje': 'Servicio temporalmente no disponible.'}, 503)
    try:
        datos = _json(request)
        codigo_id = str(UUID(str(datos.get('verificacion_id', ''))))
        codigo = datos.get('codigo')
        if not isinstance(codigo, str) or not re.fullmatch(r'\d{6}', codigo):
            raise ValueError('Código inválido.')
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return _respuesta({'ok': False, 'mensaje': 'Código o identificador inválido.'}, 400)

    try:
        with transaction.atomic(using='neon'):
            with connections['neon'].cursor() as cursor:
                cursor.execute('''
                    SELECT v.resena_id, v.codigo_hash, v.expira_en, v.intentos,
                           v.consumido_en, r.estado, r.correo_verificado
                    FROM public.verificaciones_resenas v
                    JOIN public.resenas_clientes r ON r.id = v.resena_id
                    WHERE v.id = %s
                    FOR UPDATE OF v
                ''', [codigo_id])
                fila = cursor.fetchone()
                if not fila:
                    return _respuesta({'ok': False, 'mensaje': 'Código inválido o vencido.'}, 401)
                resena_id, hash_guardado, expira, intentos, usado, estado, confirmado = fila
                if usado or expira <= timezone.now() or intentos >= 5 or estado != 'pendiente' or confirmado:
                    return _respuesta({'ok': False, 'mensaje': 'Código inválido o vencido.'}, 401)
                if not hmac.compare_digest(str(hash_guardado).strip(), _hash_codigo(codigo_id, codigo)):
                    cursor.execute('''
                        UPDATE public.verificaciones_resenas SET intentos = intentos + 1,
                        consumido_en = CASE WHEN intentos + 1 >= 5 THEN NOW() ELSE consumido_en END
                        WHERE id = %s
                    ''', [codigo_id])
                    return _respuesta({'ok': False, 'mensaje': 'Código incorrecto o vencido.'}, 401)
                cursor.execute('''
                    UPDATE public.verificaciones_resenas SET consumido_en = NOW()
                    WHERE id = %s
                ''', [codigo_id])
                cursor.execute('''
                    UPDATE public.resenas_clientes
                    SET correo_verificado = TRUE, fecha_confirmacion_correo = NOW()
                    WHERE id = %s AND estado = 'pendiente'
                ''', [str(resena_id)])
    except DatabaseError:
        logger.exception('Error confirmando correo de reseña en Neon.')
        return _respuesta({'ok': False, 'mensaje': 'No pudimos verificar el código.'}, 503)

    return _respuesta({
        'ok': True,
        'mensaje': 'Correo confirmado. Tu reseña está pendiente de revisión.',
        'estado': 'pendiente',
    })


@require_GET
def listar_resenas_publicas(request):
    if 'neon' not in connections.databases:
        return _respuesta({'ok': False, 'mensaje': 'Reseñas temporalmente no disponibles.'}, 503)
    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('''SELECT id, nombre, calificacion, comentario,
                                     fecha_publicacion, negocio, fecha_resena
                              FROM public.resenas_publicas
                              ORDER BY fecha_publicacion DESC LIMIT 60''')
            filas = cursor.fetchall()
    except DatabaseError:
        logger.exception('Error consultando reseñas públicas.')
        return _respuesta({'ok': False, 'mensaje': 'No pudimos consultar reseñas.'}, 503)
    resenas = [{
        'id': str(f[0]), 'nombre': f[1], 'calificacion': f[2], 'comentario': f[3],
        'fecha_publicacion': f[4].isoformat() if f[4] else None,
        'negocio': f[5] or None,
        'fecha_resena': f[6].isoformat() if f[6] else None,
    } for f in filas]
    return _respuesta({'ok': True, 'resenas': resenas, 'total': len(resenas)})