'''CRM Ventas > Cierre de Ventas, solo administradores.

GET  /api/sistema/cierre-ventas/?pagina=1&buscar=
POST /api/sistema/cierre-ventas/<uuid:prospecto_id>/estado/

Incluye WhatsApp y Email Marketing solo si existe una cita agendada
Y el lead sigue cumpliendo los requisitos de Cliente Potencial.
No copia prospectos y no envía correos ni cotizaciones.
'''
import json
import logging
from math import ceil

from django.db import DatabaseError, connections, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .resenas_admin_view import _autorizar_admin
from .oferta_valor_view import _UNION_POTENCIALES

logger = logging.getLogger(__name__)
POR_PAGINA = 25
FUENTES = ('whatsapp', 'email-marketing')

# Se reutiliza la misma definición de Clientes Potenciales. Al cambiar
# la oportunidad comercial/cualificación en Marketing, la lista se adapta.
DESDE_CITAS = _UNION_POTENCIALES + '''
    LEFT JOIN public.cierres_ventas v
      ON v.prospecto_id = p.id AND v.fuente = p.fuente
    WHERE p.cita_agendada_en IS NOT NULL
'''


def _respuesta(datos, codigo=200):
    resp = JsonResponse(datos, status=codigo)
    resp['Cache-Control'] = 'no-store'
    resp['Pragma'] = 'no-cache'
    return resp


def _fecha(fecha):
    return fecha.isoformat() if fecha else None


def _filtros(request):
    try:
        pagina = int(request.GET.get('pagina', '1'))
        if not 1 <= pagina <= 100000:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('Página inválida.')
    buscar = request.GET.get('buscar', '').strip()
    if len(buscar) > 100:
        raise ValueError('Búsqueda demasiado larga.')
    where_buscar = ''
    parametros = []
    if buscar:
        where_buscar = ''' AND (p.telefono ILIKE %s OR
                COALESCE(p.nombre, '') ILIKE %s OR COALESCE(p.negocio, '') ILIKE %s)'''
        parametros = [f'%{buscar}%'] * 3
    return pagina, where_buscar, parametros


@require_GET
def listar_cierres_ventas(request):
    _, error = _autorizar_admin(request)
    if error is not None:
        return error
    if 'neon' not in connections.databases:
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)
    try:
        pagina, filtro, parametros = _filtros(request)
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)

    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('''
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE v.cita_completada = TRUE),
                       COUNT(*) FILTER (WHERE v.cotizacion_enviada = TRUE),
                       COUNT(*) FILTER (WHERE v.hubo_venta = TRUE)
            ''' + DESDE_CITAS + filtro, parametros)
            resumen = cursor.fetchone()
            cursor.execute('''
                SELECT p.id, p.nombre, p.telefono, p.negocio,
                       p.servicio_recomendado, p.origen, p.fuente,
                       p.cita_agendada_en,
                       COALESCE(v.cita_completada, FALSE),
                       COALESCE(v.cotizacion_enviada, FALSE),
                       COALESCE(v.hubo_venta, FALSE),
                       v.actualizado_en
            ''' + DESDE_CITAS + filtro + '''
                ORDER BY p.cita_agendada_en DESC, p.id DESC, p.fuente
                LIMIT %s OFFSET %s
            ''', [*parametros, POR_PAGINA, (pagina - 1) * POR_PAGINA])
            filas = cursor.fetchall()
    except DatabaseError:
        logger.exception('No se pudo listar Cierre de Ventas.')
        return _respuesta({'ok': False, 'mensaje': 'No fue posible consultar las citas. Ejecuta el SQL 05.'}, 503)

    total = resumen[0]
    return _respuesta({
        'ok': True,
        'prospectos': [{
            'id': str(f[0]),
            'nombre': f[1] or '',
            'telefono': f[2] or '',
            'negocio': f[3] or '',
            'servicio_recomendado': f[4] or '',
            'origen': f[5] or ('Email Marketing' if f[6] == 'email-marketing' else 'WhatsApp'),
            'fuente': f[6],
            'cita_agendada_en': _fecha(f[7]),
            'cita_completada': bool(f[8]),
            'cotizacion_enviada': bool(f[9]),
            'hubo_venta': bool(f[10]),
            'actualizado_en': _fecha(f[11]),
        } for f in filas],
        'totales': {
            'citas': total,
            'completadas': resumen[1],
            'cotizaciones': resumen[2],
            'ventas': resumen[3],
        },
        'pagina': pagina,
        'paginas': ceil(total / POR_PAGINA),
        'por_pagina': POR_PAGINA,
    })


