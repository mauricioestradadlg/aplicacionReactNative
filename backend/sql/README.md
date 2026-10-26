# Scripts SQL de la aplicación móvil

Estos archivos instalan el esquema PostgreSQL que utiliza la aplicación. Se generaron a partir de `movil/0001_initial`, incluyendo las nueve tablas, las claves foráneas, los índices y las restricciones actuales. No contienen credenciales ni datos de ejemplo.

## Ejecución en Neon

1. Abre el SQL Editor de Neon y selecciona tu proyecto y rama. El nombre del proyecto y el nombre de la base son independientes: un proyecto llamado `aplicacion_movil` puede tener su base predeterminada `neondb`. Si ese proyecto es exclusivo de la app y `neondb` está vacía, úsala directamente. Si necesitas otra base dentro de la rama, ejecuta por separado [01_crear_base.sql](01_crear_base.sql), con un rol que pueda crear bases.
2. Selecciona la base vacía destinada a la aplicación en el desplegable superior del SQL Editor. Puede llamarse `neondb`, `aplicacion_movil` u otro nombre.
3. Ejecuta completo [02_esquema_aplicacion.sql](02_esquema_aplicacion.sql). Usa el rol cuya conexión utilizará Django: ese rol debe tener permisos de creación en el esquema `public`. Si el editor usa otro rol, utiliza la conexión de la aplicación en un cliente PostgreSQL para ejecutar el archivo.
4. Guarda la conexión de ese rol y base en `NEON_MOBILE_DATABASE_URL`, dentro de `backend/servidor/.env`, y reinicia Django.

Los archivos se ejecutan por separado: `CREATE DATABASE` debe ejecutarse fuera de una transacción. En el segundo archivo, todas las tablas se crean dentro de una sola transacción. Si existen tablas, vistas o secuencias en `public`, se detiene la instalación para conservar los registros actuales; utiliza las migraciones Django para actualizar el esquema.

Si Neon muestra `Failed transaction: ROLLBACK required`, pulsa **ROLLBACK** o ejecuta `ROLLBACK;` por separado. Después vuelve a ejecutar el archivo actualizado sobre la base vacía seleccionada. El aviso de que se recortará texto en el historial no impide ejecutar la consulta completa.

El script registra `movil/0001_initial` en `django_migrations`, para que Django reconozca esta instalación. Los valores predeterminados, UUID y fechas los proporciona el backend, igual que en la migración original. Las cuentas deben registrarse desde la aplicación para que la contraseña se almacene con el hash adecuado.

En el entorno actual, la base y el esquema ya están instalados. Estos archivos permiten repetir la instalación en otro entorno.

Referencias oficiales: [bases de datos en Neon](https://neon.com/docs/manage/databases), [CREATE DATABASE en PostgreSQL](https://www.postgresql.org/docs/current/sql-createdatabase.html) y [sqlmigrate de Django](https://docs.djangoproject.com/en/6.0/ref/django-admin/#sqlmigrate).
