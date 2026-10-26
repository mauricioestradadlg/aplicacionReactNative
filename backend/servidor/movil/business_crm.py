"""Clientes y ventas generales, aislados por la organización de la sesión."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .auth import acceso, leer_json, respuesta
from .business_common import api, booleano, buscar, correo, dinero, fecha, hoy, importe, paginar, texto
from .models import Cliente


def cliente_json(item):
    return {
        'id': str(item.id), 'nombre': item.nombre, 'correo': item.correo,
        'telefono': item.telefono, 'comentarios': item.comentarios,
        'hubo_venta': item.hubo_venta, 'monto_venta': dinero(item.monto_venta),
        'descripcion_servicio': item.descripcion_servicio,
        'importe_anticipo': dinero(item.importe_anticipo),
        'fecha_anticipo': item.fecha_anticipo.isoformat() if item.fecha_anticipo else None,
        'proyecto_liquidado': item.proyecto_liquidado,
        'fecha_liquidacion': item.fecha_liquidacion.isoformat() if item.fecha_liquidacion else None,
        'fecha_venta': item.fecha_venta.isoformat() if item.fecha_venta else None,
        'creado_en': item.creado_en.isoformat(),
        # Compatibilidad del formulario de cobros y de los tableros existentes.
        'fuente': 'directo', 'origen': 'Registro directo', 'negocio': item.nombre,
        'servicio_recomendado': item.descripcion_servicio, 'importe_total': dinero(item.monto_venta),
    }


def clientes_org(request):
    return Cliente.objects.filter(organizacion=request.organizacion_movil)


def _filtrar(query, request):
    term = buscar(request)
    if term:
        query = query.filter(Q(nombre__icontains=term) | Q(correo__icontains=term) | Q(telefono__icontains=term))
    return query.order_by('-creado_en', 'id')


def _validar(datos, item):
    allowed = {'nombre', 'correo', 'telefono', 'comentarios', 'hubo_venta', 'monto_venta', 'descripcion_servicio'}
    if not datos or set(datos) - allowed:
        raise ValueError('Envía únicamente los campos del cliente.')
    total_anterior = item.monto_venta
    for name, maximum in [('nombre', 150), ('telefono', 25), ('comentarios', 2000), ('descripcion_servicio', 2000)]:
        if name in datos:
            setattr(item, name, texto(datos[name], name.replace('_', ' ').capitalize(), maximum,
                                     requerido=name in ('nombre', 'telefono')))
    if 'correo' in datos:
        item.correo = correo(datos['correo'])
    if 'hubo_venta' in datos:
        item.hubo_venta = booleano(datos['hubo_venta'], 'Hubo venta')
    if 'monto_venta' in datos:
        item.monto_venta = importe(datos['monto_venta'], positivo=True) if datos['monto_venta'] not in (None, '') else None
    if not item.nombre or not item.correo or not item.telefono:
        raise ValueError('Completa nombre, correo y teléfono.')
    if item.hubo_venta and (item.monto_venta is None or not item.descripcion_servicio):
        raise ValueError('Una venta requiere un monto mayor que cero y la descripción del servicio.')
    if item.importe_anticipo is not None and (item.monto_venta is None or item.importe_anticipo > item.monto_venta):
        raise ValueError('El total de venta no puede ser menor que el anticipo registrado.')
    if item.proyecto_liquidado and item.monto_venta != total_anterior:
        raise ValueError('Corrige los importes de una venta liquidada desde Cobros en Finanzas.')
    if not item.hubo_venta:
        if item.fecha_anticipo or item.proyecto_liquidado or (item.pk and item.requerimientos.exists()):
            raise ValueError('No puedes cancelar una venta con cobros o requerimientos registrados.')
        item.monto_venta = None
        item.descripcion_servicio = ''
        item.fecha_venta = None
    elif not item.fecha_venta:
        item.fecha_venta = hoy()
    return item


@acceso('crm')
@api
@require_http_methods(['GET', 'POST'])
def clientes(request):
    if request.method == 'POST':
        datos = leer_json(request)
        with transaction.atomic(using='movil'):
            item = _validar(datos, Cliente(organizacion=request.organizacion_movil))
            item.save()
        return respuesta({'ok': True, 'cliente': cliente_json(item), 'mensaje': 'Cliente registrado.'}, 201)
    query = _filtrar(clientes_org(request), request)
    venta = request.GET.get('venta', 'todos')
    if venta not in ('todos', 'si', 'no'):
        raise ValueError('Selecciona un filtro de venta válido.')
    if venta != 'todos':
        query = query.filter(hubo_venta=venta == 'si')
    return respuesta(paginar(query, request, 'clientes', cliente_json))


@acceso('crm')
@api
@require_http_methods(['GET', 'PATCH'])
def editar_cliente(request, cliente_id):
    if request.method == 'GET':
        item = get_object_or_404(clientes_org(request), pk=cliente_id)
    else:
        datos = leer_json(request)
        with transaction.atomic(using='movil'):
            item = get_object_or_404(clientes_org(request).select_for_update(), pk=cliente_id)
            _validar(datos, item).save()
    return respuesta({'ok': True, 'cliente': cliente_json(item), 'mensaje': 'Cliente guardado.'})


@acceso('crm')
@api
@require_GET
def dashboard_crm(request):
    query = clientes_org(request)
    total = query.count()
    ventas = query.filter(hubo_venta=True)
    acumulado = ventas.aggregate(total=Count('id'), monto=Sum('monto_venta'))
    current = hoy().replace(day=1)
    meses = []
    for offset in range(5, -1, -1):
        ordinal = current.year * 12 + current.month - 1 - offset
        anio, mes = divmod(ordinal, 12)
        key = f'{anio:04d}-{mes + 1:02d}'
        meses.append({'mes': key, 'ventas': 0, 'monto': '0.00'})
    desde = meses[0]['mes'] + '-01'
    por_mes = {item['mes'].strftime('%Y-%m'): item for item in ventas.filter(fecha_venta__gte=desde)
               .annotate(mes=TruncMonth('fecha_venta')).values('mes').annotate(total=Count('id'), monto=Sum('monto_venta'))}
    for item in meses:
        if item['mes'] in por_mes:
            resumen = por_mes[item['mes']]
            item.update(ventas=resumen['total'], monto=dinero(resumen['monto']))
    return respuesta({'ok': True, 'total_clientes': total, 'total_ventas': acumulado['total'],
                      'prospectos': total - acumulado['total'],
                      'monto_ventas': dinero(acumulado['monto'] or Decimal('0')),
                      'conversion_pct': dinero(Decimal(acumulado['total'] * 100) / total) if total else '0.00',
                      'ventas_recientes': [cliente_json(v) for v in ventas.order_by('-fecha_venta', '-creado_en', 'id')[:5]],
                      'tendencia': meses})


@acceso('finanzas')
@api
@require_GET
def gestion_ventas(request):
    query = clientes_org(request).filter(hubo_venta=True)
    counts = {'ventas': query.count(), 'liquidados': query.filter(proyecto_liquidado=True).count(),
              'pendientes': query.filter(proyecto_liquidado=False).count()}
    return respuesta({**paginar(_filtrar(query, request), request, 'clientes', cliente_json), 'totales': counts})


@acceso('finanzas')
@api
@require_POST
def liquidacion(request, cliente_id):
    datos = leer_json(request)
    allowed = {'fuente', 'importe_total', 'importe_anticipo', 'fecha_anticipo', 'proyecto_liquidado', 'fecha_liquidacion'}
    if set(datos) - allowed or not {'importe_total', 'importe_anticipo', 'fecha_anticipo', 'proyecto_liquidado'} <= set(datos):
        raise ValueError('Completa importe total, anticipo, fecha y estado de liquidación.')
    if datos.get('fuente', 'directo') != 'directo':
        raise ValueError('Fuente de venta inválida.')
    total = importe(datos['importe_total'], positivo=True)
    anticipo = importe(datos['importe_anticipo'])
    inicio = fecha(datos['fecha_anticipo'], 'Fecha del anticipo')
    liquidado = booleano(datos['proyecto_liquidado'], 'Proyecto liquidado')
    final = fecha(datos.get('fecha_liquidacion'), 'Fecha de liquidación') if liquidado else None
    if anticipo > total or (final and final < inicio):
        raise ValueError('El anticipo no puede superar el total y la liquidación debe ser posterior al anticipo.')
    with transaction.atomic(using='movil'):
        item = get_object_or_404(clientes_org(request).filter(hubo_venta=True).select_for_update(), pk=cliente_id)
        item.monto_venta, item.importe_anticipo, item.fecha_anticipo = total, anticipo, inicio
        item.proyecto_liquidado, item.fecha_liquidacion = liquidado, final
        item.save()
    return respuesta({'ok': True, 'cliente': cliente_json(item), 'mensaje': 'Importes y estado de pago guardados.'})
