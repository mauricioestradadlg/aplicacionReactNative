"""Contrato móvil, segundo factor y separación de CSRF sin tocar bases reales."""
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.http import JsonResponse
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone

from server.security import _tipo_endpoint
from server.mobile_security import SistemaCsrfMiddleware
from server.sistemaServidor import sistema_auth as auth


@override_settings(
    SECRET_KEY="test-only-secret-" * 4,
    ALLOWED_HOSTS=["testserver"],
    SECURITY_RATE_LIMIT_ENABLED=False,
    MIDDLEWARE=["server.mobile_security.SistemaCsrfMiddleware"],
)
class MobileAuthTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.client = Client(enforce_csrf_checks=True)
        self.token = "native-token_" + "a" * 52
        self.verificacion_id = str(uuid4())

    def _codigo(self):
        return self.factory.post(
            "/api/sistema/movil/verificar/",
            {"verificacion_id": self.verificacion_id, "codigo": "123456"},
            content_type="application/json",
        )

    def _verificar(self, fila, movil=True):
        cursor = MagicMock()
        cursor.fetchone.return_value = fila
        conexiones = MagicMock()
        conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value = cursor
        with (
            patch.object(auth, "_tiene_neon", return_value=True),
            patch.object(auth, "connections", conexiones),
            patch.object(auth.transaction, "atomic"),
            patch.object(auth.secrets, "token_urlsafe", return_value=self.token),
        ):
            vista = auth.sistema_movil_verificar if movil else auth.sistema_verificar
            response = vista(self._codigo())
        return response, cursor

    def _fila_valida(self):
        return (7, auth._codigo_hash(self.verificacion_id, "123456"),
                timezone.now() + timedelta(minutes=5), 0, None, True)

    def test_segundo_factor_entrega_token_y_guarda_solo_hash(self):
        response, cursor = self._verificar(self._fila_valida())
        datos = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(datos["token"], self.token)
        self.assertIn("expira_en", datos)
        self.assertNotIn(auth.NOMBRE_COOKIE_SESION, response.cookies)
        sesiones = [c.args for c in cursor.execute.call_args_list
                    if "INSERT INTO public.sesiones_sistema" in c.args[0]]
        self.assertEqual(len(sesiones), 1)
        self.assertEqual(sesiones[0][1][2], auth._token_hash(self.token))
        self.assertNotIn(self.token, str(cursor.execute.call_args_list))
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_codigo_incorrecto_vencido_usado_o_usuario_inactivo_no_crea_sesion(self):
        fila = self._fila_valida()
        variantes = [None,
                     (fila[0], "0" * 64, *fila[2:]),
                     (*fila[:2], timezone.now() - timedelta(seconds=1), *fila[3:]),
                     (*fila[:3], 5, *fila[4:]),
                     (*fila[:4], timezone.now(), fila[5]),
                     (*fila[:5], False)]
        for variante in variantes:
            with self.subTest(fila=variante):
                response, cursor = self._verificar(variante)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("token", json.loads(response.content))
                self.assertFalse(any("INSERT INTO public.sesiones_sistema" in c.args[0]
                                     for c in cursor.execute.call_args_list))

    @override_settings(DEBUG=False)
    def test_verificacion_web_sigue_entregando_cookie_sin_exponer_token(self):
        response, _ = self._verificar(self._fila_valida(), movil=False)
        self.assertNotIn("token", json.loads(response.content))
        cookie = response.cookies[auth.NOMBRE_COOKIE_SESION]
        self.assertEqual(cookie.value, self.token)
        self.assertTrue(cookie["httponly"])
        self.assertTrue(cookie["secure"])

    def test_header_invalido_no_usa_cookie_como_respaldo(self):
        for header in ["", "Bearer ", "Basic abc", "Bearer tiny", "Bearer " + "!" * 40]:
            request = self.factory.get("/api/sistema/yo/", HTTP_AUTHORIZATION=header)
            request.COOKIES[auth.NOMBRE_COOKIE_SESION] = self.token
            self.assertIsNone(auth._extraer_token(request))

    def test_bearer_explicito_tiene_prioridad_sobre_cookie(self):
        request = self.factory.get("/api/sistema/yo/", HTTP_AUTHORIZATION="Bearer " + self.token)
        request.COOKIES[auth.NOMBRE_COOKIE_SESION] = "b" * 64
        self.assertEqual(auth._extraer_token(request), self.token)

    def test_web_y_endpoints_publicos_conservan_csrf(self):
        self.client.cookies[auth.NOMBRE_COOKIE_SESION] = self.token
        for path in ["/api/sistema/login/", "/api/sistema/verificar/", "/api/sistema/salir/"]:
            self.assertEqual(self.client.post(path, {}, content_type="application/json").status_code, 403)
        request = self.factory.post("/admin/protected/", {}, content_type="application/json",
                                    HTTP_AUTHORIZATION="Bearer " + self.token)
        response = SistemaCsrfMiddleware(lambda _: JsonResponse({"ok": True})).process_view(
            request, lambda _: JsonResponse({"ok": True}), (), {},
        )
        self.assertEqual(response.status_code, 403)

    def test_solo_login_movil_permite_desafio_sin_csrf_y_no_entrega_token(self):
        challenge = {"ok": True, "verificacion_id": self.verificacion_id, "correo_oculto": "te***@ejemplo.com"}
        with patch.object(auth, "sistema_login", return_value=JsonResponse(challenge)) as iniciar:
            response = self.client.post("/api/sistema/movil/login/", {}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("token", response.json())
        iniciar.assert_called_once()

    def test_salida_bearer_revoca_sesion_sin_cookie_ni_csrf(self):
        cursor = MagicMock()
        conexiones = MagicMock()
        conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value = cursor
        with patch.object(auth, "_tiene_neon", return_value=True), patch.object(auth, "connections", conexiones):
            response = self.client.post("/api/sistema/salir/", {}, content_type="application/json",
                                        HTTP_AUTHORIZATION="Bearer " + self.token)
        self.assertEqual(response.status_code, 200)
        sql, parametros = cursor.execute.call_args.args
        self.assertIn("revocado_en = NOW()", sql)
        self.assertEqual(parametros, [auth._token_hash(self.token)])

    def test_bearer_inexistente_no_autoriza_por_cookie(self):
        self.client.cookies[auth.NOMBRE_COOKIE_SESION] = "b" * 64
        with (patch.object(auth, "_tiene_neon", return_value=True),
              patch.object(auth, "_buscar_usuario_sesion", return_value=None) as buscar):
            response = self.client.get("/api/sistema/yo/", HTTP_AUTHORIZATION="Bearer " + self.token)
        self.assertEqual(response.status_code, 401)
        buscar.assert_called_once_with(self.token)

    def test_limites_de_acceso_cubren_nuevas_rutas(self):
        self.assertEqual(_tipo_endpoint("/api/sistema/movil/login/"), "login")
        self.assertEqual(_tipo_endpoint("/api/sistema/movil/verificar/"), "verificar_login")
