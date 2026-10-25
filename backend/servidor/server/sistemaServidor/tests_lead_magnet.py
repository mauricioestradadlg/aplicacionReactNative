"""Pruebas aisladas: no conectan a Neon ni envían correos."""
import json
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4
from urllib.parse import urlencode

from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase
from .lead_magnet_admin_view import listar_leads_magnet


class LeadsMagnetPrivadosTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch('server.sistemaServidor.lead_magnet_admin_view.connections')
    @patch('server.sistemaServidor.lead_magnet_admin_view._autorizar_admin')
    def test_sin_autorizacion_no_consulta_neon(self, autorizar, conexiones):
        autorizar.return_value = (None, JsonResponse({'ok': False}, status=403))
        response = listar_leads_magnet(self.factory.get('/api/sistema/lead-magnet/registros/'))
        self.assertEqual(response.status_code, 403)
        conexiones.__getitem__.assert_not_called()

    @patch('server.sistemaServidor.lead_magnet_admin_view.connections')
    @patch('server.sistemaServidor.lead_magnet_admin_view._autorizar_admin')
    def test_busqueda_parametrizada_paginacion_y_filtros(self, autorizar, conexiones):
        autorizar.return_value = ((1, 'Admin', 'admin', 'admin@example.com', 'admin'), None)
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        cursor.fetchall.return_value = [(
            uuid4(), 'Ana', 'ana@example.com', '+528112345678', 'Cafetería',
            'restaurante', True, False, datetime(2026, 10, 22, tzinfo=timezone.utc)
        )]
        busqueda = "X%' OR 1=1 --"
        params = urlencode({'pagina': 1, 'buscar': busqueda, 'plantilla': 'restaurante'})
        response = listar_leads_magnet(self.factory.get('/api/sistema/lead-magnet/registros/?' + params))
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['pagina'], 1)
        self.assertEqual(len(body['leads']), 1)
        self.assertFalse(body['leads'][0]['acepto_correos'])
        count_call, listado_call = cursor.execute.call_args_list
        self.assertNotIn(busqueda, count_call.args[0])
        self.assertNotIn(busqueda, listado_call.args[0])
        self.assertIn('%' + busqueda + '%', count_call.args[1])
        self.assertIn('%' + busqueda + '%', listado_call.args[1])

    @patch('server.sistemaServidor.lead_magnet_admin_view._autorizar_admin')
    def test_rechaza_pagina_invalida(self, autorizar):
        autorizar.return_value = ((1, 'Admin', 'admin', 'admin@example.com', 'admin'), None)
        response = listar_leads_magnet(self.factory.get('/api/sistema/lead-magnet/registros/?pagina=0'))
        self.assertEqual(response.status_code, 400)
