<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>@yield('title', 'Parte de Fuerza')</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}">
</head>
<body>
    <header class="topbar no-print">
        <div class="brand">
            <div class="crest">PN</div>
            <div>
                <strong>POLICÍA NACIONAL</strong>
                <span>DISTRITO CUATRO DE POLICÍA PURIFICACIÓN</span>
            </div>
        </div>
        <div class="title-block">
            <h1>PARTE DE FUERZA</h1>
            <p>FUERZA EFECTIVA, DISPONIBLE Y NOVEDADES</p>
        </div>
        <div class="top-date">
            <label>Fecha del parte</label>
            <input type="date" form="parteForm" name="fecha_top" id="fecha_top">
        </div>
    </header>

    <div class="app-shell">
        <aside class="sidebar no-print">
            <a class="nav-link {{ request()->routeIs('partes.create') || request()->routeIs('partes.edit') ? 'active' : '' }}" href="{{ route('partes.create') }}">▦ Parte de Fuerza</a>
            <a class="nav-link" href="{{ route('partes.create') }}#novedades">△ Novedades</a>
            <a class="nav-link {{ request()->routeIs('funcionarios.*') ? 'active' : '' }}" href="{{ route('funcionarios.index') }}">◉ Funcionarios</a>
            <a class="nav-link {{ request()->routeIs('partes.index') ? 'active' : '' }}" href="{{ route('partes.index') }}">▤ Historial de Partes</a>
            <a class="nav-link" href="{{ route('partes.index') }}">▥ Reportes</a>
            <span class="nav-link muted">◌ Usuarios</span>
            <span class="nav-link muted">⚙ Configuración</span>
            <form method="POST" action="{{ route('logout') }}" class="logout-form">
                @csrf
                <button class="nav-link logout" type="submit">⏻ Cerrar Sesión</button>
            </form>
        </aside>
        <main class="content">
            @if (session('status'))
                <div class="alert success">{{ session('status') }}</div>
            @endif
            @if ($errors->any())
                <div class="alert danger">
                    @foreach ($errors->all() as $error)
                        <div>{{ $error }}</div>
                    @endforeach
                </div>
            @endif
            @yield('content')
        </main>
    </div>
    @stack('scripts')
</body>
</html>
