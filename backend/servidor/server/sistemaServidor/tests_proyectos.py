"""Reglas de Proyectos con autorización y cursores simulados, sin Neon real."""
import json
from contextlib import contextmanager, nullcontext
from unittest.mock import patch
from uuid import uuid4

from django.db import DatabaseError
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from .proyectos_view import (
    actualizar_estado_requerimiento,
    kanban_proyecto,
    listar_gestion_proyectos,
    listar_proyectos_pendientes,
    requerimientos_proyecto,
)


class ProyectosTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.prospecto_id = uuid4()
        self.requerimiento_id = uuid4()
        self.admin = (7, 'Administrador', 'admin', 'admin@example.com', 'admin')
        self.autorizar = self.enterContext(patch(
            'server.sistemaServidor.proyectos_view._autorizar_admin',
            return_value=(self.admin, None),
        ))
        self.conexiones = self.enterContext(patch('server.sistemaServidor.proyectos_view.connections'))
        self.conexiones.databases = {'neon': {}}
        self.cursor = self.conexiones.__getitem__.return_value.cursor.return_value.__enter__.return_value
        self.atomic = self.enterContext(patch(
            'server.sistemaServidor.proyectos_view.transaction.atomic',
            side_effect=lambda **kwargs: nullcontext(),
        ))

    def proyecto(self, fuente='whatsapp', total=0, completados=0):
        return (
            self.prospecto_id, fuente, 'Lucía', '+528100000101', 'Taller de diseño',
            'sistema-web', 'WhatsApp' if fuente == 'whatsapp' else 'Email Marketing',
            total, completados,
        )

    def requerimiento(self, estado='por_hacer'):
        return (self.requerimiento_id, 'Acceso de usuarios', 'Validar credenciales.', estado)

    def post(self, datos):
        return self.factory.post('/api/sistema/proyectos/', json.dumps(datos), content_type='application/json')

    def guardar(self, datos, fuente='whatsapp'):
        return requerimientos_proyecto(self.post(datos), fuente, self.prospecto_id)

    def cambiar_estado(self, datos, fuente='whatsapp'):
        return actualizar_estado_requerimiento(
            self.post(datos), fuente, self.prospecto_id, self.requerimiento_id,
        )

    def test_todas_las_operaciones_requieren_administrador_antes_de_usar_neon(self):
        operaciones = (
            lambda: listar_proyectos_pendientes(self.factory.get('/')),
            lambda: listar_gestion_proyectos(self.factory.get('/')),
            lambda: requerimientos_proyecto(self.factory.get('/'), 'whatsapp', self.prospecto_id),
            lambda: kanban_proyecto(self.factory.get('/'), 'whatsapp', self.prospecto_id),
            lambda: self.guardar({'requerimientos': [{'titulo': 'Acceso', 'descripcion': ''}]}),
            lambda: self.cambiar_estado({'estado': 'completado'}),
        )
        for estado in (401, 403):
            self.autorizar.return_value = (None, JsonResponse({'ok': False}, status=estado))
            for indice, operacion in enumerate(operaciones):
                with self.subTest(estado=estado, operacion=indice):
                    self.assertEqual(operacion().status_code, estado)
        self.conexiones.__getitem__.assert_not_called()
        self.atomic.assert_not_called()

    def test_fuente_invalida_no_accede_a_base(self):
        for fuente in ('otro', '', 'WhatsApp', "whatsapp' OR TRUE --"):
            for operacion in (
                lambda: requerimientos_proyecto(self.factory.get('/'), fuente, self.prospecto_id),
                lambda: kanban_proyecto(self.factory.get('/'), fuente, self.prospecto_id),
                lambda: self.guardar({'requerimientos': [{'titulo': 'Acceso', 'descripcion': ''}]}, fuente),
                lambda: self.cambiar_estado({'estado': 'completado'}, fuente),
            ):
                with self.subTest(fuente=fuente):
                    self.assertEqual(operacion().status_code, 400)
        self.conexiones.__getitem__.assert_not_called()

    def test_paginacion_y_busqueda_invalidas_no_consultan_base(self):
        for listar in (listar_proyectos_pendientes, listar_gestion_proyectos):
            for filtros in ({'pagina': '0'}, {'pagina': '-1'}, {'pagina': 'a'},
                            {'pagina': '100001'}, {'buscar': 'x' * 101}):
                with self.subTest(vista=listar.__name__, filtros=filtros):
                    self.assertEqual(listar(self.factory.get('/', filtros)).status_code, 400)
        self.conexiones.__getitem__.assert_not_called()

    def test_pendientes_y_gestion_separan_las_ventas_por_requerimientos(self):
        for fuente in ('whatsapp', 'email-marketing'):
            for listar, definidos in ((listar_proyectos_pendientes, False), (listar_gestion_proyectos, True)):
                with self.subTest(fuente=fuente, definidos=definidos):
                    self.cursor.reset_mock()
                    self.cursor.fetchone.return_value = (1,)
                    self.cursor.fetchall.return_value = [self.proyecto(fuente, int(definidos), 0)]
                    respuesta = listar(self.factory.get('/'))
                    self.assertEqual(respuesta.status_code, 200)
                    datos = json.loads(respuesta.content)
                    self.assertEqual(datos['total'], 1)
                    self.assertEqual(datos['proyectos'][0]['fuente'], fuente)
                    self.assertEqual(datos['proyectos'][0]['id'], str(self.prospecto_id))
                    self.assertEqual(datos['proyectos'][0]['total_requerimientos'], int(definidos))
                    self.assertEqual(respuesta['Cache-Control'], 'no-store')
                    for consulta in self.cursor.execute.call_args_list:
                        sql = consulta.args[0]
                        self.assertIn('v.hubo_venta = TRUE', sql)
                        self.assertIn('public.prospectos_oferta_valor', sql)
                        self.assertIn('public.leads_magnet', sql)
                        # Una venta cerrada permanece independiente de su calificación comercial.
                        self.assertNotIn('brindo_nombre = TRUE', sql)
                        self.assertNotIn('respondio_mensajes = TRUE', sql)
                        self.assertNotIn('proyecto_liquidado =', sql)
                        self.assertIn(
                            'AND COALESCE(r.total_requerimientos, 0) ' + ('> 0' if definidos else '= 0'),
                            sql,
                        )

    def test_busqueda_se_parametriza_y_paginacion_limita_resultados(self):
        buscar = "x%' OR 1=1 --"
        self.cursor.fetchone.return_value = (26,)
        self.cursor.fetchall.return_value = []
        for listar in (listar_proyectos_pendientes, listar_gestion_proyectos):
            self.cursor.reset_mock()
            respuesta = listar(self.factory.get('/', {'buscar': buscar, 'pagina': '2'}))
            self.assertEqual(respuesta.status_code, 200)
            datos = json.loads(respuesta.content)
            self.assertEqual(datos['pagina'], 2)
            self.assertEqual(datos['paginas'], 2)
            for consulta in self.cursor.execute.call_args_list:
                sql, parametros = consulta.args
                self.assertNotIn(buscar, sql)
                self.assertIn('%' + buscar + '%', parametros)
            sql, parametros = self.cursor.execute.call_args.args
            self.assertIn('LIMIT %s OFFSET %s', sql)
            self.assertEqual(parametros[-2:], [datos['por_pagina'], datos['por_pagina']])

    def test_lista_inicial_requiere_entre_uno_y_cien_requerimientos_validos(self):
        validos = [{'titulo': 'Acceso', 'descripcion': ''}]
        invalidos = (
            None, [], {}, {'requerimientos': []}, {'requerimientos': validos * 101},
            {'requerimientos': 'Acceso'}, {'requerimientos': validos, 'admin': True},
            {'requerimientos': [None]}, {'requerimientos': ['Acceso']},
            {'requerimientos': [{'titulo': '', 'descripcion': ''}]},
            {'requerimientos': [{'titulo': '   ', 'descripcion': ''}]},
            {'requerimientos': [{'titulo': 'x' * 151, 'descripcion': ''}]},
            {'requerimientos': [{'titulo': None, 'descripcion': ''}]},
            {'requerimientos': [{'titulo': 'Acceso', 'descripcion': 'x' * 2001}]},
            {'requerimientos': [{'titulo': 'Acceso', 'descripcion': None}]},
            {'requerimientos': [{'titulo': 'Acceso', 'descripcion': '', 'estado': 'completado'}]},
            {'requerimientos': [{'titulo': 'Acceso\x00', 'descripcion': ''}]},
            {'requerimientos': [{'titulo': 'Acceso', 'descripcion': '\x00'}]},
            {'requerimientos': [{'titulo': '\ud800', 'descripcion': ''}]},
            {'requerimientos': [{'titulo': 'Acceso', 'descripcion': '\ud800'}]},
        )
        for payload in invalidos:
            with self.subTest(payload=repr(payload)):
                self.assertEqual(self.guardar(payload).status_code, 400)
        self.conexiones.__getitem__.assert_not_called()
        self.atomic.assert_not_called()

    def test_mutaciones_rechazan_json_invalido_y_content_type_incorrecto(self):
        for cuerpo in ('{', '[', 'null', 'true', '{"estado": NaN}'):
            for vista, argumentos in (
                (requerimientos_proyecto, ('whatsapp', self.prospecto_id)),
                (actualizar_estado_requerimiento, ('whatsapp', self.prospecto_id, self.requerimiento_id)),
            ):
                with self.subTest(cuerpo=cuerpo, vista=vista.__name__):
                    request = self.factory.post('/', data=cuerpo, content_type='application/json')
                    self.assertEqual(vista(request, *argumentos).status_code, 400)
        for vista, argumentos in (
            (requerimientos_proyecto, ('whatsapp', self.prospecto_id)),
            (actualizar_estado_requerimiento, ('whatsapp', self.prospecto_id, self.requerimiento_id)),
        ):
            request = self.factory.post('/', data='estado=completado', content_type='text/plain')
            self.assertEqual(vista(request, *argumentos).status_code, 415)
        self.conexiones.__getitem__.assert_not_called()

    def test_estados_invalidos_no_llegan_a_neon(self):
        for datos in ({}, [], None, {'estado': 'Completado'}, {'estado': 'pendiente'},
                      {'estado': True}, {'estado': None}, {'estado': []},
                      {'estado': 'completado', 'prospecto_id': str(uuid4())}):
            with self.subTest(datos=datos):
                self.assertEqual(self.cambiar_estado(datos).status_code, 400)
        self.conexiones.__getitem__.assert_not_called()

    def test_solicitudes_demasiado_grandes_se_rechazan_antes_de_consultar_neon(self):
        for vista, argumentos in (
            (requerimientos_proyecto, ('whatsapp', self.prospecto_id)),
            (actualizar_estado_requerimiento, ('whatsapp', self.prospecto_id, self.requerimiento_id)),
        ):
            with self.subTest(vista=vista.__name__):
                request = self.factory.post('/', data=' ' * (60 * 1024 + 1), content_type='application/json')
                self.assertEqual(vista(request, *argumentos).status_code, 413)
        self.conexiones.__getitem__.assert_not_called()

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=100)
    def test_limite_global_de_django_devuelve_json_413(self):
        for vista, argumentos in (
            (requerimientos_proyecto, ('whatsapp', self.prospecto_id)),
            (actualizar_estado_requerimiento, ('whatsapp', self.prospecto_id, self.requerimiento_id)),
        ):
            with self.subTest(vista=vista.__name__):
                request = self.factory.post('/', data=' ' * 101, content_type='application/json')
                respuesta = vista(request, *argumentos)
                self.assertEqual(respuesta.status_code, 413)
                self.assertFalse(json.loads(respuesta.content)['ok'])
                self.assertEqual(respuesta['Cache-Control'], 'no-store')
        self.conexiones.__getitem__.assert_not_called()

    def test_detalle_pendiente_abre_lista_vacia_y_no_abre_kanban(self):
        self.cursor.fetchone.return_value = self.proyecto()
        self.cursor.fetchall.return_value = []
        respuesta = requerimientos_proyecto(self.factory.get('/'), 'whatsapp', self.prospecto_id)
        self.assertEqual(respuesta.status_code, 200)
        datos = json.loads(respuesta.content)
        self.assertEqual(datos['requerimientos'], [])
        self.assertFalse(datos['requerimientos_definidos'])
        self.assertEqual(kanban_proyecto(self.factory.get('/'), 'whatsapp', self.prospecto_id).status_code, 409)

    def test_detalle_exige_venta_cerrada_y_acota_ambas_lecturas_a_la_fuente_y_cliente(self):
        self.cursor.fetchone.return_value = self.proyecto('email-marketing', 1)
        self.cursor.fetchall.return_value = [self.requerimiento()]
        respuesta = requerimientos_proyecto(self.factory.get('/'), 'email-marketing', self.prospecto_id)
        self.assertEqual(respuesta.status_code, 200)
        for consulta in self.cursor.execute.call_args_list:
            sql, parametros = consulta.args
            self.assertEqual(parametros, ['email-marketing', str(self.prospecto_id)])
            self.assertIn('fuente = %s', sql)
            self.assertIn('prospecto_id = %s', sql)
        self.assertIn('v.hubo_venta = TRUE', self.cursor.execute.call_args_list[0].args[0])

    def test_detalle_y_kanban_rechazan_proyecto_sin_venta_cerrada(self):
        self.cursor.fetchone.return_value = None
        for vista in (requerimientos_proyecto, kanban_proyecto):
            with self.subTest(vista=vista.__name__):
                self.assertEqual(vista(self.factory.get('/'), 'whatsapp', self.prospecto_id).status_code, 404)
        self.cursor.fetchall.assert_not_called()

    def test_guardado_inicial_completo_en_una_transaccion_y_todos_por_hacer(self):
        for fuente in ('whatsapp', 'email-marketing'):
            with self.subTest(fuente=fuente):
                self.cursor.reset_mock()
                self.atomic.reset_mock()
                segundo_id = uuid4()
                self.cursor.fetchone.side_effect = [(self.prospecto_id,), None, self.proyecto(fuente, 2)]
                self.cursor.fetchall.return_value = [
                    self.requerimiento(), (segundo_id, 'Reportes', '', 'por_hacer'),
                ]
                respuesta = self.guardar({'requerimientos': [
                    {'titulo': ' Acceso de usuarios ', 'descripcion': ' Validar credenciales. '},
                    {'titulo': 'Reportes', 'descripcion': ''},
                ]}, fuente)
                self.assertEqual(respuesta.status_code, 200)
                datos = json.loads(respuesta.content)
                self.assertTrue(datos['requerimientos_definidos'])
                self.assertEqual(datos['proyecto']['total_requerimientos'], 2)
                self.assertEqual([r['estado'] for r in datos['requerimientos']], ['por_hacer', 'por_hacer'])
                self.atomic.assert_called_once_with(using='neon')
                bloqueo = self.cursor.execute.call_args_list[0]
                self.assertIn('FOR UPDATE OF v', bloqueo.args[0])
                self.assertIn('v.hubo_venta = TRUE', bloqueo.args[0])
                self.assertEqual(bloqueo.args[1], [fuente, str(self.prospecto_id)])
                self.cursor.executemany.assert_called_once()
                sql, filas = self.cursor.executemany.call_args.args
                self.assertIn("'por_hacer'", sql)
                self.assertEqual(len(filas), 2)
                self.assertNotEqual(filas[0][0], filas[1][0])
                self.assertEqual(filas[0][1:], [fuente, str(self.prospecto_id), 1,
                                               'Acceso de usuarios', 'Validar credenciales.', self.admin[0]])
                self.assertEqual(filas[1][1:], [fuente, str(self.prospecto_id), 2, 'Reportes', '', self.admin[0]])

    def test_se_aceptan_cien_requerimientos_y_limites_de_texto(self):
        texto_largo = {'titulo': 'x' * 150, 'descripcion': 'y' * 2000}
        requerimientos = [texto_largo] + [{'titulo': 'Requerimiento', 'descripcion': ''}] * 99
        self.cursor.fetchone.side_effect = [(self.prospecto_id,), None, self.proyecto(total=100)]
        self.cursor.fetchall.return_value = [self.requerimiento()] * 100
        respuesta = self.guardar({'requerimientos': requerimientos})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(self.cursor.executemany.call_args.args[1]), 100)

    def test_doble_guardado_no_reemplaza_requerimientos_ni_sus_estados(self):
        self.cursor.fetchone.side_effect = [(self.prospecto_id,), (1,)]
        respuesta = self.guardar({'requerimientos': [{'titulo': 'Nueva captura', 'descripcion': ''}]})
        self.assertEqual(respuesta.status_code, 409)
        self.cursor.executemany.assert_not_called()
        for consulta in self.cursor.execute.call_args_list:
            self.assertTrue(consulta.args[0].lstrip().startswith('SELECT'))

    def test_no_se_escriben_requerimientos_ni_estado_si_se_revoco_la_venta(self):
        self.cursor.fetchone.return_value = None
        for operacion in (
            lambda: self.guardar({'requerimientos': [{'titulo': 'Acceso', 'descripcion': ''}]}),
            lambda: self.cambiar_estado({'estado': 'en_progreso'}),
        ):
            self.cursor.reset_mock()
            self.assertEqual(operacion().status_code, 409)
            self.cursor.executemany.assert_not_called()
            self.cursor.execute.assert_called_once()
            self.assertIn('v.hubo_venta = TRUE', self.cursor.execute.call_args.args[0])

    def test_fallo_al_insertar_se_propaga_fuera_de_la_transaccion_para_revertir_la_lista(self):
        errores_transaccion = []

        @contextmanager
        def transaccion(**kwargs):
            try:
                yield
            except DatabaseError as error:
                errores_transaccion.append(error)
                raise

        self.atomic.side_effect = transaccion
        self.cursor.fetchone.side_effect = [(self.prospecto_id,), None]
        self.cursor.executemany.side_effect = DatabaseError('falla durante la segunda fila')
        with self.assertLogs('server.sistemaServidor.proyectos_view', level='ERROR'):
            respuesta = self.guardar({'requerimientos': [
                {'titulo': 'Acceso', 'descripcion': ''}, {'titulo': 'Reportes', 'descripcion': ''},
            ]})
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(len(errores_transaccion), 1)
        self.assertNotIn('falla durante', respuesta.content.decode())

    def test_kanban_conserva_las_tres_columnas_y_calcula_avance_de_las_tarjetas(self):
        self.cursor.fetchone.return_value = self.proyecto(total=3)
        self.cursor.fetchall.return_value = [
            (uuid4(), 'Acceso', '', 'por_hacer'),
            (uuid4(), 'Reportes', 'Exportar PDF', 'en_progreso'),
            (uuid4(), 'Clientes', '', 'completado'),
        ]
        respuesta = kanban_proyecto(self.factory.get('/'), 'whatsapp', self.prospecto_id)
        self.assertEqual(respuesta.status_code, 200)
        datos = json.loads(respuesta.content)
        self.assertTrue(datos['requerimientos_definidos'])
        self.assertEqual([r['estado'] for r in datos['requerimientos']], ['por_hacer', 'en_progreso', 'completado'])
        self.assertEqual(datos['proyecto']['total_requerimientos'], 3)
        self.assertEqual(datos['proyecto']['completados'], 1)

    def test_cambio_de_estado_aisla_requerimiento_fuente_y_proyecto(self):
        for fuente in ('whatsapp', 'email-marketing'):
            for estado in ('por_hacer', 'en_progreso', 'completado'):
                with self.subTest(fuente=fuente, estado=estado):
                    self.cursor.reset_mock()
                    self.cursor.fetchone.side_effect = [(self.prospecto_id,), self.requerimiento(estado)]
                    respuesta = self.cambiar_estado({'estado': estado}, fuente)
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertEqual(json.loads(respuesta.content)['requerimiento']['estado'], estado)
                    sql, parametros = self.cursor.execute.call_args.args
                    self.assertIn('WHERE id = %s AND fuente = %s AND prospecto_id = %s', sql)
                    self.assertEqual(parametros, [estado, self.admin[0], str(self.requerimiento_id),
                                                  fuente, str(self.prospecto_id)])
                    self.assertIn('FOR UPDATE OF v', self.cursor.execute.call_args_list[0].args[0])

    def test_requerimiento_de_otro_proyecto_no_se_actualiza(self):
        self.cursor.fetchone.side_effect = [(self.prospecto_id,), None]
        respuesta = self.cambiar_estado({'estado': 'completado'}, 'email-marketing')
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(self.cursor.execute.call_count, 2)
        self.cursor.executemany.assert_not_called()

    def test_metodos_no_soportados_se_rechazan(self):
        self.assertEqual(listar_proyectos_pendientes(self.factory.post('/')).status_code, 405)
        self.assertEqual(listar_gestion_proyectos(self.factory.post('/')).status_code, 405)
        self.assertEqual(kanban_proyecto(self.factory.post('/'), 'whatsapp', self.prospecto_id).status_code, 405)
        self.assertEqual(requerimientos_proyecto(self.factory.delete('/'), 'whatsapp', self.prospecto_id).status_code, 405)
        self.assertEqual(actualizar_estado_requerimiento(
            self.factory.get('/'), 'whatsapp', self.prospecto_id, self.requerimiento_id,
        ).status_code, 405)
        self.conexiones.__getitem__.assert_not_called()

    def test_error_de_neon_al_listar_no_expone_detalles_sql(self):
        self.cursor.execute.side_effect = DatabaseError('secret connection SQL detail')
        with self.assertLogs('server.sistemaServidor.proyectos_view', level='ERROR'):
            respuesta = listar_proyectos_pendientes(self.factory.get('/'))
        self.assertEqual(respuesta.status_code, 503)
        self.assertNotIn('secret connection SQL detail', respuesta.content.decode())

