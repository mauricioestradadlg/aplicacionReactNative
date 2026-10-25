"""Requerimientos y tablero Kanban de las ventas cerradas, solo administradores.

La identidad de un proyecto es (fuente, prospecto_id), igual que en Ventas.
Una venta sin requerimientos está pendiente; al guardar su lista completa pasa
a Gestión. No se crean copias de clientes ni se modifica su liquidación.
"""
import json
import logging
from math import ceil
from uuid import uuid4

from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError, connections, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .resenas_admin_view import _autorizar_admin

logger = logging.getLogger(__name__)
FUENTES = ('whatsapp', 'email-marketing')
ESTADOS = ('por_hacer', 'en_progreso', 'completado')
POR_PAGINA = 25
MAX_CUERPO = 60 * 1024

_DESDE_PROYECTOS = '''
    FROM public.cierres_ventas AS v
    LEFT JOIN public.prospectos_oferta_valor AS w
      ON v.fuente = 'whatsapp' AND w.id = v.prospecto_id
    LEFT JOIN public.leads_magnet AS l
      ON v.fuente = 'email-marketing' AND l.id = v.prospecto_id
    LEFT JOIN (
        SELECT fuente, prospecto_id, COUNT(*) AS total_requerimientos,
               COUNT(*) FILTER (WHERE estado = 'completado') AS completados
        FROM public.proyectos_requerimientos
        GROUP BY fuente, prospecto_id
    ) AS r ON r.fuente = v.fuente AND r.prospecto_id = v.prospecto_id
    WHERE v.hubo_venta = TRUE
      AND (
        (v.fuente = 'whatsapp' AND w.id IS NOT NULL)
        OR (v.fuente = 'email-marketing' AND l.id IS NOT NULL)
      )
'''
_COLUMNAS = '''
    SELECT v.prospecto_id, v.fuente,
           COALESCE(w.nombre, l.nombre, ''),
           COALESCE(w.telefono, l.whatsapp, ''),
           COALESCE(w.negocio, l.negocio, ''),
           COALESCE(w.servicio_recomendado, l.servicio_recomendado, ''),
           COALESCE(w.origen, l.origen_potencial,
               CASE WHEN v.fuente = 'whatsapp' THEN 'WhatsApp'
                    ELSE 'Email Marketing' END),
           COALESCE(r.total_requerimientos, 0), COALESCE(r.completados, 0)
'''
_BLOQUEAR_VENTA = '''
    SELECT v.prospecto_id
    FROM public.cierres_ventas AS v
    WHERE v.fuente = %s AND v.prospecto_id = %s AND v.hubo_venta = TRUE
      AND (
        (v.fuente = 'whatsapp' AND EXISTS (
            SELECT 1 FROM public.prospectos_oferta_valor w WHERE w.id = v.prospecto_id
        ))
        OR (v.fuente = 'email-marketing' AND EXISTS (
            SELECT 1 FROM public.leads_magnet l WHERE l.id = v.prospecto_id
        ))
      )
    FOR UPDATE OF v
'''


def _respuesta(datos, estado=200):
    respuesta = JsonResponse(datos, status=estado)
    respuesta['Cache-Control'] = 'no-store'
    respuesta['Pragma'] = 'no-cache'
    return respuesta


def _preparar(request, fuente=None):
    administrador, error = _autorizar_admin(request)
    if error is not None:
        if error.status_code == 403:
            return None, _respuesta({'ok': False, 'mensaje': 'Solo administradores pueden consultar y modificar los proyectos.'}, 403)
        return None, error
    if 'neon' not in connections.databases:
        return None, _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)
    if fuente is not None and fuente not in FUENTES:
        return None, _respuesta({'ok': False, 'mensaje': 'Fuente de proyecto inválida.'}, 400)
    return administrador, None


def _error_base():
    return _respuesta({
        'ok': False,
        'mensaje': 'No fue posible consultar o guardar el proyecto. Revisa la conexión y la instalación del módulo de Proyectos.',
    }, 503)


def _proyecto(fila):
    return {
        'id': str(fila[0]), 'fuente': fila[1], 'nombre': fila[2],
        'telefono': fila[3], 'negocio': fila[4],
        'servicio_recomendado': fila[5], 'origen': fila[6],
        'total_requerimientos': fila[7], 'completados': fila[8],
    }


def _requerimiento(fila):
    return {'id': str(fila[0]), 'titulo': fila[1], 'descripcion': fila[2], 'estado': fila[3]}


