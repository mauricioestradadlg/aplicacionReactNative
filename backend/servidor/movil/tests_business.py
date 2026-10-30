"""Regresiones funcionales y aislamiento entre empresas, sin servicios externos."""
import hashlib
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import include, path
from django.utils import timezone

from .models import Cliente, GastoHistorial, GastoOperativo, Membresia, Organizacion, Requerimiento, Sesion, Usuario

urlpatterns = [path('api/sistema/app/', include('movil.urls_business'))]
BASE = '/api/sistema/app/'


@override_settings(ROOT_URLCONF='movil.tests_business')
class BusinessTests(TestCase):
    databases = {'default', 'movil'}

    def setUp(self):
        self.org = Organizacion.objects.create(nombre='Primera empresa')
        self.other = Organizacion.objects.create(nombre='Segunda empresa')
        self.user = Usuario.objects.create(nombre_completo='Administrador', usuario='admin', correo='admin@example.com',
                                           telefono='5511111111', contrasena_hash='unused')
        self.member = Membresia.objects.create(usuario=self.user, organizacion=self.org, estado='aceptado', rol='admin')
        self.token = 'mobile-test-session-token-with-sufficient-length'
        Sesion.objects.create(usuario=self.user, token_hash=hashlib.sha256(self.token.encode()).hexdigest(),
                              expira_en=timezone.now() + timedelta(days=1))
        self.client.defaults['HTTP_AUTHORIZATION'] = 'Bearer ' + self.token
        self.foreign = Cliente.objects.create(organizacion=self.other, nombre='Cliente privado', correo='private@example.com',
                                             telefono='5512345678', hubo_venta=True, monto_venta=Decimal('9000'),
                                             descripcion_servicio='Aplicación privada', fecha_venta=date(2026, 1, 1))

    def post(self, route, data):
        return self.client.post(BASE + route, data, content_type='application/json')

    def sold(self, **kwargs):
        fields = {'organizacion': self.org, 'nombre': 'Cliente local', 'correo': 'local@example.com',
                  'telefono': '5587654321', 'hubo_venta': True, 'monto_venta': Decimal('1000'),
                  'descripcion_servicio': 'Aplicación de inventario', 'fecha_venta': date(2026, 1, 1)}
        return Cliente.objects.create(**{**fields, **kwargs})

    def test_client_lists_search_and_dashboard_hide_other_organizations(self):
        self.sold()
        response = self.client.get(BASE + 'clientes/?buscar=privado')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['clientes'], [])
        dashboard = self.client.get(BASE + 'dashboard-crm/').json()
        self.assertEqual(dashboard['total_clientes'], 1)
        self.assertEqual(dashboard['total_ventas'], 1)
        self.assertEqual(dashboard['monto_ventas'], '1000.00')
        self.assertEqual([v['nombre'] for v in dashboard['ventas_recientes']], ['Cliente local'])

    def test_cross_company_client_writes_and_retired_payment_routes_are_denied(self):
        response = self.client.patch(BASE + f'clientes/{self.foreign.id}/', {'nombre': 'Intruso'}, content_type='application/json')
        self.assertEqual(response.status_code, 404)
        response = self.post(f'gestion-ventas/{self.foreign.id}/liquidacion/', {
            'importe_total': '9000', 'importe_anticipo': '100', 'fecha_anticipo': '2020-01-01', 'proyecto_liquidado': False})
        self.assertEqual(response.status_code, 404)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.nombre, 'Cliente privado')
        self.assertEqual(self.foreign.monto_venta, Decimal('9000'))

    def test_registration_and_sale_validation(self):
        data = {'nombre': 'Persona', 'correo': 'PERSON@example.com', 'telefono': '5512345678', 'comentarios': 'Reunión',
                'hubo_venta': False, 'monto_venta': None, 'descripcion_servicio': ''}
        response = self.post('clientes/', data)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['cliente']['correo'], 'person@example.com')
        item_id = response.json()['cliente']['id']
        for bad in ['NaN', 'Infinity', '-1', '0', '1.234', '10000000000', True]:
            result = self.client.patch(BASE + f'clientes/{item_id}/', {
                'hubo_venta': True, 'monto_venta': bad, 'descripcion_servicio': 'Desarrollo'}, content_type='application/json')
            self.assertEqual(result.status_code, 400, (bad, result.content))
        result = self.client.patch(BASE + f'clientes/{item_id}/', {'hubo_venta': True, 'monto_venta': '2500.50',
                                   'descripcion_servicio': 'Desarrollo'}, content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['cliente']['fuente'], 'directo')
        from .business_common import hoy
        self.assertEqual(result.json()['cliente']['fecha_venta'], hoy().isoformat())
        self.assertFalse({'importe_anticipo', 'fecha_anticipo', 'proyecto_liquidado', 'fecha_liquidacion'} & result.json()['cliente'].keys())
        self.assertEqual(self.client.get(BASE + 'proyectos/pendientes/').json()['total'], 1)

    def test_client_rejects_organization_override_and_duplicate_email(self):
        self.sold()
        data = {'nombre': 'Duplicado', 'correo': 'LOCAL@example.com', 'telefono': '5555555555', 'hubo_venta': False}
        response = self.post('clientes/', data)
        self.assertEqual(response.status_code, 409)
        response = self.post('clientes/', {**data, 'correo': 'new@example.com', 'organizacion': str(self.other.id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Cliente.objects.filter(organizacion=self.org).count(), 1)

    def test_role_boundaries_and_revoked_membership(self):
        for role, allowed, forbidden in [
            ('crm', 'clientes/', 'proyectos/pendientes/'),
            ('desarrollador', 'proyectos/pendientes/', 'finanzas/gastos-operativos/'),
            ('finanzas', 'finanzas/gastos-operativos/', 'clientes/'),
        ]:
            self.member.rol = role
            self.member.save()
            self.assertEqual(self.client.get(BASE + allowed).status_code, 200)
            self.assertEqual(self.client.get(BASE + forbidden).status_code, 403)
        self.member.estado = 'eliminado'
        self.member.save()
        self.assertEqual(self.client.get(BASE + 'finanzas/gastos-operativos/').status_code, 403)

    def test_requirements_capture_moves_project_and_preserves_on_repeat(self):
        item = self.sold()
        route = f'proyectos/directo/{item.id}/'
        self.assertEqual(self.client.get(BASE + route + 'kanban/').status_code, 409)
        response = self.post(route + 'requerimientos/', {'requerimientos': [
            {'titulo': 'Inicio de sesión', 'descripcion': 'Con permisos'}, {'titulo': 'Inventario', 'descripcion': ''}]})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get(BASE + 'proyectos/pendientes/').json()['total'], 0)
        self.assertEqual(self.client.get(BASE + 'proyectos/gestion/').json()['total'], 1)
        self.assertEqual(self.post(route + 'requerimientos/', {'requerimientos': [{'titulo': 'Otra tarea'}]}).status_code, 409)
        self.assertEqual(item.requerimientos.count(), 2)
        task_id = response.json()['requerimientos'][0]['id']
        self.assertEqual(self.post(route + f'requerimientos/{task_id}/estado/', {'estado': 'invalido'}).status_code, 400)
        self.assertEqual(self.post(route + f'requerimientos/{task_id}/estado/', {'estado': 'en_progreso'}).status_code, 200)
        self.assertEqual(self.post(route + f'requerimientos/{task_id}/estado/', {'estado': 'completado'}).status_code, 200)
        self.assertEqual(self.client.get(BASE + 'proyectos/gestion/').json()['proyectos'][0]['completados'], 1)
        self.assertEqual(self.client.patch(BASE + f'clientes/{item.id}/', {'hubo_venta': False}, content_type='application/json').status_code, 400)

    def test_requirements_foreign_project_and_foreign_requirement_are_hidden(self):
        local = self.sold()
        foreign_task = Requerimiento.objects.create(cliente=self.foreign, orden=1, titulo='Confidencial')
        prefix = f'proyectos/directo/{self.foreign.id}/'
        self.assertEqual(self.client.get(BASE + prefix + 'requerimientos/').status_code, 404)
        self.assertEqual(self.post(prefix + 'requerimientos/', {'requerimientos': [{'titulo': 'Intruso'}]}).status_code, 404)
        self.assertEqual(self.post(f'proyectos/directo/{local.id}/requerimientos/{foreign_task.id}/estado/', {'estado': 'completado'}).status_code, 404)
        foreign_task.refresh_from_db()
        self.assertEqual(foreign_task.estado, 'por_hacer')

    def test_requirements_validation_is_atomic(self):
        item = self.sold()
        route = f'proyectos/directo/{item.id}/requerimientos/'
        for items in [[], [{'titulo': 'Correcto'}, {'titulo': ' '}], [{'titulo': 'x' * 151}], [{'titulo': 'Tarea'}] * 101]:
            self.assertEqual(self.post(route, {'requerimientos': items}).status_code, 400)
            self.assertEqual(item.requerimientos.count(), 0)

    def test_finance_uses_full_sale_amount_and_excludes_foreign_money(self):
        local = self.sold(fecha_venta=date(2020, 1, 15))
        self.foreign.fecha_venta = date(2020, 1, 15)
        self.foreign.save()
        january = self.client.get(BASE + 'finanzas/dashboard/?periodo=2020-01').json()
        february = self.client.get(BASE + 'finanzas/dashboard/?periodo=2020-02').json()
        self.assertEqual(january['resumen']['cobros_mes'], '1000.00')
        self.assertEqual(february['resumen']['cobros_mes'], '0.00')
        self.assertIsNone(january['resumen']['gastos_mes'])
        self.assertIsNone(january['resumen']['resultado_operativo'])
        report = self.client.get(BASE + 'finanzas/reportes/?periodo=2020-02&tipo=balance-general').json()
        lines = {line['clave']: line['importe'] for line in report['lineas']}
        self.assertEqual(lines['cobros_acumulados'], '1000.00')
        self.assertIsNone(lines['efectivo'])
        self.assertIsNone(lines['patrimonio'])
        # Corregir una venta sin requerimientos no exige un flujo de pagos aparte.
        self.assertEqual(self.client.patch(BASE + f'clientes/{local.id}/', {'hubo_venta': False}, content_type='application/json').status_code, 200)
        local.refresh_from_db()
        self.assertIsNone(local.monto_venta)
        self.assertIsNone(local.fecha_venta)

    def test_finance_retires_partial_payment_writes_without_changing_sale(self):
        local = self.sold()
        route = f'gestion-ventas/{local.id}/liquidacion/'
        self.assertEqual(self.client.get(BASE + 'gestion-ventas/').status_code, 404)
        self.assertEqual(self.post(route, {'importe_total': '1000', 'importe_anticipo': '100',
                         'fecha_anticipo': '2020-01-15', 'proyecto_liquidado': False}).status_code, 404)
        for forbidden in [{'importe_anticipo': '100'}, {'fecha_anticipo': '2020-01-15'},
                          {'fecha_liquidacion': '2020-02-15'}, {'proyecto_liquidado': True}]:
            self.assertEqual(self.client.patch(BASE + f'clientes/{local.id}/', forbidden,
                             content_type='application/json').status_code, 400)
            local.refresh_from_db()
            self.assertEqual(local.monto_venta, Decimal('1000'))
            self.assertEqual(local.fecha_venta, date(2026, 1, 1))

    def test_expense_history_is_preserved_and_tenant_scoped(self):
        foreign = GastoOperativo.objects.create(organizacion=self.other, concepto='Gasto ajeno', monto_mensual=Decimal('999'))
        GastoHistorial.objects.create(gasto=foreign, vigente_desde=date(2020, 1, 1), concepto=foreign.concepto, monto_mensual=foreign.monto_mensual)
        with patch('movil.business_finance._mes', return_value=date(2020, 1, 1)):
            response = self.post('finanzas/gastos-operativos/', {'concepto': 'Hosting', 'monto_mensual': '100'})
        self.assertEqual(response.status_code, 201, response.content)
        item_id = response.json()['gastos'][0]['id']
        self.assertEqual(response.json()['total_mensual'], '100.00')
        with patch('movil.business_finance._mes', return_value=date(2020, 2, 1)):
            response = self.post(f'finanzas/gastos-operativos/{item_id}/', {'concepto': 'Hosting mejorado', 'monto_mensual': '200'})
        self.assertEqual(response.status_code, 200)
        with patch('movil.business_finance._mes', return_value=date(2020, 3, 1)):
            self.assertEqual(self.client.delete(BASE + f'finanzas/gastos-operativos/{item_id}/').status_code, 200)
        for period, expected in [('2020-01', '100.00'), ('2020-02', '200.00'), ('2020-03', '0.00')]:
            dashboard = self.client.get(BASE + 'finanzas/dashboard/?periodo=' + period).json()
            self.assertEqual(dashboard['resumen']['gastos_mes'], expected, dashboard)
        report = self.client.get(BASE + 'finanzas/reportes/?periodo=2020-03&tipo=balance-general').json()
        self.assertEqual(next(line['importe'] for line in report['lineas'] if line['clave'] == 'gastos_acumulados'), '300.00')
        self.assertEqual(self.post(f'finanzas/gastos-operativos/{foreign.id}/', {'concepto': 'Intrusión', 'monto_mensual': '0'}).status_code, 404)

    def test_finance_rejects_invalid_periods_and_preserves_unknown_values(self):
        for period in ['1899-12', '2020-13', '2999-01', '20-01', '2020-01-01']:
            self.assertEqual(self.client.get(BASE + 'finanzas/dashboard/?periodo=' + period).status_code, 400)
        self.assertEqual(self.client.get(BASE + 'finanzas/reportes/?tipo=no-existe').status_code, 400)
        report = self.client.get(BASE + 'finanzas/reportes/?periodo=2020-01&tipo=estado-resultados').json()
        lines = {line['clave']: line['importe'] for line in report['lineas']}
        self.assertEqual(lines['ingresos'], '0.00')
        self.assertIsNone(lines['impuestos'])
        self.assertIsNone(lines['utilidad_neta'])

    def test_finance_expenses_reject_nonfinite_and_fractional_cents(self):
        for bad in ['NaN', 'Infinity', '-1', '1.001', '10000000000.00', False]:
            self.assertEqual(self.post('finanzas/gastos-operativos/', {'concepto': 'Gasto', 'monto_mensual': bad}).status_code, 400)
        self.assertFalse(GastoOperativo.objects.filter(organizacion=self.org).exists())

    def test_business_json_errors_preserve_http_status(self):
        self.assertEqual(self.client.post(BASE + 'clientes/', {'nombre': 'Nombre'}).status_code, 415)
        response = self.post('clientes/', {'nombre': 'x' * 66000})
        self.assertEqual(response.status_code, 413)

    def test_crm_to_project_and_full_payment_reports_across_roles(self):
        from .business_common import hoy
        day = hoy().isoformat()
        period = day[:7]
        self.member.rol = 'crm'
        self.member.save()
        created = self.post('clientes/', {'nombre': 'Nuevo proyecto', 'correo': 'nuevo@example.com', 'telefono': '5555555555',
                            'hubo_venta': True, 'monto_venta': '1000.00', 'descripcion_servicio': 'Sistema general'})
        self.assertEqual(created.status_code, 201, created.content)
        item_id = created.json()['cliente']['id']
        self.assertEqual(self.client.get(BASE + 'finanzas/dashboard/').status_code, 403)
        self.member.rol = 'desarrollador'
        self.member.save()
        self.assertEqual(self.client.get(BASE + 'proyectos/pendientes/').json()['proyectos'][0]['id'], item_id)
        project_route = f'proyectos/directo/{item_id}/'
        defined = self.post(project_route + 'requerimientos/', {'requerimientos': [{'titulo': 'Entregar aplicación'}]})
        self.assertEqual(defined.status_code, 200, defined.content)
        task_id = defined.json()['requerimientos'][0]['id']
        self.assertEqual(self.post(project_route + f'requerimientos/{task_id}/estado/', {'estado': 'completado'}).status_code, 200)
        self.assertEqual(self.client.get(BASE + project_route + 'kanban/').json()['proyecto']['completados'], 1)
        self.member.rol = 'finanzas'
        self.member.save()
        self.assertEqual(self.client.get(BASE + 'clientes/').status_code, 403)
        self.assertEqual(self.post('finanzas/gastos-operativos/', {'concepto': 'Hosting', 'monto_mensual': '100.00'}).status_code, 201)
        dashboard = self.client.get(BASE + 'finanzas/dashboard/?periodo=' + period).json()
        self.assertEqual(dashboard['resumen']['cobros_mes'], '1000.00')
        self.assertEqual(dashboard['resumen']['resultado_operativo'], '900.00')
        report = self.client.get(BASE + f'finanzas/reportes/?periodo={period}&tipo=flujo-efectivo').json()
        lines = {line['clave']: line['importe'] for line in report['lineas']}
        self.assertEqual(lines['cobros_operacion'], '1000.00')
        self.assertEqual(lines['flujo_operacion'], '900.00')
        self.member.rol = 'crm'
        self.member.save()
        changed = self.client.patch(BASE + f'clientes/{item_id}/', {'monto_venta': '500'}, content_type='application/json')
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(Cliente.objects.get(pk=item_id).monto_venta, Decimal('500'))
        self.assertEqual(Cliente.objects.get(pk=item_id).fecha_venta.isoformat(), day)
        self.assertEqual(self.client.patch(BASE + f'clientes/{item_id}/', {'hubo_venta': False}, content_type='application/json').status_code, 400)
