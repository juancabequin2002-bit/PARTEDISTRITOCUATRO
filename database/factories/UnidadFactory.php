<?php

namespace Database\Factories;

use App\Models\Unidad;
use Illuminate\Database\Eloquent\Factories\Factory;

class UnidadFactory extends Factory
{
    protected $model = Unidad::class;

    public function definition(): array
    {
        return [
            'nombre' => 'Unidad '.$this->faker->city(),
            'estado' => 'activa',
        ];
    }
}
