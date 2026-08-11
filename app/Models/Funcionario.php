<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Funcionario extends Model
{
    use HasFactory;

    public const CATEGORIAS = [
        'oficiales' => 'Oficiales',
        'nivel_ejecutivo' => 'Nivel Ejecutivo',
        'patrulleros' => 'Patrulleros',
        'patrulleros_policia' => 'Patrulleros de Policía',
        'auxiliares' => 'Auxiliares de Policía',
    ];

    protected $fillable = ['grado', 'nombres', 'apellidos', 'categoria', 'unidad_id', 'estado'];

    public function unidad()
    {
        return $this->belongsTo(Unidad::class);
    }

    public function novedades()
    {
        return $this->hasMany(Novedad::class);
    }

    public function getNombreCompletoAttribute(): string
    {
        return trim("{$this->grado} {$this->nombres} {$this->apellidos}");
    }

    public function getCategoriaNombreAttribute(): string
    {
        return self::CATEGORIAS[$this->categoria] ?? $this->categoria;
    }
}
