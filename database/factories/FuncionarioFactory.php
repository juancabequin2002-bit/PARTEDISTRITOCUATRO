<?php

namespace Database\Factories;

use App\Models\Funcionario;
use App\Models\Unidad;
use Illuminate\Database\Eloquent\Factories\Factory;

class FuncionarioFactory extends Factory
{
    protected $model = Funcionario::class;

    public function definition(): array
    {
        $categorias = array_keys(Funcionario::CATEGORIAS);

        return [
            'grado' => $this->faker->randomElement(['Subintendente', 'Intendente', 'Patrullero', 'Auxiliar de Policía']),
            'nombres' => $this->faker->firstName(),
            'apellidos' => $this->faker->lastName().' '.$this->faker->lastName(),
            'categoria' => $this->faker->randomElement($categorias),
            'unidad_id' => Unidad::factory(),
            'estado' => 'activo',
        ];
    }
}
