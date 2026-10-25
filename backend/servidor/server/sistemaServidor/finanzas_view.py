"""Finanzas privadas: gastos mensuales e indicadores de cobros del CRM."""
import json
import logging
import re
from datetime import date
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.db import DatabaseError, connections, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .resenas_admin_view import _autorizar_admin
from .finanzas_reportes import leer_resumen

logger = logging.getLogger(__name__)
MAX_IMPORTE = Decimal('9999999999.99')
PATRON_IMPORTE = re.compile(r'-?[0-9]+(?:\.[0-9]{1,2})?\Z')
PATRON_PERIODO = re.compile(r'[0-9]{4}-[0-9]{2}\Z')

CAMPOS = {
    'estado-resultados': (
        ('ingresos', 'Ingresos'),
        ('costos_ventas', 'Costos de ventas'),
        ('gastos_operativos', 'Gastos operativos'),
        ('otros_gastos', 'Otros gastos'),
        ('impuestos', 'Impuestos'),
    ),
    'balance-general': (
        ('efectivo', 'Efectivo y equivalentes'),
        ('cuentas_cobrar', 'Cuentas por cobrar'),
        ('otros_activos_corrientes', 'Otros activos corrientes'),
        ('activos_no_corrientes', 'Activos no corrientes'),
        ('pasivos_corrientes', 'Pasivos corrientes'),
        ('pasivos_no_corrientes', 'Pasivos no corrientes'),
        ('capital_aportado', 'Capital aportado'),
        ('resultados_acumulados', 'Resultados acumulados'),
    ),
    'flujo-efectivo': (
        ('saldo_inicial', 'Saldo inicial de efectivo'),
        ('cobros_operacion', 'Cobros de operación'),
        ('pagos_operacion', 'Pagos de operación'),
        ('cobros_inversion', 'Cobros de inversión'),
        ('pagos_inversion', 'Pagos de inversión'),
        ('cobros_financiamiento', 'Cobros de financiamiento'),
        ('pagos_financiamiento', 'Pagos de financiamiento'),
    ),
}

LINEAS = {
    'estado-resultados': (
        ('ingresos', 'Ingresos', 'detalle'),
        ('costos_ventas', 'Costos de ventas', 'detalle'),
        ('utilidad_bruta', 'Utilidad bruta', 'total'),
        ('gastos_operativos', 'Gastos operativos', 'detalle'),
        ('utilidad_operativa', 'Utilidad operativa', 'total'),
        ('otros_gastos', 'Otros gastos', 'detalle'),
        ('utilidad_antes_impuestos', 'Utilidad antes de impuestos', 'total'),
        ('impuestos', 'Impuestos', 'detalle'),
        ('utilidad_neta', 'Utilidad neta', 'total'),
    ),
    'balance-general': (
        ('efectivo', 'Efectivo y equivalentes', 'detalle'),
        ('cuentas_cobrar', 'Cuentas por cobrar', 'detalle'),
        ('otros_activos_corrientes', 'Otros activos corrientes', 'detalle'),
        ('activos_corrientes', 'Total de activos corrientes', 'total'),
        ('activos_no_corrientes', 'Activos no corrientes', 'detalle'),
        ('activos', 'Total de activos', 'total'),
        ('pasivos_corrientes', 'Pasivos corrientes', 'detalle'),
        ('pasivos_no_corrientes', 'Pasivos no corrientes', 'detalle'),
        ('pasivos', 'Total de pasivos', 'total'),
        ('capital_aportado', 'Capital aportado', 'detalle'),
        ('resultados_acumulados', 'Resultados acumulados', 'detalle'),
        ('patrimonio', 'Total de patrimonio', 'total'),
        ('pasivos_patrimonio', 'Total de pasivos y patrimonio', 'total'),
        ('diferencia_balance', 'Diferencia: activos menos pasivos y patrimonio', 'total'),
    ),
    'flujo-efectivo': (
        ('saldo_inicial', 'Saldo inicial de efectivo', 'detalle'),
        ('cobros_operacion', 'Cobros de operación', 'detalle'),
        ('pagos_operacion', 'Pagos de operación', 'detalle'),
        ('flujo_operacion', 'Flujo neto de operación', 'total'),
        ('cobros_inversion', 'Cobros de inversión', 'detalle'),
        ('pagos_inversion', 'Pagos de inversión', 'detalle'),
        ('flujo_inversion', 'Flujo neto de inversión', 'total'),
        ('cobros_financiamiento', 'Cobros de financiamiento', 'detalle'),
        ('pagos_financiamiento', 'Pagos de financiamiento', 'detalle'),
        ('flujo_financiamiento', 'Flujo neto de financiamiento', 'total'),
        ('variacion_efectivo', 'Variación neta de efectivo', 'total'),
        ('saldo_final', 'Saldo final de efectivo', 'total'),
    ),
}


