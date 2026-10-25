"""Crea o actualiza un usuario del sistema interno en Neon SIN guardar contraseñas planas."""
import getpass
import re

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, connections, transaction


class Command(BaseCommand):
    help = "Crear usuario interno en Neon con contraseña protegida por hash."

    def add_arguments(self, parser):
        parser.add_argument("--nombre", required=True)
        parser.add_argument("--usuario", required=True)
        parser.add_argument("--correo", required=True)
        parser.add_argument("--rol", choices=["admin", "colaborador"], default="colaborador")

    def handle(self, *args, **opciones):
        nombre = opciones["nombre"].strip()
        usuario = opciones["usuario"].strip().lower()
        correo = opciones["correo"].strip().lower()
        rol = opciones["rol"]

        if not (2 <= len(nombre) <= 150):
            raise CommandError("Nombre completo inválido.")
        if not re.fullmatch(r"[a-z0-9._-]{3,80}", usuario):
            raise CommandError("Usuario: 3-80 caracteres, minúsculas, números, punto, guion y guion bajo.")
        if len(correo) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
            raise CommandError("Correo inválido.")
        if "neon" not in connections.databases:
            raise CommandError("Configura NEON_DATABASE_URL en el backend.")

        password = getpass.getpass("Contraseña nueva (mín. 12 caracteres): ")
        confirmacion = getpass.getpass("Confirmar contraseña: ")
        if password != confirmacion:
            raise CommandError("Las contraseñas no coinciden.")
        if len(password) < 12 or len(password) > 128:
            raise CommandError("Elige una contraseña de 12 a 128 caracteres.")
        if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            raise CommandError("La contraseña debe incluir letras y números.")

        # Utiliza el hasher de Django (PBKDF2 por defecto).
        password_hash = make_password(password)
        try:
            with transaction.atomic(using="neon"):
                with connections["neon"].cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO public.usuarios_sistema
                            (nombre_completo, usuario, correo, contrasena_hash, rol)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        [nombre, usuario, correo, password_hash, rol],
                    )
                    nuevo_id = cursor.fetchone()[0]
        except IntegrityError as error:
            raise CommandError("Ese usuario o correo ya existe. Usa otro.") from error

        self.stdout.write(self.style.SUCCESS(
            f"Usuario creado en Neon. ID: {nuevo_id} | {usuario} | rol: {rol}"
        ))
