"""Dashboard financiero: cálculos exactos y acceso aislados de Neon."""
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.db import DatabaseError
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase

from .dashboard_finanzas_view import (
    _porcentaje, _ventana_meses, construir_dashboard_finanzas, resumen_dashboard_finanzas,
)
from .finanzas_reportes import calcular_gastos


MODULO = 'server.sistemaServidor.dashboard_finanzas_view'
OCTUBRE = date(2026, 10, 1)


class DashboardFinanzasTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.ruta = '/api/sistema/finanzas/dashboard/'
        self.autorizacion = self.enterContext(patch(
            'server.sistemaServidor.finanzas_view._autorizar_admin',
            return_value=((7, 'Admin', 'admin', 'admin@example.com', 'admin'), None),
        ))
        self.conexiones = self.enterContext(patch(MODULO + '.connections'))
        self.cursor = self.conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value = (Decimal('0.00'), Decimal('0.00'), Decimal('0.00'), 0)
        self.cursor.fetchall.return_value = []
        self.enterContext(patch(MODULO + '._mes_actual', return_value=OCTUBRE))
        self.enterContext(patch('server.sistemaServidor.finanzas_view._mes_actual', return_value=OCTUBRE))

    def consultar(self, periodo=None):
        return resumen_dashboard_finanzas(self.factory.get(
            self.ruta, {'periodo': periodo} if periodo is not None else {},
        ))

    def test_requiere_sesion_y_administrador_antes_de_consultar(self):
        for estado in (401, 403):
            with self.subTest(estado=estado):
                self.autorizacion.return_value = (None, JsonResponse({'ok': False}, status=estado))
                respuesta = self.consultar()
                self.assertEqual(respuesta.status_code, estado)
                if estado == 403:
                    self.assertIn('Finanzas', json.loads(respuesta.content)['mensaje'])
        self.conexiones.__getitem__.assert_not_called()

    def test_solo_lectura_no_admite_post(self):
        respuesta = resumen_dashboard_finanzas(self.factory.post(self.ruta))
        self.assertEqual(respuesta.status_code, 405)
        self.conexiones.__getitem__.assert_not_called()

    def test_rechaza_periodos_invalidos_y_futuros_sin_consultar(self):
        for periodo in ('', '2026-1', '2026-00', '2026-13', '0000-01', '9999-12',
                        '2026-11', '2026-10-01', '2026-10 OR 1=1', ' 2026-10'):
            with self.subTest(periodo=periodo):
                respuesta = self.consultar(periodo)
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(respuesta['Cache-Control'], 'no-store')
        self.conexiones.__getitem__.assert_not_called()

    def test_mes_actual_predeterminado_y_seis_meses_sin_cache(self):
        respuesta = self.consultar()
        datos = json.loads(respuesta.content)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Cache-Control'], 'no-store')
        self.assertEqual(respuesta['Pragma'], 'no-cache')
        self.assertEqual(datos['periodo'], '2026-10')
        self.assertEqual(datos['moneda'], 'MXN')
        self.assertTrue(datos['parcial'])
        self.assertEqual([fila['mes'] for fila in datos['tendencia']], [
            '2026-05', '2026-06', '2026-07', '2026-08', '2026-09', '2026-10',
        ])
        self.assertEqual(datos['comparativo']['periodo'], '2026-09')
        self.assertEqual(datos['resumen']['cobros_mes'], '0.00')
        self.assertIsNone(datos['resumen']['gastos_mes'])
        self.assertIsNone(datos['resumen']['resultado_operativo'])
        self.assertIsNone(datos['resumen']['margen_operativo_pct'])
        self.assertIsNone(datos['resumen']['cobertura_gastos_pct'])
        self.assertIsNone(datos['resumen']['variacion_cobros_pct'])
        self.assertEqual(datos['gastos'], [])
        self.assertIn('No hay historial', datos['advertencias'][0])
        self.assertNotIn('correo', datos)
        self.assertEqual(self.cursor.execute.call_count, 7)
        self.assertEqual(self.cursor.fetchall.call_count, 1)
        for llamada in self.cursor.execute.call_args_list:
            self.assertTrue(llamada.args[0].strip().startswith(('SELECT', 'WITH')))
        primera = self.cursor.execute.call_args_list[1].args
        ultima = self.cursor.execute.call_args_list[-1].args
        self.assertEqual(primera[1], [date(2026, 5, 1), date(2026, 6, 1),
                                    date(2026, 5, 1), date(2026, 6, 1), date(2026, 6, 1)])
        self.assertEqual(ultima[1], [OCTUBRE, date(2026, 11, 1), OCTUBRE,
                                   date(2026, 11, 1), date(2026, 11, 1)])

    def test_importes_y_comparacion_respetan_centavos_e_historial(self):
        render, publicidad = uuid4(), uuid4()
        self.cursor.fetchall.return_value = [
            (render, date(2026, 9, 1), 'Render', Decimal('250.10')),
            (render, OCTUBRE, 'Render actualizado', Decimal('300.20')),
            (publicidad, OCTUBRE, 'Publicidad', Decimal('99.80')),
        ]
        self.cursor.fetchone.side_effect = [
            (Decimal('0.00'), Decimal('0.00'), Decimal('0.00'), 0),
        ] * 4 + [
            (Decimal('600.00'), Decimal('400.00'), Decimal('1000.00'), 0),
            (Decimal('1200.10'), Decimal('800.20'), Decimal('3000.30'), 2),
        ]
        datos = json.loads(self.consultar().content)
        self.assertEqual(datos['resumen'], {
            'cobros_mes': '2000.30', 'anticipos_mes': '1200.10', 'saldos_mes': '800.20',
            'gastos_mes': '400.00', 'resultado_operativo': '1600.30',
            'margen_operativo_pct': '80.00', 'cobertura_gastos_pct': '500.08',
            'variacion_cobros_pct': '100.03',
        })
        self.assertEqual(datos['comparativo'], {
            'periodo': '2026-09', 'cobros_mes': '1000.00',
            'gastos_mes': '250.10', 'resultado_operativo': '749.90',
        })
        self.assertEqual(datos['inicio_historial_gastos'], '2026-09-01')
        self.assertEqual({fila['concepto']: fila['monto'] for fila in datos['gastos']}, {
            'Render actualizado': '300.20', 'Publicidad': '99.80',
        })
        self.assertEqual(datos['ventas_sin_importes'], 2)
        self.assertIn('2 ventas cerradas', datos['advertencias'][0])

    def test_error_neon_no_expone_datos_de_conexion(self):
        self.cursor.execute.side_effect = DatabaseError('credenciales privadas de Neon')
        with self.assertLogs(MODULO, level='ERROR'):
            respuesta = self.consultar()
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(respuesta['Cache-Control'], 'no-store')
        self.assertNotIn('credenciales privadas', respuesta.content.decode('utf-8'))

    def test_mes_1900_enero_cruza_anio_y_conserva_seis_puntos(self):
        datos = json.loads(self.consultar('1900-01').content)
        self.assertEqual([fila['mes'] for fila in datos['tendencia']], [
            '1899-08', '1899-09', '1899-10', '1899-11', '1899-12', '1900-01',
        ])

    def test_primer_mes_del_calendario_no_desborda_y_no_inventa_comparativo(self):
        respuesta = self.consultar('0001-01')
        datos = json.loads(respuesta.content)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(datos['periodo'], '0001-01')
        self.assertEqual(len(datos['tendencia']), 1)
        self.assertIsNone(datos['comparativo'])
        self.assertEqual(self.cursor.execute.call_count, 2)