def _respuesta(datos, estado=200):
    respuesta = JsonResponse(datos, status=estado)
    respuesta['Cache-Control'] = 'no-store'
    respuesta['Pragma'] = 'no-cache'
    return respuesta


def _autorizar(request):
    administrador, error = _autorizar_admin(request)
    if error is not None and error.status_code == 403:
        error = _respuesta({'ok': False, 'mensaje': 'Solo administradores pueden acceder a Finanzas.'}, 403)
    return administrador, error


def _importe(valor):
    if not isinstance(valor, str) or len(valor) > 24:
        raise ValueError('Captura los importes como números decimales con máximo dos decimales.')
    texto = valor.strip()
    if not PATRON_IMPORTE.fullmatch(texto):
        raise ValueError('Captura los importes sin separadores de miles y con máximo dos decimales.')
    importe = Decimal(texto)
    if importe > MAX_IMPORTE or importe < 0:
        raise ValueError('El importe está fuera del rango permitido.')
    return importe if importe else Decimal('0.00')


def _dinero(valor):
    return format(valor, '.2f') if valor is not None else None


def _mes_actual():
    return timezone.localdate(timezone=ZoneInfo('America/Mexico_City')).replace(day=1)


def _registrar_version(cursor, gasto_id):
    cursor.execute('''
        INSERT INTO public.gastos_operativos_historial
            (gasto_id, vigente_desde, concepto, monto_mensual)
        SELECT id, %s, concepto, monto_mensual
        FROM public.gastos_operativos WHERE id = %s
        ON CONFLICT (gasto_id, vigente_desde) DO UPDATE
        SET concepto = EXCLUDED.concepto, monto_mensual = EXCLUDED.monto_mensual,
            actualizado_en = NOW()
    ''', [_mes_actual(), str(gasto_id)])


def _leer_json(request, claves):
    if (request.content_type or '').split(';', 1)[0].lower() != 'application/json':
        return None, _respuesta({'ok': False, 'mensaje': 'Envía datos JSON.'}, 415)
    if len(request.body) > 8192:
        return None, _respuesta({'ok': False, 'mensaje': 'Solicitud demasiado grande.'}, 413)
    try:
        datos = json.loads(request.body.decode('utf-8'))
        if not isinstance(datos, dict) or set(datos) != set(claves):
            raise ValueError
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None, _respuesta({'ok': False, 'mensaje': 'Envía todos los campos requeridos en un objeto JSON válido.'}, 400)
    return datos, None


def _validar_gasto(datos):
    concepto = datos['concepto']
    if not isinstance(concepto, str) or not 1 <= len(concepto.strip()) <= 150:
        raise ValueError('El concepto debe tener entre 1 y 150 caracteres.')
    if '\x00' in concepto:
        raise ValueError('El concepto contiene caracteres inválidos.')
    try:
        concepto.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError('El concepto contiene caracteres inválidos.') from None
    return concepto.strip(), _importe(datos['monto_mensual'])


def _leer_gastos(cursor):
    cursor.execute('''
        SELECT id, concepto, monto_mensual
        FROM public.gastos_operativos
        ORDER BY creado_en, id
    ''')
    filas = cursor.fetchall()
    return {
        'ok': True,
        'gastos': [{'id': str(f[0]), 'concepto': f[1], 'monto_mensual': _dinero(f[2])} for f in filas],
        'total_mensual': _dinero(sum((f[2] for f in filas), Decimal('0.00'))),
    }


def _error_base():
    return _respuesta({
        'ok': False,
        'mensaje': 'No fue posible consultar o guardar Finanzas. Revisa la conexión y la instalación de las actualizaciones de Finanzas.',
    }, 503)


