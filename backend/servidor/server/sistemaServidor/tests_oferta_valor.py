"""Pruebas aisladas: no usan Neon ni realizan comunicaciones externas."""
import json
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase

from .oferta_valor_view import (
    _validar_edicion_potencial,
    _validar_prospecto,
    actualizar_cita_oferta_valor,
    clientes_potenciales_oferta_valor,
    editar_cliente_potencial,
    prospectos_oferta_valor,
)


class OfertaValorUnificadoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.id = uuid4()
        self.admin = (7, 'Administrador', 'admin', 'admin@example.com', 'admin')
        self.ahora = datetime(2026, 10, 23, tzinfo=timezone.utc)

    @patch('server.sistemaServidor.oferta_valor_view.connections')
    @patch('server.sistemaServidor.oferta_valor_view._autorizar_admin')
    def test_sin_autorizacion_no_consulta_neon(self, autorizar, conexiones):
        autorizar.return_value = (None, JsonResponse({'ok': False}, status=403))
        respuesta = clientes_potenciales_oferta_valor(
            self.factory.get('/api/sistema/oferta-valor/potenciales/'))
        self.assertEqual(respuesta.status_code, 403)
        conexiones.__getitem__.assert_not_called()

    @patch('server.sistemaServidor.oferta_valor_view.connections')
    @patch('server.sistemaServidor.oferta_valor_view._autorizar_admin')
    def test_listado_unifica_email_y_whatsapp(self, autorizar, conexiones):
        autorizar.return_value = (self.admin, None)
        conexiones.databases = {'neon': {}}
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (2,)
        cursor.fetchall.return_value = [
            (self.id, '+528100000107', 'Ana', True, True, 'Tienda', 'landing-page',
             None, self.ahora, 'WhatsApp', 'whatsapp'),
            (uuid4(), '+528100000007', 'Bruno', True, False, 'Pizzería', '',
             self.ahora, self.ahora, 'Email Marketing', 'email-marketing'),
        ]
        busqueda = "x%' OR 1=1 --"
        respuesta = clientes_potenciales_oferta_valor(
            self.factory.get('/api/sistema/oferta-valor/potenciales/', {'buscar': busqueda}))
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = json.loads(respuesta.content)
        self.assertEqual(cuerpo['total'], 2)
        self.assertEqual([p['fuente'] for p in cuerpo['prospectos']], ['whatsapp', 'email-marketing'])
        self.assertFalse(cuerpo['prospectos'][1]['respondio_mensajes'])
        llamadas = cursor.execute.call_args_list
        for llamada in llamadas:
            sql, parametros = llamada.args
            self.assertIn('p.respondio_mensajes = TRUE', sql)
            self.assertIn('l.oportunidad_comercial_en IS NOT NULL', sql)
            self.assertIn('l.acepto_correos = TRUE', sql)
            self.assertNotIn(busqueda, sql)
            self.assertIn('%' + busqueda + '%', parametros)

    def test_nombre_y_telefono_prospecto(self):
        resultado = _validar_prospecto({
            'telefono': '+52 81 1234 5678', 'nombre': 'Ana', 'negocio': '',
            'servicio_recomendado': 'sitio-web', 'respondio_mensajes': True,
        })
        self.assertEqual(resultado[0], '+528112345678')
        self.assertTrue(resultado[2])
        self.assertTrue(resultado[3])

    def test_validacion_origen_y_fuente(self):
        datos = {
            'fuente': 'email-marketing', 'telefono': '+528100000009',
            'nombre': 'Ana', 'negocio': '', 'servicio_recomendado': '',
            'origen': 'Email Marketing',
        }
        self.assertEqual(_validar_edicion_potencial(datos)[0], 'email-marketing')
        datos['origen'] = 'LinkedIn'
        with self.assertRaises(ValueError):
            _validar_edicion_potencial(datos)
        datos['origen'] = 'WhatsApp'
        datos['fuente'] = 'origen-inventado'
        with self.assertRaises(ValueError):
            _validar_edicion_potencial(datos)

    @patch('server.sistemaServidor.oferta_valor_view._verificar_neon', return_value=True)
    @patch('server.sistemaServidor.oferta_valor_view._autorizar_admin')
    def test_rechaza_cita_no_booleana(self, autorizar, _neon):
        autorizar.return_value = (self.admin, None)
        request = self.factory.post('/api/sistema/oferta-valor/potenciales/id/cita/',
            data=json.dumps({'fuente': 'email-marketing', 'cita_agendada': 'sí'}),
            content_type='application/json')
        self.assertEqual(actualizar_cita_oferta_valor(request, self.id).status_code, 400)

    @patch('server.sistemaServidor.oferta_valor_view.connections')
    @patch('server.sistemaServidor.oferta_valor_view._autorizar_admin')
    def test_cita_email_solo_si_oportunidad_activa(self, autorizar, conexiones):
        autorizar.return_value = (self.admin, None)
        conexiones.databases = {'neon': {}}
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (self.ahora,)
        request = self.factory.post('/api/sistema/oferta-valor/potenciales/id/cita/',
            data=json.dumps({'fuente': 'email-marketing', 'cita_agendada': True}),
            content_type='application/json')
        respuesta = actualizar_cita_oferta_valor(request, self.id)
        self.assertEqual(respuesta.status_code, 200)
        sql, params = cursor.execute.call_args.args
        self.assertIn('public.leads_magnet', sql)
        self.assertIn('oportunidad_comercial_en IS NOT NULL', sql)
        self.assertIn('acepto_correos = TRUE', sql)
        self.assertEqual(params, [True, str(self.id)])

    @patch('server.sistemaServidor.oferta_valor_view.connections')
    @patch('server.sistemaServidor.oferta_valor_view._autorizar_admin')
    def test_guardar_origen_email_no_cambia_fuente(self, autorizar, conexiones):
        autorizar.return_value = (self.admin, None)
        conexiones.databases = {'neon': {}}
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (
            self.id, '+528100000007', 'Bruno', True, False,
            'Pizzería', 'sitio-web', None, self.ahora, 'WhatsApp',
        )
        request = self.factory.post('/api/sistema/oferta-valor/potenciales/id/editar/',
            data=json.dumps({
                'fuente': 'email-marketing', 'nombre': 'Bruno',
                'telefono': '+528100000007', 'negocio': 'Pizzería',
                'servicio_recomendado': 'sitio-web', 'origen': 'WhatsApp',
            }), content_type='application/json')
        respuesta = editar_cliente_potencial(request, self.id)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(json.loads(respuesta.content)['prospecto']['fuente'], 'email-marketing')
        sql = cursor.execute.call_args.args[0]
        self.assertIn('UPDATE public.leads_magnet', sql)
        self.assertIn('oportunidad_comercial_en IS NOT NULL', sql)

    @patch('server.sistemaServidor.oferta_valor_view.connections')
    @patch('server.sistemaServidor.oferta_valor_view._autorizar_admin')
    def test_registros_whatsapp_no_cambian_origen(self, autorizar, conexiones):
        autorizar.return_value = (self.admin, None)
        conexiones.databases = {'neon': {}}
        cursor = conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (0,)
        cursor.fetchall.return_value = []
        respuesta = prospectos_oferta_valor(self.factory.get('/api/sistema/oferta-valor/prospectos/'))
        self.assertEqual(respuesta.status_code, 200)
        for call in cursor.execute.call_args_list:
            self.assertNotIn('UNION ALL', call.args[0])
