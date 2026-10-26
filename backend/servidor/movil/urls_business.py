from django.urls import path

from . import business_crm as crm, business_finance as finance, business_projects as projects

urlpatterns = [
    path('clientes/', crm.clientes),
    path('clientes/<uuid:cliente_id>/', crm.editar_cliente),
    path('dashboard-crm/', crm.dashboard_crm),
    path('gestion-ventas/', crm.gestion_ventas),
    path('gestion-ventas/<uuid:cliente_id>/liquidacion/', crm.liquidacion),
    path('proyectos/pendientes/', projects.pendientes),
    path('proyectos/gestion/', projects.gestion),
    path('proyectos/<str:fuente>/<uuid:prospecto_id>/requerimientos/', projects.requerimientos),
    path('proyectos/<str:fuente>/<uuid:prospecto_id>/kanban/', projects.kanban),
    path('proyectos/<str:fuente>/<uuid:prospecto_id>/requerimientos/<uuid:requerimiento_id>/estado/', projects.estado_requerimiento),
    path('finanzas/gastos-operativos/', finance.gastos),
    path('finanzas/gastos-operativos/<uuid:gasto_id>/', finance.editar_gasto),
    path('finanzas/dashboard/', finance.dashboard_finanzas),
    path('finanzas/reportes/', finance.reportes),
]
