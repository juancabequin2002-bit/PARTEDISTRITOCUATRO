<?php

namespace App\Http\Controllers;

use App\Models\Funcionario;
use App\Models\Novedad;
use App\Models\Parte;
use App\Models\Unidad;
use Carbon\Carbon;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;
use Illuminate\Validation\ValidationException;

class ParteController extends Controller
{
    public function create()
    {
        return view('partes.form', [
            'parte' => null,
            'unidades' => Unidad::where('estado', 'activa')->orderBy('nombre')->get(),
            'funcionarios' => Funcionario::with('unidad')->where('estado', 'activo')->orderBy('grado')->orderBy('nombres')->get(),
            'categorias' => Funcionario::CATEGORIAS,
            'tipos' => Novedad::TIPOS,
        ]);
    }

    public function store(Request $request)
    {
        $data = $this->validatedParte($request);
        $novedades = $request->input('novedades', []);

        return DB::transaction(function () use ($data, $novedades) {
            $parte = Parte::create($data + ['usuario_id' => auth()->id()]);
            $this->syncNovedades($parte, $novedades);

            return response()->json([
                'message' => 'Parte de fuerza guardado correctamente.',
                'redirect' => route('partes.edit', $parte),
            ]);
        });
    }

    public function edit(Parte $parte)
    {
        $parte->load('novedades.funcionario', 'unidad');

        return view('partes.form', [
            'parte' => $parte,
            'unidades' => Unidad::where('estado', 'activa')->orderBy('nombre')->get(),
            'funcionarios' => Funcionario::with('unidad')->where('estado', 'activo')->orderBy('grado')->orderBy('nombres')->get(),
            'categorias' => Funcionario::CATEGORIAS,
            'tipos' => Novedad::TIPOS,
        ]);
    }

    public function update(Request $request, Parte $parte)
    {
        $data = $this->validatedParte($request);
        $novedades = $request->input('novedades', []);

        return DB::transaction(function () use ($parte, $data, $novedades) {
            $parte->update($data);
            $parte->novedades()->delete();
            $this->syncNovedades($parte->fresh(), $novedades);

            return response()->json([
                'message' => 'Parte de fuerza actualizado correctamente.',
                'redirect' => route('partes.edit', $parte),
            ]);
        });
    }

    public function index(Request $request)
    {
        $partes = Parte::with('unidad', 'novedades')
            ->when($request->filled('fecha'), fn ($q) => $q->whereDate('fecha', $request->fecha))
            ->when($request->filled('unidad_id'), fn ($q) => $q->where('unidad_id', $request->unidad_id))
            ->when($request->filled('turno'), fn ($q) => $q->where('turno', 'like', '%'.$request->turno.'%'))
            ->when($request->filled('comandante'), fn ($q) => $q->where('comandante', 'like', '%'.$request->comandante.'%'))
            ->latest('fecha')
            ->paginate(12)
            ->withQueryString();

        return view('partes.index', [
            'partes' => $partes,
            'unidades' => Unidad::orderBy('nombre')->get(),
        ]);
    }

    public function print(Parte $parte)
    {
        $parte->load('unidad', 'novedades.funcionario');

        return view('partes.print', [
            'parte' => $parte,
            'categorias' => Funcionario::CATEGORIAS,
            'resumen' => $this->resumenParte($parte),
        ]);
    }

    public function destroy(Parte $parte)
    {
        $parte->delete();
        return redirect()->route('partes.index')->with('status', 'Parte eliminado correctamente.');
    }

    public function funcionarios(Unidad $unidad)
    {
        return Funcionario::where('unidad_id', $unidad->id)
            ->where('estado', 'activo')
            ->orderBy('grado')
            ->orderBy('nombres')
            ->get()
            ->map(fn ($funcionario) => [
                'id' => $funcionario->id,
                'grado' => $funcionario->grado,
                'nombres' => $funcionario->nombres,
                'apellidos' => $funcionario->apellidos,
                'nombre_completo' => $funcionario->nombre_completo,
                'categoria' => $funcionario->categoria,
                'categoria_nombre' => $funcionario->categoria_nombre,
            ]);
    }

