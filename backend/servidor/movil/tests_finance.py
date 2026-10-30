"""Cobros completos por venta, precisión e independencia entre organizaciones."""
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import include, path
from django.utils import timezone

from .models import Cliente, GastoHistorial, GastoOperativo, Membresia, Organizacion, Requerimiento, Sesion, Usuario


urlpatterns = [path('api/sistema/app/', include('movil.urls_business'))]
BASE = '/api/sistema/app/'


@override_settings(ROOT_URLCONF='movil.tests_finance')
class FullPaymentFinanceTests(TestCase):
    databases = {'default', 'movil'}

    def setUp(self):
        self.org = Organizacion.objects.create(nombre='Empresa local')
        self.foreign = Organizacion.objects.create(nombre='Empresa ajena')
        self.user = Usuario.objects.create(nombre_completo='Finanzas', usuario='finanzas', correo='finance@example.com',
                                           telefono='5511111111', contrasena_hash='unused')
        Membresia.objects.create(usuario=self.user, organizacion=self.org, estado='aceptado', rol='finanzas')
        token = 'finance-full-payment-test-token-with-sufficient-length'
        Sesion.objects.create(usuario=self.user, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                              expira_en=timezone.now() + timedelta(days=1))
        self.client.defaults['HTTP_AUTHORIZATION'] = 'Bearer ' + token
        self.sales = 0

    def sold(self, amount='1000.00', day=date(2020, 1, 15), organization=None, **kwargs):
        self.sales += 1
        fields = {'organizacion': organization or self.org, 'nombre': f'Cliente {self.sales}',
                  'correo': f'client{self.sales}@example.com', 'telefono': '5512345678',
                  'hubo_venta': True, 'monto_venta': Decimal(amount), 'descripcion_servicio': 'Desarrollo',
                  'fecha_venta': day}
        return Cliente.objects.create(**{**fields, **kwargs})

    def dashboard(self, period):
        response = self.client.get(BASE + 'finanzas/dashboard/?periodo=' + period)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def report(self, kind, period='2020-01'):
        response = self.client.get(BASE + f'finanzas/reportes/?periodo={period}&tipo={kind}')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def expense(self, amount='100.00', day=date(2020, 1, 1), organization=None):
        item = GastoOperativo.objects.create(organizacion=organization or self.org, concepto='Hosting',
                                            monto_mensual=Decimal(amount))
        GastoHistorial.objects.create(gasto=item, vigente_desde=day, concepto=item.concepto,
                                     monto_mensual=item.monto_mensual)
        return item

    def test_sale_is_collected_once_in_its_sale_month_with_exact_cents(self):
        project = self.sold('1000.00', date(2020, 1, 31))
        Requerimiento.objects.create(cliente=project, orden=1, titulo='Primera entrega')
        Requerimiento.objects.create(cliente=project, orden=2, titulo='Segunda entrega')
        self.sold('0.10', date(2020, 1, 31))
        self.sold('0.20', date(2020, 1, 31))
        self.sold('2000.15', date(2020, 2, 1))
        # El alta ocurre hoy, pero Finanzas usa la fecha histórica de la venta.
        self.assertNotEqual(project.creado_en.date(), project.fecha_venta)
        january = self.dashboard('2020-01')
        february = self.dashboard('2020-02')
        self.assertEqual(january['resumen']['cobros_mes'], '1000.30')
        self.assertEqual(february['resumen']['cobros_mes'], '2000.15')
        self.assertEqual(february['comparativo']['cobros_mes'], '1000.30')
        january_trend = next(row for row in february['tendencia'] if row['mes'] == '2020-01')
        self.assertEqual(january_trend['cobros_mes'], '1000.30')
        balance = self.report('balance-general', '2020-02')
        lines = {row['clave']: row['importe'] for row in balance['lineas']}
        self.assertEqual(lines['cobros_acumulados'], '3000.45')

    def test_foreign_sales_expenses_and_prospects_do_not_affect_finance(self):
        self.sold('1234.56')
        self.sold('9000.00', organization=self.foreign)
        self.sold('500.00', hubo_venta=False)
        self.expense('100.00')
        self.expense('900.00', organization=self.foreign)
        dashboard = self.dashboard('2020-01')
        self.assertEqual(dashboard['resumen']['cobros_mes'], '1234.56')
        self.assertEqual(dashboard['resumen']['gastos_mes'], '100.00')
        self.assertEqual(dashboard['resumen']['resultado_operativo'], '1134.56')
        self.assertEqual(len(dashboard['gastos']), 1)

    def test_all_reports_contain_only_complete_sale_income(self):
        self.sold('1200.50')
        self.expense('100.00')
        expected = {
            'estado-resultados': ('ingresos', 'resultado_registrado'),
            'flujo-efectivo': ('cobros_operacion', 'flujo_operacion'),
            'balance-general': ('cobros_acumulados', 'variacion_operativa_acumulada'),
        }
        for kind, (income_key, result_key) in expected.items():
            with self.subTest(kind=kind):
                report = self.report(kind)
                lines = {row['clave']: row['importe'] for row in report['lineas']}
                self.assertEqual(lines[income_key], '1200.50')
                self.assertEqual(lines[result_key], '1100.50')
                self.assertEqual(sum(row['clave'] == income_key for row in report['lineas']), 1)
                content = json.dumps(report, ensure_ascii=False).lower()
                self.assertNotIn('anticipo', content)
                self.assertNotIn('saldos_mes', content)
                self.assertNotIn('saldos finales', content)
                self.assertIn('importe total', report['alcance'])
        summary = self.dashboard('2020-01')['resumen']
        self.assertNotIn('anticipos_mes', summary)
        self.assertNotIn('saldos_mes', summary)

    def test_missing_invalid_and_future_sale_dates_are_not_collected(self):
        self.sold('250.00', date(2026, 10, 29))
        self.sold('1000.00', None)
        self.sold('2000.00', date(1899, 12, 31))
        self.sold('3000.00', date(2026, 10, 30))
        with patch('movil.business_finance.hoy', return_value=date(2026, 10, 29)):
            dashboard = self.dashboard('2026-10')
            balance = self.report('balance-general', '2026-10')
        self.assertEqual(dashboard['resumen']['cobros_mes'], '250.00')
        self.assertEqual(dashboard['ventas_sin_importes'], 3)
        lines = {row['clave']: row['importe'] for row in balance['lineas']}
        self.assertEqual(lines['cobros_acumulados'], '250.00')
        self.assertTrue(any('3 ventas' in message for message in dashboard['advertencias']))

    def test_empty_sales_are_zero_but_unknown_financial_concepts_stay_unknown(self):
        dashboard = self.dashboard('2020-01')
        self.assertEqual(dashboard['resumen']['cobros_mes'], '0.00')
        self.assertIsNone(dashboard['resumen']['gastos_mes'])
        self.assertIsNone(dashboard['resumen']['resultado_operativo'])
        self.assertIsNone(dashboard['resumen']['margen_operativo_pct'])
        report = self.report('estado-resultados')
        lines = {row['clave']: row['importe'] for row in report['lineas']}
        self.assertEqual(lines['ingresos'], '0.00')
        self.assertIsNone(lines['impuestos'])
        self.assertIsNone(lines['utilidad_neta'])
        balance = self.report('balance-general')
        lines = {row['clave']: row['importe'] for row in balance['lineas']}
        self.assertEqual(lines['cobros_acumulados'], '0.00')
        self.assertIsNone(lines['efectivo'])
        self.assertIsNone(lines['patrimonio'])

    def test_zero_expenses_are_distinct_from_missing_history(self):
        self.expense('0.00')
        summary = self.dashboard('2020-01')['resumen']
        self.assertEqual(summary['gastos_mes'], '0.00')
        self.assertEqual(summary['resultado_operativo'], '0.00')
        self.assertIsNone(summary['cobertura_gastos_pct'])
        self.assertIsNone(summary['margen_operativo_pct'])
