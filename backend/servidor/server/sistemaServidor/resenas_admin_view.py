"""Moderación interna de reseñas de Proyectos MEG.

GET  /api/sistema/resenas/?estado=pendiente&pagina=1
POST /api/sistema/resenas/<uuid>/decision/ {"decision": "aprobar" | "rechazar"}

El acceso se verifica SIEMPRE en el backend: sesión activa + rol admin.
No se altera la VIEW public.resenas_publicas; lee la tabla subyacente.
"""
import json
import logging
from math import ceil

from django.db import DatabaseError, connections, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .sistema_auth import _extraer_token, _buscar_usuario_sesion

logger = logging.getLogger(__name__)
ESTADOS = ('pendiente', 'aprobada', 'rechazada')
POR_PAGINA = 12


def _respuesta(datos, estado=200):
    respuesta = JsonResponse(datos, status=estado)
    respuesta['Cache-Control'] = 'no-store'
    respuesta['Pragma'] = 'no-cache'
    return respuesta


def _autorizar_admin(request):
    """Retorna (usuario, respuesta_error). Nunca confiar en rol proporcionado por React."""
    if 'neon' not in connections.databases:
        return None, _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)

    token = _extraer_token(request)
    if not token:
        return None, _respuesta({'ok': False, 'mensaje': 'Inicia sesión para continuar.'}, 401)

    try:
        usuario = _buscar_usuario_sesion(token)
    except DatabaseError:
        logger.exception('Error validando sesión en moderación de reseñas.')
        return None, _respuesta({'ok': False, 'mensaje': 'Servicio temporalmente no disponible.'}, 503)

    if not usuario:
        return None, _respuesta({'ok': False, 'mensaje': 'Sesión inválida o caducada.'}, 401)

    # Tuplas de sistema_auth: (id, nombre_completo, usuario, correo, rol).
    if usuario[4] != 'admin':
        return None, _respuesta({'ok': False, 'mensaje': 'Solo administradores pueden moderar reseñas.'}, 403)

    return usuario, None


def _fecha(valor):
    return valor.isoformat() if valor else None


@require_GET
def listar_resenas_admin(request):
    _, error = _autorizar_admin(request)
    if error is not None:
        return error

    estado = request.GET.get('estado', 'pendiente')
    if estado not in ESTADOS:
        return _respuesta({'ok': False, 'mensaje': 'Filtro de estado inválido.'}, 400)

    try:
        pagina = int(request.GET.get('pagina', '1'))
        if not 1 <= pagina <= 10000:
            raise ValueError
    except (TypeError, ValueError):
        return _respuesta({'ok': False, 'mensaje': 'Número de página inválido.'}, 400)

    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('''
                SELECT estado, COUNT(*)
                FROM public.resenas_clientes
                GROUP BY estado
            ''')
            totales = {item: 0 for item in ESTADOS}
            for clave, cantidad in cursor.fetchall():
                if clave in totales:
                    totales[clave] = cantidad

            cursor.execute('''
                SELECT r.id, r.nombre, r.negocio, r.correo, r.servicio,
                       r.calificacion, r.titulo, r.comentario, r.estado,
                       r.autoriza_publicacion, r.verificada,
                       r.fecha_creacion, r.fecha_publicacion, r.correo_verificado,
                       (c.id IS NOT NULL AND c.correo = r.correo
                           AND c.servicio_contratado = r.servicio) AS cliente_coincide
                FROM public.resenas_clientes r
                LEFT JOIN public.clientes c ON c.id = r.cliente_id
                WHERE r.estado = %s
                ORDER BY r.fecha_creacion DESC, r.id DESC
                LIMIT %s OFFSET %s
            ''', [estado, POR_PAGINA, (pagina - 1) * POR_PAGINA])
            filas = cursor.fetchall()
    except DatabaseError:
        logger.exception('Error consultando reseñas para moderación.')
        return _respuesta({'ok': False, 'mensaje': 'No pudimos consultar las reseñas.'}, 503)

    resenas = [
        {
            'id': str(fila[0]),
            'nombre': fila[1],
            'negocio': fila[2] or '',
            'correo': fila[3],
            'servicio': fila[4],
            'calificacion': fila[5],
            'titulo': fila[6] or '',
            'comentario': fila[7],
            'estado': fila[8],
            'autoriza_publicacion': fila[9],
            'verificada': fila[10],
            'fecha_creacion': _fecha(fila[11]),
            'fecha_publicacion': _fecha(fila[12]),
            'correo_verificado': bool(fila[13]),
            'cliente_coincide': bool(fila[14]),
        }
        for fila in filas
    ]
    return _respuesta({
        'ok': True,
        'resenas': resenas,
        'estado': estado,
        'pagina': pagina,
        'paginas': ceil(totales[estado] / POR_PAGINA),
        'por_pagina': POR_PAGINA,
        'totales': totales,
    })


