'''Pruebas aisladas: no conectan con Neon ni procesan pagos.'''
import json
from contextlib import nullcontext
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase

from .gestion_ventas_view import listar_gestion_ventas, guardar_liquidacion


class GestionVentasTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.id = uuid4()
        self.admin = (1, 'Admin', 'admin', 'admin@example.com', 'admin')
        self.ahora = datetime(2026, 10, 23, tzinfo=timezone.utc)

    @patch('server.sistemaServidor.gestion_ventas_view.connections')
    @patch('server.sistemaServidor.gestion_ventas_view._autorizar_admin')
    def test_sin_admin_no_accede_a_neon(self, autorizar, conexiones):
        autorizar.return_value = (None, JsonResponse({'ok': False}, status=403))
        resp = listar_gestion_ventas(self.factory.get('/api/sistema/gestion-ventas/'))
        self.assertEqual(resp.status_code, 403)
        conexiones.__getitem__.assert_not_called()

    @patch('server.sistemaServidor.gestion_ventas_view.connections')
    @patch('server.sistemaServidor.gestion_ventas_view._autorizar_admin')
    def test_listar_solo_ventas_y_proyecto_pendiente(self, autorizar, conexiones):
        autorizar.return_value = (self.admin, None)
        conexiones.databases = {'neon': {}}
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1, 0)
        cursor.fetchall.return_value = [(
            self.id, 'email-marketing', 'Roberto', '+528100000007', 'Pizzería',
            'sitio-web', 'Email Marketing', self.ahora, True, True, True,
            False, None, None, Decimal('6000.00'), Decimal('3000.00'), date(2026, 10, 20),
        )]
        busqueda = "x%' OR 1=1 --"
        resp = listar_gestion_ventas(self.factory.get('/api/sistema/gestion-ventas/', {'buscar': busqueda}))
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertEqual(body['totales'], {'ventas': 1, 'liquidados': 0, 'pendientes': 1})
        self.assertFalse(body['clientes'][0]['proyecto_liquidado'])
        self.assertEqual(body['clientes'][0]['importe_total'], '6000.00')
        self.assertEqual(body['clientes'][0]['importe_anticipo'], '3000.00')
        self.assertEqual(body['clientes'][0]['fecha_anticipo'], '2026-10-20')
        for call in cursor.execute.call_args_list:
            sql, params = call.args
            self.assertIn('v.hubo_venta = TRUE', sql)
            self.assertNotIn(busqueda, sql)
            self.assertIn('%' + busqueda + '%', params)

    @patch('server.sistemaServidor.gestion_ventas_view._autorizar_admin')
    def test_valida_bool_en_vez_de_cadena(self, autorizar):
        autorizar.return_value = (self.admin, None)
        with patch('server.sistemaServidor.gestion_ventas_view.connections') as conexiones:
            conexiones.databases = {'neon': {}}
            req = self.factory.post('/api/sistema/gestion-ventas/x/liquidacion/',
                data=json.dumps({'fuente': 'whatsapp', 'proyecto_liquidado': 'SI'}),
                content_type='application/json')
            self.assertEqual(guardar_liquidacion(req, self.id).status_code, 400)
            conexiones.__getitem__.assert_not_called()

    @patch('server.sistemaServidor.gestion_ventas_view.transaction.atomic', return_value=nullcontext())
    @patch('server.sistemaServidor.gestion_ventas_view.connections')
    @patch('server.sistemaServidor.gestion_ventas_view._autorizar_admin')
    def test_liquidacion_solo_venta_cerrada(self, autorizar, conexiones, atomic):
        autorizar.return_value = (self.admin, None)
        conexiones.databases = {'neon': {}}
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            (False, None),
            (True, self.ahora, self.ahora, Decimal('6000'), Decimal('3000'), date(2026, 10, 20)),
        ]
        req = self.factory.post('/api/sistema/gestion-ventas/x/liquidacion/',
            data=json.dumps({'fuente': 'email-marketing', 'proyecto_liquidado': True}),
            content_type='application/json')
        resp = guardar_liquidacion(req, self.id)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content)['proyecto_liquidado'])
        select_call, update_call = cursor.execute.call_args_list
        self.assertIn('v.hubo_venta = TRUE', select_call.args[0])
        self.assertIn('hubo_venta = TRUE', update_call.args[0])
        self.assertEqual(update_call.args[1], [True, True, 1, 'email-marketing', str(self.id)])
        self.assertNotIn('importe_total =', update_call.args[0])
        self.assertNotIn('importe_anticipo =', update_call.args[0])
        self.assertIn('COALESCE(fecha_liquidacion, NOW())', update_call.args[0])

    @patch('server.sistemaServidor.gestion_ventas_view.transaction.atomic', return_value=nullcontext())
    @patch('server.sistemaServidor.gestion_ventas_view.connections')
    @patch('server.sistemaServidor.gestion_ventas_view._autorizar_admin')
    def test_no_guarda_si_la_venta_dejo_de_existir(self, autorizar, conexiones, atomic):
        autorizar.return_value = (self.admin, None)
        conexiones.databases = {'neon': {}}
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        req = self.factory.post('/api/sistema/gestion-ventas/x/liquidacion/',
            data=json.dumps({'fuente': 'whatsapp', 'proyecto_liquidado': True}),
            content_type='application/json')
        resp = guardar_liquidacion(req, self.id)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(len(cursor.execute.call_args_list), 1)


class ImportesVentasTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.id = uuid4()
        self.admin = (1, 'Admin', 'admin', 'admin@example.com', 'admin')
        self.ahora = datetime(2026, 10, 23, 18, tzinfo=timezone.utc)
        self.payload = {
            'fuente': 'whatsapp', 'proyecto_liquidado': False,
            'importe_total': '6595.00', 'importe_anticipo': '3595.00',
            'fecha_anticipo': '2026-09-20', 'fecha_liquidacion': None,
        }
        self.autorizar = self.enterContext(patch(
            'server.sistemaServidor.gestion_ventas_view._autorizar_admin',
            return_value=(self.admin, None),
        ))
        self.conexiones = self.enterContext(patch('server.sistemaServidor.gestion_ventas_view.connections'))
        self.conexiones.databases = {'neon': {}}
        self.atomic = self.enterContext(patch(
            'server.sistemaServidor.gestion_ventas_view.transaction.atomic',
            side_effect=lambda **kwargs: nullcontext(),
        ))
        self.enterContext(patch(
            'server.sistemaServidor.gestion_ventas_view._hoy_mexico',
            return_value=date(2026, 10, 23),
        ))
        self.cursor = self.conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value

    def request(self, payload=None):
        return self.factory.post(
            '/api/sistema/gestion-ventas/' + str(self.id) + '/liquidacion/',
            data=json.dumps(self.payload if payload is None else payload),
            content_type='application/json',
        )

    def test_anticipo_real_no_se_fuerza_al_cincuenta_por_ciento(self):
        self.cursor.fetchone.side_effect = [
            (False, None),
            (False, None, self.ahora, Decimal('6595'), Decimal('3595'), date(2026, 9, 20)),
        ]
        respuesta = guardar_liquidacion(self.request(), self.id)
        self.assertEqual(respuesta.status_code, 200)
        datos = json.loads(respuesta.content)
        self.assertEqual(datos['importe_total'], '6595.00')
        self.assertEqual(datos['importe_anticipo'], '3595.00')
        self.assertEqual(datos['fecha_anticipo'], '2026-09-20')
        self.assertIsNone(datos['fecha_liquidacion'])
        self.assertEqual(respuesta['Cache-Control'], 'no-store')
        select, update = self.cursor.execute.call_args_list
        self.assertIn('FOR UPDATE OF v', select.args[0])
        self.assertIn('v.hubo_venta = TRUE', select.args[0])
        self.assertEqual(update.args[1], [
            False, None, Decimal('6595'), Decimal('3595'), date(2026, 9, 20),
            1, 'whatsapp', str(self.id),
        ])
        self.atomic.assert_called_once_with(using='neon')

    def test_liquidacion_en_otro_mes_guarda_fecha_real_y_no_mueve_anticipo(self):
        payload = {**self.payload, 'fuente': 'email-marketing', 'proyecto_liquidado': True,
                   'fecha_liquidacion': '2026-10-20'}
        final = datetime(2026, 10, 20, 12, tzinfo=ZoneInfo('America/Mexico_City'))
        self.cursor.fetchone.side_effect = [
            (False, None),
            (True, final, self.ahora, Decimal('6595'), Decimal('3595'), date(2026, 9, 20)),
        ]
        respuesta = guardar_liquidacion(self.request(payload), self.id)
        self.assertEqual(respuesta.status_code, 200)
        parametros = self.cursor.execute.call_args_list[1].args[1]
        self.assertEqual(parametros, [
            True, final, Decimal('6595'), Decimal('3595'), date(2026, 9, 20),
            1, 'email-marketing', str(self.id),
        ])
        self.assertEqual(json.loads(respuesta.content)['fecha_liquidacion'], final.isoformat())

    def test_guardar_misma_fecha_final_conserva_instante_original(self):
        original = datetime(2026, 10, 21, 2, 15, tzinfo=timezone.utc)  # 20/oct en México.
        payload = {**self.payload, 'proyecto_liquidado': True, 'fecha_liquidacion': '2026-10-20'}
        self.cursor.fetchone.side_effect = [
            (True, original),
            (True, original, self.ahora, Decimal('6595'), Decimal('3595'), date(2026, 9, 20)),
        ]
        self.assertEqual(guardar_liquidacion(self.request(payload), self.id).status_code, 200)
        self.assertIs(self.cursor.execute.call_args_list[1].args[1][1], original)

    def test_importes_invalidos_se_rechazan_antes_de_consultar_base(self):
        for campo in ('importe_total', 'importe_anticipo'):
            for importe in ('-1', '1.001', 'NaN', 'Infinity', '1e3', '6,000.00', '',
                            '10000000000.00', None, True, 6000, 150.25, [], {}):
                with self.subTest(campo=campo, importe=importe):
                    self.assertEqual(guardar_liquidacion(
                        self.request({**self.payload, campo: importe}), self.id,
                    ).status_code, 400)
        for cambios in ({'importe_total': '0'}, {'importe_anticipo': '7000'}):
            self.assertEqual(guardar_liquidacion(self.request({**self.payload, **cambios}), self.id).status_code, 400)
        self.conexiones.__getitem__.assert_not_called()

    def test_fechas_de_cobro_invalidas_o_incongruentes_se_rechazan(self):
        for cambios in (
            {'fecha_anticipo': '2026-02-30'}, {'fecha_anticipo': '2026-9-20'},
            {'fecha_anticipo': '2026-10-24'}, {'fecha_anticipo': None},
            {'fecha_anticipo': '20260920'}, {'fecha_anticipo': ['2026-09-20']},
            {'fecha_liquidacion': '2026-10-20'},
            {'proyecto_liquidado': True, 'fecha_liquidacion': None},
            {'proyecto_liquidado': True, 'fecha_liquidacion': '2026-09-19'},
            {'proyecto_liquidado': True, 'fecha_liquidacion': '2026-10-24'},
            {'proyecto_liquidado': True, 'fecha_liquidacion': '2026-02-30'},
        ):
            with self.subTest(cambios=cambios):
                self.assertEqual(guardar_liquidacion(
                    self.request({**self.payload, **cambios}), self.id,
                ).status_code, 400)
        self.conexiones.__getitem__.assert_not_called()

    def test_payload_parcial_y_campos_adicionales_se_rechazan(self):
        parcial = {**self.payload}
        del parcial['importe_anticipo']
        for payload in (parcial, {**self.payload, 'admin': True}, [], None):
            with self.subTest(payload=payload):
                request = self.factory.post('/api/sistema/gestion-ventas/id/liquidacion/',
                    data=json.dumps(payload), content_type='application/json')
                self.assertEqual(guardar_liquidacion(request, self.id).status_code, 400)
        self.conexiones.__getitem__.assert_not_called()

    def test_no_permite_captura_sin_venta_cerrada(self):
        self.cursor.fetchone.return_value = None
        self.assertEqual(guardar_liquidacion(self.request(), self.id).status_code, 409)
        self.assertEqual(self.cursor.execute.call_count, 1)

    def test_importes_requieren_sesion_administrador(self):
        for estado in (401, 403):
            with self.subTest(estado=estado):
                self.autorizar.return_value = (None, JsonResponse({'ok': False}, status=estado))
                self.assertEqual(guardar_liquidacion(self.request(), self.id).status_code, estado)
        self.conexiones.__getitem__.assert_not_called()
