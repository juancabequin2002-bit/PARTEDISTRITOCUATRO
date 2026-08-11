<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('funcionarios', function (Blueprint $table) {
            $table->id();
            $table->string('grado');
            $table->string('nombres');
            $table->string('apellidos');
            $table->string('categoria')->index();
            $table->foreignId('unidad_id')->constrained('unidades')->cascadeOnDelete();
            $table->string('estado')->default('activo')->index();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('funcionarios');
    }
};
