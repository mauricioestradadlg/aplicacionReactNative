# API compartida de Proyectos MEG

Esta carpeta contiene el backend Django del ZIP proporcionado, con acceso móvil agregado. La web y la app usan las mismas tablas PostgreSQL/Neon mediante `NEON_DATABASE_URL`; la app nunca recibe esa conexión ni contraseñas de la base. No se necesita crear otra base, ejecutar el archivo SQL completo ni migrar los datos existentes.

## Preparación local

Desde `backend/` con Python 3.13:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path servidor/.env)) { Copy-Item servidor/.env.example servidor/.env }
```

Configura `servidor/.env` con la misma `NEON_DATABASE_URL`, `SECRET_KEY`, remitente y API key de Resend del servidor actual. Conserva su `SECRET_KEY` para que los códigos pendientes sigan siendo válidos. No agregues estos valores al frontend ni al control de versiones.

En este workspace ya se prepararon `backend/.venv` con Django 6.1 y `servidor/.env` con la configuración original del ZIP. El comando de copia de arriba solo aplica si falta ese archivo; no reemplaces la configuración existente.

Para desarrollar contra una base de pruebas: establece `DEBUG=True`, agrega la IP LAN de la computadora a `ALLOWED_HOSTS` y ejecuta desde `backend/`:

```powershell
.\.venv\Scripts\python.exe servidor/manage.py runserver 0.0.0.0:8000
```

En la app, `EXPO_PUBLIC_API_URL=http://IP_LAN_DE_LA_COMPUTADORA:8000` apunta a ese servidor. En Android Emulator puede usarse `http://10.0.2.2:8000`. Un teléfono físico necesita la IP LAN, la misma red y acceso al puerto 8000. La prueba local de la variante web usa `http://localhost:8081`; debe figurar en `CORS_ALLOWED_ORIGINS`.

## Despliegue en el servidor existente

Integra estos cambios en el backend Django que ya publica tu web, conservando sus variables privadas, dominio y conexión Neon. Puedes desplegar esta carpeta como raíz de servicio. El Dockerfile usa Gunicorn en el puerto 8000; en plataformas que requieren `$PORT`, establece su comando de arranque como `gunicorn servidor.wsgi:application --bind 0.0.0.0:$PORT` desde `backend/servidor`.

Para producción: `DEBUG=False`, `SECRET_KEY` real, `ALLOWED_HOSTS=api.TU_DOMINIO` y `CORS_ALLOWED_ORIGINS` con los orígenes HTTPS de la web. El servidor requiere HTTPS. Conserva los parámetros de correo y de los formularios públicos que ya tengas configurados. Solo activa `TRUST_PROXY_HTTPS=True` cuando el proxy garantice que sobrescribe `X-Forwarded-Proto`.

La app móvil necesita este despliegue antes de poder iniciar sesión con `/movil/`. La URL de un backend anterior sin estos endpoints devolverá 404. No se ha desplegado ni alterado la base de producción automáticamente.

## Contrato móvil

Todas las rutas parten de `/api/sistema/` y responden JSON:

| Método y ruta | Datos / comportamiento |
| --- | --- |
| `POST movil/login/` | `{ "usuario": "...", "contrasena": "..." }` devuelve `verificacion_id` y `correo_oculto`. Aplica los mismos límites, bloqueos y envío de código de la web. No entrega sesión. |
| `POST movil/verificar/` | `{ "verificacion_id": "UUID", "codigo": "123456" }` devuelve `token` y `expira_en` después de validar el código de seis dígitos. |
| `GET yo/` | `Authorization: Bearer TOKEN` devuelve `usuario` con `id`, `nombre_completo`, `usuario`, `correo` y `rol`. |
| `POST salir/` | Revoca en Neon el token recibido por `Authorization`. |
| Resto de rutas privadas | Aceptan el mismo Bearer y conservan las validaciones por rol y por entidad de la web. |

La sesión dura 30 días y se almacena en `sesiones_sistema` como hash SHA-256. Se comprueban vencimiento, revocación y usuario activo en cada consulta. Los módulos internos requieren `rol=admin`, igual que en la web. Los colaboradores pueden autenticarse, pero no adquieren acceso administrativo.

El cliente nativo debe guardar el token en Expo SecureStore y enviarlo explícitamente con `credentials: 'omit'`. La web continúa usando `login/`, `verificar/`, cookie HttpOnly y `X-CSRFToken`; nunca debe almacenar el token de sesión en localStorage.

`SistemaCsrfMiddleware` conserva CSRF para cookies y limita la excepción a las dos rutas móviles de credenciales y a las rutas privadas con un Bearer de formato válido. Las vistas verifican la credencial contra la base; un header inválido nunca usa una cookie como respaldo. No se amplía CORS a todos los orígenes ni se exime CSRF globalmente.

## Validación sin base real

```powershell
python servidor/manage.py test server --settings=servidor.test_settings --noinput
```

Las pruebas usan configuración aislada, mocks de Neon y correo. Cubren las funciones existentes, el código de segundo factor, la persistencia exclusiva del hash, la revocación Bearer y la preservación de CSRF/cookies web. No requieren ni leen `servidor/.env` y no ejecutan consultas de producción.
