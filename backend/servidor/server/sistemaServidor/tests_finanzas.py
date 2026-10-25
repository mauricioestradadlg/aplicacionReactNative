"""Pruebas de Finanzas aisladas: no conectan a Neon ni escriben datos reales."""
import json
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

from django.db import DatabaseError
from django.http import JsonResponse
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve

from .finanzas_view import (
    gastos_operativos, editar_gasto_operativo, reportes_financieros,
)


class FinanzasTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = (7, 'Administrador', 'admin', 'admin@example.com', 'admin')
        self.id = uuid4()
        self.ruta_gastos = '/api/sistema/finanzas/gastos-operativos/'
        self.ruta_reportes = '/api/sistema/finanzas/reportes/'
        self.autorizacion = self.enterContext(patch(
            'server.sistemaServidor.finanzas_view._autorizar_admin',
            return_value=(self.admin, None),
        ))
        self.conexiones = self.enterContext(patch('server.sistemaServidor.finanzas_view.connections'))
        self.atomic = self.enterContext(patch(
            'server.sistemaServidor.finanzas_view.transaction.atomic',
            side_effect=lambda **kwargs: nullcontext(),
        ))
        self.cursor = self.conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        self.enterContext(patch(
            'server.sistemaServidor.finanzas_view._mes_actual', return_value=date(2026, 10, 1),
        ))

    def post(self, datos, ruta=None):
        return self.factory.post(ruta or self.ruta_gastos, data=json.dumps(datos), content_type='application/json')

    def test_autorizacion_obligatoria_en_todas_las_operaciones(self):
        for estado in (401, 403):
            self.autorizacion.return_value = (None, JsonResponse({'ok': False}, status=estado))
            llamadas = (
                lambda: gastos_operativos(self.factory.get(self.ruta_gastos)),
                lambda: gastos_operativos(self.post({'concepto': 'Ejemplo', 'monto_mensual': '10.00'})),
                lambda: editar_gasto_operativo(self.post({'concepto': 'Ejemplo', 'monto_mensual': '10.00'}), self.id),
                lambda: reportes_financieros(self.factory.get(self.ruta_reportes, {'periodo': '2026-10', 'tipo': 'estado-resultados'})),
            )
            for llamada in llamadas:
                with self.subTest(estado=estado, operacion=llamada):
                    respuesta = llamada()
                    self.assertEqual(respuesta.status_code, estado)
                    if estado == 403:
                        self.assertIn('Finanzas', json.loads(respuesta.content)['mensaje'])
            self.conexiones.__getitem__.assert_not_called()

    def test_gastos_total_decimal_sin_mutaciones_en_get(self):
        self.cursor.fetchall.return_value = [
            (self.id, 'Ejemplo A', Decimal('0.10')),
            (uuid4(), 'Ejemplo B', Decimal('0.20')),
        ]
        respuesta = gastos_operativos(self.factory.get(self.ruta_gastos))
        datos = json.loads(respuesta.content)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Cache-Control'], 'no-store')
        self.assertEqual(respuesta['Pragma'], 'no-cache')
        self.assertEqual(datos['total_mensual'], '0.30')
        self.assertEqual(datos['gastos'][0]['monto_mensual'], '0.10')
        self.assertEqual(datos['gastos'][0]['id'], str(self.id))
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.assertTrue(self.cursor.execute.call_args.args[0].strip().startswith('SELECT'))
        self.atomic.assert_not_called()

    def test_catalogo_vacio_total_cero(self):
        self.cursor.fetchall.return_value = []
        respuesta = gastos_operativos(self.factory.get(self.ruta_gastos))
        self.assertEqual(json.loads(respuesta.content), {'ok': True, 'gastos': [], 'total_mensual': '0.00'})

    def test_crear_parametriza_concepto_y_guarda_decimal(self):
        concepto = "Publicidad'); DROP TABLE gastos_operativos; --"
        self.cursor.fetchall.return_value = [(self.id, concepto, Decimal('150.25'))]
        respuesta = gastos_operativos(self.post({'concepto': concepto, 'monto_mensual': '150.25'}))
        self.assertEqual(respuesta.status_code, 201)
        sql, parametros = self.cursor.execute.call_args_list[0].args
        self.assertNotIn(concepto, sql)
        self.assertIn('INSERT INTO public.gastos_operativos', sql)
        self.assertEqual(parametros[1:], [concepto, Decimal('150.25'), self.admin[0]])
        self.assertIsInstance(UUID(parametros[0]), UUID)
        self.assertEqual(json.loads(respuesta.content)['total_mensual'], '150.25')
        self.atomic.assert_called_once_with(using='neon')
        version_sql, version_parametros = self.cursor.execute.call_args_list[1].args
        self.assertIn('INSERT INTO public.gastos_operativos_historial', version_sql)
        self.assertIn('ON CONFLICT (gasto_id, vigente_desde) DO UPDATE', version_sql)
        self.assertEqual(version_parametros, [date(2026, 10, 1), parametros[0]])

    def test_editar_actualiza_el_registro_existente_y_retorna_total(self):
        self.cursor.fetchone.return_value = (self.id,)
        self.cursor.fetchall.return_value = [(self.id, 'Render', Decimal('200.00'))]
        respuesta = editar_gasto_operativo(self.post({'concepto': ' Render ', 'monto_mensual': '200'}), self.id)
        self.assertEqual(respuesta.status_code, 200)
        sql, parametros = self.cursor.execute.call_args_list[0].args
        self.assertIn('UPDATE public.gastos_operativos', sql)
        self.assertIn('WHERE id = %s', sql)
        self.assertEqual(parametros, ['Render', Decimal('200'), self.admin[0], str(self.id)])
        self.assertEqual(json.loads(respuesta.content)['total_mensual'], '200.00')
        version_sql, version_parametros = self.cursor.execute.call_args_list[1].args
        self.assertIn('INSERT INTO public.gastos_operativos_historial', version_sql)
        self.assertEqual(version_parametros, [date(2026, 10, 1), str(self.id)])
        self.atomic.assert_called_once_with(using='neon')

    def test_editar_gasto_inexistente(self):
        self.cursor.fetchone.return_value = None
        respuesta = editar_gasto_operativo(self.post({'concepto': 'Render', 'monto_mensual': '200.00'}), self.id)
        self.assertEqual(respuesta.status_code, 404)
        self.cursor.fetchall.assert_not_called()

    def test_rechaza_importes_invalidos_sin_consultar_base(self):
        for monto in ('-0.01', '1.001', 'NaN', 'Infinity', '1e3', '3,000.00',
                      '10000000000.00', '', None, True, [], {}, 150, 150.25):
            for editar in (False, True):
                with self.subTest(monto=monto, editar=editar):
                    request = self.post({'concepto': 'Ejemplo', 'monto_mensual': monto})
                    respuesta = editar_gasto_operativo(request, self.id) if editar else gastos_operativos(request)
                    self.assertEqual(respuesta.status_code, 400)
        self.conexiones.__getitem__.assert_not_called()

    def test_valida_concepto_y_objeto_json_completo(self):
        invalidos = (
            [], None, True, 'texto', {},
            {'concepto': 'Ejemplo'},
            {'concepto': 'Ejemplo', 'monto_mensual': '1', 'admin': True},
            {'concepto': ' ', 'monto_mensual': '1'},
            {'concepto': 'a' * 151, 'monto_mensual': '1'},
            {'concepto': ['Ejemplo'], 'monto_mensual': '1'},
            {'concepto': 'Ejemplo\x00', 'monto_mensual': '1'},
            {'concepto': '\ud800', 'monto_mensual': '1'},
        )
        for datos in invalidos:
            with self.subTest(datos=datos):
                self.assertEqual(gastos_operativos(self.post(datos)).status_code, 400)
        self.conexiones.__getitem__.assert_not_called()

    def test_json_roto_codificacion_tipo_y_limite(self):
        for body in (b'{', b'\xff', b'[' * 1200 + b'0' + b']' * 1200):
            with self.subTest(body=body):
                request = self.factory.generic('POST', self.ruta_gastos, body, content_type='application/json')
                self.assertEqual(gastos_operativos(request).status_code, 400)
        request = self.factory.post(self.ruta_gastos, {'concepto': 'Ejemplo', 'monto_mensual': '1'})
        self.assertEqual(gastos_operativos(request).status_code, 415)
        request = self.factory.post(self.ruta_gastos, ' ' * 8193, content_type='application/json')
        self.assertEqual(gastos_operativos(request).status_code, 413)
        self.conexiones.__getitem__.assert_not_called()

    def test_limites_inclusivos_y_normalizacion(self):
        for monto, esperado in (('0', '0.00'), ('-0.00', '0.00'), ('9999999999.99', '9999999999.99')):
            with self.subTest(monto=monto):
                self.cursor.fetchall.return_value = [(self.id, 'Ejemplo', Decimal(esperado))]
                respuesta = gastos_operativos(self.post({'concepto': 'Ejemplo', 'monto_mensual': monto}))
                self.assertEqual(respuesta.status_code, 201)
                self.assertEqual(json.loads(respuesta.content)['gastos'][0]['monto_mensual'], esperado)

    def test_error_de_base_no_filtra_detalles(self):
        self.cursor.execute.side_effect = DatabaseError('password=secreto host=privado')
        with self.assertLogs('server.sistemaServidor.finanzas_view', level='ERROR'):
            respuesta = gastos_operativos(self.factory.get(self.ruta_gastos))
        self.assertEqual(respuesta.status_code, 503)
        self.assertNotIn('secreto', respuesta.content.decode())
        self.assertNotIn('privado', respuesta.content.decode())

    def test_reportes_conectan_cobros_y_gastos_sin_inventar_saldos(self):
        self.cursor.fetchone.return_value = (Decimal('3000.00'), Decimal('0.00'), Decimal('3000.00'), 0)
        self.cursor.fetchall.return_value = [(self.id, date(2026, 10, 1), 'Render', Decimal('150.00'))]
        esperados = {
            'estado-resultados': {'ingresos': '3000.00', 'gastos_operativos': '150.00',
                                 'resultado_registrado': '2850.00', 'utilidad_neta': None},
            'balance-general': {'efectivo': None, 'activos': None, 'pasivos': None,
                               'cobros_acumulados': '3000.00', 'gastos_acumulados': '150.00',
                               'variacion_operativa_acumulada': '2850.00'},
            'flujo-efectivo': {'saldo_inicial': None, 'cobros_operacion': '3000.00',
                              'pagos_operacion': '150.00', 'flujo_operacion': '2850.00', 'saldo_final': None},
        }
        for tipo, importes in esperados.items():
            with self.subTest(tipo=tipo):
                self.cursor.execute.reset_mock()
                respuesta = reportes_financieros(self.factory.get(self.ruta_reportes, {'periodo': '2026-10', 'tipo': tipo}))
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta['Cache-Control'], 'no-store')
                datos = json.loads(respuesta.content)
                self.assertEqual(datos['tipo'], tipo)
                self.assertEqual(datos['periodo'], '2026-10')
                self.assertFalse(datos['guardado'])
                self.assertTrue(datos['conectado'])
                self.assertTrue(datos['parcial'])
                filas = {linea['clave']: linea['importe'] for linea in datos['lineas']}
                for clave, esperado in importes.items():
                    self.assertEqual(filas[clave], esperado)
                self.assertTrue(all(linea['tipo'] in ('total', 'detalle') for linea in datos['lineas']))
                self.assertTrue(all(llamada.args[0].lstrip().startswith(('WITH', 'SELECT'))
                                    for llamada in self.cursor.execute.call_args_list))
        self.atomic.assert_not_called()

    def test_error_de_base_en_reportes_no_filtra_detalles(self):
        self.cursor.execute.side_effect = DatabaseError('password=secreto host=privado')
        with self.assertLogs('server.sistemaServidor.finanzas_view', level='ERROR'):
            respuesta = reportes_financieros(self.factory.get(self.ruta_reportes, {
                'periodo': '2026-10', 'tipo': 'estado-resultados',
            }))
        self.assertEqual(respuesta.status_code, 503)
        self.assertNotIn('secreto', respuesta.content.decode())
        self.assertNotIn('privado', respuesta.content.decode())

    def test_reportes_filtran_tipo_y_periodo_validos(self):
        for periodo, tipo in (('2026-00', 'estado-resultados'), ('2026-13', 'balance-general'),
                              ('2026-1', 'flujo-efectivo'), ('0000-10', 'estado-resultados'),
                              ('2026-10-01', 'estado-resultados'), ('2026-10', 'inventado'),
                              ('2026-10', "x'; DROP TABLE gastos_operativos;--"),
                              ('2026-11', 'estado-resultados'), ('', ''), (None, None)):
            with self.subTest(periodo=periodo, tipo=tipo):
                parametros = {k: v for k, v in {'periodo': periodo, 'tipo': tipo}.items() if v is not None}
                self.assertEqual(reportes_financieros(self.factory.get(self.ruta_reportes, parametros)).status_code, 400)
        self.conexiones.__getitem__.assert_not_called()

    def test_metodos_no_admitidos_y_rutas(self):
        self.assertEqual(reportes_financieros(self.post({}, self.ruta_reportes)).status_code, 405)
        self.assertEqual(gastos_operativos(self.factory.delete(self.ruta_gastos)).status_code, 405)
        self.assertEqual(editar_gasto_operativo(self.factory.get(self.ruta_gastos), self.id).status_code, 405)
        self.assertIs(resolve(self.ruta_gastos).func, gastos_operativos)
        self.assertIs(resolve(self.ruta_gastos + str(self.id) + '/').func, editar_gasto_operativo)
        self.assertIs(resolve(self.ruta_reportes).func, reportes_financieros)

    @override_settings(ALLOWED_HOSTS=['testserver'])
    def test_post_protegido_por_csrf_middleware(self):
        cliente = Client(enforce_csrf_checks=True)
        respuesta = cliente.post(self.ruta_gastos, data=json.dumps({'concepto': 'Ejemplo', 'monto_mensual': '1.00'}), content_type='application/json')
        self.assertEqual(respuesta.status_code, 403)
        self.autorizacion.assert_not_called()
        self.conexiones.__getitem__.assert_not_called()
