@extends('layouts.app')

@section('title', 'Funcionarios')

@section('content')
<section class="panel">
    <h2>Registrar funcionario</h2>
    <form method="POST" action="{{ route('funcionarios.store') }}" class="grid six">
        @csrf
        <input name="grado" placeholder="Grado" required>
        <input name="nombres" placeholder="Nombres" required>
        <input name="apellidos" placeholder="Apellidos" required>
        <select name="categoria" required>
            @foreach($categorias as $key => $label)
                <option value="{{ $key }}">{{ $label }}</option>
            @endforeach
        </select>
        <select name="unidad_id" required>
            @foreach($unidades as $unidad)
                <option value="{{ $unidad->id }}">{{ $unidad->nombre }}</option>
            @endforeach
        </select>
        <select name="estado"><option>activo</option><option>inactivo</option></select>
        <button class="btn primary">Guardar</button>
    </form>
</section>

<section class="panel">
    <h2>Funcionarios</h2>
    <table class="data-table">
        <thead><tr><th>Grado</th><th>Nombres</th><th>Apellidos</th><th>Categoría</th><th>Unidad</th><th>Estado</th><th>Acción</th></tr></thead>
        <tbody>
            @foreach($funcionarios as $funcionario)
                <tr>
                    <form method="POST" action="{{ route('funcionarios.update', $funcionario) }}">
                        @csrf @method('PUT')
                        <td><input name="grado" value="{{ $funcionario->grado }}" required></td>
                        <td><input name="nombres" value="{{ $funcionario->nombres }}" required></td>
                        <td><input name="apellidos" value="{{ $funcionario->apellidos }}" required></td>
                        <td><select name="categoria">@foreach($categorias as $key => $label)<option value="{{ $key }}" @selected($funcionario->categoria === $key)>{{ $label }}</option>@endforeach</select></td>
                        <td><select name="unidad_id">@foreach($unidades as $unidad)<option value="{{ $unidad->id }}" @selected($funcionario->unidad_id === $unidad->id)>{{ $unidad->nombre }}</option>@endforeach</select></td>
                        <td><select name="estado"><option @selected($funcionario->estado === 'activo')>activo</option><option @selected($funcionario->estado === 'inactivo')>inactivo</option></select></td>
                        <td class="actions-inline">
                            <button class="btn small">Editar</button>
                    </form>
                    <form method="POST" action="{{ route('funcionarios.destroy', $funcionario) }}" onsubmit="return confirm('¿Eliminar funcionario?')">
                        @csrf @method('DELETE')
                        <button class="link-danger">Eliminar</button>
                    </form>
                        </td>
                </tr>
            @endforeach
        </tbody>
    </table>
    {{ $funcionarios->links() }}
</section>
@endsection
