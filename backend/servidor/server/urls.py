from django.urls import path

from .views import contacto, health, lead_magnet
from .resenas_view import registrar_resena, verificar_correo_resena, listar_resenas_publicas
from .sistemaServidor.resenas_admin_view import listar_resenas_admin, decidir_resena_admin
from .sistemaServidor.lead_magnet_admin_view import (
    listar_leads_magnet, listar_email_marketing, actualizar_email_marketing,
)
from .sistemaServidor.oferta_valor_view import (
    prospectos_oferta_valor,
    editar_prospecto_oferta_valor,
    clientes_potenciales_oferta_valor,
    actualizar_cita_oferta_valor,
    editar_cliente_potencial,
)
from .sistemaServidor.cierre_ventas_view import listar_cierres_ventas, guardar_cierre_ventas
from .sistemaServidor.gestion_ventas_view import listar_gestion_ventas, guardar_liquidacion
from .sistemaServidor.proyectos_view import (
    listar_proyectos_pendientes, listar_gestion_proyectos,
    requerimientos_proyecto, kanban_proyecto, actualizar_estado_requerimiento,
)
from .sistemaServidor.dashboard_crm_view import resumen_dashboard_crm
from .sistemaServidor.dashboard_finanzas_view import resumen_dashboard_finanzas
from .sistemaServidor.finanzas_view import (
    gastos_operativos, editar_gasto_operativo, reportes_financieros,
)
from .sistemaServidor.sistema_auth import (
    sistema_csrf,
    sistema_login,
    sistema_verificar,
    sistema_yo,
    sistema_salir,
    sistema_movil_login,
    sistema_movil_verificar,
)

urlpatterns = [
    path("contacto/", contacto, name="contacto"),
    path("lead-magnet/", lead_magnet, name="lead_magnet"),
    path("health/", health, name="health"),
    path("resenas/publicas/", listar_resenas_publicas, name="listar_resenas_publicas"),
    path("resenas/", registrar_resena, name="registrar_resena"),
    path("resenas/verificar/", verificar_correo_resena, name="verificar_correo_resena"),

    # Autenticación del sistema privado (sesiones persistentes + CSRF)
    path("sistema/csrf/", sistema_csrf, name="sistema_csrf"),
    path("sistema/login/", sistema_login, name="sistema_login"),
    path("sistema/verificar/", sistema_verificar, name="sistema_verificar"),
    path("sistema/yo/", sistema_yo, name="sistema_yo"),
    path("sistema/salir/", sistema_salir, name="sistema_salir"),
    path("sistema/movil/login/", sistema_movil_login, name="sistema_movil_login"),
    path("sistema/movil/verificar/", sistema_movil_verificar, name="sistema_movil_verificar"),
    # Registros privados del Lead Magnet (rol admin obligatorio)
    path("sistema/lead-magnet/registros/", listar_leads_magnet, name="listar_leads_magnet"),
    path("sistema/lead-magnet/email-marketing/", listar_email_marketing, name="listar_email_marketing"),
    path("sistema/lead-magnet/email-marketing/<uuid:lead_id>/estado/", actualizar_email_marketing, name="actualizar_email_marketing"),
    # CRM > Marketing > Oferta de Valor (sesión cookie y rol administrador)
    path("sistema/oferta-valor/prospectos/", prospectos_oferta_valor, name="ov_prospectos"),
    path("sistema/oferta-valor/prospectos/<uuid:prospecto_id>/editar/", editar_prospecto_oferta_valor, name="ov_editar"),
    path("sistema/oferta-valor/potenciales/", clientes_potenciales_oferta_valor, name="ov_potenciales"),
    path("sistema/oferta-valor/potenciales/<uuid:prospecto_id>/editar/", editar_cliente_potencial, name="ov_editar_potencial"),
    path("sistema/oferta-valor/potenciales/<uuid:prospecto_id>/cita/", actualizar_cita_oferta_valor, name="ov_cita"),
    # CRM > Dashboard: métricas agregadas, cookie de sesión y rol admin
    path("sistema/dashboard-crm/", resumen_dashboard_crm, name="dashboard_crm"),
    # CRM > Ventas > Cierre de Ventas (admin, dos fuentes)
    path("sistema/cierre-ventas/", listar_cierres_ventas, name="cierre_ventas"),
    path("sistema/cierre-ventas/<uuid:prospecto_id>/estado/", guardar_cierre_ventas, name="guardar_cierre_ventas"),
    # CRM > Ventas > Gestión de Ventas: solo ventas cerradas
    path("sistema/gestion-ventas/", listar_gestion_ventas, name="listar_gestion_ventas"),
    path("sistema/gestion-ventas/<uuid:prospecto_id>/liquidacion/", guardar_liquidacion, name="guardar_liquidacion"),
    # Proyectos: captura inicial de requerimientos y seguimiento Kanban.
    path("sistema/proyectos/pendientes/", listar_proyectos_pendientes, name="proyectos_pendientes"),
    path("sistema/proyectos/gestion/", listar_gestion_proyectos, name="gestion_proyectos"),
    path("sistema/proyectos/<str:fuente>/<uuid:prospecto_id>/requerimientos/", requerimientos_proyecto, name="requerimientos_proyecto"),
    path("sistema/proyectos/<str:fuente>/<uuid:prospecto_id>/kanban/", kanban_proyecto, name="kanban_proyecto"),
    path("sistema/proyectos/<str:fuente>/<uuid:prospecto_id>/requerimientos/<uuid:requerimiento_id>/estado/", actualizar_estado_requerimiento, name="estado_requerimiento_proyecto"),
    # Finanzas privadas: indicadores, catálogo recurrente y reportes, solo admin.
    path("sistema/finanzas/dashboard/", resumen_dashboard_finanzas, name="dashboard_finanzas"),
    path("sistema/finanzas/gastos-operativos/", gastos_operativos, name="gastos_operativos"),
    path("sistema/finanzas/gastos-operativos/<uuid:gasto_id>/", editar_gasto_operativo, name="editar_gasto_operativo"),
    path("sistema/finanzas/reportes/", reportes_financieros, name="reportes_financieros"),
    # Panel privado de moderación (rol admin obligatorio)
    path("sistema/resenas/", listar_resenas_admin, name="listar_resenas_admin"),
    path("sistema/resenas/<uuid:resena_id>/decision/", decidir_resena_admin, name="decidir_resena_admin"),
]
