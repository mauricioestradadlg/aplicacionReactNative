"""Reglas de cobros y recurrencia: sin conexiones ni escrituras en Neon.

El CTE se ejecuta sobre SQLite en memoria adaptando únicamente placeholders
y la expresión de fecha local de PostgreSQL. Los fixtures usan fechas sin hora;
esta prueba cubre la selección y agregación, no la conversión horaria de Neon.
"""
import sqlite3
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from django.test import SimpleTestCase

from .finanzas_reportes import SQL_COBROS, calcular_gastos, leer_resumen
from .finanzas_view import construir_reporte


OCTUBRE = date(2026, 10, 1)
NOVIEMBRE = date(2026, 11, 1)
DICIEMBRE = date(2026, 12, 1)


class CobrosSQLTests(SimpleTestCase):
    def setUp(self):
        self.base = sqlite3.connect(':memory:')
        self.addCleanup(self.base.close)
        self.base.execute("ATTACH DATABASE ':memory:' AS public")
        self.base.execute('''
            CREATE TABLE public.cierres_ventas (
                fuente TEXT, prospecto_id TEXT, hubo_venta BOOLEAN,
                importe_total NUMERIC, importe_anticipo NUMERIC, fecha_anticipo TEXT,
                proyecto_liquidado BOOLEAN, fecha_liquidacion TEXT,
                PRIMARY KEY (fuente, prospecto_id)
            )
        ''')
        self.base.execute('CREATE TABLE public.prospectos_oferta_valor (id TEXT PRIMARY KEY)')
        self.base.execute('CREATE TABLE public.leads_magnet (id TEXT PRIMARY KEY)')
        self.sql = SQL_COBROS.replace(
            "(v.fecha_liquidacion AT TIME ZONE 'America/Mexico_City')::date",
            'date(v.fecha_liquidacion)',
        ).replace('%s', '?')

    def venta(self, identificador='cliente', fuente='whatsapp', total=6000, anticipo=3000,
              fecha_anticipo='2026-10-10', liquidado=False, fecha_final=None,
              cerrada=True, existe=True):
        if existe:
            tabla = 'prospectos_oferta_valor' if fuente == 'whatsapp' else 'leads_magnet'
            self.base.execute(f'INSERT OR IGNORE INTO public.{tabla} VALUES (?)', [identificador])
        self.base.execute('INSERT INTO public.cierres_ventas VALUES (?, ?, ?, ?, ?, ?, ?, ?)', [
            fuente, identificador, cerrada, total, anticipo, fecha_anticipo, liquidado, fecha_final,
        ])

    def consultar(self, inicio, fin):
        return self.base.execute(self.sql, [inicio, fin, inicio, fin, fin]).fetchone()

    def test_venta_pendiente_solo_incluye_anticipo(self):
        self.venta(fecha_final='2026-10-20')
        self.assertEqual(self.consultar('2026-10-01', '2026-11-01'), (3000, 0, 3000, 0))
        self.assertEqual(self.consultar('2026-11-01', '2026-12-01'), (0, 0, 3000, 0))

    def test_liquidar_en_otro_mes_agrega_saldo_y_no_repite_total(self):
        self.venta(liquidado=True, fecha_final='2026-11-15')
        octubre = self.consultar('2026-10-01', '2026-11-01')
        noviembre = self.consultar('2026-11-01', '2026-12-01')
        self.assertEqual(octubre, (3000, 0, 3000, 0))
        self.assertEqual(noviembre, (0, 3000, 6000, 0))
        self.assertEqual(sum(octubre[:2]) + sum(noviembre[:2]), 6000)

    def test_liquidar_mismo_mes_incluye_total_una_vez_y_anticipo_real(self):
        # El primer pago puede incluir cargos completos de dominio.
        self.venta(total=6500, anticipo=3500, liquidado=True, fecha_final='2026-10-25')
        self.assertEqual(self.consultar('2026-10-01', '2026-11-01'), (3500, 3000, 6500, 0))

    def test_limites_del_mes_separan_anticipo_y_saldo(self):
        self.venta(fecha_anticipo='2026-10-31', liquidado=True, fecha_final='2026-11-01')
        self.assertEqual(self.consultar('2026-10-01', '2026-11-01'), (3000, 0, 3000, 0))
        self.assertEqual(self.consultar('2026-11-01', '2026-12-01'), (0, 3000, 6000, 0))

    def test_dos_fuentes_mismo_id_y_exclusion_de_no_cerradas_o_eliminadas(self):
        self.venta(identificador='compartido')
        self.venta(identificador='compartido', fuente='email-marketing', total=10000, anticipo=4500)
        self.venta(identificador='sin-cerrar', cerrada=False)
        self.venta(identificador='eliminado', existe=False)
        self.assertEqual(self.consultar('2026-10-01', '2026-11-01'), (7500, 0, 7500, 0))

    def test_venta_sin_importes_se_advierte_y_no_se_rellena_con_precio_catalogo(self):
        self.venta(total=None, anticipo=None, fecha_anticipo=None)
        self.assertEqual(self.consultar('2026-10-01', '2026-11-01'), (0, 0, 0, 1))

    def test_liquidacion_sin_fecha_valida_conserva_anticipo_y_advierte(self):
        self.venta(liquidado=True, fecha_final='2026-10-01')
        self.assertEqual(self.consultar('2026-10-01', '2026-11-01'), (3000, 0, 3000, 1))