@require_POST
def guardar_cierre_ventas(request, prospecto_id):
    administrador, error = _autorizar_admin(request)
    if error is not None:
        return error
    if 'neon' not in connections.databases:
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)
    if request.content_type.split(';', 1)[0].strip().lower() != 'application/json':
        return _respuesta({'ok': False, 'mensaje': 'Envía JSON válido.'}, 415)
    if len(request.body) > 1024:
        return _respuesta({'ok': False, 'mensaje': 'Solicitud demasiado grande.'}, 413)
    try:
        datos = json.loads(request.body.decode('utf-8'))
        if not isinstance(datos, dict) or set(datos.keys()) != {
            'fuente', 'cita_completada', 'cotizacion_enviada', 'hubo_venta'
        }:
            raise ValueError
        fuente = datos['fuente']
        completada = datos['cita_completada']
        cotizada = datos['cotizacion_enviada']
        venta = datos['hubo_venta']
        if fuente not in FUENTES or any(type(v) is not bool for v in (completada, cotizada, venta)):
            raise ValueError
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return _respuesta({'ok': False, 'mensaje': 'Los estados deben ser Sí o No y la fuente debe ser válida.'}, 400)

    if venta and not (completada and cotizada):
        return _respuesta({'ok': False, 'mensaje': 'Para marcar una venta se requiere cita completada y cotización enviada.'}, 400)

    # La fuente es técnica, distinta de la etiqueta Origen editable.
    # Se bloquea el registro original hasta confirmar que continúa calificado.
    if fuente == 'whatsapp':
        origen_sql = '''
            SELECT id FROM public.prospectos_oferta_valor
            WHERE id = %s AND brindo_nombre = TRUE AND respondio_mensajes = TRUE
              AND cita_agendada_en IS NOT NULL FOR UPDATE
        '''
    else:
        origen_sql = '''
            SELECT id FROM public.leads_magnet
            WHERE id = %s AND acepto_correos = TRUE
              AND oportunidad_comercial_en IS NOT NULL
              AND NULLIF(BTRIM(nombre), '') IS NOT NULL
              AND cita_agendada_en IS NOT NULL FOR UPDATE
        '''

    try:
        with transaction.atomic(using='neon'):
            with connections['neon'].cursor() as cursor:
                cursor.execute(origen_sql, [str(prospecto_id)])
                if cursor.fetchone() is None:
                    return _respuesta({
                        'ok': False,
                        'mensaje': 'El prospecto ya no tiene cita agendada o dejó de calificar.',
                    }, 409)
                cursor.execute('''
                    INSERT INTO public.cierres_ventas
                        (fuente, prospecto_id, cita_completada,
                         cotizacion_enviada, hubo_venta, actualizado_por)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (fuente, prospecto_id) DO UPDATE
                    SET cita_completada = EXCLUDED.cita_completada,
                        cotizacion_enviada = EXCLUDED.cotizacion_enviada,
                        hubo_venta = EXCLUDED.hubo_venta,
                        actualizado_por = EXCLUDED.actualizado_por,
                        actualizado_en = NOW()
                    RETURNING cita_completada, cotizacion_enviada,
                              hubo_venta, actualizado_en
                ''', [fuente, str(prospecto_id), completada, cotizada, venta, administrador[0]])
                fila = cursor.fetchone()
    except DatabaseError:
        logger.exception('Error guardando Cierre de Ventas: fuente=%s.', fuente)
        return _respuesta({'ok': False, 'mensaje': 'No fue posible guardar el seguimiento.'}, 503)

    logger.info('Cierre de Ventas actualizado por administrador_id=%s.', administrador[0])
    return _respuesta({
        'ok': True,
        'cita_completada': bool(fila[0]),
        'cotizacion_enviada': bool(fila[1]),
        'hubo_venta': bool(fila[2]),
        'actualizado_en': _fecha(fila[3]),
        'mensaje': 'Seguimiento de venta guardado.',
    })
