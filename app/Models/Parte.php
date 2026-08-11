<?php

namespace App\Models;

use Carbon\Carbon;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Parte extends Model
{
    use HasFactory;

    protected $fillable = [
        'unidad_id',
        'fecha',
        'hora_parte',
        'turno',
        'comandante',
        'fuerza_efectiva_oficiales',
        'fuerza_efectiva_nivel_ejecutivo',
        'fuerza_efectiva_patrulleros',
        'fuerza_efectiva_patrulleros_policia',
        'fuerza_efectiva_auxiliares',
        'observaciones',
        'usuario_id',
    ];

    protected function casts(): array
    {
        return ['fecha' => 'date'];
    }

    public function unidad()
    {
        return $this->belongsTo(Unidad::class);
    }

    public function usuario()
    {
        return $this->belongsTo(User::class, 'usuario_id');
    }

    public function novedades()
    {
        return $this->hasMany(Novedad::class);
    }

    public function efectivaPorCategoria(): array
    {
        return [
            'oficiales' => (int) $this->fuerza_efectiva_oficiales,
            'nivel_ejecutivo' => (int) $this->fuerza_efectiva_nivel_ejecutivo,
            'patrulleros' => (int) $this->fuerza_efectiva_patrulleros,
            'patrulleros_policia' => (int) $this->fuerza_efectiva_patrulleros_policia,
            'auxiliares' => (int) $this->fuerza_efectiva_auxiliares,
        ];
    }

    public function fechaHoraParte(): Carbon
    {
        return Carbon::parse($this->fecha->format('Y-m-d').' '.substr((string) $this->hora_parte, 0, 5));
    }
}