class GastosHistorialTests(SimpleTestCase):
    def setUp(self):
        self.render = uuid4()
        self.meta = uuid4()
        self.historial = [
            (self.meta, NOVIEMBRE, 'Publicidad', Decimal('3000.00')),
            (self.render, NOVIEMBRE, 'Render actualizado', Decimal('200.00')),
            (self.render, OCTUBRE, 'Render', Decimal('150.00')),
        ]

    def test_mes_anterior_a_primera_version_no_inventa_gastos_pasados(self):
        datos = calcular_gastos(self.historial, date(2026, 9, 1))
        self.assertEqual(datos, {
            'gastos_detalle': [], 'gastos_mes': None,
            'gastos_acumulados': None, 'inicio_gastos': '2026-10-01',
        })

    def test_historial_vacio_es_pendiente_en_vez_de_cero(self):
        self.assertEqual(calcular_gastos([], OCTUBRE), {
            'gastos_detalle': [], 'gastos_mes': None,
            'gastos_acumulados': None, 'inicio_gastos': None,
        })

    def test_cambio_posterior_no_reescribe_mes_previo(self):
        datos = calcular_gastos(self.historial, OCTUBRE)
        self.assertEqual(datos['gastos_mes'], Decimal('150.00'))
        self.assertEqual(datos['gastos_acumulados'], Decimal('150.00'))
        self.assertEqual(datos['gastos_detalle'][0]['concepto'], 'Render')
        self.assertEqual(datos['inicio_gastos'], '2026-10-01')

    def test_nueva_version_y_nuevo_gasto_se_aplican_desde_su_mes(self):
        datos = calcular_gastos(self.historial, NOVIEMBRE)
        self.assertEqual(datos['gastos_mes'], Decimal('3200.00'))
        self.assertEqual(datos['gastos_acumulados'], Decimal('3350.00'))
        conceptos = {g['concepto']: g['monto'] for g in datos['gastos_detalle']}
        self.assertEqual(conceptos, {'Publicidad': Decimal('3000.00'), 'Render actualizado': Decimal('200.00')})

    def test_mes_sin_edicion_arrastra_ultima_version_sin_duplicar_la_anterior(self):
        datos = calcular_gastos(self.historial, DICIEMBRE)
        self.assertEqual(datos['gastos_mes'], Decimal('3200.00'))
        self.assertEqual(datos['gastos_acumulados'], Decimal('6550.00'))
        self.assertEqual(len(datos['gastos_detalle']), 2)

    def test_centavos_exactos_y_cambio_de_anio(self):
        datos = calcular_gastos([
            (self.render, date(2026, 12, 1), 'Render', Decimal('0.10')),
            (self.meta, date(2027, 1, 1), 'Meta', Decimal('0.20')),
        ], date(2027, 1, 1))
        self.assertEqual(datos['gastos_mes'], Decimal('0.30'))
        self.assertEqual(datos['gastos_acumulados'], Decimal('0.40'))


