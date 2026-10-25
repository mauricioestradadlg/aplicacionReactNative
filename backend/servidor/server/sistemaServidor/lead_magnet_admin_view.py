'''Listado privado y paginado de solicitudes del Lead Magnet.

GET /api/sistema/lead-magnet/registros/?pagina=1&buscar=&plantilla=
La autorización se verifica en Django: cookie vigente + rol admin.
'''
import logging
import json
from math import ceil
from django.db import DatabaseError, connections
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from .resenas_admin_view import _autorizar_admin

logger = logging.getLogger(__name__)
POR_PAGINA = 25
PLANTILLAS = ('restaurante', 'negocio')


def _respuesta(datos, estado=200):
    response = JsonResponse(datos, status=estado)
    response['Cache-Control'] = 'no-store'
    response['Pragma'] = 'no-cache'
    return response


@require_GET
def listar_leads_magnet(request):
    _, error = _autorizar_admin(request)
    if error is not None:
        return error

    try:
        pagina = int(request.GET.get('pagina', '1'))
        if not 1 <= pagina <= 100000:
            raise ValueError
    except (TypeError, ValueError):
        return _respuesta({'ok': False, 'mensaje': 'Página inválida.'}, 400)

    busqueda = request.GET.get('buscar', '').strip()
    plantilla = request.GET.get('plantilla', '').strip()
    if len(busqueda) > 100 or plantilla not in ('', *PLANTILLAS):
        return _respuesta({'ok': False, 'mensaje': 'Filtros inválidos.'}, 400)

    filtros = []
    parametros = []
    if plantilla:
        filtros.append('plantilla = %s')
        parametros.append(plantilla)
    if busqueda:
        filtros.append('(nombre ILIKE %s OR correo ILIKE %s OR negocio ILIKE %s)')
        patron = '%' + busqueda + '%'
        parametros.extend([patron, patron, patron])
    where = (' WHERE ' + ' AND '.join(filtros)) if filtros else ''

    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM public.leads_magnet' + where, parametros)
            total = cursor.fetchone()[0]
            cursor.execute('''
                SELECT id, nombre, correo, whatsapp, negocio, plantilla,
                       acepto_privacidad, acepto_correos, fecha_registro
                FROM public.leads_magnet
            ''' + where + '''
                ORDER BY fecha_registro DESC, id DESC
                LIMIT %s OFFSET %s
            ''', [*parametros, POR_PAGINA, (pagina - 1) * POR_PAGINA])
            filas = cursor.fetchall()
    except DatabaseError:
        logger.exception('No se pudo consultar el listado de leads.')
        return _respuesta({
            'ok': False,
            'mensaje': 'No se pudo consultar el listado. Verifica que exista la tabla leads_magnet.',
        }, 503)

    leads = [
        {
            'id': str(f[0]),
            'nombre': f[1],
            'correo': f[2],
            'whatsapp': f[3],
            'negocio': f[4],
            'plantilla': f[5],
            'acepto_privacidad': bool(f[6]),
            'acepto_correos': bool(f[7]),
            'fecha_registro': f[8].isoformat() if f[8] else None,
        }
        for f in filas
    ]
    return _respuesta({
        'ok': True,
        'leads': leads,
        'total': total,
        'pagina': pagina,
        'por_pagina': POR_PAGINA,
        'paginas': ceil(total / POR_PAGINA),
    })


# ==========================================================
# SEGUIMIENTO MANUAL DE EMAIL MARKETING
# Solo leads que dieron consentimiento opcional.
# Ninguna operación envía correos automáticamente.
# ==========================================================

CAMPOS_SEGUIMIENTO = {
    'tips_enviados': 'tips_enviados_en',
    'feedback_enviado': 'feedback_enviado_en',
    'oportunidad_comercial': 'oportunidad_comercial_en',
}


