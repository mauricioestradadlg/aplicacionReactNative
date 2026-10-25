"""Cobros del CRM y costos recurrentes versionados por mes.

Los indicadores calculados son parciales: no representan saldos bancarios,
impuestos ni patrimonio que todavía no se registran en el sistema.
"""
from datetime import date
from decimal import Decimal


CERO = Decimal('0.00')

SQL_COBROS = '''
    WITH ventas AS (
        SELECT v.importe_total, v.importe_anticipo, v.fecha_anticipo,
               v.proyecto_liquidado,
               (v.fecha_liquidacion AT TIME ZONE 'America/Mexico_City')::date AS fecha_final
        FROM public.cierres_ventas v
        WHERE v.hubo_venta = TRUE AND (
            (v.fuente = 'whatsapp' AND EXISTS (
                SELECT 1 FROM public.prospectos_oferta_valor w WHERE w.id = v.prospecto_id
            )) OR
            (v.fuente = 'email-marketing' AND EXISTS (
                SELECT 1 FROM public.leads_magnet l WHERE l.id = v.prospecto_id
            ))
        )
    ), importes_validos AS (
        SELECT * FROM ventas
        WHERE importe_total > 0 AND importe_anticipo >= 0
          AND importe_anticipo <= importe_total AND fecha_anticipo IS NOT NULL
    ), cobros AS (
        SELECT importe_anticipo AS importe, fecha_anticipo AS fecha, 'anticipo' AS clase
        FROM importes_validos
        UNION ALL
        SELECT importe_total - importe_anticipo, fecha_final, 'saldo'
        FROM importes_validos
        WHERE proyecto_liquidado = TRUE AND fecha_final >= fecha_anticipo
    )
    SELECT
        COALESCE(SUM(importe) FILTER (WHERE fecha >= %s AND fecha < %s AND clase = 'anticipo'), 0),
        COALESCE(SUM(importe) FILTER (WHERE fecha >= %s AND fecha < %s AND clase = 'saldo'), 0),
        COALESCE(SUM(importe) FILTER (WHERE fecha < %s), 0),
        (SELECT COUNT(*) FROM ventas WHERE importe_total IS NULL OR importe_anticipo IS NULL
            OR fecha_anticipo IS NULL OR (proyecto_liquidado AND
                (fecha_final IS NULL OR fecha_final < fecha_anticipo)))
    FROM cobros
'''


def siguiente_mes(mes):
    # La API valida el periodo antes de solicitar sus límites mensuales.
    if mes.month == 12:
        return date(mes.year + 1, 1, 1)
    return date(mes.year, mes.month + 1, 1)


def _meses(inicio, fin):
    return (fin.year - inicio.year) * 12 + fin.month - inicio.month + 1


def calcular_gastos(historial, mes):
    """Aplica la última versión vigente y acumula intervalos sin expandir meses.

    historial: filas (gasto_id, vigente_desde, concepto, monto_mensual).
    No se infieren importes anteriores a la primera versión registrada.
    """
    grupos = {}
    inicio = min((fila[1] for fila in historial), default=None)
    if inicio is None or mes < inicio:
        return {
            'gastos_detalle': [], 'gastos_mes': None, 'gastos_acumulados': None,
            'inicio_gastos': inicio.isoformat() if inicio else None,
        }
    for identificador, desde, concepto, monto in historial:
        if desde <= mes:
            grupos.setdefault(str(identificador), []).append((desde, concepto, monto))
    detalle = []
    acumulado = CERO
    for identificador, versiones in grupos.items():
        versiones.sort(key=lambda v: v[0])
        for i, (desde, _, monto) in enumerate(versiones):
            if i + 1 < len(versiones):
                hasta = versiones[i + 1][0]
                meses = _meses(desde, hasta) - 1
            else:
                meses = _meses(desde, mes)
            acumulado += monto * meses
        _, concepto, monto = versiones[-1]
        detalle.append({'id': identificador, 'concepto': concepto, 'monto': monto})
    detalle.sort(key=lambda g: (g['concepto'].casefold(), g['id']))
    return {
        'gastos_detalle': detalle,
        'gastos_mes': sum((g['monto'] for g in detalle), CERO),
        'gastos_acumulados': acumulado,
        'inicio_gastos': inicio.isoformat() if inicio else None,
    }


def leer_resumen(cursor, mes):
    fin = siguiente_mes(mes)
    cursor.execute(SQL_COBROS, [mes, fin, mes, fin, fin])
    anticipos, saldos, acumulado, pendientes = cursor.fetchone()
    cursor.execute('''
        SELECT gasto_id, vigente_desde, concepto, monto_mensual
        FROM public.gastos_operativos_historial
        ORDER BY gasto_id, vigente_desde
    ''')
    gastos = calcular_gastos(cursor.fetchall(), mes)
    return {
        **gastos,
        'anticipos_mes': anticipos,
        'saldos_mes': saldos,
        'cobros_mes': anticipos + saldos,
        'cobros_acumulados': acumulado,
        'ventas_sin_importes': pendientes,
    }
