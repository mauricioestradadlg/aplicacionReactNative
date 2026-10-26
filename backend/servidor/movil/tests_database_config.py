from unittest import TestCase

from .database_config import configuracion_neon_movil


class DatabaseConfigTests(TestCase):
    def test_no_fallback_cuando_falta_url_movil(self):
        self.assertIsNone(configuracion_neon_movil("", "postgresql://user:pass@original.neon.tech/web"))

    def test_rechaza_misma_base_con_credenciales_o_parametros_distintos(self):
        with self.assertRaisesRegex(ValueError, "base distinta"):
            configuracion_neon_movil("postgres://mobile:other@ep-example.neon.tech:5432/web?sslmode=require", "postgresql://web:secret@ep-example.neon.tech/web")

    def test_rechaza_la_misma_base_con_alias_pooler_neon(self):
        with self.assertRaisesRegex(ValueError, "base distinta"):
            configuracion_neon_movil("postgresql://mobile:other@ep-example-pooler.us-east-2.aws.neon.tech/web", "postgresql://web:secret@ep-example.us-east-2.aws.neon.tech/web")

    def test_acepta_base_distinta_y_fuerza_tls(self):
        result = configuracion_neon_movil("postgresql://mobile:encoded%40password@ep-example-pooler.neon.tech/mobile?sslmode=disable", "postgresql://web:secret@ep-example.neon.tech/web")
        self.assertEqual(result["NAME"], "mobile")
        self.assertEqual(result["PASSWORD"], "encoded@password")
        self.assertEqual(result["OPTIONS"]["sslmode"], "require")
        self.assertEqual(result["OPTIONS"]["connect_timeout"], 8)
        self.assertEqual(result["ENGINE"], "django.db.backends.postgresql")

    def test_rechaza_url_incompleta_o_esquema_incorrecto(self):
        for value in ("https://example.com/db", "postgresql://host", "postgresql:///db"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                configuracion_neon_movil(value)
