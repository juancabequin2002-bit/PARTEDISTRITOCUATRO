#!/usr/bin/env sh
set -e

if [ -n "$APP_KEY" ]; then
    php artisan config:cache || true
fi

php artisan migrate --force || true

exec "$@"
