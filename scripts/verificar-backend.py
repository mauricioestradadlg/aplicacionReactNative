"""Verifica conexión y tablas existentes; no consulta datos personales ni modifica la base."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend' / 'servidor'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'servidor.settings')

import django
django.setup()
from django.db import connections

if 'neon' not in connections.databases:
    print('Falta NEON_DATABASE_URL en backend/servidor/.env.')
    sys.exit(1)

connection = connections['neon']
connection.settings_dict.setdefault('OPTIONS', {})['connect_timeout'] = 8
tables = ['usuarios_sistema', 'sesiones_sistema', 'codigos_login_sistema',
          'leads_magnet', 'prospectos_oferta_valor', 'cierres_ventas',
          'proyectos_requerimientos', 'gastos_operativos', 'gastos_operativos_historial']
try:
    with connection.cursor() as cursor:
        cursor.execute('BEGIN READ ONLY')
        try:
            cursor.execute('SELECT 1')
            cursor.fetchone()
            missing = []
            for table in tables:
                cursor.execute('SELECT to_regclass(%s)', [f'public.{table}'])
                if cursor.fetchone()[0] is None:
                    missing.append(table)
        finally:
            cursor.execute('ROLLBACK')
    if missing:
        print('Conexión correcta. Tablas esperadas no encontradas: ' + ', '.join(missing))
        sys.exit(1)
    print(f'Conexión PostgreSQL correcta. {len(tables)} tablas existentes verificadas en solo lectura.')
except Exception as error:
    # Las excepciones del driver pueden contener partes de la conexión privada.
    print(f'No se pudo verificar PostgreSQL ({type(error).__name__}). Revisa la conexión y la red.')
    sys.exit(1)
finally:
    connection.close()
