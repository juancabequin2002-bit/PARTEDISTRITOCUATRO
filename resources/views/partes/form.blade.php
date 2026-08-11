@extends('layouts.app')

@section('title', 'Parte de Fuerza')

@section('content')
@php
    $unidadDefault = $parte?->unidad_id ?? optional($unidades->first())->id;
    $initialNovedades = $parte
        ? $parte->novedades->map(fn ($n) => [
            'id' => $n->id,
            'tipo_novedad' => $n->tipo_novedad,
            'funcionario_id' => $n->funcionario_id,
            'funcionario' => trim(($n->funcionario?->nombres ?? '').' '.($n->funcionario?->apellidos ?? '')),
            'grado' => $n->funcionario?->grado,
            'categoria' => $n->funcionario?->categoria,
            'categoria_nombre' => $n->funcionario?->categoria_nombre,
            'fecha_inicio' => $n->fecha_inicio?->format('Y-m-d'),
            'hora_inicio' => substr($n->hora_inicio, 0, 5),
            'fecha_fin' => $n->fecha_fin?->format('Y-m-d'),
            'hora_fin' => substr($n->hora_fin, 0, 5),
            'dias_calculados' => (float) $n->dias_calculados,
            'observaciones' => $n->observaciones,
            'estado' => $n->estado,
        ])
        : collect();
@endphp

