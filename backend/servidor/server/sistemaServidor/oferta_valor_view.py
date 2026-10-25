"""CRM Oferta de Valor: clientes potenciales de WhatsApp y Email Marketing.

GET/POST  /api/sistema/oferta-valor/prospectos/
POST      /api/sistema/oferta-valor/prospectos/<uuid>/editar/
GET       /api/sistema/oferta-valor/potenciales/
POST      /api/sistema/oferta-valor/potenciales/<uuid>/editar/
POST      /api/sistema/oferta-valor/potenciales/<uuid>/cita/

Ambas fuentes conservan sus propios registros; el listado se unifica en lectura.
La etiqueta editable "origen" no cambia la fuente interna de datos.
Todas las vistas requieren sesión privada y rol administrador.
"""
import json
import logging
import re
from math import ceil

from django.db import DatabaseError, IntegrityError, connections, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .resenas_admin_view import _autorizar_admin

logger = logging.getLogger(__name__)
POR_PAGINA = 25
SERVICIOS = ('', 'landing-page', 'sitio-web')
ORIGENES = ('Email Marketing', 'WhatsApp')
FUENTES = ('email-marketing', 'whatsapp')

# Orden consistente para serializar resultados de ambas fuentes.
_CAMPOS_SQL = '''id, telefono, nombre, brindo_nombre, respondio_mensajes,
                negocio, servicio_recomendado, cita_agendada_en,
                fecha_registro, origen'''

# Unión SQL: no inventamos que un lead de correo respondió mensajes.
# Un registro WhatsApp califica por nombre+respuesta; un lead de email
# califica por tener la oportunidad comercial activa y consentimiento.
_UNION_POTENCIALES = '''
    FROM (
        SELECT
            p.id, p.telefono, p.nombre, p.brindo_nombre,
            p.respondio_mensajes, p.negocio, p.servicio_recomendado,
            p.cita_agendada_en, p.fecha_registro, p.origen,
            'whatsapp'::text AS fuente
        FROM public.prospectos_oferta_valor p
        WHERE p.brindo_nombre = TRUE
          AND p.respondio_mensajes = TRUE

        UNION ALL

        SELECT
            l.id, l.whatsapp AS telefono, l.nombre,
            TRUE AS brindo_nombre,
            FALSE AS respondio_mensajes,
            l.negocio, l.servicio_recomendado,
            l.cita_agendada_en, l.fecha_registro,
            l.origen_potencial AS origen,
            'email-marketing'::text AS fuente
        FROM public.leads_magnet l
        WHERE l.acepto_correos = TRUE
          AND l.oportunidad_comercial_en IS NOT NULL
          AND NULLIF(BTRIM(l.nombre), '') IS NOT NULL
    ) AS p
'''


def _respuesta(datos, status=200):
    response = JsonResponse(datos, status=status)
    response['Cache-Control'] = 'no-store'
    response['Pragma'] = 'no-cache'
    return response


def _verificar_neon():
    return 'neon' in connections.databases


def _leer_json(request):
    if request.content_type.split(';', 1)[0].strip().lower() != 'application/json':
        raise ValueError('Envía datos JSON.')
    if len(request.body) > 4096:
        raise ValueError('Solicitud demasiado grande.')
    try:
        datos = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('JSON inválido.') from error
    if not isinstance(datos, dict):
        raise ValueError('Se esperaba un objeto JSON.')
    return datos


def _texto(datos, campo, maximo):
    valor = datos.get(campo, '')
    if not isinstance(valor, str):
        raise ValueError(f'El campo {campo} debe ser texto.')
    valor = valor.strip()
    if len(valor) > maximo:
        raise ValueError(f'El campo {campo} supera {maximo} caracteres.')
    return valor


def _telefono(valor):
    if not re.fullmatch(r'\+?[0-9 ()-]{10,25}', valor):
        raise ValueError('Ingresa un teléfono válido de 10 a 15 dígitos.')
    digitos = ''.join(c for c in valor if c.isdigit())
    if not 10 <= len(digitos) <= 15:
        raise ValueError('Ingresa un teléfono válido de 10 a 15 dígitos.')
    return ('+' if valor.startswith('+') else '') + digitos


