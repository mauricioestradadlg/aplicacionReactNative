"""Pruebas unitarias sin acceso real a Neon ni envío de correo."""
from unittest.mock import patch
from uuid import uuid4

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from .security import SeguridadAPIMiddleware, _ip_cliente, _tipo_endpoint
from .resenas_view import _hash_codigo, _texto


class SeguridadAPIPruebas(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_rutas_sensibles_protegidas(self):
        self.assertEqual(_tipo_endpoint('/api/sistema/login/'), 'login')
        self.assertEqual(_tipo_endpoint('/api/resenas/'), 'resena')
        self.assertEqual(_tipo_endpoint('/api/resenas/verificar/'), 'confirmar_resena')
        self.assertIsNone(_tipo_endpoint('/api/resenas/publicas/'))

    @override_settings(TRUSTED_CLIENT_IP_HEADER='')
    def test_no_confia_en_x_forwarded_for_del_cliente(self):
        request = self.factory.get('/', HTTP_X_FORWARDED_FOR='3.4.5.6', REMOTE_ADDR='127.0.0.1')
        self.assertEqual(_ip_cliente(request), '127.0.0.1')

    @override_settings(SECRET_KEY='Z' * 60)
    def test_codigo_hash_no_coincide_con_otro_codigo_ni_id(self):
        identificador = uuid4()
        self.assertEqual(_hash_codigo(identificador, '123456'), _hash_codigo(identificador, '123456'))
        self.assertNotEqual(_hash_codigo(identificador, '123456'), _hash_codigo(identificador, '123457'))
        self.assertNotEqual(_hash_codigo(identificador, '123456'), _hash_codigo(uuid4(), '123456'))

    def test_validacion_rechaza_valor_no_texto(self):
        with self.assertRaises(ValueError):
            _texto({'nombre': ['malicioso']}, 'nombre', 70, True)

    @override_settings(SECURITY_RATE_LIMIT_ENABLED=True)
    @patch('server.security._aplicar_limites', return_value=(True, 900))
    @patch('server.security.connections')
    def test_limite_devuelve_429(self, conexiones, limitar):
        conexiones.databases = {'neon': {}}
        request = self.factory.post('/api/sistema/login/',
                                    data='{"usuario":"prueba","contrasena":"clave"}',
                                    content_type='application/json')
        middleware = SeguridadAPIMiddleware(lambda _: HttpResponse('ok'))
        respuesta = middleware(request)
        self.assertEqual(respuesta.status_code, 429)
        self.assertEqual(respuesta['Retry-After'], '900')

    @override_settings(SECURITY_RATE_LIMIT_ENABLED=True)
    def test_peticion_muy_grande_se_rechaza_antes_de_neon(self):
        request = self.factory.post('/api/resenas/',
                                    data='x' * 17000,
                                    content_type='application/json')
        middleware = SeguridadAPIMiddleware(lambda _: HttpResponse('ok'))
        self.assertEqual(middleware(request).status_code, 413)

    @override_settings(SECURITY_RATE_LIMIT_ENABLED=True)
    def test_health_get_sin_limitador(self):
        request = self.factory.get('/api/health/')
        middleware = SeguridadAPIMiddleware(lambda _: HttpResponse('ok'))
        self.assertEqual(middleware(request).status_code, 200)
