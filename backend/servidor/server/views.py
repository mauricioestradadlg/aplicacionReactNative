import html
import json
import logging

import requests

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.db import DatabaseError, connections
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .resend_service import enviar_correo_resend


logger = logging.getLogger(__name__)


# =========================================================
# BREVO
# =========================================================
#
# BREVO SE CONSERVA ÚNICAMENTE PARA EL FORMULARIO
# DE CONTACTO NORMAL DEL SITIO.
#
# EL LEAD MAGNET UTILIZA RESEND.
# =========================================================

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


# =========================================================
# SERVICIOS DISPONIBLES
# =========================================================

SERVICIOS = {

    "sitio-corporativo-estatico":
        "Sitio Corporativo - Página Estática",

    "sitio-corporativo-formulario":
        (
            "Sitio Corporativo - Página con Formulario / "
            "Sistema de Reservaciones"
        ),

    "landing-page-estatica":
        "Landing Page - Estática",

    "landing-page-formulario":
        (
            "Landing Page con Formulario / "
            "Sistema de Reservaciones"
        ),

    # Compatibilidad anterior

    "pagina-estatica":
        "Sitio Corporativo - Página Estática",

    "pagina-formulario":
        (
            "Sitio Corporativo - Página con Formulario / "
            "Sistema de Reservaciones"
        ),

    "no-se":
        "Aún no sabe cuál necesita",

}


# =========================================================
# HEALTH CHECK
# =========================================================

def health(request):

    return JsonResponse(
        {
            "ok": True,
            "mensaje":
                "Backend de Proyectos MEG funcionando correctamente."
        }
    )


# =========================================================
# FUNCIÓN BREVO
# =========================================================
#
# ESTA FUNCIÓN SIGUE EXISTIENDO PARA TU FORMULARIO
# DE CONTACTO NORMAL.
# =========================================================

def enviar_correo_brevo(
    destinatario,
    nombre_destinatario,
    asunto,
    contenido_html,
    reply_to=None
):

    if not settings.BREVO_API_KEY:

        raise ValueError(
            "BREVO_API_KEY no está configurada."
        )


    if not settings.BREVO_SENDER_EMAIL:

        raise ValueError(
            "BREVO_SENDER_EMAIL no está configurado."
        )


    headers = {

        "accept":
            "application/json",

        "api-key":
            settings.BREVO_API_KEY,

        "content-type":
            "application/json",

    }


    payload = {

        "sender": {

            "name":
                settings.BREVO_SENDER_NAME,

            "email":
                settings.BREVO_SENDER_EMAIL,

        },

        "to": [

            {

                "email":
                    destinatario,

                "name":
                    nombre_destinatario,

            }

        ],

        "subject":
            asunto,

        "htmlContent":
            contenido_html,

    }


    if reply_to:

        payload["replyTo"] = {

            "email":
                reply_to["email"],

            "name":
                reply_to["name"],

        }


    response = requests.post(

        BREVO_URL,

        headers=headers,

        json=payload,

        timeout=15

    )


    response.raise_for_status()


    return response.json()


# =========================================================
# FORMULARIO DE CONTACTO NORMAL
# =========================================================

