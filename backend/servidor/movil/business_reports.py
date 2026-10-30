"""Reportes de ventas cobradas completas, sin depender del CRM web original."""
from .business_common import dinero


CAMPOS = {
    'estado-resultados': (
        ('ingresos', 'Ingresos'), ('costos_ventas', 'Costos de ventas'),
        ('gastos_operativos', 'Gastos operativos'), ('otros_gastos', 'Otros gastos'),
        ('impuestos', 'Impuestos'),
    ),
    'balance-general': (
        ('efectivo', 'Efectivo y equivalentes'), ('cuentas_cobrar', 'Cuentas por cobrar'),
        ('otros_activos_corrientes', 'Otros activos corrientes'),
        ('activos_no_corrientes', 'Activos no corrientes'),
        ('pasivos_corrientes', 'Pasivos corrientes'), ('pasivos_no_corrientes', 'Pasivos no corrientes'),
        ('capital_aportado', 'Capital aportado'), ('resultados_acumulados', 'Resultados acumulados'),
    ),
    'flujo-efectivo': (
        ('saldo_inicial', 'Saldo inicial de efectivo'), ('cobros_operacion', 'Cobros de operación'),
        ('pagos_operacion', 'Pagos de operación'), ('cobros_inversion', 'Cobros de inversión'),
        ('pagos_inversion', 'Pagos de inversión'), ('cobros_financiamiento', 'Cobros de financiamiento'),
        ('pagos_financiamiento', 'Pagos de financiamiento'),
    ),
}

LINEAS = {
    'estado-resultados': (
        ('ingresos', 'Ventas cobradas del mes', 'total'),
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
        ('cobros_operacion', 'Cobros de ventas del mes', 'total'),
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


def construir_reporte(periodo, tipo, resumen):
    """Cada venta aporta un solo cobro; conceptos desconocidos conservan null."""
    cobros, gastos = resumen['cobros_mes'], resumen['gastos_mes']
    resultado = cobros - gastos if gastos is not None else None
    valores = {
        'estado-resultados': {'ingresos': cobros, 'gastos_operativos': gastos},
        'balance-general': {},
        'flujo-efectivo': {
            'cobros_operacion': cobros, 'pagos_operacion': gastos, 'flujo_operacion': resultado,
        },
    }[tipo]
    lineas = [
        {'clave': clave, 'concepto': concepto, 'importe': dinero(valores.get(clave)), 'tipo': clase}
        for clave, concepto, clase in LINEAS[tipo]
    ]
    if tipo in ('estado-resultados', 'flujo-efectivo'):
        clave_gasto = 'gastos_operativos' if tipo == 'estado-resultados' else 'pagos_operacion'
        indice = next(i for i, fila in enumerate(lineas) if fila['clave'] == clave_gasto)
        lineas[indice].update(tipo='total', concepto='Total de gastos operativos mensuales registrados')
        lineas[indice:indice] = [
            {'clave': 'gasto-' + g['id'], 'concepto': 'Gasto mensual: ' + g['concepto'],
             'importe': dinero(g['monto']), 'tipo': 'detalle'}
            for g in resumen['gastos_detalle']
        ]
        if tipo == 'estado-resultados':
            indice = next(i for i, fila in enumerate(lineas) if fila['clave'] == clave_gasto)
            lineas.insert(indice + 1, {
                'clave': 'resultado_registrado', 'concepto': 'Ventas cobradas menos gastos operativos registrados',
                'importe': dinero(resultado), 'tipo': 'total',
            })
    else:
        acumulado = resumen['cobros_acumulados']
        gastos_acumulados = resumen['gastos_acumulados']
        lineas[0:0] = [
            {'clave': 'cobros_acumulados', 'concepto': 'Ventas cobradas acumuladas',
             'importe': dinero(acumulado), 'tipo': 'detalle'},
            {'clave': 'gastos_acumulados', 'concepto': 'Gastos operativos acumulados registrados',
             'importe': dinero(gastos_acumulados), 'tipo': 'detalle'},
            {'clave': 'variacion_operativa_acumulada',
             'concepto': 'Variación acumulada por ventas cobradas menos gastos registrados',
             'importe': dinero(acumulado - gastos_acumulados) if gastos_acumulados is not None else None,
             'tipo': 'total'},
        ]
    advertencias = []
    if gastos is None:
        advertencias.append('No hay historial de gastos operativos para el mes seleccionado. '
                            'Los gastos y resultados que dependen de ellos se muestran como pendientes.')
    if resumen['ventas_sin_importes']:
        advertencias.append(
            f"Hay {resumen['ventas_sin_importes']} ventas con importe o fecha de venta inválidos o pendientes."
        )
    return {
        'ok': True, 'periodo': periodo, 'tipo': tipo, 'guardado': False,
        'conectado': True, 'parcial': True, 'base': 'ventas_cobradas_y_gastos_mensuales_registrados',
        'campos': [
            {'clave': clave, 'etiqueta': etiqueta, 'valor': dinero(valores.get(clave))}
            for clave, etiqueta in CAMPOS[tipo]
        ],
        'lineas': lineas, 'advertencias': advertencias,
        'ventas_sin_importes': resumen['ventas_sin_importes'],
        'inicio_historial_gastos': resumen['inicio_gastos'],
        'alcance': 'Las ventas se cobran por su importe total y se contabilizan una sola vez en su fecha de venta. '
                   'Los gastos operativos registrados se aplican como egresos mensuales.',
        'pendientes': 'Los saldos iniciales, otros activos y pasivos, costos e impuestos aún no están registrados. '
                      '«—» indica información pendiente; los resultados mostrados son parciales.',
    }