@require_POST
def decidir_resena_admin(request, resena_id):
    administrador, error = _autorizar_admin(request)
    if error is not None:
        return error

    if request.content_type.split(';', 1)[0].strip().lower() != 'application/json':
        return _respuesta({'ok': False, 'mensaje': 'Envía JSON válido.'}, 415)
    if len(request.body) > 2048:
        return _respuesta({'ok': False, 'mensaje': 'Solicitud demasiado grande.'}, 413)

    try:
        datos = json.loads(request.body.decode('utf-8'))
        if not isinstance(datos, dict):
            raise ValueError
        decision = datos.get('decision')
        if decision not in ('aprobar', 'rechazar'):
            raise ValueError
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return _respuesta({'ok': False, 'mensaje': 'Selecciona una decisión válida.'}, 400)

    try:
        with transaction.atomic(using='neon'):
            with connections['neon'].cursor() as cursor:
                # Bloqueo contra aprobaciones/rechazos simultáneos.
                cursor.execute('''
                    SELECT r.estado, r.autoriza_publicacion, r.correo_verificado,
                           (c.id IS NOT NULL AND c.correo = r.correo
                              AND c.servicio_contratado = r.servicio) AS cliente_coincide
                    FROM public.resenas_clientes r
                    LEFT JOIN public.clientes c ON c.id = r.cliente_id
                    WHERE r.id = %s
                    FOR UPDATE OF r
                ''', [str(resena_id)])
                fila = cursor.fetchone()

                if fila is None:
                    return _respuesta({'ok': False, 'mensaje': 'No encontramos esa reseña.'}, 404)
                estado_actual, autorizada, correo_verificado, cliente_coincide = fila

                if estado_actual != 'pendiente':
                    return _respuesta({
                        'ok': False,
                        'mensaje': 'La reseña ya fue revisada. Actualiza la lista.',
                    }, 409)

                if decision == 'aprobar':
                    if not correo_verificado:
                        return _respuesta({
                            'ok': False,
                            'mensaje': 'El cliente todavía no confirmó su correo mediante código.',
                        }, 409)
                    if not autorizada:
                        return _respuesta({
                            'ok': False,
                            'mensaje': 'El cliente no autorizó la publicación.',
                        }, 409)
                    if not cliente_coincide:
                        return _respuesta({
                            'ok': False,
                            'mensaje': 'No coincide con un cliente y servicio registrados. Revisa los datos antes de aprobar.',
                        }, 409)

                    cursor.execute('''
                        UPDATE public.resenas_clientes
                        SET estado = 'aprobada',
                            verificada = TRUE,
                            metodo_verificacion = 'correo_codigo_y_registro_cliente',
                            fecha_verificacion = NOW(),
                            fecha_publicacion = NOW()
                        WHERE id = %s AND estado = 'pendiente'
                        RETURNING id
                    ''', [str(resena_id)])
                    mensaje = 'Reseña aprobada y habilitada para aparecer públicamente.'
                    nuevo_estado = 'aprobada'
                else:
                    cursor.execute('''
                        UPDATE public.resenas_clientes
                        SET estado = 'rechazada',
                            verificada = FALSE,
                            metodo_verificacion = NULL,
                            fecha_verificacion = NULL,
                            fecha_publicacion = NULL
                        WHERE id = %s AND estado = 'pendiente'
                        RETURNING id
                    ''', [str(resena_id)])
                    mensaje = 'Reseña rechazada. No se mostrará públicamente.'
                    nuevo_estado = 'rechazada'

                if cursor.fetchone() is None:
                    return _respuesta({'ok': False, 'mensaje': 'La reseña cambió de estado. Actualiza la lista.'}, 409)

                # Registrar auditoría dentro de la MISMA transacción.
                cursor.execute('''
                    INSERT INTO public.auditoria_crm
                      (administrador_id, entidad, entidad_id, accion, estado_anterior, estado_nuevo)
                    VALUES (%s, 'resena', %s, %s, %s, %s)
                ''', [administrador[0], str(resena_id), decision, estado_actual, nuevo_estado])

    except DatabaseError:
        logger.exception('Error al moderar reseña (admin_id=%s).', administrador[0])
        return _respuesta({'ok': False, 'mensaje': 'No pudimos guardar la decisión.'}, 503)

    logger.info('Reseña %s: %s por admin_id=%s', resena_id, nuevo_estado, administrador[0])
    return _respuesta({'ok': True, 'estado': nuevo_estado, 'mensaje': mensaje})
