'''CRM > Ventas > Gestión de Ventas.

GET  /api/sistema/gestion-ventas/?pagina=1&buscar=
POST /api/sistema/gestion-ventas/<uuid:prospecto_id>/liquidacion/

Sin duplicar clientes: se lee cierres_ventas y las tablas de origen.
Solo las ventas cerradas (hubo_venta=TRUE) aparecen en Gestión.
El usuario registra el importe acordado, el anticipo y sus fechas de cobro,
y confirma manualmente si recibió el saldo final. No se ejecutan cobros.
'''
import json
import logging
import re
from datetime import date, datetime, time
from decimal import Decimal
from math import ceil
from zoneinfo import ZoneInfo

from django.db import DatabaseError, connections, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .resenas_admin_view import _autorizar_admin

logger = logging.getLogger(__name__)
POR_PAGINA = 25
FUENTES = ('whatsapp', 'email-marketing')
ZONA_FINANZAS = ZoneInfo('America/Mexico_City')
MAX_IMPORTE = Decimal('9999999999.99')
PATRON_IMPORTE = re.compile(r'[0-9]+(?:\.[0-9]{1,2})?\Z')
PATRON_FECHA = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}\Z')
CAMPOS_LEGACY = {'fuente', 'proyecto_liquidado'}
CAMPOS_IMPORTES = CAMPOS_LEGACY | {
    'importe_total', 'importe_anticipo', 'fecha_anticipo', 'fecha_liquidacion',
}

# La fuente (no la etiqueta editable origen) determina de dónde
# proviene la identidad, para evitar cruces de UUID entre tablas.
_DESDE_VENTAS = '''
    FROM public.cierres_ventas AS v
    LEFT JOIN public.prospectos_oferta_valor AS w
      ON v.fuente = 'whatsapp' AND w.id = v.prospecto_id
    LEFT JOIN public.leads_magnet AS l
      ON v.fuente = 'email-marketing' AND l.id = v.prospecto_id
    WHERE v.hubo_venta = TRUE
      AND (
        (v.fuente = 'whatsapp' AND w.id IS NOT NULL)
        OR (v.fuente = 'email-marketing' AND l.id IS NOT NULL)
      )
'''


def _respuesta(datos, estado=200):
    respuesta = JsonResponse(datos, status=estado)
    respuesta['Cache-Control'] = 'no-store'
    respuesta['Pragma'] = 'no-cache'
    return respuesta


def _fecha(valor):
    return valor.isoformat() if valor else None


def _dinero(valor):
    return format(valor, '.2f') if valor is not None else None


def _hoy_mexico():
    return datetime.now(ZONA_FINANZAS).date()


def _importe(valor):
    if not isinstance(valor, str) or len(valor) > 24 or not PATRON_IMPORTE.fullmatch(valor.strip()):
        raise ValueError('Captura importes sin separadores de miles y con máximo dos decimales.')
    importe = Decimal(valor.strip())
    if importe > MAX_IMPORTE:
        raise ValueError('El importe está fuera del rango permitido.')
    return importe


def _fecha_cobro(valor):
    if not isinstance(valor, str) or not PATRON_FECHA.fullmatch(valor):
        raise ValueError('Captura las fechas de cobro en formato AAAA-MM-DD.')
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise ValueError('Captura una fecha de cobro válida.') from None


def _validar_importes(datos):
    total = _importe(datos['importe_total'])
    anticipo = _importe(datos['importe_anticipo'])
    if total <= 0 or anticipo > total:
        raise ValueError('El total debe ser mayor a cero y el anticipo no puede superar el total.')
    fecha_anticipo = _fecha_cobro(datos['fecha_anticipo'])
    hoy = _hoy_mexico()
    if fecha_anticipo > hoy:
        raise ValueError('La fecha del anticipo no puede estar en el futuro.')
    fecha_final = None
    if datos['proyecto_liquidado']:
        fecha_final = _fecha_cobro(datos['fecha_liquidacion'])
        if fecha_final < fecha_anticipo or fecha_final > hoy:
            raise ValueError('La liquidación debe ser igual o posterior al anticipo y no estar en el futuro.')
    elif datos['fecha_liquidacion'] is not None:
        raise ValueError('Un proyecto pendiente de liquidación no debe tener fecha de pago final.')
    return total, anticipo, fecha_anticipo, fecha_final