def _fecha(valor):
    return valor.isoformat() if valor else None


def _serializar(fila, fuente='whatsapp'):
    return {
        'id': str(fila[0]),
        'telefono': fila[1] or '',
        'nombre': fila[2] or '',
        'brindo_nombre': bool(fila[3]),
        'respondio_mensajes': bool(fila[4]),
        'negocio': fila[5] or '',
        'servicio_recomendado': fila[6] or '',
        'cita_agendada_en': _fecha(fila[7]),
        'fecha_registro': _fecha(fila[8]),
        'origen': fila[9] or ('Email Marketing' if fuente == 'email-marketing' else 'WhatsApp'),
        # Fuente técnica fija: no depende del desplegable Origen.
        'fuente': fila[10] if len(fila) > 10 else fuente,
    }


def _validar_prospecto(datos):
    telefono = _telefono(_texto(datos, 'telefono', 25))
    nombre = _texto(datos, 'nombre', 100)
    negocio = _texto(datos, 'negocio', 120)
    servicio = _texto(datos, 'servicio_recomendado', 25)
    if servicio not in SERVICIOS:
        raise ValueError('Selecciona Landing Page, Sitio Web o Sin definir.')
    respondio = datos.get('respondio_mensajes', False)
    if type(respondio) is not bool:
        raise ValueError('Respondió mensajes debe ser verdadero o falso.')
    return telefono, nombre or None, bool(nombre), respondio, negocio or None, servicio or None


def _validar_edicion_potencial(datos):
    fuente = datos.get('fuente')
    if fuente not in FUENTES:
        raise ValueError('Fuente de prospecto inválida.')
    telefono = _telefono(_texto(datos, 'telefono', 25))
    nombre = _texto(datos, 'nombre', 100)
    if not nombre:
        raise ValueError('El nombre del cliente potencial es obligatorio.')
    negocio = _texto(datos, 'negocio', 120)
    servicio = _texto(datos, 'servicio_recomendado', 25)
    origen = _texto(datos, 'origen', 24)
    if servicio not in SERVICIOS:
        raise ValueError('Servicio recomendado inválido.')
    if origen not in ORIGENES:
        raise ValueError('Elige Email Marketing o WhatsApp en Origen.')
    return fuente, telefono, nombre, negocio or None, servicio or None, origen


def _filtros(request):
    try:
        pagina = int(request.GET.get('pagina', '1'))
        if not 1 <= pagina <= 100000:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('Página inválida.')
    buscar = request.GET.get('buscar', '').strip()
    if len(buscar) > 100:
        raise ValueError('Búsqueda demasiado larga.')
    return pagina, buscar


def _listar_prospectos(request):
    _, error = _autorizar_admin(request)
    if error is not None:
        return error
    if not _verificar_neon():
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)
    try:
        pagina, buscar = _filtros(request)
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    parametros = []
    where = ''
    if buscar:
        where = " WHERE telefono ILIKE %s OR COALESCE(nombre, '') ILIKE %s OR COALESCE(negocio, '') ILIKE %s"
        parametros = ['%' + buscar + '%'] * 3
    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM public.prospectos_oferta_valor' + where, parametros)
            total = cursor.fetchone()[0]
            cursor.execute('SELECT ' + _CAMPOS_SQL + ' FROM public.prospectos_oferta_valor' + where + '''
                ORDER BY fecha_registro DESC, id DESC
                LIMIT %s OFFSET %s''', [*parametros, POR_PAGINA, (pagina - 1) * POR_PAGINA])
            filas = cursor.fetchall()
    except DatabaseError:
        logger.exception('Error consultando prospectos de WhatsApp.')
        return _respuesta({'ok': False, 'mensaje': 'No fue posible consultar los prospectos.'}, 503)
    return _respuesta({
        'ok': True, 'prospectos': [_serializar(fila) for fila in filas],
        'total': total, 'pagina': pagina, 'por_pagina': POR_PAGINA,
        'paginas': ceil(total / POR_PAGINA),
    })


