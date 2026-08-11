<?php

namespace Database\Seeders;

use App\Models\Funcionario;
use App\Models\Unidad;
use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class DatabaseSeeder extends Seeder
{
    public function run(): void
    {
        User::updateOrCreate(
            ['email' => 'admin@policia.local'],
            ['name' => 'Administrador', 'password' => Hash::make('password')]
        );

        $unidad = Unidad::updateOrCreate(
            ['nombre' => 'Distrito Cuatro de Policía Purificación'],
            ['estado' => 'activa']
        );

        $funcionarios = [
            ['Subintendente', 'Juan', 'Pérez', 'nivel_ejecutivo'],
            ['Intendente', 'María Fernanda', 'Gómez', 'nivel_ejecutivo'],
            ['Patrullero', 'Carlos', 'Rodríguez', 'patrulleros'],
            ['Patrullero', 'Andrés Felipe', 'Morales', 'patrulleros'],
            ['Patrullero', 'Laura Natalia', 'Suárez', 'patrulleros'],
            ['Patrullera de Policía', 'Diana Carolina', 'Rojas', 'patrulleros_policia'],
            ['Patrullero de Policía', 'Miguel Ángel', 'Torres', 'patrulleros_policia'],
            ['Auxiliar de Policía', 'Santiago', 'López', 'auxiliares'],
        ];

        foreach ($funcionarios as [$grado, $nombres, $apellidos, $categoria]) {
            Funcionario::updateOrCreate(
                ['grado' => $grado, 'nombres' => $nombres, 'apellidos' => $apellidos, 'unidad_id' => $unidad->id],
                ['categoria' => $categoria, 'estado' => 'activo']
            );
        }
    }
}
