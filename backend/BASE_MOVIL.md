# Base de datos de la aplicación móvil

La app usa una única base PostgreSQL/Neon para todas las empresas, con separación por organización. Es distinta de la base del sistema web. El alias Django `movil` solo acepta `NEON_MOBILE_DATABASE_URL`; no utiliza la conexión antigua ni SQLite cuando falta esa variable.

El esquema está versionado en [0001_initial.py](servidor/movil/migrations/0001_initial.py) y sus modelos en [models.py](servidor/movil/models.py). No es necesario ejecutar el SQL original ni copiar los esquemas `auth` o `neon_auth`: la app tiene sus propias cuentas, sesiones y membresías.

```mermaid
erDiagram
  movil_usuario ||--o{ movil_sesion : tiene
  movil_usuario ||--o{ movil_membresia : solicita
  movil_organizacion ||--o{ movil_membresia : autoriza
  movil_organizacion ||--o{ movil_cliente : registra
  movil_cliente ||--o{ movil_requerimiento : define
  movil_organizacion ||--o{ movil_gastooperativo : mantiene
  movil_gastooperativo ||--o{ movil_gastohistorial : versiona
```

| Tabla | Función |
| --- | --- |
| `movil_usuario` | Datos personales; usuario, correo y teléfono únicos; contraseña con hash. |
| `movil_sesion` | Hash del token, vencimiento y revocación. |
| `movil_limiteacceso` | Contadores compartidos para limitar registro e inicio de sesión. |
| `movil_organizacion` | Empresa, nombre y descripción. |
| `movil_membresia` | Organización, usuario, rol y estado de acceso. |
| `movil_cliente` | Prospecto, venta y datos de anticipo/liquidación. |
| `movil_requerimiento` | Título, descripción, orden y estado del trabajo de una venta. |
| `movil_gastooperativo` | Gasto recurrente de una organización. |
| `movil_gastohistorial` | Versiones del gasto vigentes desde cada mes. |

Cada usuario puede tener una organización aceptada o una solicitud pendiente. Un rechazo o eliminación permite volver a solicitar acceso. Las invitaciones al crear una organización se asignan a usuarios registrados y disponibles. El administrador puede aceptar o rechazar solicitudes, asignar un rol y retirar miembros; no puede eliminar su propia membresía.

Una venta crea la entrada pendiente de requerimientos sin duplicar al cliente. Al guardar requerimientos, el proyecto pasa a gestión. Los importes contratados se separan de los cobros: Finanzas cuenta el anticipo y el saldo por sus fechas efectivas. Se conserva el historial de gastos y el alcance parcial de los reportes originales.

## Instalación en Neon

Si prefieres usar el SQL Editor de Neon, los archivos listos para ejecutar están en [sql/README.md](sql/README.md): [crear la base](sql/01_crear_base.sql) e [instalar el esquema completo](sql/02_esquema_aplicacion.sql).

En este entorno ya se crearon la base `aplicacion_movil` y el rol dedicado `aplicacion_movil_app`, se guardó `NEON_MOBILE_DATABASE_URL` en el archivo privado del servidor y se aplicó la migración inicial. Se verificaron las nueve tablas vacías, sus 19 restricciones e índices, y que el rol móvil no tiene permisos de lectura sobre las tablas originales. El archivo `.env` está excluido de Git. Reinicia Django para cargar esta conexión.

Los pasos siguientes sirven para instalar el proyecto en otro entorno:

1. Crea una base vacía llamada `aplicacion_movil`, distinta de la base web. Puede estar en un proyecto propio o en otra base de la misma rama. Utiliza un rol dedicado con permisos sobre esa base.
2. Guarda su conexión privada como `NEON_MOBILE_DATABASE_URL` en `backend/servidor/.env`. Nunca la pongas en una variable `EXPO_PUBLIC_*`.
3. Desde la raíz del proyecto ejecuta:

```powershell
.\backend\.venv\Scripts\python.exe backend/servidor/manage.py migrate movil --database=movil
.\backend\.venv\Scripts\python.exe scripts/verificar-base-movil.py
```

La migración crea las nueve tablas móviles y el registro de migraciones en esa base. No se ejecuta contra `neon` ni contra la base del sistema web. El router impide crear tablas de otras aplicaciones en `movil`. La configuración rechaza reutilizar la misma base original, incluso con otro usuario o el host pooler de Neon.

Para revisar el SQL antes de instalar, una vez configurada la conexión:

```powershell
.\backend\.venv\Scripts\python.exe backend/servidor/manage.py sqlmigrate movil 0001 --database=movil
```

Referencia oficial: [administrar bases en Neon](https://neon.com/docs/manage/databases).
