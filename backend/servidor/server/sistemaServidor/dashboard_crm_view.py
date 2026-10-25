"""Dashboard CRM: métricas agregadas, sin exponer datos personales.

GET /api/sistema/dashboard-crm/
Requiere sesión HttpOnly vigente y rol administrador.
Los importes publicitarios viven como supuestos editables en el frontend;
no se deduce atribución de campañas ni ingresos de los registros.
"""
import logging

from django.db import DatabaseError, connections
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .resenas_admin_view import _autorizar_admin

logger = logging.getLogger(__name__)

# Nombre de cada campo en el mismo orden del SELECT. Sólo conteos agregados.
COLUMNAS = (
    'whatsapp_registros', 'lead_magnet_registros', 'lead_magnet_consentimiento',
    'lead_magnet_tips', 'lead_magnet_feedback',
    'whatsapp_potenciales', 'email_potenciales',
    'whatsapp_citas', 'email_citas',
    'whatsapp_completadas', 'email_completadas',
    'whatsapp_cotizaciones', 'email_cotizaciones',
    'whatsapp_ventas', 'email_ventas',
    'ventas_liquidadas',
)

SQL_RESUMEN = """
WITH fuentes AS (
    SELECT p.id, 'whatsapp'::text AS fuente,
           p.fecha_registro, p.cita_agendada_en,
           (p.brindo_nombre = TRUE AND p.respondio_mensajes = TRUE) AS calificado,
           FALSE AS acepto_tips, FALSE AS tips, FALSE AS feedback
    FROM public.prospectos_oferta_valor p
    UNION ALL
    SELECT l.id, 'email-marketing'::text AS fuente,
           l.fecha_registro, l.cita_agendada_en,
           (l.acepto_correos = TRUE
             AND l.oportunidad_comercial_en IS NOT NULL
             AND NULLIF(BTRIM(l.nombre), '') IS NOT NULL) AS calificado,
           l.acepto_correos AS acepto_tips,
           l.tips_enviados_en IS NOT NULL AS tips,
           l.feedback_enviado_en IS NOT NULL AS feedback
    FROM public.leads_magnet l
),
base AS (
    SELECT f.*,
           (f.calificado AND f.cita_agendada_en IS NOT NULL) AS tiene_cita,
           COALESCE(v.cita_completada, FALSE) AS completada,
           COALESCE(v.cotizacion_enviada, FALSE) AS cotizada,
           COALESCE(v.hubo_venta, FALSE) AS venta,
           COALESCE(v.proyecto_liquidado, FALSE) AS liquidada
    FROM fuentes f
    LEFT JOIN public.cierres_ventas v
      ON v.prospecto_id = f.id AND v.fuente = f.fuente
)
SELECT
    COUNT(*) FILTER (WHERE fuente = 'whatsapp') AS whatsapp_registros,
    COUNT(*) FILTER (WHERE fuente = 'email-marketing') AS lead_magnet_registros,
    COUNT(*) FILTER (WHERE fuente = 'email-marketing' AND acepto_tips) AS lead_magnet_consentimiento,
    COUNT(*) FILTER (WHERE fuente = 'email-marketing' AND acepto_tips AND tips) AS lead_magnet_tips,
    COUNT(*) FILTER (WHERE fuente = 'email-marketing' AND acepto_tips AND feedback) AS lead_magnet_feedback,
    COUNT(*) FILTER (WHERE fuente = 'whatsapp' AND calificado) AS whatsapp_potenciales,
    COUNT(*) FILTER (WHERE fuente = 'email-marketing' AND calificado) AS email_potenciales,
    COUNT(*) FILTER (WHERE fuente = 'whatsapp' AND tiene_cita) AS whatsapp_citas,
    COUNT(*) FILTER (WHERE fuente = 'email-marketing' AND tiene_cita) AS email_citas,
    COUNT(*) FILTER (WHERE fuente = 'whatsapp' AND tiene_cita AND completada) AS whatsapp_completadas,
    COUNT(*) FILTER (WHERE fuente = 'email-marketing' AND tiene_cita AND completada) AS email_completadas,
    COUNT(*) FILTER (WHERE fuente = 'whatsapp' AND tiene_cita AND cotizada) AS whatsapp_cotizaciones,
    COUNT(*) FILTER (WHERE fuente = 'email-marketing' AND tiene_cita AND cotizada) AS email_cotizaciones,
    COUNT(*) FILTER (WHERE fuente = 'whatsapp' AND tiene_cita AND venta) AS whatsapp_ventas,
    COUNT(*) FILTER (WHERE fuente = 'email-marketing' AND tiene_cita AND venta) AS email_ventas,
    COUNT(*) FILTER (WHERE tiene_cita AND venta AND liquidada) AS ventas_liquidadas
FROM base;
"""

