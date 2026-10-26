-- CREAR LA BASE POSTGRESQL EN NEON
-- OPCIONAL: si creaste un proyecto nuevo exclusivo para la app y su neondb
-- esta vacia, puedes ejecutar directamente 02_esquema_aplicacion.sql alli.
-- Ejecuta solamente este archivo desde otra base de la misma rama,
-- usando el propietario del proyecto o un rol con permiso CREATEDB.
-- CREATE DATABASE debe ejecutarse solo, fuera de BEGIN / COMMIT.
-- Si aplicacion_movil ya existe, omite este paso.
-- Si creas esta base, despues seleccionala en el SQL Editor y ejecuta
-- 02_esquema_aplicacion.sql. El rol que lo ejecute sera dueno de las tablas.

CREATE DATABASE aplicacion_movil;
