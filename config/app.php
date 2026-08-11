<?php

return [
    'name' => env('APP_NAME', 'Parte de Fuerza'),
    'env' => env('APP_ENV', 'production'),
    'debug' => (bool) env('APP_DEBUG', false),
    'url' => env('APP_URL', 'http://localhost'),
    'timezone' => 'America/Bogota',
    'locale' => 'es',
    'fallback_locale' => 'es',
    'faker_locale' => 'es_CO',
    'cipher' => 'AES-256-CBC',
    'key' => env('APP_KEY'),
    'previous_keys' => [
        ...array_filter(explode(',', env('APP_PREVIOUS_KEYS', ''))),
    ],
];
