"""Pruebas aisladas del seguimiento manual: sin conexión real a Neon."""
import json
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase
from .lead_magnet_admin_view import listar_email_marketing, actualizar_email_marketing


class EmailMarketingTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.lead_id = uuid4()
        self.admin = (42, 'Admin', 'admin', 'admin@example.com', 'admin')

    @patch('server.sistemaServidor.lead_magnet_admin_view.connections')
    @patch('server.sistemaServidor.lead_magnet_admin_view._autorizar_admin')
    def test_sin_autorizacion_no_consulta_neon(self, autorizar, conexiones):
        autorizar.return_value = (None, JsonResponse({'ok': False}, status=403))
        respuesta = listar_email_marketing(self.factory.get('/api/sistema/lead-magnet/email-marketing/'))
        self.assertEqual(respuesta.status_code, 403)
        conexiones.__getitem__.assert_not_called()

    @patch('server.sistemaServidor.lead_magnet_admin_view.connections')
    @patch('server.sistemaServidor.lead_magnet_admin_view._autorizar_admin')
    def test_lista_solo_consentimiento_y_parametriza_busqueda(self, autorizar, conexiones):
        autorizar.return_value = (self.admin, None)
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        cursor.fetchall.return_value = [(
            self.lead_id, 'Ana', 'ana@example.com', '+528100000000', 'Tienda',
            'negocio', datetime(2026, 10, 22, tzinfo=timezone.utc), None, None, None,
        )]
        respuesta = listar_email_marketing(self.factory.get('/api/sistema/lead-magnet/email-marketing/', {'buscar': "a%' OR 1=1 --"}))
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = json.loads(respuesta.content)
        self.assertEqual(cuerpo['total'], 1)
        for sql_call in cursor.execute.call_args_list:
            self.assertIn('acepto_correos = TRUE', sql_call.args[0])
            self.assertNotIn("a%' OR 1=1 --", sql_call.args[0])

    @patch('server.sistemaServidor.lead_magnet_admin_view._autorizar_admin')
    def test_campo_desconocido_rechazado(self, autorizar):
        autorizar.return_value = (self.admin, None)
        request = self.factory.post('/api/sistema/lead-magnet/email-marketing/x/estado/',
            data=json.dumps({'campo': 'contrasena_hash', 'valor': True}), content_type='application/json')
        self.assertEqual(actualizar_email_marketing(request, self.lead_id).status_code, 400)

    @patch('server.sistemaServidor.lead_magnet_admin_view._autorizar_admin')
    def test_valor_debe_ser_booleano(self, autorizar):
        autorizar.return_value = (self.admin, None)
        request = self.factory.post('/api/sistema/lead-magnet/email-marketing/x/estado/',
            data=json.dumps({'campo': 'tips_enviados', 'valor': 'sí'}), content_type='application/json')
        self.assertEqual(actualizar_email_marketing(request, self.lead_id).status_code, 400)

    @patch('server.sistemaServidor.lead_magnet_admin_view.connections')
    @patch('server.sistemaServidor.lead_magnet_admin_view._autorizar_admin')
    def test_actualizacion_parametrizada_restringida_a_consentimiento(self, autorizar, conexiones):
        autorizar.return_value = (self.admin, None)
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (datetime(2026, 10, 22, tzinfo=timezone.utc), None, None)
        request = self.factory.post('/api/sistema/lead-magnet/email-marketing/x/estado/',
            data=json.dumps({'campo': 'tips_enviados', 'valor': True}), content_type='application/json')
        resp = actualizar_email_marketing(request, self.lead_id)
        self.assertEqual(resp.status_code, 200)
        sql, params = cursor.execute.call_args.args
        self.assertIn('acepto_correos = TRUE', sql)
        self.assertEqual(params, [True, 42, str(self.lead_id)])