@require_GET
def listar_email_marketing(request):
    _, error = _autorizar_admin(request)
    if error is not None:
        return error

    try:
        pagina = int(request.GET.get('pagina', '1'))
        if pagina < 1 or pagina > 100000:
            raise ValueError
    except (ValueError, TypeError):
        return _respuesta({'ok': False, 'mensaje': 'Página inválida.'}, 400)

    buscar = request.GET.get('buscar', '').strip()
    if len(buscar) > 100:
        return _respuesta({'ok': False, 'mensaje': 'Búsqueda demasiado larga.'}, 400)

    filtros = ['acepto_correos = TRUE']
    parametros = []
    if buscar:
        filtros.append('(nombre ILIKE %s OR correo ILIKE %s OR negocio ILIKE %s)')
        patron = '%' + buscar + '%'
        parametros = [patron, patron, patron]
    where = ' WHERE ' + ' AND '.join(filtros)

    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM public.leads_magnet' + where, parametros)
            total = cursor.fetchone()[0]
            cursor.execute('''
                SELECT id, nombre, correo, whatsapp, negocio, plantilla,
                       fecha_registro, tips_enviados_en, feedback_enviado_en,
                       oportunidad_comercial_en
                FROM public.leads_magnet
            ''' + where + '''
                ORDER BY fecha_registro DESC, id DESC
                LIMIT %s OFFSET %s
            ''', [*parametros, POR_PAGINA, (pagina - 1) * POR_PAGINA])
            filas = cursor.fetchall()
    except DatabaseError:
        logger.exception('Error consultando el seguimiento de Email Marketing.')
        return _respuesta({'ok': False, 'mensaje': 'No fue posible consultar Email Marketing. Verifica la migración SQL.'}, 503)

    return _respuesta({
        'ok': True,
        'leads': [{
            'id': str(f[0]),
            'nombre': f[1],
            'correo': f[2],
            'whatsapp': f[3],
            'negocio': f[4],
            'plantilla': f[5],
            'fecha_registro': f[6].isoformat() if f[6] else None,
            'tips_enviados_en': f[7].isoformat() if f[7] else None,
            'feedback_enviado_en': f[8].isoformat() if f[8] else None,
            'oportunidad_comercial_en': f[9].isoformat() if f[9] else None,
        } for f in filas],
        'total': total,
        'pagina': pagina,
        'paginas': ceil(total / POR_PAGINA),
        'por_pagina': POR_PAGINA,
    })


@require_POST
def actualizar_email_marketing(request, lead_id):
    administrador, error = _autorizar_admin(request)
    if error is not None:
        return error

    if request.content_type.split(';', 1)[0].strip().lower() != 'application/json':
        return _respuesta({'ok': False, 'mensaje': 'Envía datos JSON.'}, 415)
    if len(request.body) > 1024:
        return _respuesta({'ok': False, 'mensaje': 'Solicitud demasiado grande.'}, 413)

    try:
        datos = json.loads(request.body.decode('utf-8'))
        if not isinstance(datos, dict):
            raise ValueError
        campo = datos.get('campo')
        valor = datos.get('valor')
        if campo not in CAMPOS_SEGUIMIENTO or type(valor) is not bool:
            raise ValueError
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return _respuesta({'ok': False, 'mensaje': 'Campo o valor inválido.'}, 400)

    # La columna SQL procede exclusivamente de esta lista cerrada,
    # nunca del texto proporcionado por el usuario.
    columna = CAMPOS_SEGUIMIENTO[campo]
    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute(f'''
                UPDATE public.leads_magnet
                SET {columna} = CASE WHEN %s THEN COALESCE({columna}, NOW()) ELSE NULL END,
                    seguimiento_actualizado_en = NOW(),
                    seguimiento_actualizado_por = %s
                WHERE id = %s AND acepto_correos = TRUE
                RETURNING tips_enviados_en, feedback_enviado_en,
                          oportunidad_comercial_en
            ''', [valor, administrador[0], str(lead_id)])
            actualizado = cursor.fetchone()
    except DatabaseError:
        logger.exception('Error guardando seguimiento de Email Marketing.')
        return _respuesta({'ok': False, 'mensaje': 'No fue posible guardar el cambio.'}, 503)

    if actualizado is None:
        return _respuesta({'ok': False, 'mensaje': 'Lead no encontrado o sin consentimiento para correos.'}, 404)

    logger.info('Seguimiento de email marketing actualizado por admin_id=%s', administrador[0])
    return _respuesta({
        'ok': True,
        'mensaje': 'Seguimiento actualizado correctamente.',
        'tips_enviados_en': actualizado[0].isoformat() if actualizado[0] else None,
        'feedback_enviado_en': actualizado[1].isoformat() if actualizado[1] else None,
        'oportunidad_comercial_en': actualizado[2].isoformat() if actualizado[2] else None,
    })
