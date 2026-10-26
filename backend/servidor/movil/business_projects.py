"""Captura de requerimientos y tablero de las ventas de cada organización."""
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .auth import acceso, leer_json, respuesta
from .business_common import api, buscar, paginar, texto
from .models import Cliente, Requerimiento

ESTADOS = ('por_hacer', 'en_progreso', 'completado')


def _query(request):
    return Cliente.objects.filter(organizacion=request.organizacion_movil, hubo_venta=True).annotate(
        total_requerimientos=Count('requerimientos'),
        completados=Count('requerimientos', filter=Q(requerimientos__estado='completado')),
    )


def _proyecto(item):
    return {'id': str(item.id), 'fuente': 'directo', 'nombre': item.nombre,
            'negocio': item.nombre, 'telefono': item.telefono, 'origen': 'Registro directo',
            'servicio_recomendado': item.descripcion_servicio,
            'total_requerimientos': item.total_requerimientos, 'completados': item.completados}


def _tarea(item):
    return {'id': str(item.id), 'titulo': item.titulo, 'descripcion': item.descripcion, 'estado': item.estado}


def _fuente(fuente):
    if fuente != 'directo':
        raise ValueError('Fuente de proyecto inválida.')


def _detalle(request, cliente_id):
    item = get_object_or_404(_query(request), pk=cliente_id)
    tareas = list(item.requerimientos.order_by('orden'))
    return {'ok': True, 'proyecto': _proyecto(item), 'requerimientos_definidos': bool(tareas),
            'requerimientos': [_tarea(t) for t in tareas]}


def _listado(request, gestion):
    term = buscar(request)
    query = _query(request)
    query = query.filter(total_requerimientos__gt=0) if gestion else query.filter(total_requerimientos=0)
    if term:
        query = query.filter(Q(nombre__icontains=term) | Q(telefono__icontains=term) | Q(descripcion_servicio__icontains=term))
    return respuesta(paginar(query.order_by('-creado_en', 'id'), request, 'proyectos', _proyecto))


@acceso('desarrollador')
@api
@require_GET
def pendientes(request):
    return _listado(request, False)


@acceso('desarrollador')
@api
@require_GET
def gestion(request):
    return _listado(request, True)


@acceso('desarrollador')
@api
@require_http_methods(['GET', 'POST'])
def requerimientos(request, fuente, prospecto_id):
    _fuente(fuente)
    if request.method == 'GET':
        return respuesta(_detalle(request, prospecto_id))
    datos = leer_json(request, max_bytes=60 * 1024)
    lista = datos.get('requerimientos')
    if set(datos) != {'requerimientos'} or not isinstance(lista, list) or not 1 <= len(lista) <= 100:
        raise ValueError('Captura entre 1 y 100 requerimientos.')
    validos = []
    for item in lista:
        if not isinstance(item, dict) or set(item) - {'titulo', 'descripcion'} or 'titulo' not in item:
            raise ValueError('Cada requerimiento debe contener título y descripción.')
        validos.append({'titulo': texto(item['titulo'], 'Título', 150),
                        'descripcion': texto(item.get('descripcion', ''), 'Descripción', 2000, requerido=False)})
    with transaction.atomic(using='movil'):
        # La misma fila de venta serializa cancelaciones y capturas simultáneas.
        cliente = get_object_or_404(Cliente.objects.select_for_update(), pk=prospecto_id,
                                    organizacion=request.organizacion_movil, hubo_venta=True)
        if cliente.requerimientos.exists():
            return respuesta({'ok': False, 'mensaje': 'Este proyecto ya tiene requerimientos. Abre su tablero.'}, 409)
        Requerimiento.objects.bulk_create([
            Requerimiento(cliente=cliente, orden=orden, **item) for orden, item in enumerate(validos, 1)
        ])
        result = _detalle(request, prospecto_id)
    return respuesta({**result, 'mensaje': 'Requerimientos guardados. El proyecto está en gestión.'})


@acceso('desarrollador')
@api
@require_GET
def kanban(request, fuente, prospecto_id):
    _fuente(fuente)
    result = _detalle(request, prospecto_id)
    if not result['requerimientos_definidos']:
        return respuesta({'ok': False, 'mensaje': 'Primero define los requerimientos del proyecto.'}, 409)
    return respuesta(result)


@acceso('desarrollador')
@api
@require_POST
def estado_requerimiento(request, fuente, prospecto_id, requerimiento_id):
    _fuente(fuente)
    datos = leer_json(request)
    if set(datos) != {'estado'} or datos['estado'] not in ESTADOS:
        raise ValueError('Selecciona Por hacer, En progreso o Completado.')
    with transaction.atomic(using='movil'):
        cliente = get_object_or_404(Cliente.objects.select_for_update(), pk=prospecto_id,
                                    organizacion=request.organizacion_movil, hubo_venta=True)
        item = get_object_or_404(Requerimiento.objects, pk=requerimiento_id, cliente=cliente)
        item.estado = datos['estado']
        item.save(update_fields=['estado', 'actualizado_en'])
    return respuesta({'ok': True, 'requerimiento': _tarea(item), 'mensaje': 'Estado guardado.'})