@require_http_methods(['GET', 'POST'])
def gastos_operativos(request):
    administrador, error = _autorizar(request)
    if error is not None:
        return error
    if request.method == 'POST':
        datos, error = _leer_json(request, ('concepto', 'monto_mensual'))
        if error is not None:
            return error
        try:
            concepto, monto = _validar_gasto(datos)
        except ValueError as error:
            return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
        try:
            with transaction.atomic(using='neon'):
                with connections['neon'].cursor() as cursor:
                    gasto_id = uuid4()
                    cursor.execute('''
                        INSERT INTO public.gastos_operativos
                            (id, concepto, monto_mensual, actualizado_por)
                        VALUES (%s, %s, %s, %s)
                    ''', [str(gasto_id), concepto, monto, administrador[0]])
                    _registrar_version(cursor, gasto_id)
                    respuesta = _leer_gastos(cursor)
        except DatabaseError:
            logger.exception('Error creando gasto operativo.')
            return _error_base()
        respuesta['mensaje'] = 'Gasto operativo guardado.'
        return _respuesta(respuesta, 201)
    try:
        with connections['neon'].cursor() as cursor:
            respuesta = _leer_gastos(cursor)
    except DatabaseError:
        logger.exception('Error consultando gastos operativos.')
        return _error_base()
    return _respuesta(respuesta)


@require_POST
def editar_gasto_operativo(request, gasto_id):
    administrador, error = _autorizar(request)
    if error is not None:
        return error
    datos, error = _leer_json(request, ('concepto', 'monto_mensual'))
    if error is not None:
        return error
    try:
        concepto, monto = _validar_gasto(datos)
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    try:
        with transaction.atomic(using='neon'):
            with connections['neon'].cursor() as cursor:
                cursor.execute('''
                    UPDATE public.gastos_operativos
                    SET concepto = %s, monto_mensual = %s,
                        actualizado_por = %s, actualizado_en = NOW()
                    WHERE id = %s RETURNING id
                ''', [concepto, monto, administrador[0], str(gasto_id)])
                if cursor.fetchone() is None:
                    return _respuesta({'ok': False, 'mensaje': 'El gasto operativo ya no existe.'}, 404)
                _registrar_version(cursor, gasto_id)
                respuesta = _leer_gastos(cursor)
    except DatabaseError:
        logger.exception('Error editando gasto operativo.')
        return _error_base()
    respuesta['mensaje'] = 'Gasto operativo actualizado.'
    return _respuesta(respuesta)


def _validar_periodo_tipo(periodo, tipo):
    if not isinstance(periodo, str) or not PATRON_PERIODO.fullmatch(periodo):
        raise ValueError('Selecciona un mes válido en formato AAAA-MM.')
    try:
        fecha = date.fromisoformat(periodo + '-01')
    except ValueError:
        raise ValueError('Selecciona un mes válido en formato AAAA-MM.') from None
    if not isinstance(tipo, str) or tipo not in CAMPOS:
        raise ValueError('Selecciona un reporte financiero válido.')
    if fecha > _mes_actual():
        raise ValueError('Selecciona el mes actual o uno anterior.')
    return fecha


