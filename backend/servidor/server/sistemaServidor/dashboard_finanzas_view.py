"""Dashboard privado de cobros y gastos operativos mensuales registrados.

Reutiliza las reglas de Reportes Financieros. Los resultados son parciales:
no se infieren costos, impuestos, saldos bancarios ni utilidad neta.
"""
import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import DatabaseError, connections
from django.utils import timezone
from django.views.decorators.http import require_GET

from .finanzas_reportes import SQL_COBROS, calcular_gastos, siguiente_mes
from .finanzas_view import _autorizar, _dinero, _mes_actual, _respuesta, _validar_periodo_tipo


logger = logging.getLogger(__name__)
CIEN = Decimal('100')
CENTESIMA = Decimal('0.01')


def _periodo(mes):
    return f'{mes.year:04d}-{mes.month:02d}'


def _ventana_meses(mes):
    """Hasta seis meses, sin desbordar el límite inferior de datetime.date."""
    meses = [mes]
    while len(meses) < 6 and meses[-1] != date.min:
        ultimo = meses[-1]
        meses.append(date(ultimo.year, ultimo.month - 1, 1) if ultimo.month > 1
                     else date(ultimo.year - 1, 12, 1))
    return list(reversed(meses))


def _porcentaje(numerador, denominador):
    if numerador is None or denominador is None or denominador <= 0:
        return None
    return format((numerador * CIEN / denominador).quantize(
        CENTESIMA, rounding=ROUND_HALF_UP,
    ), '.2f')


def _resultado(resumen):
    gastos = resumen['gastos_mes']
    return resumen['cobros_mes'] - gastos if gastos is not None else None


def _serie(mes, resumen):
    return {
        'mes': _periodo(mes),
        'cobros_mes': _dinero(resumen['cobros_mes']),
        'gastos_mes': _dinero(resumen['gastos_mes']),
        'resultado_operativo': _dinero(_resultado(resumen)),
    }


def leer_meses_dashboard(cursor, mes):
    """Lee el historial de gastos una vez y los cobros de cada mes de la ventana."""
    cursor.execute('''
        SELECT gasto_id, vigente_desde, concepto, monto_mensual
        FROM public.gastos_operativos_historial
        ORDER BY gasto_id, vigente_desde
    ''')
    historial = cursor.fetchall()
    meses = []
    for inicio in _ventana_meses(mes):
        fin = siguiente_mes(inicio)
        cursor.execute(SQL_COBROS, [inicio, fin, inicio, fin, fin])
        anticipos, saldos, acumulado, pendientes = cursor.fetchone()
        meses.append((inicio, {
            **calcular_gastos(historial, inicio),
            'anticipos_mes': anticipos,
            'saldos_mes': saldos,
            'cobros_mes': anticipos + saldos,
            'cobros_acumulados': acumulado,
            'ventas_sin_importes': pendientes,
        }))
    return meses


def construir_dashboard_finanzas(meses):
    """Serializa importes exactos y conserva null cuando falta información."""
    mes, actual = meses[-1]
    anterior = meses[-2][1] if len(meses) > 1 else None
    cobros = actual['cobros_mes']
    gastos = actual['gastos_mes']
    resultado = _resultado(actual)
    advertencias = []
    if gastos is None:
        advertencias.append(
            'No hay historial de gastos operativos para el mes seleccionado. '
            'Los gastos y los indicadores que dependen de ellos están pendientes.'
        )
    if actual['ventas_sin_importes']:
        advertencias.append(
            f"Hay {actual['ventas_sin_importes']} ventas cerradas con importes o fechas de pago pendientes. "
            'Completa sus datos en Gestión de Ventas para incluir todos sus cobros.'
        )
    comparativo = None
    if anterior is not None:
        comparativo = _serie(meses[-2][0], anterior)
        comparativo['periodo'] = comparativo.pop('mes')
    return {
        'ok': True,
        'periodo': _periodo(mes),
        'moneda': 'MXN',
        'parcial': True,
        'resumen': {
            'cobros_mes': _dinero(cobros),
            'anticipos_mes': _dinero(actual['anticipos_mes']),
            'saldos_mes': _dinero(actual['saldos_mes']),
            'gastos_mes': _dinero(gastos),
            'resultado_operativo': _dinero(resultado),
            'margen_operativo_pct': _porcentaje(resultado, cobros),
            'cobertura_gastos_pct': _porcentaje(cobros, gastos),
            'variacion_cobros_pct': _porcentaje(
                cobros - anterior['cobros_mes'], anterior['cobros_mes'],
            ) if anterior is not None else None,
        },
        'comparativo': comparativo,
        'tendencia': [_serie(fecha, resumen) for fecha, resumen in meses],
        'gastos': [
            {'id': gasto['id'], 'concepto': gasto['concepto'], 'monto': _dinero(gasto['monto'])}
            for gasto in actual['gastos_detalle']
        ],
        'ventas_sin_importes': actual['ventas_sin_importes'],
        'inicio_historial_gastos': actual['inicio_gastos'],
        'advertencias': advertencias,
        'alcance': 'Incluye anticipos y saldos cobrados del CRM en su mes de recepción, '
                   'y los gastos operativos mensuales registrados. El resultado y el margen son parciales: '
                   'faltan costos de venta, impuestos y otros movimientos. Los gastos recurrentes '
                   'no confirman pagos realizados; el resultado no representa utilidad neta ni saldo bancario.',
        'actualizado_en': timezone.now().isoformat(),
    }


@require_GET
def resumen_dashboard_finanzas(request):
    _, error = _autorizar(request)
    if error is not None:
        return error
    periodo = request.GET.get('periodo', _periodo(_mes_actual()))
    try:
        mes = _validar_periodo_tipo(periodo, 'estado-resultados')
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    try:
        with connections['neon'].cursor() as cursor:
            meses = leer_meses_dashboard(cursor, mes)
    except DatabaseError:
        logger.exception('Error consultando el dashboard de Finanzas.')
        return _respuesta({
            'ok': False,
            'mensaje': 'No fue posible consultar el dashboard financiero. '
                       'Revisa la conexión y las actualizaciones de Finanzas.',
        }, 503)
    return _respuesta(construir_dashboard_finanzas(meses))
