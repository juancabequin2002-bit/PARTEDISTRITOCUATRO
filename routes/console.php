<?php

use Illuminate\Support\Facades\Artisan;

Artisan::command('app:admin', function () {
    $name = $this->ask('Nombre', 'Administrador');
    $email = $this->ask('Correo', 'admin@policia.local');
    $password = $this->secret('Contraseña') ?: 'password';

    \App\Models\User::updateOrCreate(
        ['email' => $email],
        ['name' => $name, 'password' => \Illuminate\Support\Facades\Hash::make($password)]
    );

    $this->info("Usuario administrador listo: {$email}");
});