def _detalle(cursor, fuente, prospecto_id):
    cursor.execute(_COLUMNAS + _DESDE_PROYECTOS + '''
        AND v.fuente = %s AND v.prospecto_id = %s
    ''', [fuente, str(prospecto_id)])
    fila = cursor.fetchone()
    if fila is None:
        return None
    proyecto = _proyecto(fila)
    cursor.execute('''
        SELECT id, titulo, descripcion, estado
        FROM public.proyectos_requerimientos
        WHERE fuente = %s AND prospecto_id = %s
        ORDER BY orden, id
    ''', [fuente, str(prospecto_id)])
    requerimientos = [_requerimiento(r) for r in cursor.fetchall()]
    # El detalle y sus contadores se construyen con la misma lectura de tarjetas.
    proyecto['total_requerimientos'] = len(requerimientos)
    proyecto['completados'] = sum(r['estado'] == 'completado' for r in requerimientos)
    return {
        'ok': True, 'proyecto': proyecto, 'requerimientos': requerimientos,
        'requerimientos_definidos': bool(requerimientos),
    }


def _filtros(request):
    try:
        pagina = int(request.GET.get('pagina', '1'))
        if not 1 <= pagina <= 100000:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError('Página inválida.') from None
    buscar = request.GET.get('buscar', '').strip()
    _texto(buscar, 100, 'La búsqueda', permite_vacio=True)
    if not buscar:
        return pagina, '', []
    return pagina, '''
        AND (COALESCE(w.nombre, l.nombre, '') ILIKE %s
          OR COALESCE(w.telefono, l.whatsapp, '') ILIKE %s
          OR COALESCE(w.negocio, l.negocio, '') ILIKE %s)
    ''', ['%' + buscar + '%'] * 3


def _listar(request, definidos):
    _, error = _preparar(request)
    if error is not None:
        return error
    try:
        pagina, filtro, parametros = _filtros(request)
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    etapa = (' AND COALESCE(r.total_requerimientos, 0) > 0' if definidos
             else ' AND COALESCE(r.total_requerimientos, 0) = 0')
    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('SELECT COUNT(*) ' + _DESDE_PROYECTOS + etapa + filtro, parametros)
            total = cursor.fetchone()[0]
            cursor.execute(_COLUMNAS + _DESDE_PROYECTOS + etapa + filtro + '''
                ORDER BY v.actualizado_en DESC, v.prospecto_id DESC, v.fuente
                LIMIT %s OFFSET %s
            ''', [*parametros, POR_PAGINA, (pagina - 1) * POR_PAGINA])
            proyectos = [_proyecto(f) for f in cursor.fetchall()]
    except DatabaseError:
        logger.exception('Error consultando proyectos; definidos=%s.', definidos)
        return _error_base()
    return _respuesta({
        'ok': True, 'proyectos': proyectos, 'total': total,
        'pagina': pagina, 'paginas': ceil(total / POR_PAGINA), 'por_pagina': POR_PAGINA,
    })


@require_GET
def listar_proyectos_pendientes(request):
    return _listar(request, definidos=False)


@require_GET
def listar_gestion_proyectos(request):
    return _listar(request, definidos=True)


