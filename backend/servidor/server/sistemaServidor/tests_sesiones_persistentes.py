"""Pruebas unitarias de cookies persistentes (sin usar Neon real)."""
from unittest.mock import patch
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.http import JsonResponse
from server.sistemaServidor import sistema_auth


class SesionesPersistentesTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_lee_cookie_del_navegador(self):
        request = self.factory.get('/api/sistema/yo/')
        request.COOKIES[sistema_auth.NOMBRE_COOKIE_SESION] = 'x' * 48
        self.assertEqual(sistema_auth._extraer_token(request), 'x' * 48)

    @override_settings(DEBUG=False)
    def test_cookie_proteccion_produccion(self):
        response = sistema_auth._establecer_cookie_sesion(JsonResponse({'ok': True}), 'x' * 48)
        cookie = response.cookies[sistema_auth.NOMBRE_COOKIE_SESION]
        self.assertTrue(cookie['httponly'])
        self.assertTrue(cookie['secure'])
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertEqual(cookie['path'], '/api/sistema/')
        self.assertEqual(int(cookie['max-age']), 30 * 86400)

    def test_cierre_borra_cookie(self):
        response = sistema_auth._eliminar_cookie_sesion(JsonResponse({'ok': True}))
        cookie = response.cookies[sistema_auth.NOMBRE_COOKIE_SESION]
        self.assertEqual(int(cookie['max-age']), 0)
        self.assertEqual(cookie['path'], '/api/sistema/')

    def test_codigo_csrf(self):
        request = self.factory.get('/api/sistema/csrf/')
        response = sistema_auth.sistema_csrf(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', response.cookies)
