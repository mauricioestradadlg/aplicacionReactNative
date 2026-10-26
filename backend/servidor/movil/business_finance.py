"""Cobros reales y gastos versionados: mismas reglas contables del sistema original."""
import re
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

# Estas funciones son cálculos puros. No ejecutan consultas al sistema web.
from server.sistemaServidor.finanzas_reportes import calcular_gastos, siguiente_mes
from server.sistemaServidor.finanzas_view import construir_reporte

from .auth import acceso, leer_json, respuesta
from .business_common import CERO, api, dinero, hoy, importe, texto
from .models import Cliente, GastoHistorial, GastoOperativo


def _mes():
    return hoy().replace(day=1)


def _periodo(request):
    value = request.GET.get('periodo', _mes().strftime('%Y-%m'))
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value):
        raise ValueError('Selecciona un mes válido en formato AAAA-MM.')
    mes = date.fromisoformat(value + '-01')
    if mes.year < 1900 or mes > _mes():
        raise ValueError('Selecciona un mes entre 1900-01 y el mes actual.')
    return mes


def _historial(request):
    return list(GastoHistorial.objects.filter(gasto__organizacion=request.organizacion_movil)
                .order_by('gasto_id', 'vigente_desde')
                .values_list('gasto_id', 'vigente_desde', 'concepto', 'monto_mensual'))


def _cobros(request):
    # Las fechas de cobro son independientes del alta del cliente y de la venta.
    ventas = Cliente.objects.filter(organizacion=request.organizacion_movil, hubo_venta=True)
    incompleta = Q(monto_venta__isnull=True) | Q(importe_anticipo__isnull=True) | Q(fecha_anticipo__isnull=True)
    final_invalida = Q(proyecto_liquidado=True) & (Q(fecha_liquidacion__isnull=True) | Q(fecha_liquidacion__lt=F('fecha_anticipo')))
    pendientes = ventas.filter(incompleta | final_invalida).count()
    validas = ventas.exclude(incompleta)
    # Agrupar en SQL evita transferir cada cliente al generar la tendencia.
    result = [(item['fecha_anticipo'], item['importe'], 'anticipo') for item in
              validas.values('fecha_anticipo').annotate(importe=Sum('importe_anticipo'))]
    result.extend((item['fecha_liquidacion'], item['importe'], 'saldo') for item in
                  validas.filter(proyecto_liquidado=True, fecha_liquidacion__gte=F('fecha_anticipo'))
                  .values('fecha_liquidacion').annotate(importe=Sum(F('monto_venta') - F('importe_anticipo'))))
    return result, pendientes


def _resumen(mes, historial, cobros, pendientes):
    fin = siguiente_mes(mes)
    anticipos = sum((amount for dia, amount, clase in cobros if mes <= dia < fin and clase == 'anticipo'), CERO)
    saldos = sum((amount for dia, amount, clase in cobros if mes <= dia < fin and clase == 'saldo'), CERO)
    return {**calcular_gastos(historial, mes), 'anticipos_mes': anticipos, 'saldos_mes': saldos,
            'cobros_mes': anticipos + saldos,
            'cobros_acumulados': sum((amount for dia, amount, _ in cobros if dia < fin), CERO),
            'ventas_sin_importes': pendientes}


def _gastos(request):
    items = list(GastoOperativo.objects.filter(organizacion=request.organizacion_movil, activo=True).order_by('creado_en', 'id'))
    return {'ok': True, 'gastos': [{'id': str(g.id), 'concepto': g.concepto, 'monto_mensual': dinero(g.monto_mensual)} for g in items],
            'total_mensual': dinero(sum((g.monto_mensual for g in items), CERO))}


def _guardar_gasto(request, item):
    datos = leer_json(request)
    if set(datos) != {'concepto', 'monto_mensual'}:
        raise ValueError('Completa concepto y monto mensual.')
    item.concepto = texto(datos['concepto'], 'Concepto', 150)
    item.monto_mensual = importe(datos['monto_mensual'])
    item.save()
    GastoHistorial.objects.update_or_create(gasto=item, vigente_desde=_mes(), defaults={
        'concepto': item.concepto, 'monto_mensual': item.monto_mensual,
    })


@acceso('finanzas')
@api
@require_http_methods(['GET', 'POST'])
def gastos(request):
    if request.method == 'POST':
        with transaction.atomic(using='movil'):
            _guardar_gasto(request, GastoOperativo(organizacion=request.organizacion_movil))
        return respuesta({**_gastos(request), 'mensaje': 'Gasto mensual guardado.'}, 201)
    return respuesta(_gastos(request))