def _leer_json(request):
    if (request.content_type or '').split(';', 1)[0].strip().lower() != 'application/json':
        return None, _respuesta({'ok': False, 'mensaje': 'Envía datos JSON.'}, 415)
    try:
        cuerpo = request.body
    except RequestDataTooBig:
        return None, _respuesta({'ok': False, 'mensaje': 'La lista supera el tamaño permitido de 60 KB. Reduce el texto de los requerimientos.'}, 413)
    if len(cuerpo) > MAX_CUERPO:
        return None, _respuesta({'ok': False, 'mensaje': 'La lista supera el tamaño permitido de 60 KB. Reduce el texto de los requerimientos.'}, 413)
    try:
        datos = json.loads(cuerpo.decode('utf-8'))
        if not isinstance(datos, dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None, _respuesta({'ok': False, 'mensaje': 'Envía un objeto JSON válido.'}, 400)
    return datos, None


def _texto(valor, limite, nombre, permite_vacio=False):
    if not isinstance(valor, str):
        raise ValueError(f'{nombre} debe ser texto.')
    valor = valor.strip()
    try:
        valor.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError(f'{nombre} contiene caracteres inválidos.') from None
    if '\x00' in valor or len(valor) > limite or (not permite_vacio and not valor):
        raise ValueError(f'{nombre} debe tener {"hasta" if permite_vacio else "entre 1 y"} {limite} caracteres válidos.')
    return valor


def _validar_requerimientos(datos):
    if set(datos) != {'requerimientos'}:
        raise ValueError('Envía únicamente la lista de requerimientos.')
    lista = datos['requerimientos']
    if not isinstance(lista, list) or not 1 <= len(lista) <= 100:
        raise ValueError('Añade entre 1 y 100 requerimientos antes de guardar.')
    resultado = []
    for item in lista:
        if not isinstance(item, dict) or set(item) != {'titulo', 'descripcion'}:
            raise ValueError('Cada requerimiento debe incluir título y descripción.')
        resultado.append({
            'titulo': _texto(item['titulo'], 150, 'El título'),
            'descripcion': _texto(item['descripcion'], 2000, 'La descripción', permite_vacio=True),
        })
    return resultado


def _obtener_detalle(request, fuente, prospecto_id, requiere_definidos=False):
    _, error = _preparar(request, fuente)
    if error is not None:
        return error
    try:
        with connections['neon'].cursor() as cursor:
            datos = _detalle(cursor, fuente, prospecto_id)
    except DatabaseError:
        logger.exception('Error consultando detalle de proyecto; fuente=%s.', fuente)
        return _error_base()
    if datos is None:
        return _respuesta({'ok': False, 'mensaje': 'El proyecto no tiene una venta cerrada o ya no existe.'}, 404)
    if requiere_definidos and not datos['requerimientos_definidos']:
        return _respuesta({'ok': False, 'mensaje': 'Primero define y guarda los requerimientos del proyecto.'}, 409)
    return _respuesta(datos)


@require_http_methods(['GET', 'POST'])
def requerimientos_proyecto(request, fuente, prospecto_id):
    if request.method == 'GET':
        return _obtener_detalle(request, fuente, prospecto_id)
    administrador, error = _preparar(request, fuente)
    if error is not None:
        return error
    datos, error = _leer_json(request)
    if error is not None:
        return error
    try:
        lista = _validar_requerimientos(datos)
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    try:
        with transaction.atomic(using='neon'):
            with connections['neon'].cursor() as cursor:
                # Serializa el guardado completo con otros guardados y cambios de venta.
                cursor.execute(_BLOQUEAR_VENTA, [fuente, str(prospecto_id)])
                if cursor.fetchone() is None:
                    return _respuesta({'ok': False, 'mensaje': 'El proyecto ya no tiene una venta cerrada o no existe.'}, 409)
                cursor.execute('''
                    SELECT 1 FROM public.proyectos_requerimientos
                    WHERE fuente = %s AND prospecto_id = %s LIMIT 1
                ''', [fuente, str(prospecto_id)])
                if cursor.fetchone() is not None:
                    return _respuesta({'ok': False, 'mensaje': 'Este proyecto ya tiene requerimientos. Continúa en Gestión de Proyectos.'}, 409)
                cursor.executemany('''
                    INSERT INTO public.proyectos_requerimientos
                        (id, fuente, prospecto_id, orden, titulo, descripcion, estado, actualizado_por)
                    VALUES (%s, %s, %s, %s, %s, %s, 'por_hacer', %s)
                ''', [
                    [str(uuid4()), fuente, str(prospecto_id), posicion,
                     item['titulo'], item['descripcion'], administrador[0]]
                    for posicion, item in enumerate(lista, start=1)
                ])
                resultado = _detalle(cursor, fuente, prospecto_id)
                if resultado is None:
                    # Una eliminación concurrente del registro de origen debe
                    # deshacer toda la captura, no dejar una respuesta parcial.
                    raise DatabaseError('El registro de origen desapareció durante la captura.')
    except DatabaseError:
        logger.exception('Error guardando requerimientos de proyecto; fuente=%s.', fuente)
        return _error_base()
    resultado['mensaje'] = 'Requerimientos guardados. El proyecto ya está en Gestión de Proyectos.'
    return _respuesta(resultado)


@require_GET
def kanban_proyecto(request, fuente, prospecto_id):
    return _obtener_detalle(request, fuente, prospecto_id, requiere_definidos=True)


@require_POST
def actualizar_estado_requerimiento(request, fuente, prospecto_id, requerimiento_id):
    administrador, error = _preparar(request, fuente)
    if error is not None:
        return error
    datos, error = _leer_json(request)
    if error is not None:
        return error
    if set(datos) != {'estado'} or datos['estado'] not in ESTADOS:
        return _respuesta({'ok': False, 'mensaje': 'Selecciona Por Hacer, En Progreso o Completado.'}, 400)
    try:
        with transaction.atomic(using='neon'):
            with connections['neon'].cursor() as cursor:
                cursor.execute(_BLOQUEAR_VENTA, [fuente, str(prospecto_id)])
                if cursor.fetchone() is None:
                    return _respuesta({'ok': False, 'mensaje': 'El proyecto ya no tiene una venta cerrada o no existe.'}, 409)
                cursor.execute('''
                    UPDATE public.proyectos_requerimientos
                    SET estado = %s, actualizado_en = NOW(), actualizado_por = %s
                    WHERE id = %s AND fuente = %s AND prospecto_id = %s
                    RETURNING id, titulo, descripcion, estado
                ''', [datos['estado'], administrador[0], str(requerimiento_id), fuente, str(prospecto_id)])
                fila = cursor.fetchone()
                if fila is None:
                    return _respuesta({'ok': False, 'mensaje': 'El requerimiento no pertenece a este proyecto o ya no existe.'}, 404)
    except DatabaseError:
        logger.exception('Error actualizando estado de requerimiento; fuente=%s.', fuente)
        return _error_base()
    return _respuesta({'ok': True, 'requerimiento': _requerimiento(fila), 'mensaje': 'Estado del requerimiento guardado.'})
