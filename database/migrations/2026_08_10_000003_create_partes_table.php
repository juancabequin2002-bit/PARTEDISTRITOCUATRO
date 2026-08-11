<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('partes', function (Blueprint $table) {
            $table->id();
            $table->foreignId('unidad_id')->constrained('unidades')->cascadeOnDelete();
            $table->date('fecha')->index();
            $table->time('hora_parte')->default('12:00');
            $table->string('turno');
            $table->string('comandante');
            $table->unsignedInteger('fuerza_efectiva_oficiales')->default(0);
            $table->unsignedInteger('fuerza_efectiva_nivel_ejecutivo')->default(0);
            $table->unsignedInteger('fuerza_efectiva_patrulleros')->default(0);
            $table->unsignedInteger('fuerza_efectiva_patrulleros_policia')->default(0);
            $table->unsignedInteger('fuerza_efectiva_auxiliares')->default(0);
            $table->text('observaciones')->nullable();
            $table->foreignId('usuario_id')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('partes');
    }
};