    private function validatedParte(Request $request): array
    {
        return $request->validate([
            'unidad_id' => ['required', 'exists:unidades,id'],
            'fecha' => ['required', 'date'],
            'hora_parte' => ['required', 'date_format:H:i'],
            'turno' => ['required', 'string', 'max:120'],
            'comandante' => ['required', 'string', 'max:160'],
            'fuerza_efectiva_oficiales' => ['required', 'integer', 'min:0'],
            'fuerza_efectiva_nivel_ejecutivo' => ['required', 'integer', 'min:0'],
            'fuerza_efectiva_patrulleros' => ['required', 'integer', 'min:0'],
            'fuerza_efectiva_patrulleros_policia' => ['required', 'integer', 'min:0'],
            'fuerza_efectiva_auxiliares' => ['required', 'integer', 'min:0'],
            'observaciones' => ['nullable', 'string'],
        ]);
    }

    private function syncNovedades(Parte $parte, array $novedades): void
    {
        $efectiva = $parte->efectivaPorCategoria();
        $ocupacion = array_fill_keys(array_keys(Funcionario::CATEGORIAS), 0);
        $rangosPorFuncionario = [];
        $fechaHoraParte = $parte->fechaHoraParte();

        foreach ($novedades as $index => $item) {
            $data = validator($item, [
                'tipo_novedad' => ['required', Rule::in(Novedad::TIPOS)],
                'funcionario_id' => ['required', 'exists:funcionarios,id'],
                'fecha_inicio' => ['required', 'date'],
                'hora_inicio' => ['required', 'date_format:H:i'],
                'fecha_fin' => ['required', 'date'],
                'hora_fin' => ['required', 'date_format:H:i'],
                'dias_calculados' => ['nullable', 'numeric', 'min:0'],
                'observaciones' => ['nullable', 'string'],
                'estado' => ['nullable', 'string'],
            ])->validate();

            $inicio = Carbon::parse($data['fecha_inicio'].' '.$data['hora_inicio']);
            $fin = Carbon::parse($data['fecha_fin'].' '.$data['hora_fin']);

            if ($fin->lte($inicio)) {
                throw ValidationException::withMessages([
                    "novedades.{$index}.fecha_fin" => 'La fecha y hora final debe ser posterior a la inicial.',
                ]);
            }

            $funcionario = Funcionario::findOrFail($data['funcionario_id']);
            if ((int) $funcionario->unidad_id !== (int) $parte->unidad_id) {
                throw ValidationException::withMessages([
                    "novedades.{$index}.funcionario_id" => 'El funcionario no pertenece a la unidad seleccionada.',
                ]);
            }

            foreach ($rangosPorFuncionario[$funcionario->id] ?? [] as [$ini, $end]) {
                if ($inicio->lt($end) && $fin->gt($ini)) {
                    throw ValidationException::withMessages([
                        "novedades.{$index}.funcionario_id" => 'Ya existe una novedad simultánea para este funcionario.',
                    ]);
                }
            }

            $rangosPorFuncionario[$funcionario->id][] = [$inicio, $fin];
            $vigente = $inicio->lte($fechaHoraParte) && $fin->gte($fechaHoraParte);

            if ($vigente) {
                $ocupacion[$funcionario->categoria]++;
                if ($ocupacion[$funcionario->categoria] > ($efectiva[$funcionario->categoria] ?? 0)) {
                    $categoria = $funcionario->categoria_nombre;
                    throw ValidationException::withMessages([
                        "novedades.{$index}.funcionario_id" => "No es posible registrar esta novedad. La unidad solamente cuenta con {$efectiva[$funcionario->categoria]} funcionarios de {$categoria} y ya existen {$efectiva[$funcionario->categoria]} funcionarios registrados en novedad.",
                    ]);
                }
            }

            $parte->novedades()->create([
                ...$data,
                'dias_calculados' => round($inicio->diffInMinutes($fin) / 1440, 2),
                'estado' => $data['estado'] ?? 'activa',
            ]);
        }
    }

    private function resumenParte(Parte $parte): array
    {
        $efectiva = $parte->efectivaPorCategoria();
        $novedades = array_fill_keys(array_keys(Funcionario::CATEGORIAS), 0);
        $fechaHoraParte = $parte->fechaHoraParte();

        foreach ($parte->novedades as $novedad) {
            if ($novedad->vigentePara($fechaHoraParte)) {
                $novedades[$novedad->funcionario->categoria]++;
            }
        }

        $disponible = [];
        foreach ($efectiva as $categoria => $cantidad) {
            $disponible[$categoria] = max(0, $cantidad - ($novedades[$categoria] ?? 0));
        }

        return compact('efectiva', 'novedades', 'disponible');
    }
}