def _listar_potenciales(request):
    _, error = _autorizar_admin(request)
    if error is not None:
        return error
    if not _verificar_neon():
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)
    try:
        pagina, buscar = _filtros(request)
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    parametros = []
    where = ''
    if buscar:
        where = " WHERE (p.telefono ILIKE %s OR COALESCE(p.nombre, '') ILIKE %s OR COALESCE(p.negocio, '') ILIKE %s)"
        parametros = ['%' + buscar + '%'] * 3
    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('SELECT COUNT(*) ' + _UNION_POTENCIALES + where, parametros)
            total = cursor.fetchone()[0]
            cursor.execute('SELECT p.* ' + _UNION_POTENCIALES + where + '''
                ORDER BY p.fecha_registro DESC, p.id DESC, p.fuente
                LIMIT %s OFFSET %s''', [*parametros, POR_PAGINA, (pagina - 1) * POR_PAGINA])
            filas = cursor.fetchall()
    except DatabaseError:
        logger.exception('Error unificando Clientes Potenciales.')
        return _respuesta({'ok': False, 'mensaje': 'No fue posible consultar clientes potenciales. Ejecuta la migración SQL.'}, 503)
    return _respuesta({
        'ok': True, 'prospectos': [_serializar(fila) for fila in filas],
        'total': total, 'pagina': pagina, 'por_pagina': POR_PAGINA,
        'paginas': ceil(total / POR_PAGINA),
    })


@require_http_methods(['GET', 'POST'])
def prospectos_oferta_valor(request):
    if request.method == 'GET':
        return _listar_prospectos(request)
    admin, error = _autorizar_admin(request)
    if error is not None:
        return error
    if not _verificar_neon():
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)
    try:
        valores = _validar_prospecto(_leer_json(request))
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('''
                INSERT INTO public.prospectos_oferta_valor
                    (telefono, nombre, brindo_nombre, respondio_mensajes,
                     negocio, servicio_recomendado, actualizado_por)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING ''' + _CAMPOS_SQL, [*valores, admin[0]])
            fila = cursor.fetchone()
    except IntegrityError:
        return _respuesta({'ok': False, 'mensaje': 'Ese teléfono ya está registrado.'}, 409)
    except DatabaseError:
        logger.exception('Error registrando prospecto.')
        return _respuesta({'ok': False, 'mensaje': 'No se pudo registrar el prospecto.'}, 503)
    return _respuesta({'ok': True, 'prospecto': _serializar(fila)}, 201)


@require_POST
def editar_prospecto_oferta_valor(request, prospecto_id):
    admin, error = _autorizar_admin(request)
    if error is not None:
        return error
    if not _verificar_neon():
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)
    try:
        valores = _validar_prospecto(_leer_json(request))
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    telefono, nombre, brindo, respondio, negocio, servicio = valores
    try:
        with transaction.atomic(using='neon'):
            with connections['neon'].cursor() as cursor:
                cursor.execute('''
                    UPDATE public.prospectos_oferta_valor
                    SET telefono = %s, nombre = %s, brindo_nombre = %s,
                        respondio_mensajes = %s, negocio = %s, servicio_recomendado = %s,
                        cita_agendada_en = CASE
                            WHEN %s AND %s THEN cita_agendada_en ELSE NULL END,
                        actualizado_en = NOW(), actualizado_por = %s
                    WHERE id = %s
                    RETURNING ''' + _CAMPOS_SQL,
                    [telefono, nombre, brindo, respondio, negocio, servicio,
                     brindo, respondio, admin[0], str(prospecto_id)])
                fila = cursor.fetchone()
    except IntegrityError:
        return _respuesta({'ok': False, 'mensaje': 'Otro prospecto ya usa ese teléfono.'}, 409)
    except DatabaseError:
        logger.exception('Error actualizando prospecto.')
        return _respuesta({'ok': False, 'mensaje': 'No se pudo guardar el prospecto.'}, 503)
    if fila is None:
        return _respuesta({'ok': False, 'mensaje': 'Prospecto no encontrado.'}, 404)
    return _respuesta({'ok': True, 'prospecto': _serializar(fila)})


@require_GET
def clientes_potenciales_oferta_valor(request):
    return _listar_potenciales(request)


