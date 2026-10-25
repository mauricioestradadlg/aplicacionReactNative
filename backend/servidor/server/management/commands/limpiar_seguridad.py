"""Limpiar datos temporales caducados; ejecutar mediante Cron Job seguro."""
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connections, transaction


class Command(BaseCommand):
    help = 'Elimina límites y códigos temporales expirados, sin borrar reseñas.'

    def handle(self, *args, **kwargs):
        if 'neon' not in connections.databases:
            raise CommandError('Neon no está configurado.')
        try:
            with transaction.atomic(using='neon'):
                with connections['neon'].cursor() as cur:
                    cur.execute('DELETE FROM public.limites_api WHERE expira_en < NOW()')
                    limites = cur.rowcount
                    cur.execute('''DELETE FROM public.verificaciones_resenas
                                   WHERE expira_en < NOW() - INTERVAL '7 days' ''')
                    codigos = cur.rowcount
                    cur.execute('''DELETE FROM public.codigos_login_sistema
                                   WHERE expira_en < NOW() - INTERVAL '7 days' ''')
                    login = cur.rowcount
                    cur.execute('''DELETE FROM public.sesiones_sistema
                                   WHERE expira_en < NOW() - INTERVAL '30 days'
                                      OR revocado_en < NOW() - INTERVAL '30 days' ''')
                    sesiones = cur.rowcount
        except DatabaseError as ex:
            raise CommandError('No se pudieron limpiar registros temporales.') from ex
        self.stdout.write(self.style.SUCCESS(
            f'Límites: {limites}; códigos reseñas: {codigos}; '
            f'códigos login: {login}; sesiones: {sesiones}'
        ))
