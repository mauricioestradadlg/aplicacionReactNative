"""Validación y respuestas compartidas por los módulos de la aplicación móvil."""
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import DatabaseError, IntegrityError
from django.http import Http404
from django.utils import timezone

from .auth import ErrorAPI, respuesta

logger = logging.getLogger(__name__)
CERO = Decimal('0.00')
MAX_IMPORTE = Decimal('9999999999.99')


def api(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except ErrorAPI as error:
            return respuesta({'ok': False, 'mensaje': str(error)}, error.status)
        except (ValueError, ValidationError) as error:
            return respuesta({'ok': False, 'mensaje': str(error)}, 400)
        except Http404:
            return respuesta({'ok': False, 'mensaje': 'El registro no existe en tu organización.'}, 404)
        except IntegrityError:
            return respuesta({'ok': False, 'mensaje': 'El registro entra en conflicto con datos existentes.'}, 409)
        except DatabaseError:
            logger.exception('Error en módulo móvil %s.', view.__name__)
            return respuesta({'ok': False, 'mensaje': 'No fue posible consultar o guardar los datos. Intenta de nuevo.'}, 503)
    return wrapped


def texto(value, campo, maximo, requerido=True):
    if not isinstance(value, str):
        raise ValueError(f'{campo} debe ser texto.')
    value = value.strip()
    if (requerido and not value) or len(value) > maximo or '\x00' in value:
        raise ValueError(f'{campo} debe tener {"entre 1 y" if requerido else "hasta"} {maximo} caracteres.')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError(f'{campo} contiene caracteres inválidos.') from None
    return value


def correo(value):
    value = texto(value, 'Correo', 254).lower()
    try:
        validate_email(value)
    except ValidationError:
        raise ValueError('Escribe un correo válido.') from None
    return value


def importe(value, positivo=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('Captura un importe decimal válido.')
    value = str(value).strip()
    if len(value) > 24 or not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?', value):
        raise ValueError('Captura importes sin separadores de miles y con máximo dos decimales.')
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ValueError('Captura un importe decimal válido.') from None
    if not amount.is_finite() or amount > MAX_IMPORTE or amount < 0 or (positivo and amount == 0):
        raise ValueError('El importe está fuera del rango permitido.')
    return amount.quantize(Decimal('0.01'))


def dinero(value):
    return format(value, '.2f') if value is not None else None


def hoy():
    return timezone.localdate(timezone=ZoneInfo('America/Mexico_City'))


def fecha(value, campo):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(f'{campo} debe usar el formato AAAA-MM-DD.')
    try:
        result = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f'{campo} no es válida.') from None
    if result > hoy() or result.year < 1900:
        raise ValueError(f'{campo} debe estar entre 1900-01-01 y el día actual.')
    return result


def booleano(value, campo):
    if not isinstance(value, bool):
        raise ValueError(f'{campo} debe ser verdadero o falso.')
    return value


def paginar(queryset, request, campo, serializar):
    try:
        page = int(request.GET.get('pagina', '1'))
    except (ValueError, TypeError):
        raise ValueError('Página inválida.') from None
    if page < 1 or page > 1000000:
        raise ValueError('Página inválida.')
    paginator = Paginator(queryset, 25)
    result = paginator.get_page(page)
    return {'ok': True, campo: [serializar(item) for item in result],
            'total': paginator.count, 'pagina': result.number, 'paginas': paginator.num_pages}


def buscar(request):
    return texto(request.GET.get('buscar', ''), 'Búsqueda', 100, requerido=False)