def construir_reporte(periodo, tipo, resumen):
    """Conecta lo registrado; los saldos y conceptos desconocidos siguen null."""
    cobros = resumen['cobros_mes']
    gastos = resumen['gastos_mes']
    valores = {
        'estado-resultados': {'ingresos': cobros, 'gastos_operativos': gastos},
        'balance-general': {},
        'flujo-efectivo': {
            'cobros_operacion': cobros, 'pagos_operacion': gastos,
            'flujo_operacion': cobros - gastos if gastos is not None else None,
        },
    }[tipo]
    lineas = [
        {'clave': clave, 'concepto': concepto,
         'importe': _dinero(valores[clave]) if clave in valores else None, 'tipo': clase}
        for clave, concepto, clase in LINEAS[tipo]
    ]
    desglose_gastos = [
        {'clave': 'gasto-' + g['id'], 'concepto': 'Gasto mensual: ' + g['concepto'],
         'importe': _dinero(g['monto']), 'tipo': 'detalle'}
        for g in resumen['gastos_detalle']
    ]
    if tipo in ('estado-resultados', 'flujo-efectivo'):
        clave_gasto = 'gastos_operativos' if tipo == 'estado-resultados' else 'pagos_operacion'
        indice = next(i for i, fila in enumerate(lineas) if fila['clave'] == clave_gasto)
        lineas[indice]['tipo'] = 'total'
        lineas[indice]['concepto'] = 'Total de gastos operativos mensuales registrados'
        lineas[indice:indice] = desglose_gastos
        clave_cobro = 'ingresos' if tipo == 'estado-resultados' else 'cobros_operacion'
        indice = next(i for i, fila in enumerate(lineas) if fila['clave'] == clave_cobro)
        lineas[indice]['concepto'] = 'Ingresos cobrados del mes' if tipo == 'estado-resultados' else 'Cobros de operación del mes'
        lineas[indice]['tipo'] = 'total'
        lineas[indice:indice] = [
            {'clave': 'anticipos_mes', 'concepto': 'Anticipos recibidos del CRM',
             'importe': _dinero(resumen['anticipos_mes']), 'tipo': 'detalle'},
            {'clave': 'saldos_mes', 'concepto': 'Saldos finales recibidos del CRM',
             'importe': _dinero(resumen['saldos_mes']), 'tipo': 'detalle'},
        ]
        if tipo == 'estado-resultados':
            indice = next(i for i, fila in enumerate(lineas) if fila['clave'] == 'gastos_operativos')
            lineas.insert(indice + 1, {
                'clave': 'resultado_registrado', 'concepto': 'Cobros menos gastos operativos registrados',
                'importe': _dinero(cobros - gastos) if gastos is not None else None, 'tipo': 'total',
            })
    else:
        # Indicadores complementarios, separados de efectivo/patrimonio reales.
        lineas[0:0] = [
            {'clave': 'cobros_acumulados', 'concepto': 'Cobros acumulados registrados del CRM',
             'importe': _dinero(resumen['cobros_acumulados']), 'tipo': 'detalle'},
            {'clave': 'gastos_acumulados', 'concepto': 'Gastos operativos acumulados registrados',
             'importe': _dinero(resumen['gastos_acumulados']), 'tipo': 'detalle'},
            {'clave': 'variacion_operativa_acumulada',
             'concepto': 'Variación acumulada por cobros menos gastos registrados',
             'importe': _dinero(resumen['cobros_acumulados'] - resumen['gastos_acumulados'])
             if resumen['gastos_acumulados'] is not None else None,
             'tipo': 'total'},
        ]
    advertencias = []
    if gastos is None:
        advertencias.append('No hay historial de gastos operativos para el mes seleccionado. '
                            'Los gastos y resultados que dependen de ellos se muestran como pendientes.')
    if resumen['ventas_sin_importes']:
        advertencias.append(
            f"Hay {resumen['ventas_sin_importes']} ventas cerradas con importes o fechas de pago pendientes. "
            'Completa sus datos en Gestión de Ventas para incluir todos sus cobros.'
        )
    return {
        'ok': True,
        'periodo': periodo,
        'tipo': tipo,
        'guardado': False,
        'conectado': True,
        'parcial': True,
        'base': 'cobros_y_gastos_mensuales_registrados',
        'campos': [
            {'clave': clave, 'etiqueta': etiqueta,
             'valor': _dinero(valores[clave]) if clave in valores else None}
            for clave, etiqueta in CAMPOS[tipo]
        ],
        'lineas': lineas,
        'advertencias': advertencias,
        'ventas_sin_importes': resumen['ventas_sin_importes'],
        'inicio_historial_gastos': resumen['inicio_gastos'],
        'alcance': 'Incluye anticipos y saldos cobrados del CRM en su mes de recepción. '
                   'Los gastos operativos registrados se aplican como egresos mensuales.',
        'pendientes': 'Los saldos iniciales, otros activos y pasivos, costos e impuestos aún no están registrados. '
                      '«—» indica información pendiente; los resultados mostrados son parciales.',
    }


@require_GET
def reportes_financieros(request):
    _, error = _autorizar(request)
    if error is not None:
        return error
    datos = request.GET
    periodo, tipo = datos.get('periodo'), datos.get('tipo')
    try:
        mes = _validar_periodo_tipo(periodo, tipo)
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    try:
        with connections['neon'].cursor() as cursor:
            resumen = leer_resumen(cursor, mes)
    except DatabaseError:
        logger.exception('Error consultando importes de reportes financieros.')
        return _error_base()
    return _respuesta(construir_reporte(periodo, tipo, resumen))