@csrf_exempt
@require_POST
def contacto(request):

    # =====================================================
    # LEER JSON
    # =====================================================

    try:

        datos = json.loads(
            request.body.decode("utf-8")
        )

    except (
        json.JSONDecodeError,
        UnicodeDecodeError
    ):

        return JsonResponse(
            {
                "ok":
                    False,

                "mensaje":
                    (
                        "Los datos enviados no tienen "
                        "un formato válido."
                    )
            },
            status=400
        )


    # =====================================================
    # OBTENER DATOS
    # =====================================================

    nombre = str(
        datos.get("nombre", "")
    ).strip()


    correo = str(
        datos.get("correo", "")
    ).strip()


    telefono = str(
        datos.get("telefono", "")
    ).strip()


    empresa = str(
        datos.get("empresa", "")
    ).strip()


    servicio = str(
        datos.get("servicio", "")
    ).strip()


    comentarios = str(
        datos.get("comentarios", "")
    ).strip()


    acepto_privacidad = datos.get(
        "acepto_privacidad",
        False
    )


    # =====================================================
    # VALIDACIONES
    # =====================================================

    if not nombre:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "El nombre es obligatorio."
            },
            status=400
        )


    if not correo:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "El correo electrónico es obligatorio."
            },
            status=400
        )


    try:

        validate_email(correo)

    except ValidationError:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "El correo electrónico no es válido."
            },
            status=400
        )


    if not telefono:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "El número telefónico es obligatorio."
            },
            status=400
        )


    if servicio not in SERVICIOS:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "Selecciona un servicio válido."
            },
            status=400
        )


    if not comentarios:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "Cuéntanos brevemente sobre tu proyecto."
            },
            status=400
        )


    if acepto_privacidad is not True:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "Debes aceptar el Aviso de Privacidad."
            },
            status=400
        )


    if not settings.CONTACT_RECEIVER_EMAIL:

        logger.error(
            "CONTACT_RECEIVER_EMAIL no está configurado."
        )

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    (
                        "El servidor de correo no está "
                        "configurado correctamente."
                    )
            },
            status=500
        )


    # =====================================================
    # SERVICIO
    # =====================================================

    servicio_texto = SERVICIOS[
        servicio
    ]


    # =====================================================
    # ESCAPAR HTML
    # =====================================================

    nombre_html = html.escape(
        nombre
    )


    correo_html = html.escape(
        correo
    )


    telefono_html = html.escape(
        telefono
    )


    empresa_html = html.escape(
        empresa or "No especificado"
    )


    servicio_html = html.escape(
        servicio_texto
    )


    comentarios_html = html.escape(
        comentarios
    ).replace(
        "\n",
        "<br>"
    )


    # =====================================================
    # EMAIL ADMINISTRADOR
    # =====================================================

    correo_administrador = f"""
    <!DOCTYPE html>

    <html lang="es">

    <head>

        <meta charset="UTF-8">

    </head>

    <body
        style="
            margin: 0;
            padding: 30px;
            background-color: #f5f7fa;
            font-family: Arial, Helvetica, sans-serif;
            color: #1f2937;
        "
    >

        <div
            style="
                max-width: 650px;
                margin: 0 auto;
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                overflow: hidden;
            "
        >

            <div
                style="
                    padding: 28px 32px;
                    background-color: #0b2232;
                    color: #ffffff;
                "
            >

                <h1
                    style="
                        margin: 0;
                        font-size: 24px;
                    "
                >
                    Nuevo prospecto
                </h1>


                <p
                    style="
                        margin: 8px 0 0;
                    "
                >
                    Formulario de contacto - Proyectos MEG
                </p>

            </div>


            <div
                style="
                    padding: 32px;
                "
            >

                <p>
                    Se recibió una nueva solicitud
                    de información desde la página web.
                </p>


                <table
                    style="
                        width: 100%;
                        border-collapse: collapse;
                    "
                >

                    <tr>

                        <td
                            style="
                                padding: 10px 0;
                                font-weight: bold;
                            "
                        >
                            Nombre:
                        </td>

                        <td style="padding: 10px 0;">
                            {nombre_html}
                        </td>

                    </tr>


                    <tr>

                        <td
                            style="
                                padding: 10px 0;
                                font-weight: bold;
                            "
                        >
                            Correo:
                        </td>

                        <td style="padding: 10px 0;">
                            {correo_html}
                        </td>

                    </tr>


                    <tr>

                        <td
                            style="
                                padding: 10px 0;
                                font-weight: bold;
                            "
                        >
                            Teléfono:
                        </td>

                        <td style="padding: 10px 0;">
                            {telefono_html}
                        </td>

                    </tr>


                    <tr>

                        <td
                            style="
                                padding: 10px 0;
                                font-weight: bold;
                            "
                        >
                            Restaurante / negocio:
                        </td>

                        <td style="padding: 10px 0;">
                            {empresa_html}
                        </td>

                    </tr>


                    <tr>

                        <td
                            style="
                                padding: 10px 0;
                                font-weight: bold;
                            "
                        >
                            Servicio:
                        </td>

                        <td style="padding: 10px 0;">
                            {servicio_html}
                        </td>

                    </tr>

                </table>


                <div
                    style="
                        margin-top: 25px;
                    "
                >

                    <strong>
                        Descripción del proyecto:
                    </strong>


                    <div
                        style="
                            margin-top: 10px;
                            padding: 16px;
                            background-color: #f3f4f6;
                            border-radius: 8px;
                            line-height: 1.6;
                        "
                    >
                        {comentarios_html}
                    </div>

                </div>


                <p
                    style="
                        margin-top: 25px;
                        font-size: 13px;
                        color: #6b7280;
                    "
                >
                    El usuario confirmó haber leído
                    y aceptado el Aviso de Privacidad.
                </p>

            </div>

        </div>

    </body>

    </html>
    """


    # =====================================================
    # ENVIAR CON BREVO
    # =====================================================

    try:

        enviar_correo_brevo(

            destinatario=
                settings.CONTACT_RECEIVER_EMAIL,

            nombre_destinatario=
                "Proyectos MEG",

            asunto=
                f"Nueva solicitud web - {nombre}",

            contenido_html=
                correo_administrador,

            reply_to={

                "email":
                    correo,

                "name":
                    nombre,

            }

        )


    except (
        requests.RequestException,
        ValueError
    ):

        logger.exception(
            "Error enviando formulario de contacto mediante Brevo."
        )

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    (
                        "No fue posible enviar el formulario. "
                        "Intenta nuevamente."
                    )
            },
            status=502
        )


    return JsonResponse(
        {
            "ok": True,
            "mensaje":
                "Formulario enviado correctamente."
        },
        status=200
    )