def _parametros_busqueda(request):
    try:
        pagina = int(request.GET.get('pagina', '1'))
        if not 1 <= pagina <= 100000:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError('Página inválida.')

    buscar = request.GET.get('buscar', '').strip()
    if len(buscar) > 100:
        raise ValueError('La búsqueda debe tener máximo 100 caracteres.')

    filtro = ''
    parametros = []
    if buscar:
        filtro = '''
          AND (
            COALESCE(w.nombre, l.nombre, '') ILIKE %s
            OR COALESCE(w.telefono, l.whatsapp, '') ILIKE %s
            OR COALESCE(w.negocio, l.negocio, '') ILIKE %s
          )
        '''
        patron = '%' + buscar + '%'
        parametros = [patron, patron, patron]
    return pagina, filtro, parametros


@require_GET
def listar_gestion_ventas(request):
    _, error = _autorizar_admin(request)
    if error is not None:
        return error
    if 'neon' not in connections.databases:
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)

    try:
        pagina, filtro, parametros = _parametros_busqueda(request)
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)

    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('''
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE v.proyecto_liquidado = TRUE)
            ''' + _DESDE_VENTAS + filtro, parametros)
            total, liquidados = cursor.fetchone()

            cursor.execute('''
                SELECT v.prospecto_id, v.fuente,
                       COALESCE(w.nombre, l.nombre, ''),
                       COALESCE(w.telefono, l.whatsapp, ''),
                       COALESCE(w.negocio, l.negocio, ''),
                       COALESCE(w.servicio_recomendado, l.servicio_recomendado, ''),
                       COALESCE(w.origen, l.origen_potencial,
                           CASE WHEN v.fuente = 'whatsapp' THEN 'WhatsApp'
                                ELSE 'Email Marketing' END),
                       COALESCE(w.cita_agendada_en, l.cita_agendada_en),
                       v.cita_completada, v.cotizacion_enviada,
                       v.hubo_venta, v.proyecto_liquidado,
                       v.fecha_liquidacion, v.liquidacion_actualizada_en,
                       v.importe_total, v.importe_anticipo, v.fecha_anticipo
            ''' + _DESDE_VENTAS + filtro + '''
                ORDER BY v.actualizado_en DESC, v.prospecto_id DESC, v.fuente
                LIMIT %s OFFSET %s
            ''', [*parametros, POR_PAGINA, (pagina - 1) * POR_PAGINA])
            filas = cursor.fetchall()
    except DatabaseError:
        logger.exception('Error consultando Gestión de Ventas.')
        return _respuesta({
            'ok': False,
            'mensaje': 'No fue posible cargar las ventas. Revisa la conexión y la instalación de los importes de ventas.',
        }, 503)

    return _respuesta({
        'ok': True,
        'clientes': [
            {
                'id': str(f[0]),
                'fuente': f[1],
                'nombre': f[2],
                'telefono': f[3],
                'negocio': f[4],
                'servicio_recomendado': f[5],
                'origen': f[6],
                'cita_agendada_en': _fecha(f[7]),
                'cita_completada': bool(f[8]),
                'cotizacion_enviada': bool(f[9]),
                'hubo_venta': bool(f[10]),
                'proyecto_liquidado': bool(f[11]),
                'fecha_liquidacion': _fecha(f[12]),
                'liquidacion_actualizada_en': _fecha(f[13]),
                'importe_total': _dinero(f[14]),
                'importe_anticipo': _dinero(f[15]),
                'fecha_anticipo': _fecha(f[16]),
            }
            for f in filas
        ],
        'totales': {
            'ventas': total,
            'liquidados': liquidados,
            'pendientes': total - liquidados,
        },
        'pagina': pagina,
        'paginas': ceil(total / POR_PAGINA),
        'por_pagina': POR_PAGINA,
    })


