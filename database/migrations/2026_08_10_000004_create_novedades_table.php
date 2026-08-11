<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('novedades', function (Blueprint $table) {
            $table->id();
            $table->foreignId('parte_id')->constrained('partes')->cascadeOnDelete();
            $table->foreignId('funcionario_id')->constrained('funcionarios')->cascadeOnDelete();
            $table->string('tipo_novedad');
            $table->date('fecha_inicio');
            $table->time('hora_inicio');
            $table->date('fecha_fin');
            $table->time('hora_fin');
            $table->decimal('dias_calculados', 8, 2)->default(0);
            $table->text('observaciones')->nullable();
            $table->string('estado')->default('activa')->index();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('novedades');
    }
};