@acceso('finanzas')
@api
@require_http_methods(['POST', 'PATCH', 'DELETE'])
def editar_gasto(request, gasto_id):
    with transaction.atomic(using='movil'):
        item = get_object_or_404(GastoOperativo.objects.select_for_update(), pk=gasto_id,
                                organizacion=request.organizacion_movil, activo=True)
        if request.method == 'DELETE':
            item.activo = False
            item.save(update_fields=['activo', 'actualizado_en'])
            GastoHistorial.objects.update_or_create(gasto=item, vigente_desde=_mes(), defaults={
                'concepto': item.concepto, 'monto_mensual': CERO,
            })
        else:
            _guardar_gasto(request, item)
    return respuesta({**_gastos(request), 'mensaje': 'Gasto actualizado; el historial anterior se conserva.'})


def _resultado(resumen):
    return resumen['cobros_mes'] - resumen['gastos_mes'] if resumen['gastos_mes'] is not None else None


def _pct(numerador, denominador):
    if numerador is None or denominador is None or denominador <= 0:
        return None
    return dinero(numerador * Decimal('100') / denominador)


def _serie(mes, resumen):
    return {'mes': mes.strftime('%Y-%m'), 'cobros_mes': dinero(resumen['cobros_mes']),
            'gastos_mes': dinero(resumen['gastos_mes']), 'resultado_operativo': dinero(_resultado(resumen))}


@acceso('finanzas')
@api
@require_GET
def dashboard_finanzas(request):
    mes = _periodo(request)
    historial = _historial(request)
    cobros, pendientes = _cobros(request)
    resumen = _resumen(mes, historial, cobros, pendientes)
    meses = []
    for offset in range(5, -1, -1):
        ordinal = mes.year * 12 + mes.month - 1 - offset
        anio, month = divmod(ordinal, 12)
        if anio >= 1900:
            inicio = date(anio, month + 1, 1)
            meses.append(_serie(inicio, _resumen(inicio, historial, cobros, pendientes)))
    ordinal = mes.year * 12 + mes.month - 2
    year, month = divmod(ordinal, 12)
    previo = date(year, month + 1, 1) if year >= 1900 else None
    anterior = _resumen(previo, historial, cobros, pendientes) if previo else None
    reporte = construir_reporte(mes.strftime('%Y-%m'), 'estado-resultados', resumen)
    return respuesta({'ok': True, 'periodo': mes.strftime('%Y-%m'),
                      'resumen': {
                          **{k: dinero(resumen[k]) for k in ('cobros_mes', 'gastos_mes', 'anticipos_mes', 'saldos_mes')},
                          'resultado_operativo': dinero(_resultado(resumen)),
                          'margen_operativo_pct': _pct(_resultado(resumen), resumen['cobros_mes']),
                          'cobertura_gastos_pct': _pct(resumen['cobros_mes'], resumen['gastos_mes']),
                          'variacion_cobros_pct': _pct(resumen['cobros_mes'] - anterior['cobros_mes'], anterior['cobros_mes']) if anterior else None,
                      }, 'tendencia': meses,
                      'comparativo': {'periodo': previo.strftime('%Y-%m'), **{k: dinero(anterior[k]) for k in ('cobros_mes', 'gastos_mes')},
                                      'resultado_operativo': dinero(_resultado(anterior))} if anterior else None,
                      'gastos': [{**g, 'monto': dinero(g['monto'])} for g in resumen['gastos_detalle']],
                      'advertencias': reporte['advertencias'], 'alcance': reporte['alcance'],
                      'ventas_sin_importes': pendientes, 'inicio_historial_gastos': resumen['inicio_gastos'],
                      'actualizado_en': timezone.now().isoformat()})


@acceso('finanzas')
@api
@require_GET
def reportes(request):
    mes = _periodo(request)
    tipo = request.GET.get('tipo', 'estado-resultados')
    if tipo not in ('estado-resultados', 'balance-general', 'flujo-efectivo'):
        raise ValueError('Selecciona un reporte financiero válido.')
    cobros, pendientes = _cobros(request)
    resumen = _resumen(mes, _historial(request), cobros, pendientes)
    return respuesta(construir_reporte(mes.strftime('%Y-%m'), tipo, resumen))
