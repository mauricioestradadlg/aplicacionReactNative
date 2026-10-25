
from django.contrib import admin
from django.urls import include, path


# =========================================================
# URLS PRINCIPALES DEL PROYECTO
# =========================================================

urlpatterns = [

    # Panel de administración Django
    path(
        "admin/",
        admin.site.urls
    ),

    # Endpoints de nuestra aplicación
    path(
        "api/",
        include("server.urls")
    ),

]