<form id="parteForm" class="parte-form" data-mode="{{ $parte ? 'edit' : 'create' }}" data-action="{{ $parte ? route('partes.update', $parte) : route('partes.store') }}" data-print="{{ $parte ? route('partes.print', $parte) : '' }}">
    @csrf
    @if($parte)
        @method('PUT')
    @endif

    <section class="panel general-panel">
        <h2>Información general</h2>
        <div class="grid five">
            <label>Unidad
                <select name="unidad_id" id="unidad_id" required>
                    @foreach($unidades as $unidad)
                        <option value="{{ $unidad->id }}" @selected($unidadDefault == $unidad->id)>{{ $unidad->nombre }}</option>
                    @endforeach
                </select>
            </label>
            <label>Comandante que reporta
                <input name="comandante" id="comandante" value="{{ old('comandante', $parte->comandante ?? 'Cap. YESICA LICETH GÓMEZ TRUJILLO') }}" required>
            </label>
            <label>Turno
                <select name="turno" id="turno" required>
                    @foreach(['Turno A (06:00 - 18:00)', 'Turno B (18:00 - 06:00)', 'Primer turno', 'Segundo turno', 'Tercer turno'] as $turno)
                        <option @selected(($parte->turno ?? 'Turno A (06:00 - 18:00)') === $turno)>{{ $turno }}</option>
                    @endforeach
                </select>
            </label>
            <label>Fecha del parte
                <input type="date" name="fecha" id="fecha" value="{{ old('fecha', $parte?->fecha?->format('Y-m-d') ?? '2026-08-05') }}" required>
            </label>
            <label>Hora del parte
                <input type="time" name="hora_parte" id="hora_parte" value="{{ old('hora_parte', $parte ? substr((string) $parte->hora_parte, 0, 5) : '12:00') }}" required>
            </label>
        </div>
    </section>

    <div class="grid main-grid">
        <section class="panel">
            <h2>1. Fuerza efectiva <small>(total unidad)</small></h2>
            <table class="data-table effective-table">
                <thead><tr><th>Categoría</th><th>Cantidad</th></tr></thead>
                <tbody>
                    <tr><td>Oficiales</td><td><input class="qty efectiva" id="efectiva_oficiales" name="fuerza_efectiva_oficiales" type="number" min="0" value="{{ $parte->fuerza_efectiva_oficiales ?? 0 }}"></td></tr>
                    <tr><td>Nivel Ejecutivo</td><td><input class="qty efectiva" id="efectiva_nivel_ejecutivo" name="fuerza_efectiva_nivel_ejecutivo" type="number" min="0" value="{{ $parte->fuerza_efectiva_nivel_ejecutivo ?? 2 }}"></td></tr>
                    <tr><td>Patrulleros</td><td><input class="qty efectiva" id="efectiva_patrulleros" name="fuerza_efectiva_patrulleros" type="number" min="0" value="{{ $parte->fuerza_efectiva_patrulleros ?? 3 }}"></td></tr>
                    <tr><td>Patrulleros de Policía</td><td><input class="qty efectiva" id="efectiva_patrulleros_policia" name="fuerza_efectiva_patrulleros_policia" type="number" min="0" value="{{ $parte->fuerza_efectiva_patrulleros_policia ?? 2 }}"></td></tr>
                    <tr><td>Auxiliares de Policía</td><td><input class="qty efectiva" id="efectiva_auxiliares" name="fuerza_efectiva_auxiliares" type="number" min="0" value="{{ $parte->fuerza_efectiva_auxiliares ?? 1 }}"></td></tr>
                </tbody>
                <tfoot><tr><th>Total fuerza efectiva</th><th id="total_efectiva">0</th></tr></tfoot>
            </table>
        </section>

        <div class="flow-arrow no-mobile">
            <span>➜</span>
            <small>Cálculo<br>Automático</small>
        </div>

        <section class="panel" id="novedades">
            <div class="section-head">
                <h2>2. Novedades del personal</h2>
                <button type="button" class="btn primary" id="toggleNovedad">+ Registrar Novedad</button>
            </div>
            <table class="data-table">
                <thead><tr><th>Tipo</th><th>Funcionario</th><th>Inicio</th><th>Fin</th><th>Días</th><th>Acción</th></tr></thead>
                <tbody id="novedadesBody"></tbody>
                <tfoot><tr><th colspan="4">Total funcionarios en novedades:</th><th id="totalNovedadesTabla">0</th><th></th></tr></tfoot>
            </table>

            <div class="subpanel" id="novedadForm">
                <h3>Registrar novedad</h3>
                <div class="grid two">
                    <label>Tipo de novedad
                        <select id="tipo_novedad">
                            <option value="">Seleccione...</option>
                            @foreach($tipos as $tipo)
                                <option>{{ $tipo }}</option>
                            @endforeach
                        </select>
                    </label>
                    <label>Funcionario
                        <select id="funcionario_id">
                            <option value="">Seleccione...</option>
                        </select>
                    </label>
                </div>
                <div class="grid four compact">
                    <label>Fecha inicio<input type="date" id="fecha_inicio" value="2026-08-05"></label>
                    <label>Hora inicio<input type="time" id="hora_inicio" value="06:00"></label>
                    <label>Fecha fin<input type="date" id="fecha_fin" value="2026-08-05"></label>
                    <label>Hora fin<input type="time" id="hora_fin" value="18:00"></label>
                </div>
                <div class="novedad-actions">
                    <div class="duration-box">Días calculados: <strong id="diasTexto">0 días</strong><input type="hidden" id="dias_calculados"></div>
                    <button type="button" class="btn primary" id="guardarNovedad">Guardar Novedad</button>
                </div>
                <div class="alert info">El cálculo de días se realiza automáticamente teniendo en cuenta la fecha y hora de inicio y fin de la novedad.</div>
            </div>
        </section>
    </div>

    <div class="grid lower-grid">
        <section class="panel">
            <h2>3. Fuerza disponible <small>(después de novedades)</small></h2>
            <table class="data-table available-table">
                <thead><tr><th>Categoría</th><th>Efectiva</th><th>En novedades</th><th>Disponible</th></tr></thead>
                <tbody>
                    @foreach($categorias as $key => $label)
                        <tr><td>{{ $label }}</td><td id="ef_{{ $key }}">0</td><td id="nov_{{ $key }}">0</td><td id="disp_{{ $key }}">0</td></tr>
                    @endforeach
                </tbody>
                <tfoot><tr><th>Total</th><th id="total_efectiva_2">0</th><th id="total_novedades">0</th><th id="total_disponible">0</th></tr></tfoot>
            </table>
        </section>

        <aside class="panel summary-card">
            <h2>Resumen del parte</h2>
            <div class="metric"><span>Fuerza Efectiva Total:</span><strong id="res_efectiva">0</strong></div>
            <div class="metric"><span>Total en Novedades:</span><strong id="res_novedades">0</strong></div>
            <div class="metric green"><span>Fuerza Disponible:</span><strong id="res_disponible">0</strong></div>
            <div class="metric"><span>Porcentaje Disponible:</span><strong id="porcentaje_disponible">0%</strong></div>
            <div class="alert success compact-alert"><strong>Cálculo automático</strong><br>La fuerza disponible se calcula restando las novedades vigentes por categoría.</div>
        </aside>
    </div>

    <div class="grid lower-grid">
        <section class="panel">
            <h2>Observaciones del comandante</h2>
            <textarea name="observaciones" id="observaciones" rows="5" placeholder="Ingrese las observaciones o novedades relevantes del parte...">{{ $parte->observaciones ?? '' }}</textarea>
        </section>
        <section class="panel actions-panel no-print">
            <h2>Acciones</h2>
            <button class="btn primary full" type="submit">Guardar Parte de Fuerza</button>
            <button class="btn outline full" type="button" id="imprimirParte">Imprimir Parte</button>
            <a class="btn outline full" href="{{ route('partes.index') }}">Historial de Partes</a>
        </section>
    </div>
    <div class="alert info no-print">Este parte de fuerza es generado automáticamente con base en los datos registrados en novedades. Usuario: {{ auth()->user()->email }}</div>
</form>
@endsection

@push('scripts')
<script>
window.ParteFuerza = {
    categorias: @json($categorias),
    funcionarios: @json($funcionarios->map(fn($f) => [
        'id' => $f->id,
        'unidad_id' => $f->unidad_id,
        'grado' => $f->grado,
        'nombres' => $f->nombres,
        'apellidos' => $f->apellidos,
        'nombre_completo' => $f->nombre_completo,
        'categoria' => $f->categoria,
        'categoria_nombre' => $f->categoria_nombre,
    ])->values()),
    novedades: @json($initialNovedades->values()),
};
</script>
<script src="{{ asset('js/parte-fuerza.js') }}"></script>
@endpush
