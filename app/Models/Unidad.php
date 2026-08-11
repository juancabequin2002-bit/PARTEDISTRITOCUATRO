<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Unidad extends Model
{
    use HasFactory;

    protected $fillable = ['nombre', 'estado'];

    public function funcionarios()
    {
        return $this->hasMany(Funcionario::class);
    }

    public function partes()
    {
        return $this->hasMany(Parte::class);
    }
}