class ReportesImportesTests(SimpleTestCase):
    def setUp(self):
        self.id = uuid4()
        self.resumen = {
            **calcular_gastos([(self.id, OCTUBRE, 'Render', Decimal('150.25'))], NOVIEMBRE),
            'anticipos_mes': Decimal('0.00'), 'saldos_mes': Decimal('3000.00'),
            'cobros_mes': Decimal('3000.00'), 'cobros_acumulados': Decimal('6000.00'),
            'ventas_sin_importes': 0,
        }

    def filas(self, tipo, resumen=None):
        datos = construir_reporte('2026-11', tipo, resumen or self.resumen)
        return datos, {fila['clave']: fila for fila in datos['lineas']}

    def test_estado_resultados_muestra_desglose_y_resultado_parcial_exacto(self):
        datos, filas = self.filas('estado-resultados')
        self.assertEqual(filas['ingresos']['importe'], '3000.00')
        self.assertEqual(filas['anticipos_mes']['importe'], '0.00')
        self.assertEqual(filas['saldos_mes']['importe'], '3000.00')
        self.assertEqual(filas['gasto-' + str(self.id)]['importe'], '150.25')
        self.assertEqual(filas['gastos_operativos']['importe'], '150.25')
        self.assertEqual(filas['resultado_registrado']['importe'], '2849.75')
        for pendiente in ('costos_ventas', 'utilidad_bruta', 'utilidad_operativa', 'impuestos', 'utilidad_neta'):
            self.assertIsNone(filas[pendiente]['importe'])
        self.assertTrue(datos['conectado'])
        self.assertTrue(datos['parcial'])

    def test_flujo_muestra_movimiento_del_mes_sin_inventar_saldo_bancario(self):
        _, filas = self.filas('flujo-efectivo')
        self.assertEqual(filas['cobros_operacion']['importe'], '3000.00')
        self.assertEqual(filas['pagos_operacion']['importe'], '150.25')
        self.assertEqual(filas['flujo_operacion']['importe'], '2849.75')
        for pendiente in ('saldo_inicial', 'saldo_final', 'flujo_inversion', 'flujo_financiamiento'):
            self.assertIsNone(filas[pendiente]['importe'])

    def test_balance_complementa_con_acumulados_sin_convertirlos_en_patrimonio(self):
        _, filas = self.filas('balance-general')
        self.assertEqual(filas['cobros_acumulados']['importe'], '6000.00')
        self.assertEqual(filas['gastos_acumulados']['importe'], '300.50')
        self.assertEqual(filas['variacion_operativa_acumulada']['importe'], '5699.50')
        for pendiente in ('efectivo', 'cuentas_cobrar', 'activos', 'pasivos', 'capital_aportado',
                          'resultados_acumulados', 'patrimonio', 'pasivos_patrimonio', 'diferencia_balance'):
            self.assertIsNone(filas[pendiente]['importe'])

    def test_ventas_incompletas_advierte_en_todos_los_reportes(self):
        for tipo in ('estado-resultados', 'balance-general', 'flujo-efectivo'):
            with self.subTest(tipo=tipo):
                datos, _ = self.filas(tipo, {**self.resumen, 'ventas_sin_importes': 2})
                self.assertEqual(datos['ventas_sin_importes'], 2)
                self.assertIn('2 ventas cerradas', datos['advertencias'][0])
                self.assertIn('Gestión de Ventas', datos['advertencias'][0])

    def test_sin_historial_conserva_cobros_pero_no_inventa_egresos_ni_resultados(self):
        pendientes = {
            'estado-resultados': ('gastos_operativos', 'resultado_registrado'),
            'balance-general': ('gastos_acumulados', 'variacion_operativa_acumulada'),
            'flujo-efectivo': ('pagos_operacion', 'flujo_operacion'),
        }
        for tipo, claves in pendientes.items():
            with self.subTest(tipo=tipo):
                datos, filas = self.filas(tipo, {
                    **self.resumen, **calcular_gastos([], NOVIEMBRE),
                })
                for clave in claves:
                    self.assertIsNone(filas[clave]['importe'])
                clave_cobro = {'estado-resultados': 'ingresos', 'balance-general': 'cobros_acumulados',
                               'flujo-efectivo': 'cobros_operacion'}[tipo]
                self.assertIsNotNone(filas[clave_cobro]['importe'])
                self.assertIn('No hay historial', datos['advertencias'][0])

    def test_resumen_mapea_agregados_y_parametriza_rangos_mensuales(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (Decimal('100.10'), Decimal('200.20'), Decimal('600.30'), 2)
        cursor.fetchall.return_value = [(self.id, OCTUBRE, 'Render', Decimal('0.10'))]
        datos = leer_resumen(cursor, NOVIEMBRE)
        self.assertEqual(datos['anticipos_mes'], Decimal('100.10'))
        self.assertEqual(datos['saldos_mes'], Decimal('200.20'))
        self.assertEqual(datos['cobros_mes'], Decimal('300.30'))
        self.assertEqual(datos['cobros_acumulados'], Decimal('600.30'))
        self.assertEqual(datos['ventas_sin_importes'], 2)
        self.assertEqual(datos['gastos_mes'], Decimal('0.10'))
        self.assertEqual(datos['gastos_acumulados'], Decimal('0.20'))
        cobros, gastos = cursor.execute.call_args_list
        self.assertEqual(cobros.args[1], [NOVIEMBRE, DICIEMBRE, NOVIEMBRE, DICIEMBRE, DICIEMBRE])
        self.assertIn("AT TIME ZONE 'America/Mexico_City'", cobros.args[0])
        self.assertEqual(len(gastos.args), 1)
        self.assertIn('FROM public.gastos_operativos_historial', gastos.args[0])
        self.assertNotIn('WHERE vigente_desde', gastos.args[0])