# =========================================================
# PLANTILLAS LEAD MAGNET
# =========================================================

PLANTILLAS_LEAD_MAGNET = {

    "restaurante": {

        "nombre":
            "Plantilla para Restaurante",

        "archivo":
            "/plantillas/Plantilla_Restaurante.zip",

    },


    "negocio": {

        "nombre":
            "Plantilla para Negocio Regular",

        "archivo":
            "/plantillas/Plantilla_PYMES.zip",

    },

}


# =========================================================
# LEAD MAGNET
# =========================================================
#
# IMPORTANTE:
#
# ESTE FORMULARIO:
#
# REACT
#   ↓
# DJANGO
#   ↓
# RESEND
#   ↓
# CORREO CORPORATIVO DE PROYECTOS MEG
#
# TAMBIÉN SE ENVÍA UN CORREO DE CONFIRMACIÓN AL PROSPECTO.
#
# EL CONSENTIMIENTO DE TIPS ES OPCIONAL Y SOLO INDICA
# SI ACEPTA RECIBIR CORREOS DE SEGUIMIENTO / MARKETING.
# =========================================================

@csrf_exempt
@require_POST
def lead_magnet(request):


    # =====================================================
    # LEER JSON
    # =====================================================

    try:

        datos = json.loads(
            request.body.decode("utf-8")
        )


    except (
        json.JSONDecodeError,
        UnicodeDecodeError
    ):

        return JsonResponse(
            {
                "ok":
                    False,

                "mensaje":
                    (
                        "Los datos enviados no tienen "
                        "un formato válido."
                    )
            },
            status=400
        )


    # =====================================================
    # DATOS
    # =====================================================

    nombre = str(
        datos.get("nombre", "")
    ).strip()


    correo = str(
        datos.get("correo", "")
    ).strip()


    whatsapp = str(
        datos.get("whatsapp", "")
    ).strip()


    negocio = str(
        datos.get("negocio", "")
    ).strip()


    plantilla = str(
        datos.get("plantilla", "")
    ).strip()


    acepto_privacidad = datos.get(
        "acepto_privacidad",
        False
    )


    acepto_correos = datos.get(
        "acepto_correos",
        False
    )


    # =====================================================
    # VALIDAR NOMBRE
    # =====================================================

    if not nombre:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "El nombre es obligatorio."
            },
            status=400
        )


    # =====================================================
    # VALIDAR CORREO
    # =====================================================

    if not correo:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "El correo electrónico es obligatorio."
            },
            status=400
        )


    try:

        validate_email(
            correo
        )


    except ValidationError:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "El correo electrónico no es válido."
            },
            status=400
        )


    # =====================================================
    # VALIDAR WHATSAPP
    # =====================================================

    if not whatsapp:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "El número de WhatsApp es obligatorio."
            },
            status=400
        )


    # Los tamaños coinciden con la tabla SQL public.leads_magnet.
    # Evita errores 500 por datos más largos que las columnas.
    correo = correo.lower()
    if len(nombre) > 100 or len(correo) > 254 or len(whatsapp) > 25 or len(negocio) > 120:
        return JsonResponse(
            {"ok": False, "mensaje": "Uno de los campos supera la longitud permitida."},
            status=400,
        )

    whatsapp_digitos = "".join(
        caracter
        for caracter in whatsapp
        if caracter.isdigit()
    )


    if not 10 <= len(whatsapp_digitos) <= 15:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    (
                        "Ingresa un número de WhatsApp válido "
                        "incluyendo el código de país."
                    )
            },
            status=400
        )



    # =====================================================
    # VALIDAR NEGOCIO
    # =====================================================

    if not negocio:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "El nombre del negocio es obligatorio."
            },
            status=400
        )


    # =====================================================
    # VALIDAR PLANTILLA
    # =====================================================

    if plantilla not in PLANTILLAS_LEAD_MAGNET:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "Selecciona una plantilla válida."
            },
            status=400
        )


    # =====================================================
    # VALIDAR PRIVACIDAD
    # =====================================================

    if acepto_privacidad is not True:

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    "Debes aceptar el Aviso de Privacidad."
            },
            status=400
        )


    # =====================================================
    # VALIDAR RESEND API KEY
    # =====================================================

    if not settings.RESEND_API_KEY:

        logger.error(
            "RESEND_API_KEY no está configurada."
        )

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    (
                        "El servicio de correo no está "
                        "configurado correctamente."
                    )
            },
            status=500
        )


    # =====================================================
    # VALIDAR REMITENTE
    # =====================================================

    if not settings.RESEND_SENDER_EMAIL:

        logger.error(
            "RESEND_SENDER_EMAIL no está configurado."
        )

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    (
                        "El remitente de Resend no está "
                        "configurado."
                    )
            },
            status=500
        )


    # =====================================================
    # VALIDAR RECEPTOR
    # =====================================================

    if not settings.LEAD_MAGNET_RECEIVER_EMAIL:

        logger.error(
            "LEAD_MAGNET_RECEIVER_EMAIL no está configurado."
        )

        return JsonResponse(
            {
                "ok": False,
                "mensaje":
                    (
                        "El correo receptor del Lead Magnet "
                        "no está configurado."
                    )
            },
            status=500
        )


    # =====================================================
    # INFORMACIÓN PLANTILLA
    # =====================================================

    plantilla_info = (
        PLANTILLAS_LEAD_MAGNET[
            plantilla
        ]
    )


    plantilla_nombre = (
        plantilla_info[
            "nombre"
        ]
    )


    # =====================================================
    # ESCAPAR DATOS PARA HTML
    # =====================================================

    nombre_html = html.escape(
        nombre
    )


    correo_html = html.escape(
        correo
    )


    whatsapp_html = html.escape(
        whatsapp
    )


    whatsapp_url = (
        f"https://wa.me/{whatsapp_digitos}"
    )


    correos_tips_estado = (
        "Aceptado"
        if acepto_correos is True
        else "No aceptado"
    )


    negocio_html = html.escape(
        negocio
    )


    plantilla_html = html.escape(
        plantilla_nombre
    )


    # =====================================================
    # CORREO QUE RECIBIRÁ PROYECTOS MEG
    # =====================================================

    contenido_administrador_html = f"""
    <!DOCTYPE html>

    <html lang="es">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >

    </head>


    <body
        style="
            margin: 0;
            padding: 30px;
            background-color: #f4f7fb;
            font-family: Arial, Helvetica, sans-serif;
            color: #172033;
        "
    >


        <div
            style="
                max-width: 680px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 14px;
                overflow: hidden;
                border: 1px solid #e5e7eb;
            "
        >


            <!-- HEADER -->

            <div
                style="
                    padding: 28px 32px;
                    background-color: #071126;
                    color: #ffffff;
                "
            >

                <p
                    style="
                        margin: 0 0 8px;
                        color: #69b9ff;
                        font-size: 12px;
                        font-weight: bold;
                        letter-spacing: 1px;
                    "
                >

                    PROYECTOS MEG

                </p>


                <h1
                    style="
                        margin: 0;
                        font-size: 24px;
                    "
                >

                    Nuevo prospecto de plantilla gratuita

                </h1>

            </div>


            <!-- CONTENIDO -->

            <div
                style="
                    padding: 32px;
                "
            >


                <p
                    style="
                        margin-top: 0;
                        line-height: 1.7;
                    "
                >

                    Se recibieron nuevos datos desde el formulario
                    de la plantilla gratuita de Proyectos MEG.

                </p>


                <table
                    style="
                        width: 100%;
                        border-collapse: collapse;
                    "
                >


                    <!-- NOMBRE -->

                    <tr>

                        <td
                            style="
                                width: 190px;
                                padding: 11px 0;
                                font-weight: bold;
                                vertical-align: top;
                            "
                        >

                            Nombre:

                        </td>


                        <td
                            style="
                                padding: 11px 0;
                            "
                        >

                            {nombre_html}

                        </td>

                    </tr>


                    <!-- CORREO -->

                    <tr>

                        <td
                            style="
                                padding: 11px 0;
                                font-weight: bold;
                                vertical-align: top;
                            "
                        >

                            Correo:

                        </td>


                        <td
                            style="
                                padding: 11px 0;
                            "
                        >

                            <a
                                href="mailto:{correo_html}"
                                style="
                                    color: #007bff;
                                    text-decoration: none;
                                "
                            >

                                {correo_html}

                            </a>

                        </td>

                    </tr>


                    <!-- WHATSAPP -->

                    <tr>

                        <td
                            style="
                                padding: 11px 0;
                                font-weight: bold;
                                vertical-align: top;
                            "
                        >

                            WhatsApp:

                        </td>


                        <td
                            style="
                                padding: 11px 0;
                            "
                        >

                            <a
                                href="{whatsapp_url}"
                                style="
                                    color: #25d366;
                                    text-decoration: none;
                                "
                            >

                                {whatsapp_html}

                            </a>

                        </td>

                    </tr>



                    <!-- NEGOCIO -->

                    <tr>

                        <td
                            style="
                                padding: 11px 0;
                                font-weight: bold;
                                vertical-align: top;
                            "
                        >

                            Negocio:

                        </td>


                        <td
                            style="
                                padding: 11px 0;
                            "
                        >

                            {negocio_html}

                        </td>

                    </tr>


                    <!-- PLANTILLA -->

                    <tr>

                        <td
                            style="
                                padding: 11px 0;
                                font-weight: bold;
                                vertical-align: top;
                            "
                        >

                            Plantilla solicitada:

                        </td>


                        <td
                            style="
                                padding: 11px 0;
                            "
                        >

                            {plantilla_html}

                        </td>

                    </tr>


                    <!-- PRIVACIDAD -->

                    <tr>

                        <td
                            style="
                                padding: 11px 0;
                                font-weight: bold;
                                vertical-align: top;
                            "
                        >

                            Aviso de Privacidad:

                        </td>


                        <td
                            style="
                                padding: 11px 0;
                            "
                        >

                            Aceptado

                        </td>

                    </tr>


                    <!-- CORREOS DE TIPS -->

                    <tr>

                        <td
                            style="
                                padding: 11px 0;
                                font-weight: bold;
                                vertical-align: top;
                            "
                        >

                            Correos con tips:

                        </td>


                        <td
                            style="
                                padding: 11px 0;
                            "
                        >

                            {correos_tips_estado}

                        </td>

                    </tr>


                </table>


                <!-- NOTA -->

                <div
                    style="
                        margin-top: 24px;
                        padding: 16px;
                        background-color: #f4f8ff;
                        border: 1px solid #dbeafe;
                        border-radius: 10px;
                        color: #496581;
                        font-size: 13px;
                        line-height: 1.6;
                    "
                >

                    Puedes responder directamente este correo.
                    El Reply-To está configurado con:

                    <strong>
                        {correo_html}
                    </strong>

                </div>


            </div>


        </div>


    </body>

    </html>
    """


    # =====================================================
    # BLOQUE OPCIONAL DE TIPS PARA EL CORREO DE CONFIRMACIÓN
    # =====================================================

    bloque_tips_html = ""

    if acepto_correos is True:

        bloque_tips_html = f"""
                <div
                    style="
                        margin: 24px 0;
                        padding: 20px;
                        background-color: #f4f8ff;
                        border: 1px solid #dbeafe;
                        border-radius: 10px;
                    "
                >

                    <h2
                        style="
                            margin: 0 0 10px;
                            color: #071126;
                            font-size: 18px;
                        "
                    >
                        Próximamente recibirás tips para aprovechar mejor tu plantilla
                    </h2>


                    <p
                        style="
                            margin: 0;
                            color: #496581;
                            font-size: 14px;
                            line-height: 1.7;
                        "
                    >
                        Durante los próximos días te estaremos enviando
                        correos con recomendaciones prácticas para ayudarte
                        a modificar y personalizar la plantilla de la página
                        de tu negocio, incluyendo textos, imágenes, secciones
                        y otros ajustes útiles.
                    </p>

                </div>
        """


    # =====================================================
    # CORREO AUTOMÁTICO PARA EL PROSPECTO
    # =====================================================

    contenido_confirmacion_html = f"""
    <!DOCTYPE html>

    <html lang="es">

    <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >

    </head>


    <body
        style="
            margin: 0;
            padding: 30px;
            background-color: #f4f7fb;
            font-family: Arial, Helvetica, sans-serif;
            color: #172033;
        "
    >


        <div
            style="
                max-width: 680px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 14px;
                overflow: hidden;
                border: 1px solid #e5e7eb;
            "
        >


            <div
                style="
                    padding: 28px 32px;
                    background-color: #071126;
                    color: #ffffff;
                "
            >

                <p
                    style="
                        margin: 0 0 8px;
                        color: #69b9ff;
                        font-size: 12px;
                        font-weight: bold;
                        letter-spacing: 1px;
                    "
                >
                    PROYECTOS MEG
                </p>


                <h1
                    style="
                        margin: 0;
                        font-size: 24px;
                    "
                >
                    ¡Gracias por tu interés en la plantilla!
                </h1>

            </div>


            <div
                style="
                    padding: 32px;
                "
            >

                <p
                    style="
                        margin-top: 0;
                        font-size: 16px;
                        line-height: 1.7;
                    "
                >
                    Hola <strong>{nombre_html}</strong>,
                </p>


                <p
                    style="
                        font-size: 15px;
                        line-height: 1.8;
                        color: #445269;
                    "
                >
                    Gracias por tu interés en nuestra
                    <strong>{plantilla_html}</strong> para
                    <strong>{negocio_html}</strong>.
                    Tu solicitud fue registrada correctamente.
                </p>


                {bloque_tips_html}


                <p
                    style="
                        font-size: 14px;
                        line-height: 1.8;
                        color: #445269;
                    "
                >
                    Si tienes alguna duda mientras trabajas con tu plantilla,
                    puedes responder directamente a este correo.
                </p>


                <p
                    style="
                        margin-bottom: 0;
                        font-size: 14px;
                        line-height: 1.7;
                        color: #6b7280;
                    "
                >
                    Gracias por confiar en <strong>Proyectos MEG</strong>.
                </p>

            </div>

        </div>

    </body>

    </html>
    """


    # =====================================================
    # REGISTRAR EL LEAD EN NEON ANTES DE ENVIAR CORREOS
    # =====================================================
    # Un formulario enviado no demuestra que el visitante haya descargado
    # el ZIP. Guardamos solicitudes, no afirmaciones de descarga.
    if 'neon' not in connections.databases:
        return JsonResponse({
            'ok': False,
            'mensaje': 'El registro de leads no está disponible en este momento.',
        }, status=503)

    try:
        with connections['neon'].cursor() as cursor:
            cursor.execute('''
                INSERT INTO public.leads_magnet
                  (nombre, correo, whatsapp, negocio, plantilla,
                   acepto_privacidad, acepto_correos)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', [
                nombre, correo, whatsapp, negocio, plantilla,
                True, acepto_correos is True,
            ])
            nuevo_lead_id = cursor.fetchone()[0]
    except DatabaseError:
        logger.exception('No fue posible guardar el lead del formulario en Neon.')
        return JsonResponse({
            'ok': False,
            'mensaje': 'No pudimos registrar tu solicitud. Intenta nuevamente.',
        }, status=503)

    # =====================================================
    # ENVIAR EXCLUSIVAMENTE A PROYECTOS MEG
    # MEDIANTE RESEND
    # =====================================================

    resultado_resend = None

    try:

        resultado_resend = enviar_correo_resend(

            destinatario=
                settings.LEAD_MAGNET_RECEIVER_EMAIL,

            asunto=
                f"Nuevo Lead Magnet - {negocio}",

            contenido_html=
                contenido_administrador_html,

            reply_to=
                correo

        )


    except (
        requests.RequestException,
        ValueError
    ) as error:

        logger.exception(
            "Lead %s guardado en Neon, pero falló el aviso por Resend: %s",
            nuevo_lead_id, error
        )


        # El lead ya está registrado de forma segura en Neon.
        # No bloqueamos la descarga si falla el aviso interno por correo.
        # Se podrá consultar el registro desde Marketing / Lead Magnet.
        resultado_resend = None


    # =====================================================
    # ENVIAR CORREO AUTOMÁTICO AL PROSPECTO
    # =====================================================

    confirmacion_enviada = False
    confirmacion_resend_id = None

    try:

        resultado_confirmacion = enviar_correo_resend(

            destinatario=
                correo,

            asunto=
                "¡Gracias por tu interés en la plantilla gratuita!",

            contenido_html=
                contenido_confirmacion_html,

            reply_to=
                settings.LEAD_MAGNET_RECEIVER_EMAIL

        )


        confirmacion_enviada = True

        if isinstance(
            resultado_confirmacion,
            dict
        ):

            confirmacion_resend_id = (
                resultado_confirmacion.get("id")
            )


    except (
        requests.RequestException,
        ValueError
    ) as error:

        # El lead ya fue enviado al correo corporativo.
        # No bloqueamos la descarga para evitar duplicados
        # si el usuario vuelve a enviar el formulario.
        logger.exception(
            "El lead se registró, pero falló el correo automático "
            "al prospecto mediante Resend: %s",
            error
        )


    # =====================================================
    # TODO CORRECTO
    # =====================================================

    return JsonResponse(
        {
            "ok":
                True,

            "mensaje":
                (
                    "Datos registrados correctamente. "
                    "Ya puedes descargar tu plantilla."
                ),

            "plantilla":
                plantilla,

            "modo_prueba":
                False,

            "confirmacion_enviada":
                confirmacion_enviada,

            "confirmacion_resend_id":
                confirmacion_resend_id,

            "resend_id":
                (
                    resultado_resend.get("id")
                    if isinstance(
                        resultado_resend,
                        dict
                    )
                    else None
                )

        },
        status=200
    )