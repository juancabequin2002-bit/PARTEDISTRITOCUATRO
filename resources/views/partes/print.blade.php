<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Imprimir Parte de Fuerza</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}">
</head>
<body class="print-body">
    <div class="print-page">
        <div class="print-header">
            <div class="crest">PN</div>
            <div>
                <h1>POLICÍA NACIONAL DE COLOMBIA</h1>
                <h2>DISTRITO CUATRO DE POLICÍA PURIFICACIÓN</h2>
                <h3>PARTE DE FUERZA</h3>
            </div>
        </div>
        <div class="print-meta">
            <span><strong>Fecha:</strong> {{ $parte->fecha->format('d/m/Y') }}</span>
            <span><strong>Hora:</strong> {{ substr((string) $parte->hora_parte, 0, 5) }}</span>
            <span><strong>Turno:</strong> {{ $parte->turno }}</span>
            <span><strong>Comandante:</strong> {{ $parte->comandante }}</span>
        </div>

        <h4>Fuerza efectiva</h4>
        <table class="data-table">
            <thead><tr><th>Categoría</th><th>Cantidad</th></tr></thead>
            <tbody>
                @foreach($categorias as $key => $label)
                    <tr><td>{{ $label }}</td><td>{{ $resumen['efectiva'][$key] }}</td></tr>
                @endforeach
                <tr><th>Total</th><th>{{ array_sum($resumen['efectiva']) }}</th></tr>
            </tbody>
        </table>

        <h4>Novedades</h4>
        <table class="data-table">
            <thead><tr><th>Tipo</th><th>Funcionario</th><th>Grado</th><th>Categoría</th><th>Inicio</th><th>Fin</th><th>Días</th></tr></thead>
            <tbody>
                @forelse($parte->novedades as $novedad)
                    <tr>
                        <td>{{ $novedad->tipo_novedad }}</td>
                        <td>{{ $novedad->funcionario->nombres }} {{ $novedad->funcionario->apellidos }}</td>
                        <td>{{ $novedad->funcionario->grado }}</td>
                        <td>{{ $novedad->funcionario->categoria_nombre }}</td>
                        <td>{{ $novedad->fecha_inicio->format('d/m/Y') }} {{ substr($novedad->hora_inicio, 0, 5) }}</td>
                        <td>{{ $novedad->fecha_fin->format('d/m/Y') }} {{ substr($novedad->hora_fin, 0, 5) }}</td>
                        <td>{{ number_format($novedad->dias_calculados, 2) }}</td>
                    </tr>
                @empty
                    <tr><td colspan="7">Sin novedades registradas.</td></tr>
                @endforelse
            </tbody>
        </table>

        <h4>Fuerza disponible</h4>
        <table class="data-table">
            <thead><tr><th>Categoría</th><th>Efectiva</th><th>En novedades</th><th>Disponible</th></tr></thead>
            <tbody>
                @foreach($categorias as $key => $label)
                    <tr><td>{{ $label }}</td><td>{{ $resumen['efectiva'][$key] }}</td><td>{{ $resumen['novedades'][$key] }}</td><td>{{ $resumen['disponible'][$key] }}</td></tr>
                @endforeach
                <tr><th>Total</th><th>{{ array_sum($resumen['efectiva']) }}</th><th>{{ array_sum($resumen['novedades']) }}</th><th>{{ array_sum($resumen['disponible']) }}</th></tr>
            </tbody>
        </table>

        <h4>Observaciones</h4>
        <p class="print-observations">{{ $parte->observaciones ?: 'Sin observaciones.' }}</p>
        <div class="signature">Firma del responsable</div>
        <button class="btn primary no-print" onclick="window.print()">Imprimir Parte</button>
    </div>
</body>
</html>