class IndicadoresFinanzasTests(SimpleTestCase):
    def resumen(self, cobros, gastos, mes=OCTUBRE):
        return {
            **calcular_gastos([(uuid4(), mes, 'Servicio', Decimal(gastos))], mes),
            'cobros_mes': Decimal(cobros), 'anticipos_mes': Decimal(cobros),
            'saldos_mes': Decimal('0.00'), 'cobros_acumulados': Decimal(cobros),
            'ventas_sin_importes': 0,
        }

    def test_resultados_y_variacion_negativos_no_se_recortan(self):
        anterior = self.resumen('100.00', '50.00', date(2026, 9, 1))
        actual = self.resumen('25.00', '50.00')
        datos = construir_dashboard_finanzas([(date(2026, 9, 1), anterior), (OCTUBRE, actual)])
        self.assertEqual(datos['resumen']['resultado_operativo'], '-25.00')
        self.assertEqual(datos['resumen']['margen_operativo_pct'], '-100.00')
        self.assertEqual(datos['resumen']['variacion_cobros_pct'], '-75.00')

    def test_sin_cobros_conserva_perdida_y_no_divide_entre_cero(self):
        datos = construir_dashboard_finanzas([(OCTUBRE, self.resumen('0.00', '125.10'))])
        self.assertEqual(datos['resumen']['resultado_operativo'], '-125.10')
        self.assertIsNone(datos['resumen']['margen_operativo_pct'])
        self.assertEqual(datos['resumen']['cobertura_gastos_pct'], '0.00')

    def test_gastos_cero_conocidos_se_distinguen_de_historial_ausente(self):
        datos = construir_dashboard_finanzas([(OCTUBRE, self.resumen('100.00', '0.00'))])
        self.assertEqual(datos['resumen']['gastos_mes'], '0.00')
        self.assertEqual(datos['resumen']['resultado_operativo'], '100.00')
        self.assertEqual(datos['resumen']['margen_operativo_pct'], '100.00')
        self.assertIsNone(datos['resumen']['cobertura_gastos_pct'])
        self.assertEqual(datos['advertencias'], [])

    def test_redondeo_decimal_y_cambio_de_anio(self):
        self.assertEqual(_porcentaje(Decimal('1.005'), Decimal('100')), '1.01')
        self.assertEqual(_ventana_meses(date(2026, 1, 1)), [
            date(2025, 8, 1), date(2025, 9, 1), date(2025, 10, 1),
            date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1),
        ])
