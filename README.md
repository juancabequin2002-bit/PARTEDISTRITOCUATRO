# Sistema Web Parte de Fuerza Policial

Aplicación Laravel para registrar fuerza efectiva, novedades del personal, fuerza disponible por categoría, historial e impresión institucional del parte.

## Requisitos

- PHP 8.2 o superior
- Composer
- MySQL

En este equipo no se encontró `php` ni `composer` en el PATH. Instálalos o agrega sus rutas al PATH antes de ejecutar los comandos.

## Instalación

```bash
composer install
copy .env.example .env
php artisan key:generate
```

Crea una base de datos MySQL llamada `parte_fuerza` y ajusta `.env` si tu usuario/contraseña son diferentes:

```env
DB_DATABASE=parte_fuerza
DB_USERNAME=root
DB_PASSWORD=
```

Ejecuta migraciones y datos iniciales:

```bash
php artisan migrate --seed
```

## Usuario Administrador

El seeder crea este usuario:

- Correo: `admin@policia.local`
- Contraseña: `password`

También puedes crear o actualizar un administrador con:

```bash
php artisan app:admin
```

## Iniciar

```bash
php artisan serve
```

Abre:

```text
http://127.0.0.1:8000
```

## Despliegue en Render

El proyecto incluye `Dockerfile`, `docker/entrypoint.sh` y `render.yaml`.

En Render crea un Blueprint desde el repositorio de GitHub y configura estas variables:

- `APP_KEY`: genera una localmente con `php artisan key:generate --show`
- `APP_URL`: URL pública asignada por Render
- `DB_HOST`: host de tu MySQL externo
- `DB_DATABASE`: nombre de la base
- `DB_USERNAME`: usuario
- `DB_PASSWORD`: contraseña

El contenedor ejecuta `php artisan migrate --force` al iniciar.

## Prueba rápida del cálculo

1. Ingresa con el usuario administrador.
2. En `Parte de Fuerza`, deja los valores de ejemplo:
   - Oficiales: 0
   - Nivel Ejecutivo: 2
   - Patrulleros: 3
   - Patrulleros de Policía: 2
   - Auxiliares de Policía: 1
3. El sistema mostrará `Total fuerza efectiva: 8`.
4. Pulsa `+ Registrar Novedad`.
5. Selecciona `Permiso` y un funcionario de `Nivel Ejecutivo`.
6. Usa inicio `2026-08-05 06:00` y fin `2026-08-05 18:00`.
7. Al guardar la novedad, el resumen mostrará:
   - Fuerza efectiva: 8
   - Novedades vigentes: 1
   - Fuerza disponible: 7
   - Porcentaje disponible: 87.5%

La novedad solo descuenta si está vigente para la fecha y hora del parte. Por defecto se usa `12:00`, pero puedes cambiar la hora en la pantalla principal.

## Funcionalidades

- Autenticación con sesión Laravel.
- CRUD de funcionarios.
- CRUD de partes de fuerza.
- Registro, edición y eliminación dinámica de novedades dentro del parte.
- Cálculo automático de días y horas con JavaScript.
- Cálculo automático de fuerza efectiva, novedades vigentes, disponible y porcentaje.
- Validaciones en navegador y servidor:
  - Sin funcionario o tipo.
  - Fechas incompletas.
  - Fecha final anterior a inicial.
  - Novedades simultáneas del mismo funcionario.
  - Novedades que exceden la fuerza efectiva por categoría.
  - Prevención de fuerza disponible negativa.
- Historial con filtros.
- Vista institucional de impresión con `window.print()`.