@require_POST
def guardar_liquidacion(request, prospecto_id):
    administrador, error = _autorizar_admin(request)
    if error is not None:
        return error
    if 'neon' not in connections.databases:
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)

    if (request.content_type or '').split(';', 1)[0].strip().lower() != 'application/json':
        return _respuesta({'ok': False, 'mensaje': 'Envía datos JSON.'}, 415)
    if len(request.body) > 1024:
        return _respuesta({'ok': False, 'mensaje': 'Solicitud demasiado grande.'}, 413)

    try:
        datos = json.loads(request.body.decode('utf-8'))
        if not isinstance(datos, dict) or set(datos) not in (CAMPOS_LEGACY, CAMPOS_IMPORTES):
            raise ValueError
        fuente = datos['fuente']
        liquidado = datos['proyecto_liquidado']
        if fuente not in FUENTES or type(liquidado) is not bool:
            raise ValueError
    except (TypeError, ValueError, UnicodeDecodeError, RecursionError):
        return _respuesta({
            'ok': False,
            'mensaje': 'Selecciona una fuente válida y Proyecto liquidado: Sí o No.',
        }, 400)

    captura = None
    if set(datos) == CAMPOS_IMPORTES:
        try:
            captura = _validar_importes(datos)
        except ValueError as error:
            return _respuesta({'ok': False, 'mensaje': str(error)}, 400)

    try:
        with transaction.atomic(using='neon'):
            with connections['neon'].cursor() as cursor:
                # Un cliente debe contar con una venta cerrada previa.
                cursor.execute('''
                    SELECT v.proyecto_liquidado, v.fecha_liquidacion
                    FROM public.cierres_ventas v
                    WHERE v.fuente = %s
                      AND v.prospecto_id = %s
                      AND v.hubo_venta = TRUE
                      AND (
                        (v.fuente = 'whatsapp' AND EXISTS (
                          SELECT 1 FROM public.prospectos_oferta_valor w
                          WHERE w.id = v.prospecto_id
                        ))
                        OR (v.fuente = 'email-marketing' AND EXISTS (
                          SELECT 1 FROM public.leads_magnet l
                          WHERE l.id = v.prospecto_id
                        ))
                      )
                    FOR UPDATE OF v
                ''', [fuente, str(prospecto_id)])
                venta = cursor.fetchone()
                if venta is None:
                    return _respuesta({
                        'ok': False,
                        'mensaje': 'El cliente no tiene una venta cerrada o ya no existe.',
                    }, 409)

                if captura is not None:
                    total, anticipo, fecha_anticipo, fecha_final = captura
                    fecha_final_timestamp = None
                    if fecha_final is not None:
                        anterior = venta[1]
                        if anterior is not None and anterior.astimezone(ZONA_FINANZAS).date() == fecha_final:
                            fecha_final_timestamp = anterior
                        else:
                            fecha_final_timestamp = datetime.combine(fecha_final, time(12), ZONA_FINANZAS)
                    cursor.execute('''
                        UPDATE public.cierres_ventas
                           SET proyecto_liquidado = %s,
                               fecha_liquidacion = %s,
                               importe_total = %s,
                               importe_anticipo = %s,
                               fecha_anticipo = %s,
                               liquidacion_actualizada_en = NOW(),
                               liquidacion_actualizada_por = %s
                         WHERE fuente = %s AND prospecto_id = %s AND hubo_venta = TRUE
                     RETURNING proyecto_liquidado, fecha_liquidacion,
                               liquidacion_actualizada_en, importe_total,
                               importe_anticipo, fecha_anticipo
                    ''', [liquidado, fecha_final_timestamp, total, anticipo, fecha_anticipo,
                          administrador[0], fuente, str(prospecto_id)])
                else:
                    cursor.execute('''
                        UPDATE public.cierres_ventas
                           SET proyecto_liquidado = %s,
                               fecha_liquidacion = CASE
                                   WHEN %s THEN COALESCE(fecha_liquidacion, NOW())
                                   ELSE NULL END,
                               liquidacion_actualizada_en = NOW(),
                               liquidacion_actualizada_por = %s
                         WHERE fuente = %s
                           AND prospecto_id = %s
                           AND hubo_venta = TRUE
                     RETURNING proyecto_liquidado,
                               fecha_liquidacion,
                               liquidacion_actualizada_en,
                               importe_total, importe_anticipo, fecha_anticipo
                    ''', [liquidado, liquidado, administrador[0], fuente, str(prospecto_id)])
                fila = cursor.fetchone()
    except DatabaseError:
        logger.exception('No fue posible guardar liquidación. fuente=%s', fuente)
        return _respuesta({'ok': False, 'mensaje': 'No fue posible guardar el estado del proyecto.'}, 503)

    if fila is None:
        return _respuesta({'ok': False, 'mensaje': 'Venta no encontrada.'}, 409)
    logger.info('Liquidación modificada por administrador_id=%s', administrador[0])
    return _respuesta({
        'ok': True,
        'proyecto_liquidado': bool(fila[0]),
        'fecha_liquidacion': _fecha(fila[1]),
        'liquidacion_actualizada_en': _fecha(fila[2]),
        'importe_total': _dinero(fila[3]),
        'importe_anticipo': _dinero(fila[4]),
        'fecha_anticipo': _fecha(fila[5]),
        'mensaje': 'Datos de la venta guardados correctamente.',
    })
