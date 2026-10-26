from django.urls import path

from . import identity

urlpatterns = [
    path("csrf/", identity.csrf),
    path("registro/", identity.registro),
    path("movil/registro/", identity.registro),
    path("login/", identity.login),
    path("movil/login/", identity.login),
    path("yo/", identity.yo),
    path("salir/", identity.salir),
    path("cuenta/", identity.cuenta),
    path("organizaciones/", identity.organizaciones),
    path("organizaciones/solicitar/", identity.solicitar),
    path("organizacion/", identity.organizacion),
    path("organizacion/miembros/", identity.miembros),
    path("organizacion/miembros/<int:miembro_id>/", identity.eliminar_miembro),
    path("organizacion/solicitudes/", identity.solicitudes),
    path("organizacion/solicitudes/<int:miembro_id>/", identity.decidir_solicitud),
]
