<?php

use App\Http\Controllers\AuthController;
use App\Http\Controllers\DashboardController;
use App\Http\Controllers\FuncionarioController;
use App\Http\Controllers\ParteController;
use Illuminate\Support\Facades\Route;

Route::middleware('guest')->group(function () {
    Route::get('login', [AuthController::class, 'showLogin'])->name('login');
    Route::post('login', [AuthController::class, 'login'])->name('login.store');
});

Route::middleware('auth')->group(function () {
    Route::post('logout', [AuthController::class, 'logout'])->name('logout');
    Route::get('/', DashboardController::class)->name('dashboard');
    Route::get('/unidades/{unidad}/funcionarios', [ParteController::class, 'funcionarios'])->name('unidades.funcionarios');
    Route::get('/partes/historial', [ParteController::class, 'index'])->name('partes.index');
    Route::get('/partes/crear', [ParteController::class, 'create'])->name('partes.create');
    Route::post('/partes', [ParteController::class, 'store'])->name('partes.store');
    Route::get('/partes/{parte}/editar', [ParteController::class, 'edit'])->name('partes.edit');
    Route::put('/partes/{parte}', [ParteController::class, 'update'])->name('partes.update');
    Route::get('/partes/{parte}/imprimir', [ParteController::class, 'print'])->name('partes.print');
    Route::delete('/partes/{parte}', [ParteController::class, 'destroy'])->name('partes.destroy');
    Route::resource('funcionarios', FuncionarioController::class)->only(['index', 'store', 'update', 'destroy']);
});
