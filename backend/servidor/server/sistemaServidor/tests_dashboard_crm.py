"""Pruebas aisladas del Dashboard CRM: no hacen consultas reales a Neon."""
import json
from unittest.mock import patch

from django.db import DatabaseError
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase

from .dashboard_crm_view import COLUMNAS, resumen_dashboard_crm


class DashboardCRMTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.ruta = '/api/sistema/dashboard-crm/'

    @patch('server.sistemaServidor.dashboard_crm_view.connections')
    @patch('server.sistemaServidor.dashboard_crm_view._autorizar_admin')
    def test_no_autorizado_no_consulta_neon(self, autorizar, conexiones):
        autorizar.return_value = (None, JsonResponse({'ok': False}, status=403))
        respuesta = resumen_dashboard_crm(self.factory.get(self.ruta))
        self.assertEqual(respuesta.status_code, 403)
        conexiones.__getitem__.assert_not_called()

    @patch('server.sistemaServidor.dashboard_crm_view.connections')
    @patch('server.sistemaServidor.dashboard_crm_view._autorizar_admin')
    def test_totales_y_seis_meses_sin_datos_personales(self, autorizar, conexiones):
        autorizar.return_value = ((1, 'Admin', 'admin', 'admin@example.com', 'admin'), None)
        conexiones.databases = {'neon': {}}
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = tuple(range(1, len(COLUMNAS) + 1))
        cursor.fetchall.return_value = [('2026-05', 0, 2, 1), ('2026-06', 1, 0, 0)]
        respuesta = resumen_dashboard_crm(self.factory.get(self.ruta))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Cache-Control'], 'no-store')
        datos = json.loads(respuesta.content)
        self.assertEqual(datos['conteos']['whatsapp_registros'], 1)
        self.assertEqual(datos['conteos']['ventas_liquidadas'], len(COLUMNAS))
        self.assertEqual(datos['tendencia'][0]['lead_magnet'], 2)
        self.assertNotIn('correo', datos)
        self.assertEqual(cursor.execute.call_count, 2)

    @patch('server.sistemaServidor.dashboard_crm_view.connections')
    @patch('server.sistemaServidor.dashboard_crm_view._autorizar_admin')
    def test_error_de_neon_no_filtra_credenciales(self, autorizar, conexiones):
        autorizar.return_value = ((1, 'Admin', 'admin', 'admin@example.com', 'admin'), None)
        conexiones.databases = {'neon': {}}
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = DatabaseError('cadena privada de conexión')
        respuesta = resumen_dashboard_crm(self.factory.get(self.ruta))
        self.assertEqual(respuesta.status_code, 503)
        self.assertNotIn('cadena privada', respuesta.content.decode('utf-8'))
