# Proyectos MEG · Aplicación móvil

Adaptación del sistema interno del ZIP a React Native, Expo SDK 58 y Expo Router. Android, iOS y web comparten las reglas del backend Django y la misma base PostgreSQL/Neon. Los archivos adjuntos se utilizaron como referencia de implementación y esquema.

## Iniciar en tu computadora

La configuración local ya quedó preparada con `EXPO_PUBLIC_API_URL=http://192.168.1.77:8000`. La configuración privada del backend del ZIP se conservó en `backend/servidor/.env`, excluido de Git, con hosts y orígenes de desarrollo local. La conexión a PostgreSQL y nueve tablas existentes se verificaron en solo lectura.

En una terminal, desde la raíz del proyecto:

```powershell
.\backend\.venv\Scripts\python.exe backend/servidor/manage.py runserver 0.0.0.0:8000
```

En otra terminal, desde la misma carpeta:

```powershell
npm start
```

Usa un teléfono en la misma red Wi-Fi y abre el proyecto con un cliente compatible con Expo SDK 58. Los módulos utilizados están incluidos en Expo Go; un development build permite probar tu propio binario y es necesario al añadir módulos nativos que no estén incluidos. El backend debe permanecer encendido. El firewall de Windows debe permitir el puerto 8000 en tu red privada.

Para navegador, abre la opción web de Expo. Usa `http://192.168.1.77:PUERTO` tanto para el frontend como para el backend configurado: las cookies web son del mismo sitio. Si usas `http://localhost:PUERTO`, configura temporalmente `EXPO_PUBLIC_API_URL=http://localhost:8000` y reinicia Expo; no uses esa URL en un teléfono físico. Los orígenes locales 8081 y 8090 ya están permitidos en Django.

Si cambia la IP de la computadora:

```powershell
npm run configurar:local
# O indica una IP concreta:
npm run configurar:local -- 192.168.1.77
```

Incluye la nueva IP en `ALLOWED_HOSTS` de `backend/servidor/.env`, actualiza el origen web en `CORS_ALLOWED_ORIGINS` si lo usas y reinicia Django y Expo. Android Emulator usa `http://10.0.2.2:8000`; `localhost` dentro de un teléfono apunta al propio teléfono.

## Backend y base compartida

Se incluyó el backend original en `backend/`, con dos rutas de autenticación móvil y compatibilidad Bearer para las rutas privadas existentes. Debes ejecutar esta versión actualizada del backend para usar la app; la versión original del ZIP no tiene `/api/sistema/movil/`.

Para instalar desde cero o en un entorno virtual, consulta [backend/README.md](backend/README.md). Conserva los valores originales de `NEON_DATABASE_URL`, `SECRET_KEY` y Resend. El archivo `databasesistemaInterno.txt` es referencia de esquema: no necesitas volver a ejecutar ese SQL, crear otra base ni copiar los datos.

La app solo conoce la URL HTTP del backend. No agregues contraseñas de PostgreSQL ni claves de correo a variables `EXPO_PUBLIC_*`. La web conserva sus cookies HttpOnly y protección CSRF; Android/iOS almacenan la sesión en SecureStore. El cierre de sesión revoca el token en la misma base. No se usan registros de demostración.

## Funciones replicadas

| Área | Funciones |
| --- | --- |
| Acceso | Usuario/contraseña, código por correo, restauración y revocación de sesión, permisos por rol. |
| CRM | Dashboard, embudo, métricas por canal y costos publicitarios configurables localmente. |
| Marketing | Lead Magnet, seguimiento Email Marketing, alta/edición de prospectos, clientes potenciales y marca de cita agendada. |
| Ventas | Cierre, cotización enviada, conversión, importes, anticipo y liquidación con fechas. |
| Cotizaciones | Importar prospecto, servicios/extras, descuentos, dominio, IVA incluido, anticipos, mantenimiento y PDF para guardar/compartir. El PDF no se guarda en la base, igual que en la web. |
| Proyectos | Proyectos pendientes y en gestión, captura inicial de requerimientos y tablero por estado. |
| Finanzas | Dashboard mensual, gastos operativos e historial, estado de resultados, balance y flujo de efectivo, con las advertencias de alcance del sistema original. |
| Reseñas | Consulta, revisión, aprobación y rechazo con las condiciones originales del servidor. |

Los módulos administrativos requieren `rol=admin`, igual que en Django. Los listados incluyen búsqueda, paginación y recarga; los errores del servidor se muestran en pantalla. El seguimiento de correo registra acciones ya realizadas, igual que el sistema web; no envía campañas automáticamente.

## Validación

```powershell
npx.cmd expo lint
npx.cmd tsc --noEmit
npm test
.\backend\.venv\Scripts\python.exe backend/servidor/manage.py test server --settings=servidor.test_settings --noinput
.\backend\.venv\Scripts\python.exe scripts/verificar-backend.py
```

Se aprobaron 20 pruebas de API/cotizaciones y 127 de Django con Django 6.1, la versión original del ZIP, en `backend/.venv`. Las pruebas automatizadas del backend usan mocks y configuración aislada; el último comando verifica la conexión y tablas reales mediante una transacción de solo lectura, sin consultar datos personales. Se conservaron los requisitos originales de Python.

También se validaron la exportación web y los bundles Android/iOS con Hermes, además del acceso web a 390 px sin desbordamiento horizontal. Eso verifica compilación y renderizado; la prueba completa de acceso requiere tu cuenta, el código real recibido por correo y tu dispositivo. No se inició sesión con credenciales reales ni se modificaron registros durante la verificación.

## Estructura

- `src/app/`: rutas Expo Router y protección de acceso.
- `src/features/`: pantallas de CRM, proyectos, finanzas y cotizaciones.
- `src/components/meg.tsx`: componentes móviles compartidos.
- `src/services/api.ts`: transporte HTTP, CSRF web y almacenamiento seguro nativo.
- `src/context/session.tsx`: ciclo de sesión y revalidación al volver a la app.
- `backend/`: Django y documentación de integración con tu web.

Para producción, publica Django con HTTPS y cambia `EXPO_PUBLIC_API_URL` al dominio de tu API. Las compilaciones de producción rechazan HTTP. No se realizó ningún despliegue ni compilación EAS en la nube.

Referencias consultadas: [Expo SDK 58](https://docs.expo.dev/versions/v58.0.0/), [Expo Router](https://docs.expo.dev/router/introduction/), [SecureStore](https://docs.expo.dev/versions/v58.0.0/sdk/securestore/), [Print](https://docs.expo.dev/versions/v58.0.0/sdk/print/).
