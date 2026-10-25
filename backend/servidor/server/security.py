"""Controles transversales para la API de Proyectos MEG.

Rate limit en PostgreSQL (Neon), compartido entre procesos/instancias.
NO confiar en X-Forwarded-For a menos que un proxy verificado lo establezca.
No almacenar direcciones IP, usuarios o correos en texto plano en la tabla de límites.
"""
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db import DatabaseError, connections, transaction
from django.http import JsonResponse

logger = logging.getLogger(__name__)

# (máximo de solicitudes, tamaño de ventana en segundos)
LIMITES = {
    'contacto': (5, 3600),
    'lead': (5, 3600),
    'resena': (4, 3600),
    'confirmar_resena': (12, 900),
    'login': (12, 900),
    'verificar_login': (20, 900),
    'admin_decision': (40, 600),
    'resenas_publicas': (120, 60),
    'admin_listado': (100, 60),
}


def _tipo_endpoint(ruta):
    ruta = ruta.rstrip('/') + '/'
    fijos = {
        '/api/contacto/': 'contacto',
        '/api/lead-magnet/': 'lead',
        '/api/resenas/': 'resena',
        '/api/resenas/verificar/': 'confirmar_resena',
        '/api/sistema/login/': 'login',
        '/api/sistema/verificar/': 'verificar_login',
        '/api/sistema/movil/login/': 'login',
        '/api/sistema/movil/verificar/': 'verificar_login',
    }
    if ruta in fijos:
        return fijos[ruta]
    if re.fullmatch(r'/api/sistema/resenas/[0-9a-fA-F-]{36}/decision/', ruta):
        return 'admin_decision'
    return None


def _tipo_get(ruta):
    ruta = ruta.rstrip('/') + '/'
    return {
        '/api/resenas/publicas/': 'resenas_publicas',
        '/api/sistema/resenas/': 'admin_listado',
    }.get(ruta)


def _ip_cliente(request):
    cabecera = getattr(settings, 'TRUSTED_CLIENT_IP_HEADER', '').strip()
    # Activar SOLO si Render/Cloudflare garantiza que esta cabecera es autenticada.
    raw = request.META.get(cabecera) if cabecera else None
    if not raw:
        raw = request.META.get('REMOTE_ADDR', '')
    # Nunca aceptar una lista de IP enviada por un cliente como fuente confiable.
    try:
        return str(ipaddress.ip_address(raw.strip()))
    except (ValueError, AttributeError):
        return 'desconocida'


def _clave_hash(identificador):
    return hmac.new(settings.SECRET_KEY.encode('utf-8'),
                    identificador.encode('utf-8'), hashlib.sha256).hexdigest()


def _incrementar(cursor, identificador, ventana_seg):
    segundo = int(time.time())
    inicio = segundo - segundo % ventana_seg
    inicio_dt = datetime.fromtimestamp(inicio, tz=timezone.utc)
    vence = inicio_dt + timedelta(seconds=ventana_seg + 120)
    cursor.execute('''
        INSERT INTO public.limites_api (clave_hash, ventana_inicio, cantidad, expira_en)
        VALUES (%s, %s, 1, %s)
        ON CONFLICT (clave_hash, ventana_inicio)
        DO UPDATE SET cantidad = public.limites_api.cantidad + 1
        RETURNING cantidad
    ''', [_clave_hash(identificador), inicio_dt, vence])
    return cursor.fetchone()[0]


def _identidad_adicional(tipo, cuerpo):
    if tipo not in ('login', 'resena', 'confirmar_resena', 'verificar_login'):
        return None
    try:
        datos = json.loads(cuerpo.decode('utf-8'))
        if not isinstance(datos, dict):
            return None
        campo = {
            'login': 'usuario',
            'resena': 'correo',
            'confirmar_resena': 'verificacion_id',
            'verificar_login': 'verificacion_id',
        }[tipo]
        valor = datos.get(campo, '')
        if not isinstance(valor, str) or not 1 <= len(valor.strip()) <= 254:
            return None
        return valor.strip().lower()
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None


def _aplicar_limites(tipo, ip, identidad):
    maximo, ventana = LIMITES[tipo]
    # Limitar por IP Y por identidad cuando corresponda; protege ataques distribuidos.
    # Ambas comprobaciones se realizan en una transacción para no contabilizar parcialmente.
    with transaction.atomic(using='neon'):
        with connections['neon'].cursor() as cursor:
            total = _incrementar(cursor, f'{tipo}:ip:{ip}', ventana)
            excedido = total > maximo
            if identidad:
                maximo_identidad = {
                    'login': 18,
                    'resena': 3,
                    'confirmar_resena': 8,
                    'verificar_login': 10,
                }.get(tipo, maximo)
                acumulado = _incrementar(cursor, f'{tipo}:id:{identidad}', ventana)
                excedido = excedido or acumulado > maximo_identidad
    return excedido, ventana


class SeguridadAPIMiddleware:
    """Opera antes de las vistas; limita POST sensibles y GET de reseñas."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tipo = (_tipo_endpoint(request.path) if request.method == 'POST'
                else _tipo_get(request.path) if request.method == 'GET' else None)
        if tipo is None or not getattr(settings, 'SECURITY_RATE_LIMIT_ENABLED', True):
            return self.get_response(request)

        respuesta = None
        content_length = request.META.get('CONTENT_LENGTH', '')
        try:
            if content_length and int(content_length) > 16384:
                respuesta = JsonResponse({'ok': False, 'mensaje': 'Solicitud demasiado grande.'}, status=413)
        except (TypeError, ValueError):
            respuesta = JsonResponse({'ok': False, 'mensaje': 'Longitud inválida.'}, status=400)

        if respuesta is None and request.method == 'POST' and request.content_type.split(';', 1)[0].lower() != 'application/json':
            respuesta = JsonResponse({'ok': False, 'mensaje': 'Envía datos JSON.'}, status=415)
        cuerpo = b''
        if respuesta is None and request.method == 'POST':
            try:
                cuerpo = request.body
            except Exception:
                respuesta = JsonResponse({'ok': False, 'mensaje': 'Solicitud demasiado grande.'}, status=413)
            else:
                if len(cuerpo) > 16384:
                    respuesta = JsonResponse({'ok': False, 'mensaje': 'Solicitud demasiado grande.'}, status=413)

        if respuesta is None:
            if 'neon' not in connections.databases:
                respuesta = JsonResponse({'ok': False, 'mensaje': 'Servicio temporalmente no disponible.'}, status=503)
            else:
                try:
                    excedido, ventana = _aplicar_limites(tipo, _ip_cliente(request),
                                                        _identidad_adicional(tipo, cuerpo))
                except DatabaseError:
                    logger.exception('Error en límites de seguridad de API.')
                    respuesta = JsonResponse({'ok': False, 'mensaje': 'Servicio temporalmente no disponible.'}, status=503)
                else:
                    if excedido:
                        respuesta = JsonResponse({'ok': False, 'mensaje': 'Demasiadas solicitudes. Intenta más tarde.'}, status=429)
                        respuesta['Retry-After'] = str(ventana)
        if respuesta is not None:
            respuesta['Cache-Control'] = 'no-store'
            return respuesta
        return self.get_response(request)