# La gráfica usa fecha de registro de cada fuente y fecha en que se marcó
# la cita; NO usa actualizado_en para inferir fecha de cierre de venta.
SQL_TENDENCIA = """
WITH meses AS (
    SELECT generate_series(
        date_trunc('month', NOW() AT TIME ZONE 'America/Monterrey') - INTERVAL '5 months',
        date_trunc('month', NOW() AT TIME ZONE 'America/Monterrey'),
        INTERVAL '1 month'
    )::date AS mes
),
eventos AS (
    SELECT (fecha_registro AT TIME ZONE 'America/Monterrey')::date AS fecha,
           'whatsapp'::text AS tipo
    FROM public.prospectos_oferta_valor
    UNION ALL
    SELECT (fecha_registro AT TIME ZONE 'America/Monterrey')::date AS fecha,
           'lead-magnet'::text AS tipo
    FROM public.leads_magnet
    UNION ALL
    SELECT (cita_agendada_en AT TIME ZONE 'America/Monterrey')::date AS fecha,
           'cita'::text AS tipo
    FROM public.prospectos_oferta_valor
    WHERE cita_agendada_en IS NOT NULL
      AND brindo_nombre = TRUE AND respondio_mensajes = TRUE
    UNION ALL
    SELECT (cita_agendada_en AT TIME ZONE 'America/Monterrey')::date AS fecha,
           'cita'::text AS tipo
    FROM public.leads_magnet
    WHERE cita_agendada_en IS NOT NULL
      AND acepto_correos = TRUE AND oportunidad_comercial_en IS NOT NULL
      AND NULLIF(BTRIM(nombre), '') IS NOT NULL
)
SELECT to_char(m.mes, 'YYYY-MM') AS mes,
       COUNT(e.tipo) FILTER (WHERE e.tipo = 'whatsapp') AS whatsapp,
       COUNT(e.tipo) FILTER (WHERE e.tipo = 'lead-magnet') AS lead_magnet,
       COUNT(e.tipo) FILTER (WHERE e.tipo = 'cita') AS citas
FROM meses m
LEFT JOIN eventos e ON date_trunc('month', e.fecha)::date = m.mes
GROUP BY m.mes
ORDER BY m.mes;
"""


def _respuesta(datos, estado=200):
    response = JsonResponse(datos, status=estado)
    response['Cache-Control'] = 'no-store'
    response['Pragma'] = 'no-cache'
    return response


@require_GET
def resumen_dashboard_crm(request):
    _, error = _autorizar_admin(request)
    if error is not None:
        return error
    if 'neon' not in connections.databases:
        return _respuesta({'ok': False, 'mensaje': 'Neon no está configurado.'}, 503)

    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute(SQL_RESUMEN)
            fila = cursor.fetchone()
            if fila is None:
                raise ValueError('Resumen vacío.')
            conteos = {clave: int(valor or 0) for clave, valor in zip(COLUMNAS, fila)}
            cursor.execute(SQL_TENDENCIA)
            meses = [
                {
                    'mes': fila[0],
                    'whatsapp': int(fila[1] or 0),
                    'lead_magnet': int(fila[2] or 0),
                    'citas': int(fila[3] or 0),
                }
                for fila in cursor.fetchall()
            ]
    except (DatabaseError, ValueError):
        logger.exception('No fue posible consultar métricas agregadas del Dashboard CRM.')
        return _respuesta({
            'ok': False,
            'mensaje': 'No fue posible cargar el dashboard. Verifica la conexión con Neon y las tablas del CRM (SQL 02 a 06).',
        }, 503)

    return _respuesta({
        'ok': True,
        'conteos': conteos,
        'tendencia': meses,
        'alcance': 'Acumulado de registros existentes; tendencia de los últimos seis meses.',
    })