@require_POST
def editar_cliente_potencial(request, prospecto_id):
    admin, error = _autorizar_admin(request)
    if error is not None:
        return error
    if not _verificar_neon():
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)
    try:
        fuente, telefono, nombre, negocio, servicio, origen = _validar_edicion_potencial(_leer_json(request))
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    try:
        with connections['neon'].cursor() as cursor:
            if fuente == 'whatsapp':
                cursor.execute('''
                    UPDATE public.prospectos_oferta_valor
                    SET telefono = %s, nombre = %s, brindo_nombre = TRUE,
                        negocio = %s, servicio_recomendado = %s, origen = %s,
                        actualizado_en = NOW(), actualizado_por = %s
                    WHERE id = %s AND brindo_nombre = TRUE AND respondio_mensajes = TRUE
                    RETURNING ''' + _CAMPOS_SQL,
                    [telefono, nombre, negocio, servicio, origen, admin[0], str(prospecto_id)])
            else:
                cursor.execute('''
                    UPDATE public.leads_magnet
                    SET whatsapp = %s, nombre = %s,
                        negocio = %s, servicio_recomendado = %s,
                        origen_potencial = %s
                    WHERE id = %s AND acepto_correos = TRUE
                      AND oportunidad_comercial_en IS NOT NULL
                    RETURNING id, whatsapp, nombre,
                              TRUE AS brindo_nombre, FALSE AS respondio_mensajes,
                              negocio, servicio_recomendado,
                              cita_agendada_en, fecha_registro, origen_potencial
                ''', [telefono, nombre, negocio, servicio, origen, str(prospecto_id)])
            fila = cursor.fetchone()
    except IntegrityError:
        return _respuesta({'ok': False, 'mensaje': 'Ese teléfono ya está registrado en WhatsApp.'}, 409)
    except DatabaseError:
        logger.exception('Error actualizando Cliente Potencial.')
        return _respuesta({'ok': False, 'mensaje': 'No se pudo actualizar el cliente potencial.'}, 503)
    if fila is None:
        return _respuesta({'ok': False, 'mensaje': 'Cliente potencial no encontrado o ya no califica.'}, 404)
    return _respuesta({'ok': True, 'prospecto': _serializar(fila, fuente=fuente)})


@require_POST
def actualizar_cita_oferta_valor(request, prospecto_id):
    admin, error = _autorizar_admin(request)
    if error is not None:
        return error
    if not _verificar_neon():
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)
    try:
        datos = _leer_json(request)
        valor = datos.get('cita_agendada')
        fuente = datos.get('fuente', 'whatsapp')
        if type(valor) is not bool or fuente not in FUENTES:
            raise ValueError('Estado de cita o fuente inválido.')
    except ValueError as error:
        return _respuesta({'ok': False, 'mensaje': str(error)}, 400)
    try:
        with connections['neon'].cursor() as cursor:
            if fuente == 'whatsapp':
                cursor.execute('''
                    UPDATE public.prospectos_oferta_valor
                    SET cita_agendada_en = CASE WHEN %s
                         THEN COALESCE(cita_agendada_en, NOW()) ELSE NULL END,
                        actualizado_en = NOW(), actualizado_por = %s
                    WHERE id = %s AND brindo_nombre = TRUE AND respondio_mensajes = TRUE
                    RETURNING cita_agendada_en
                ''', [valor, admin[0], str(prospecto_id)])
            else:
                cursor.execute('''
                    UPDATE public.leads_magnet
                    SET cita_agendada_en = CASE WHEN %s
                         THEN COALESCE(cita_agendada_en, NOW()) ELSE NULL END
                    WHERE id = %s AND acepto_correos = TRUE
                      AND oportunidad_comercial_en IS NOT NULL
                      AND NULLIF(BTRIM(nombre), '') IS NOT NULL
                    RETURNING cita_agendada_en
                ''', [valor, str(prospecto_id)])
            fila = cursor.fetchone()
    except DatabaseError:
        logger.exception('Error actualizando cita para fuente=%s.', fuente)
        return _respuesta({'ok': False, 'mensaje': 'No se pudo guardar la cita.'}, 503)
    if fila is None:
        return _respuesta({'ok': False, 'mensaje': 'Cliente potencial no encontrado o ya no califica.'}, 404)
    return _respuesta({'ok': True, 'cita_agendada_en': _fecha(fila[0])})
