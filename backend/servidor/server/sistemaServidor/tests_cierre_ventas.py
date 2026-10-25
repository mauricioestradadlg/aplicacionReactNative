"""Pruebas sin Neon real; mocks de cursores y autorización."""
import json
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase

from .cierre_ventas_view import listar_cierres_ventas, guardar_cierre_ventas


class CierreVentasTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.id = uuid4()
        self.admin = (7, 'Administrador', 'admin', 'admin@example.com', 'admin')
        self.fecha = datetime(2026, 10, 23, tzinfo=timezone.utc)

    @patch('server.sistemaServidor.cierre_ventas_view.connections')
    @patch('server.sistemaServidor.cierre_ventas_view._autorizar_admin')
    def test_denegado_no_consulta_base(self, autorizar, conexiones):
        autorizar.return_value = (None, JsonResponse({'ok': False}, status=403))
        resp = listar_cierres_ventas(self.factory.get('/api/sistema/cierre-ventas/'))
        self.assertEqual(resp.status_code, 403)
        conexiones.__getitem__.assert_not_called()

    @patch('server.sistemaServidor.cierre_ventas_view.connections')
    @patch('server.sistemaServidor.cierre_ventas_view._autorizar_admin')
    def test_listado_filtra_citas_y_unifica_fuentes(self, autorizar, conexiones):
        autorizar.return_value = (self.admin, None)
        conexiones.databases = {'neon': {}}
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (4, 3, 3, 1)
        cursor.fetchall.return_value = [
            (self.id, 'Roberto', '+528100000107', 'Pizzería', 'sitio-web',
             'Email Marketing', 'email-marketing', self.fecha, True, True, True, self.fecha),
        ]
        buscar = "x%' OR 1=1 --"
        resp = listar_cierres_ventas(self.factory.get('/api/sistema/cierre-ventas/', {'buscar': buscar}))
        self.assertEqual(resp.status_code, 200)
        datos = json.loads(resp.content)
        self.assertEqual(datos['totales'], {'citas': 4, 'completadas': 3, 'cotizaciones': 3, 'ventas': 1})
        self.assertEqual(datos['prospectos'][0]['fuente'], 'email-marketing')
        for llamada in cursor.execute.call_args_list:
            sql, params = llamada.args
            self.assertIn('p.cita_agendada_en IS NOT NULL', sql)
            self.assertIn('l.oportunidad_comercial_en IS NOT NULL', sql)
            self.assertIn('p.respondio_mensajes = TRUE', sql)
            self.assertNotIn(buscar, sql)
            self.assertIn('%' + buscar + '%', params)

    @patch('server.sistemaServidor.cierre_ventas_view._autorizar_admin')
    def test_rechaza_venta_incoherente(self, autorizar):
        autorizar.return_value = (self.admin, None)
        with patch('server.sistemaServidor.cierre_ventas_view.connections') as conexiones:
            conexiones.databases = {'neon': {}}
            solicitud = self.factory.post('/api/sistema/cierre-ventas/id/estado/',
                data=json.dumps({'fuente': 'whatsapp', 'cita_completada': False,
                                 'cotizacion_enviada': False, 'hubo_venta': True}),
                content_type='application/json')
            self.assertEqual(guardar_cierre_ventas(solicitud, self.id).status_code, 400)
            conexiones.__getitem__.assert_not_called()

    @patch('server.sistemaServidor.cierre_ventas_view._autorizar_admin')
    def test_rechaza_string_en_vez_de_booleano(self, autorizar):
        autorizar.return_value = (self.admin, None)
        with patch('server.sistemaServidor.cierre_ventas_view.connections') as conexiones:
            conexiones.databases = {'neon': {}}
            solicitud = self.factory.post('/api/sistema/cierre-ventas/id/estado/',
                data=json.dumps({'fuente': 'email-marketing', 'cita_completada': 'si',
                                 'cotizacion_enviada': True, 'hubo_venta': False}),
                content_type='application/json')
            self.assertEqual(guardar_cierre_ventas(solicitud, self.id).status_code, 400)
            conexiones.__getitem__.assert_not_called()
