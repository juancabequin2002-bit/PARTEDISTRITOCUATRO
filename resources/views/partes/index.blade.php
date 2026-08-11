@extends('layouts.app')

@section('title', 'Historial de Partes')

@section('content')
<section class="panel">
    <div class="section-head">
        <h2>Historial de partes</h2>
        <a class="btn primary" href="{{ route('partes.create') }}">Nuevo Parte</a>
    </div>
    <form class="filters" method="GET">
        <input type="date" name="fecha" value="{{ request('fecha') }}">
        <select name="unidad_id">
            <option value="">Todas las unidades</option>
            @foreach($unidades as $unidad)
                <option value="{{ $unidad->id }}" @selected(request('unidad_id') == $unidad->id)>{{ $unidad->nombre }}</option>
            @endforeach
        </select>
        <input name="turno" value="{{ request('turno') }}" placeholder="Turno">
        <input name="comandante" value="{{ request('comandante') }}" placeholder="Comandante">
        <button class="btn outline">Filtrar</button>
    </form>
    <table class="data-table">
        <thead><tr><th>Fecha</th><th>Unidad</th><th>Fuerza efectiva</th><th>Novedades</th><th>Disponible</th><th>Acción</th></tr></thead>
        <tbody>
            @forelse($partes as $parte)
                @php
                    $efectiva = array_sum($parte->efectivaPorCategoria());
                    $novedades = $parte->novedades->count();
                    $disponible = max(0, $efectiva - $novedades);
                @endphp
                <tr>
                    <td>{{ $parte->fecha->format('d/m/Y') }}</td>
                    <td>{{ $parte->unidad->nombre }}</td>
                    <td>{{ $efectiva }}</td>
                    <td>{{ $novedades }}</td>
                    <td>{{ $disponible }}</td>
                    <td class="actions-inline">
                        <a href="{{ route('partes.edit', $parte) }}">Ver / Editar</a>
                        <a href="{{ route('partes.print', $parte) }}">Imprimir</a>
                        <form method="POST" action="{{ route('partes.destroy', $parte) }}" onsubmit="return confirm('¿Eliminar este parte?')">
                            @csrf @method('DELETE')
                            <button class="link-danger">Eliminar</button>
                        </form>
                    </td>
                </tr>
            @empty
                <tr><td colspan="6">No hay partes registrados.</td></tr>
            @endforelse
        </tbody>
    </table>
    {{ $partes->links() }}
</section>
@endsection
