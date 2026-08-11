<?php

namespace App\Models;

use Carbon\Carbon;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Novedad extends Model
{
    use HasFactory;

    public const TIPOS = [
        'Permiso',
        'Excusa médica',
        'Vacaciones',
        'Franquicia',
        'Incapacidad',
        'Comisión',
        'Curso',
        'Licencia',
        'Suspensión',
        'Otra novedad',
    ];

    protected $fillable = [
        'parte_id',
        'funcionario_id',
        'tipo_novedad',
        'fecha_inicio',
        'hora_inicio',
        'fecha_fin',
        'hora_fin',
        'dias_calculados',
        'observaciones',
        'estado',
    ];

    protected function casts(): array
    {
        return [
            'fecha_inicio' => 'date',
            'fecha_fin' => 'date',
            'dias_calculados' => 'decimal:2',
        ];
    }

    public function parte()
    {
        return $this->belongsTo(Parte::class);
    }

    public function funcionario()
    {
        return $this->belongsTo(Funcionario::class);
    }

    public function inicio(): Carbon
    {
        return Carbon::parse($this->fecha_inicio->format('Y-m-d').' '.$this->hora_inicio);
    }

    public function fin(): Carbon
    {
        return Carbon::parse($this->fecha_fin->format('Y-m-d').' '.$this->hora_fin);
    }

    public function vigentePara(Carbon $fechaHora): bool
    {
        return $this->estado === 'activa' && $this->inicio()->lte($fechaHora) && $this->fin()->gte($fechaHora);
    }
}
