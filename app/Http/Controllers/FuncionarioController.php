<?php

namespace App\Http\Controllers;

use App\Models\Funcionario;
use App\Models\Unidad;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

class FuncionarioController extends Controller
{
    public function index()
    {
        return view('funcionarios.index', [
            'funcionarios' => Funcionario::with('unidad')->orderBy('grado')->orderBy('nombres')->paginate(15),
            'unidades' => Unidad::orderBy('nombre')->get(),
            'categorias' => Funcionario::CATEGORIAS,
        ]);
    }

    public function store(Request $request)
    {
        Funcionario::create($this->validated($request));
        return back()->with('status', 'Funcionario registrado correctamente.');
    }

    public function update(Request $request, Funcionario $funcionario)
    {
        $funcionario->update($this->validated($request));
        return back()->with('status', 'Funcionario actualizado correctamente.');
    }

    public function destroy(Funcionario $funcionario)
    {
        $funcionario->delete();
        return back()->with('status', 'Funcionario eliminado correctamente.');
    }

    private function validated(Request $request): array
    {
        return $request->validate([
            'grado' => ['required', 'string', 'max:80'],
            'nombres' => ['required', 'string', 'max:120'],
            'apellidos' => ['required', 'string', 'max:120'],
            'categoria' => ['required', Rule::in(array_keys(Funcionario::CATEGORIAS))],
            'unidad_id' => ['required', 'exists:unidades,id'],
            'estado' => ['required', Rule::in(['activo', 'inactivo'])],
        ]);
    }
}
