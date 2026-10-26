"""Verifica conexión y esquema móvil en solo lectura, sin mostrar credenciales."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend/servidor'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'servidor.settings')

import django
django.setup()

from django.db import connections
from movil.models import Cliente, GastoHistorial, GastoOperativo, LimiteAcceso, Membresia, Organizacion, Requerimiento, Sesion, Usuario

if 'movil' not in connections.databases:
    print('Falta NEON_MOBILE_DATABASE_URL en backend/servidor/.env.')
    sys.exit(1)

connection = connections['movil']
connection.settings_dict.setdefault('OPTIONS', {})['connect_timeout'] = 8
models = [Usuario, Sesion, LimiteAcceso, Organizacion, Membresia, Cliente, Requerimiento, GastoOperativo, GastoHistorial]
try:
    with connection.cursor() as cursor:
        cursor.execute('BEGIN READ ONLY')
        try:
            missing = []
            for model in models:
                table = model._meta.db_table
                cursor.execute('SELECT to_regclass(%s)', [f'public.{table}'])
                if cursor.fetchone()[0] is None:
                    missing.append(table)
        finally:
            cursor.execute('ROLLBACK')
    if missing:
        print('Conexión móvil correcta. Faltan tablas: ' + ', '.join(missing))
        print('Ejecuta: python backend/servidor/manage.py migrate movil --database=movil')
        sys.exit(1)
    print(f'Base móvil conectada. {len(models)} tablas verificadas en solo lectura.')
except Exception as error:
    print(f'No se pudo verificar la base móvil ({type(error).__name__}). Revisa la red y la configuración privada.')
    sys.exit(1)
finally:
    connection.close()
